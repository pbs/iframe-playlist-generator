"""
Takes a variant m3u8 playlist, creates I-frame playlists for it, and
creates an updated master playlist with links to the new I-frame playlists.
"""

import csv
from cStringIO import StringIO
from math import ceil
from subprocess32 import check_output, Popen, CalledProcessError, PIPE

import m3u8

from .exceptions import (
    PlaylistLoadError, BadPlaylistError,
    DependencyError, DataError
)


__all__ = ['update_for_iframes', 'extract_iframe_metadata']


def update_for_iframes(url):
    """
    Returns an updated master playlist and new I-frame playlists
    """
    try:
        master_playlist = m3u8.load(url)
    except IOError:
        raise PlaylistLoadError('Invalid url')

    if not master_playlist or not master_playlist.is_variant:
        raise BadPlaylistError('Not a variant playlist')

    master_playlist.iframe_playlists[:] = []

    uri = url.split('/')[-1]
    result = {'master_uri': uri,
              'master_content': None,
              'iframe_playlists': []}

    for playlist in master_playlist.playlists:
        iframe_playlist, data = create_iframe_playlist(playlist)
        if iframe_playlist is None or data is None:
            continue
        master_playlist.add_iframe_playlist(iframe_playlist)
        result['iframe_playlists'].append(data)

    result['master_content'] = master_playlist.dumps()
    return result


def create_iframe_playlist(playlist):
    """
    Creates a new I-frame playlist.
    """
    try:
        check_output(['ffprobe', '-version'])
    except (OSError, CalledProcessError):
        raise DependencyError('FFmpeg not installed correctly')

    iframe_playlist = generate_m3u8_for_iframes()

    total_bytes = 0
    total_duration = 0

    try:
        stream = m3u8.load(playlist.absolute_uri)
    except IOError:
        raise PlaylistLoadError('Invalid stream url')
    except AttributeError:
        raise BadPlaylistError('Invalid playlist - no absolute uri')

    for segment in stream.segments:

        iframe_segments, s_bytes, s_duration = create_iframe_segments(segment)

        for iframe_segment in iframe_segments:
            iframe_playlist.add_segment(iframe_segment)

        total_bytes += s_bytes
        total_duration += s_duration

    if total_bytes != 0 and total_duration != 0:
        iframe_bandwidth = int(ceil(total_bytes / total_duration * 8))
    else:
        return (None, None)

    iframe_codecs = convert_codecs_for_iframes(playlist.stream_info.codecs)
    stream_info = {'bandwidth': str(iframe_bandwidth),
                   'codecs': iframe_codecs}
    iframe_playlist_uri = playlist.uri.replace('.m3u8', '-iframes.m3u8')

    new_iframe_playlist = m3u8.IFramePlaylist(base_uri=playlist.base_uri,
                                              uri=iframe_playlist_uri,
                                              iframe_stream_info=stream_info)

    return (new_iframe_playlist, {'uri': iframe_playlist_uri,
                                  'content': iframe_playlist.dumps()})


def generate_m3u8_for_iframes():
    """
    Generates an M3U8 object to be used for an I-frame playlist
    """
    result = m3u8.M3U8()
    result.media_sequence = 0
    result.version = '4'
    result.target_duration = 10
    result.playlist_type = 'vod'
    result.is_i_frames_only = True
    result.is_endlist = True
    return result


def create_iframe_segments(segment):
    """
    Takes a transport stream segment and returns I-frame segments for it
    """
    iframes_total_size = 0
    video_duration = 0
    iframe_segments = list()

    iframes_and_format = csv.reader(StringIO(
        extract_iframe_metadata(segment.absolute_uri)))

    # Keep the details of the last processed I-frame packet which need to be
    # used in computing parameters like size and time span.
    # When no longer needed (they have been used in computing the desired
    # parameters), these attributes need to be nullified.
    prev_iframe = {'displayed_at': None,
                   'position': None,
                   'size': None}
    for row in iframes_and_format:
        decider = row[0]
        if decider == 'frame':
            prev_iframe, iframes_total_size = _process_video_frame(
                row, prev_iframe, segment.uri, segment.base_uri,
                iframe_segments, iframes_total_size
            )
        elif decider == 'format':
            iframes_total_size, video_duration = _process_video_details(
                row, prev_iframe, iframe_segments, iframes_total_size)
        else:
            raise ValueError('Received an invalid row type: got "{}", '
                             'expected "format" or "frame".'.format(decider))

    return iframe_segments, iframes_total_size, video_duration


