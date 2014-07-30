import os
import unittest
import json

import m3u8

from iframeplaylistgenerator.generator import (
    update_for_iframes, create_iframe_playlist,
    run_ffprobe, convert_codecs_for_iframes,
    get_segment_data
)
from iframeplaylistgenerator.exceptions import (
    PlaylistLoadError, BadPlaylistError, DataError
)


def read_file(file_loc):
    with open(file_loc) as myfile:
        return myfile.read()

SAMPLES_PATH = (os.path.dirname(__file__) + '/samples/').lstrip('/')
MASTER_PLAYLIST = read_file(
    SAMPLES_PATH + 'generated_playlists/bigbuckbunny.m3u8'
)
IFRAME_PLAYLIST_400K = read_file(
    SAMPLES_PATH + 'generated_playlists/bigbuckbunny-400k-iframes.m3u8'
)
IFRAME_PLAYLIST_150K = read_file(
    SAMPLES_PATH + 'generated_playlists/bigbuckbunny-150k-iframes.m3u8'
)


class IframePlaylistGeneratorTestCase(unittest.TestCase):

    def test_loading_bad_url_returns_error(self):
        with self.assertRaisesRegexp(PlaylistLoadError, 'Invalid url'):
            update_for_iframes('not a url')

    def test_loading_non_variant_playlist_returns_error(self):
        with self.assertRaisesRegexp(BadPlaylistError,
                                     'Not a variant playlist'):
            update_for_iframes(
                SAMPLES_PATH + 'original_video/bigbuckbunny-400k.m3u8'
            )

    def test_loading_playlist_with_bad_link_returns_error(self):
        with self.assertRaisesRegexp(PlaylistLoadError, 'Invalid stream url'):
            update_for_iframes(
                SAMPLES_PATH + 'original_video/bigbuckbunny-with-bad-link.m3u8'
            )

    def test_using_bad_playlist_returns_error(self):
        with self.assertRaisesRegexp(BadPlaylistError,
                                     'Invalid playlist - no absolute uri'):
            create_iframe_playlist(
                'not a playlist'
            )

    def test_get_segment_data_from_empty_ts_file_returns_error(self):
        with self.assertRaisesRegexp(DataError,
                                     'Could not read TS data'):
            get_segment_data(
                SAMPLES_PATH + 'original_video/bigbuckbunny-with-no-data.ts'
            )

    def test_convert_codecs_for_iframes(self):
        results = convert_codecs_for_iframes('avc1.4d001f, mp4a.40.5')
        self.assertEqual('avc1.4d001f', results)

    def test_convert_nonetype_codecs_returns_none(self):
        results = convert_codecs_for_iframes(None)
        self.assertEqual(None, results)

    def test_run_ffprobe(self):
        results = json.loads(
            run_ffprobe(
                SAMPLES_PATH + 'original_video/bigbuckbunny-150k-00001.ts'
            )
        )
        json_data = json.loads(
            read_file(
                SAMPLES_PATH + 'json_files/bigbuckbunny-150k-00001.json'
            )
        )
        self.assertEqual(
            len(json_data['packets_and_frames']),
            len(results['packets_and_frames'])
        )

    def test_create_iframe_playlist(self):
        iframe_playlist_uri = 'bigbuckbunny-400k-iframes.m3u8'
        iframe_playlist_content = IFRAME_PLAYLIST_400K
        master_playlist = m3u8.load(
            SAMPLES_PATH + 'original_video/bigbuckbunny.m3u8'
        )
        _, results = create_iframe_playlist(master_playlist.playlists[0])
        self.assertEqual(iframe_playlist_uri, results['uri'])
        self.assertEqual(iframe_playlist_content, results['content'])

    def test_update_for_iframes(self):
        results = update_for_iframes(
            SAMPLES_PATH + 'original_video/bigbuckbunny.m3u8'
        )
        self.assertEqual('bigbuckbunny.m3u8', results['master_uri'])
        self.assertEqual(MASTER_PLAYLIST, results['master_content'])
        self.assertEqual([{'uri': 'bigbuckbunny-400k-iframes.m3u8',
                           'content': IFRAME_PLAYLIST_400K},
                          {'uri': 'bigbuckbunny-150k-iframes.m3u8',
                           'content': IFRAME_PLAYLIST_150K}],
                         results['iframe_playlists'])

if __name__ == '__main__':
    unittest.main()
