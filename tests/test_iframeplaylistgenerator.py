import os
import unittest

import m3u8

from iframeplaylistgenerator.generator import (
    update_for_iframes, create_iframe_playlist,
    extract_iframe_metadata, convert_codecs_for_iframes,
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
).strip()
IFRAME_PLAYLIST_150K = read_file(
    SAMPLES_PATH + 'generated_playlists/bigbuckbunny-150k-iframes.m3u8'
).strip()


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

    def test_convert_codecs_for_iframes(self):
        results = convert_codecs_for_iframes('avc1.4d001f, mp4a.40.5')
        self.assertEqual('avc1.4d001f', results)

    def test_convert_nonetype_codecs_returns_none(self):
        results = convert_codecs_for_iframes(None)
        self.assertEqual(None, results)

    def test_extract_iframe_metadata(self):
        results = extract_iframe_metadata(
            SAMPLES_PATH + 'original_video/bigbuckbunny-150k-00001.ts'
        )
        self.assertEqual(
            'frame,10.000000,3008,175,I\n'
            'frame,10.066667,3196,385,P\n'
            'frame,19.266667,188376,18539,I\n'
            'frame,19.333333,210184,148,P\n'
            'format,9.881000,10.119000\n',
            results
        )

    def test_extract_iframe_metadata_for_empty_file_returns_error(self):
        with self.assertRaises(DataError):
            extract_iframe_metadata(
                SAMPLES_PATH + 'original_video/bigbuckbunny-with-no-data.ts'
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