def _process_video_frame(row, prev_iframe, segment_uri, segment_base_uri,
                         iframe_segments, iframes_total_size):
    """
    Extract the position, size and type of the frame.
    Based on the type of the frame:
    - modify the previous I-frame in the list with the given data, if necessary
    - add a new I-frame to the list and refresh the data in the `prev_iframe`

    :param row: - the frame information retrieved from ffprobe using the
    `-show_frame` flag with the following filter for entries
    `best_effort_timestamp_time,pkt_pos,pkt_size,pict_type`
    :param prev_iframe: - the information required from the previously
    processed Intra-frame (key-frame)
    :param segment_uri: - the URI of the segment from which the frames have
    been extracted. Used in creating the new I-frame segment.
    :param segment_base_uri: - the base URI of the segment from which the
    frames have been extracted. Used in creating the new I-frame segment.
    :param iframe_segments: - the list of I-frame segments created so far.
    Depending on the situation, the last element of the list will be modified,
    and/or a new element will be added.
    :param iframes_total_size: - the current total size of the *complete*
    I-frames found in the `iframe_segments` list.

    :returns: - the previous I-frame with updated fields. Some fields may be
    removed in order to signal that they should not be used in the future.
              - the new `iframes_total_size` - updated in case the size of
    the last I-frame could be set.
    """
    frame_displayed_at = float(row[1])
    frame_position = int(row[2])
    frame_size = int(row[3])
    frame_type = row[4]

    if prev_iframe['position']:
        # Compute the size of the previous I-frame packet relative to
        # the current packet.
        prev_iframe_size = frame_position - prev_iframe['position']
        # Compute the packet size using the positions of consecutive
        # frames because the one provided by ffprobe is not accurate.
        iframe_segments[-1].byterange = '{}@{}'.format(prev_iframe_size,
                                                       prev_iframe['position'])
        iframes_total_size += prev_iframe_size
        prev_iframe['position'] = None

    if frame_type == 'I':
        if prev_iframe['displayed_at']:
            # Compute the time span of the previous I-frame relative to
            # the current I-frame packet.
            iframe_segments[-1].duration = (frame_displayed_at -
                                            prev_iframe['displayed_at'])
            prev_iframe['displayed_at'] = None
        iframe_segment = m3u8.Segment(segment_uri, segment_base_uri)
        iframe_segments.append(iframe_segment)
        prev_iframe = {'displayed_at': frame_displayed_at,
                       'position': frame_position,
                       'size': frame_size}

    return prev_iframe, iframes_total_size


def _process_video_details(row, prev_iframe, iframe_segments,
                           iframes_total_size):
    """
    Extract the total duration of the video segment.
    Modify the span of the last I-frame, and its byterange, if the I-frame was
    the last frame in the video.

    :param row: - the video information retrieved from ffprobe using the
    `-show_format` flag with the following entry filter `duration,start_time`
    :param prev_iframe: - the information required from the previously
    processed Intra-frame (key-frame)
    :param iframe_segments: - the list of I-frame segments created so far.
    The duration of the last I-frame will be update, and, if the last I-frame
    was not followed by another frame, its `byterange` will be updated to
    its packet size.
    :param iframes_total_size: - the current total size of the *complete*
    I-frames found in the `iframe_segments` list.

    :returns: - the new `iframes_total_size` - updated in case the size of
    the last I-frame could be set
              - the video duration
    """
    video_started_at = float(row[1])
    video_duration = float(row[2])
    if prev_iframe['displayed_at']:
        # The last I-frame will span until the end of the segment.
        iframe_segments[-1].duration = (
            video_started_at + video_duration -
            prev_iframe['displayed_at']
        )
    if prev_iframe['position']:
        # In case the last packet is an I-frame (probably an edge-case)
        # use the packet size provided by ffprobe.
        iframe_segments[-1].byterange = '{}@{}'.format(
            prev_iframe['size'], prev_iframe['position']
        )
        iframes_total_size += prev_iframe['size']
    return iframes_total_size, video_duration


def extract_iframe_metadata(filename):
    """
    Runs ffprobe on the give file (be it local or remote) and returns a CSV
    with the key frames (I-frames) identified in the video. The last line in
    the CSV contains details about the video file as a whole.

    CSV format:
    frame,<best_effort_timestamp_time>,<pkt_pos>,<pkt_size>,<pict_type>
    ...
    format,<start_time>,<duration>
    """
    ffprobe = Popen(
        ['ffprobe',
         '-print_format', 'csv',
         '-select_streams', 'v',
         '-show_frames',
         '-show_entries',
         'frame=best_effort_timestamp_time,pkt_pos,pkt_size,pict_type',
         '-show_format',
         '-show_entries', 'format=duration,start_time',
         filename],
        stdout=PIPE,
        stderr=PIPE
    )
    grep_iframes_format = Popen(
        ['grep', '-A', '1', '--no-group-separator', r'\(I$\|^format\)'],
        stdin=ffprobe.stdout,
        stdout=PIPE,
        stderr=PIPE
    )
    exclude_unavailable_info = Popen(['grep', '-v', r'N/A'],
                                     stdin=grep_iframes_format.stdout,
                                     stdout=PIPE,
                                     stderr=PIPE)
    ffprobe.stdout.close()
    grep_iframes_format.stdout.close()
    iframes_and_format, _ = exclude_unavailable_info.communicate()
    ffprobe_status = ffprobe.wait()
    grep_iframes_format.wait()

    if ffprobe_status == 1:
        raise DataError(
            'Could not read TS data for "{}". Details: {}'.format(
                filename,
                # ffprobe outputs extra information to stderr before the actual
                # error message, which is on the line before last.
                ffprobe.stderr.read().rstrip().rsplit('\n', 1)[-1]
            )
        )
    return iframes_and_format


def convert_codecs_for_iframes(codecs):
    """
    Takes a codecs string, converts it for iframes, and returns it
    """
    if codecs is not None:
        codecs_list = codecs.split(',')
        return ', '.join([k.strip() for k in codecs_list if 'avc1' in k])
    else:
        return None
