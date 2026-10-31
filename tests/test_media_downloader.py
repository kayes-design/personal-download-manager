"""Unit tests for media_downloader module."""

import os
from pdm.core.media_downloader import (
    is_media_stream_url,
    normalize_media_url,
    get_ffmpeg_path,
    is_playlist_url,
    extract_playlist_entries,
)


def test_is_media_stream_url():
    assert is_media_stream_url("https://v.redd.it/abc123xyz/DASH_720.mp4") is True
    assert is_media_stream_url("https://www.reddit.com/r/funny/comments/123/funny_clip/") is True
    assert is_media_stream_url("https://example.com/playlist.m3u8") is True
    assert is_media_stream_url("https://example.com/stream.mpd") is True
    assert is_media_stream_url("https://video.xx.fbcdn.net/v/t39.1234/movie.mp4") is True
    assert is_media_stream_url("https://rr1---sn-abc.googlevideo.com/videoplayback?id=123") is True
    assert is_media_stream_url("https://example.com/file.zip") is False
    assert is_media_stream_url("https://example.com/installer.exe") is False
    assert is_media_stream_url("") is False


def test_normalize_media_url():
    assert normalize_media_url("https://v.redd.it/xyz123/DASH_720.mp4?source=fallback") == "https://v.redd.it/xyz123"
    assert normalize_media_url("https://v.redd.it/xyz123/HLSPlaylist.m3u8") == "https://v.redd.it/xyz123"
    assert normalize_media_url("https://v.redd.it/xyz123/audio") == "https://v.redd.it/xyz123"
    assert normalize_media_url("https://www.reddit.com/r/videos/comments/test/") == "https://www.reddit.com/r/videos/comments/test/"
    assert normalize_media_url("https://example.com/file.mp4") == "https://example.com/file.mp4"


def test_get_ffmpeg_path():
    path = get_ffmpeg_path()
    assert path is not None
    assert os.path.exists(path)


def test_is_playlist_url():
    assert is_playlist_url("https://www.youtube.com/playlist?list=PL123456789") is True
    assert is_playlist_url("https://www.youtube.com/watch?v=abc&list=PL123456789") is True
    assert is_playlist_url("https://soundcloud.com/artist/sets/cool-album") is True
    assert is_playlist_url("https://example.com/single_video.mp4") is False
    assert is_playlist_url("") is False


def test_extract_playlist_entries_structure(monkeypatch):
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, url, download=False):
            return {
                "entries": [
                    {"id": "v1", "title": "Video 1", "url": "https://example.com/v1", "duration": 120},
                    {"id": "v2", "title": "Video 2", "url": "https://example.com/v2", "duration": 240},
                ]
            }

    import yt_dlp
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)

    entries = extract_playlist_entries("https://example.com/playlist?list=123", cookies="sess=xyz")
    assert len(entries) == 2
    assert entries[0]["title"] == "Video 1"
    assert entries[1]["duration"] == 240

