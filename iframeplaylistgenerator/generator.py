"""
Takes a variant m3u8 playlist, creates I-frame playlists for it, and
creates an updated master playlist with links to the new I-frame playlists.
"""

import csv
from cStringIO import StringIO
import subprocess

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
        subprocess.check_output('ffprobe -version', stderr=subprocess.STDOUT,
                                shell=True)
    except subprocess.CalledProcessError:
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
        iframe_bandwidth = str(int(total_bytes / total_duration * 8))
    else:
        return (None, None)

    iframe_codecs = convert_codecs_for_iframes(playlist.stream_info.codecs)
    stream_info = {'bandwidth': iframe_bandwidth,
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

    prev_iframe_displayed_at = None
    for row in iframes_and_format:
        decider = row[0]
        if decider == 'frame':
            iframe_displayed_at = float(row[1])
            iframe_position = int(row[2])
            iframe_size = int(row[3])
            if prev_iframe_displayed_at is not None:
                iframe_segments[-1].duration = (iframe_displayed_at -
                                                prev_iframe_displayed_at)
            iframe_segment = m3u8.Segment(
                segment.uri,
                segment.base_uri,
                byterange='{}@{}'.format(iframe_size, iframe_position)
            )
            iframe_segments.append(iframe_segment)
            iframes_total_size += iframe_size
            prev_iframe_displayed_at = iframe_displayed_at
        elif decider == 'format':
            video_started_at = float(row[1])
            video_duration = float(row[2])
            if prev_iframe_displayed_at is not None:
                iframe_segments[-1].duration = (
                    video_started_at + video_duration -
                    prev_iframe_displayed_at
                )
        else:
            raise ValueError('Received an invalid row type: got "{}", '
                             'expected "format" or "frame".'.format(decider))

    return iframe_segments, iframes_total_size, video_duration


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
    bash_cmd = (
        'ffprobe'
        ' -print_format csv'
        ' -select_streams v'  # query only the video stream (exclude audio)
        ' -show_frames'
        ' -show_format'  # used to determine the duration of the I-frames
        ' -show_entries frame=best_effort_timestamp_time,pkt_pos,pkt_size,pict_type'  # noqa
        ' -show_entries format=duration,start_time '
        '{file_uri} '
        # throw away the header that ffmpeg utils print by default
        '2> /dev/null '
        # select only the I-frames and the format data
        '| grep "\(I$\|^format\)" '
        # exclude data that does not provide complete information. E.g: AAC
        # files have an I-frame in the video stream that we should ignore.
        '| grep -v "N/A"'
    )
    process = subprocess.Popen(bash_cmd.format(file_uri=filename),
                               shell=True, stdout=subprocess.PIPE)
    out = process.stdout.read().strip()
    return out


def convert_codecs_for_iframes(codecs):
    """
    Takes a codecs string, converts it for iframes, and returns it
    """
    if codecs is not None:
        codecs_list = codecs.split(',')
        return ', '.join([k.strip() for k in codecs_list if 'avc1' in k])
    else:
        return None
