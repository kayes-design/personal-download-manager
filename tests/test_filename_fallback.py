"""Test that adding a download does not perform metadata network requests on the caller thread."""
import sys
from types import SimpleNamespace

from pdm.storage.db import DatabaseManager
from pdm.core.coordinator import DownloadCoordinator


def test_add_download_without_filename_does_not_fetch_metadata_synchronously(monkeypatch, tmp_path):
    calls = []

    class ForbiddenYoutubeDL:
        def __init__(self, options):
            calls.append(options)
            raise AssertionError("Metadata extraction must not block add_download.")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=ForbiddenYoutubeDL))

    db_path = tmp_path / 'test.db'
    db = DatabaseManager(str(db_path))
    coord = DownloadCoordinator(db)
    task_id = coord.add_download(
        "https://example.com/video",
        destination_dir=str(tmp_path),
        filename=None,
        auto_start=False,
    )
    record = db.get_download(task_id)
    assert record["filename"] == "video"
    assert calls == []
    coord.shutdown()
