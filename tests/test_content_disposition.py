"""Test that DownloadTask correctly resolves filename from Content-Disposition and Content-Type."""
import sys
import unittest.mock as mock
from unittest.mock import MagicMock
import httpx

sys.path.append('C:/Users/MrKayes/.gemini/antigravity/scratch/personal-download-manager')

from pdm.core.engine import DownloadTask, DownloadStatus
from pdm.storage.db import DatabaseManager


def test_probe_server_content_disposition(tmp_path):
    db_path = tmp_path / "test.db"
    db = DatabaseManager(str(db_path))

    dest = str(tmp_path / "download.bin")
    url = "https://example.com/get_file?id=992"
    task_id = db.create_download(
        url=url,
        destination_path=dest,
        filename="download.bin",
        category="Other"
    )

    task = DownloadTask(task_id=task_id, url=url, destination_path=dest, filename="download.bin", db=db)

    # Mock httpx response with Content-Disposition
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.headers = {
        "Content-Length": "1048576",
        "Content-Type": "video/x-matroska",
        "Content-Disposition": 'attachment; filename="Awesome_Movie_2024.mkv"',
        "Accept-Ranges": "bytes"
    }
    fake_resp.url = "https://example.com/get_file?id=992"

    with mock.patch("httpx.Client") as MockClient:
        mock_instance = MagicMock()
        mock_instance.head.return_value = fake_resp
        MockClient.return_value.__enter__.return_value = mock_instance

        task._probe_server()

    assert task.filename == "Awesome_Movie_2024.mkv"
    assert task.filename.endswith(".mkv")

    # Verify database was updated
    record = db.get_download(task_id)
    assert record["filename"] == "Awesome_Movie_2024.mkv"
    assert record["category"] == "Video"


def test_probe_server_content_type_extension_fix(tmp_path):
    db_path = tmp_path / "test2.db"
    db = DatabaseManager(str(db_path))

    dest = str(tmp_path / "watch.php")
    url = "https://example.com/watch.php?v=123"
    task_id = db.create_download(
        url=url,
        destination_path=dest,
        filename="watch.php",
        category="Other"
    )

    task = DownloadTask(task_id=task_id, url=url, destination_path=dest, filename="watch.php", db=db)

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.headers = {
        "Content-Length": "2048",
        "Content-Type": "video/mp4",
        "Accept-Ranges": "bytes"
    }
    fake_resp.url = "https://example.com/watch.php?v=123"

    with mock.patch("httpx.Client") as MockClient:
        mock_instance = MagicMock()
        mock_instance.head.return_value = fake_resp
        MockClient.return_value.__enter__.return_value = mock_instance

        task._probe_server()

    assert task.filename == "watch.mp4"
    record = db.get_download(task_id)
    assert record["filename"] == "watch.mp4"
    assert record["category"] == "Video"
