"""Unit tests for media_downloader module."""

import os
from pathlib import Path
import pytest
import pdm.core.media_downloader as media_downloader_module
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


def test_direct_file_urls_skip_extractor_initialization(monkeypatch):
    def unexpected_extractor_load():
        pytest.fail("direct file URL should not initialize yt-dlp extractors")

    monkeypatch.setattr(media_downloader_module, "_get_extractors", unexpected_extractor_load)

    assert is_media_stream_url("https://example.com/archive.zip?download=1") is False
    assert is_media_stream_url("https://example.com/video.mp4") is False


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
    captured_options = []

    class FakeYDL:
        def __init__(self, opts):
            captured_options.append(opts)
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
    assert all(options.get("nocheckcertificate") is not True for options in captured_options)


def test_media_downloader_keeps_tls_certificate_validation_enabled(monkeypatch, tmp_path):
    captured_options = []
    output_path = str(tmp_path / "resolved.mp4")

    class FakeYDL:
        def __init__(self, options):
            captured_options.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            with open(output_path, "wb") as output:
                output.write(b"video")
            return {"title": "resolved", "ext": "mp4"}

        def prepare_filename(self, info):
            return output_path

    import yt_dlp
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)

    result = media_downloader_module.MediaStreamDownloader().download(
        "https://example.com/watch?v=1",
        str(tmp_path / "watch.mp4"),
    )

    assert result == output_path
    assert captured_options
    assert all(options.get("nocheckcertificate") is not True for options in captured_options)


def test_authenticated_media_uses_referrer_page_and_scoped_cookie_jar(monkeypatch, tmp_path):
    captured = {}
    output_path = str(tmp_path / "resolved.mp4")
    cookie_jar = (
        "# Netscape HTTP Cookie File\n"
        "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tsecret-session\n"
        ".googlevideo.com\tTRUE\t/\tTRUE\t2147483647\tVISITOR_INFO1_LIVE\tcdn-cookie\n"
    )

    class FakeYDL:
        def __init__(self, options):
            captured["options"] = options
            cookie_file = options.get("cookiefile")
            captured["cookie_contents"] = Path(cookie_file).read_text() if cookie_file else ""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            captured["url"] = url
            with open(output_path, "wb") as output:
                output.write(b"video")
            return {"title": "resolved", "ext": "mp4"}

        def prepare_filename(self, info):
            return output_path

    import yt_dlp
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)

    result = media_downloader_module.MediaStreamDownloader().download(
        "https://rr1.googlevideo.com/videoplayback?id=1",
        str(tmp_path / "watch.mp4"),
        referer="https://www.youtube.com/watch?v=abc",
        cookie_jar=cookie_jar,
    )

    assert result == output_path
    assert captured["url"] == "https://www.youtube.com/watch?v=abc"
    assert "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tsecret-session" in captured["cookie_contents"]
    assert ".googlevideo.com\tTRUE\t/\tTRUE\t2147483647\tVISITOR_INFO1_LIVE\tcdn-cookie" in captured["cookie_contents"]
    assert not os.path.exists(captured["options"]["cookiefile"])
