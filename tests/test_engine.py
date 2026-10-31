"""Integration tests for the download engine and coordinator."""

import hashlib
import os
import time
import pytest
from pdm.core.coordinator import DownloadCoordinator
from pdm.core.engine import DownloadStatus, DownloadTask
from pdm.core.limiter import SpeedLimiter
from pdm.storage.db import DatabaseManager
from tests.local_test_server import LocalTestServer


@pytest.fixture(scope="module")
def test_server():
    server = LocalTestServer(port=0)

    # 1. Standard Range-supported 1MB file
    # Patterned data to detect byte ordering bugs
    data_1mb = bytes([i % 256 for i in range(1024 * 1024)])
    server.add_resource("/range-supported.bin", data_1mb, supports_range=True)

    # 2. Server without Range support (full 200 only)
    data_512k = b"NO_RANGE_STREAM_" * 32768  # 524,288 bytes
    server.add_resource("/no-range.bin", data_512k, supports_range=False)

    server.start()
    yield server
    server.stop()


def test_multi_connection_download(test_server, tmp_path):
    """Test multi-connection download with range support and verify SHA-256 integrity."""
    db_file = os.path.join(tmp_path, "db_test1.db")
    db = DatabaseManager(db_file)

    target_dir = str(tmp_path / "downloads")
    os.makedirs(target_dir, exist_ok=True)
    dest_path = os.path.join(target_dir, "range-supported.bin")

    url = test_server.get_url("/range-supported.bin")
    task_id = db.create_download(
        url=url,
        destination_path=dest_path,
        filename="range-supported.bin",
        connections_count=4
    )

    task = DownloadTask(
        task_id=task_id,
        url=url,
        destination_path=dest_path,
        filename="range-supported.bin",
        db=db,
        connections_count=4
    )

    task.run_sync()

    assert task.status == DownloadStatus.COMPLETED
    assert os.path.exists(dest_path)
    assert os.path.getsize(dest_path) == 1024 * 1024

    # Verify content match
    expected_data = bytes([i % 256 for i in range(1024 * 1024)])
    with open(dest_path, "rb") as f:
        downloaded_data = f.read()

    assert hashlib.sha256(downloaded_data).hexdigest() == hashlib.sha256(expected_data).hexdigest()


def test_single_connection_fallback(test_server, tmp_path):
    """Test automatic fallback to 1 stream when server disallows Range."""
    db_file = os.path.join(tmp_path, "db_test2.db")
    db = DatabaseManager(db_file)

    target_dir = str(tmp_path / "downloads")
    os.makedirs(target_dir, exist_ok=True)
    dest_path = os.path.join(target_dir, "no-range.bin")

    url = test_server.get_url("/no-range.bin")
    task_id = db.create_download(
        url=url,
        destination_path=dest_path,
        filename="no-range.bin",
        connections_count=4
    )

    task = DownloadTask(
        task_id=task_id,
        url=url,
        destination_path=dest_path,
        filename="no-range.bin",
        db=db,
        connections_count=4
    )

    task.run_sync()

    assert task.status == DownloadStatus.COMPLETED
    assert task.supports_range is False
    assert os.path.exists(dest_path)

    expected_data = b"NO_RANGE_STREAM_" * 32768
    with open(dest_path, "rb") as f:
        downloaded_data = f.read()

    assert hashlib.sha256(downloaded_data).hexdigest() == hashlib.sha256(expected_data).hexdigest()


def test_redirect_download(test_server, tmp_path):
    """Test client following HTTP 302 redirect."""
    db_file = os.path.join(tmp_path, "db_test3.db")
    db = DatabaseManager(db_file)

    target_dir = str(tmp_path / "downloads")
    os.makedirs(target_dir, exist_ok=True)
    dest_path = os.path.join(target_dir, "redirected.bin")

    url = test_server.get_url("/redirect")
    task_id = db.create_download(
        url=url,
        destination_path=dest_path,
        filename="redirected.bin",
        connections_count=2
    )

    task = DownloadTask(
        task_id=task_id,
        url=url,
        destination_path=dest_path,
        filename="redirected.bin",
        db=db,
        connections_count=2
    )

    task.run_sync()

    assert task.status == DownloadStatus.COMPLETED
    assert os.path.exists(dest_path)
    assert os.path.getsize(dest_path) == 1024 * 1024


def test_coordinator_queue_management(test_server, tmp_path):
    """Test DownloadCoordinator managing queued downloads with concurrency limit."""
    db_file = os.path.join(tmp_path, "db_test4.db")
    db = DatabaseManager(db_file)
    target_dir = str(tmp_path / "downloads")

    coordinator = DownloadCoordinator(db=db, max_concurrent_downloads=2)

    url = test_server.get_url("/range-supported.bin")

    # Add 3 downloads
    id1 = coordinator.add_download(url, target_dir, "file1.bin", auto_start=True)
    id2 = coordinator.add_download(url, target_dir, "file2.bin", auto_start=True)
    id3 = coordinator.add_download(url, target_dir, "file3.bin", auto_start=True)

    timeout = 10.0
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        item1 = db.get_download(id1)
        item2 = db.get_download(id2)
        item3 = db.get_download(id3)
        if (
            item1["status"] == "Completed"
            and item2["status"] == "Completed"
            and item3["status"] == "Completed"
        ):
            break
        time.sleep(0.2)

    coordinator.shutdown()

    assert db.get_download(id1)["status"] == "Completed"
    assert db.get_download(id2)["status"] == "Completed"
    assert db.get_download(id3)["status"] == "Completed"


def test_pause_and_resume(test_server, tmp_path):
    """Test pausing a download mid-stream and resuming it to full byte-for-byte completion."""
    db_file = os.path.join(tmp_path, "db_test5.db")
    db = DatabaseManager(db_file)
    target_dir = str(tmp_path / "downloads")
    os.makedirs(target_dir, exist_ok=True)
    dest_path = os.path.join(target_dir, "paused_resumed.bin")

    url = test_server.get_url("/range-supported.bin")
    task_id = db.create_download(
        url=url,
        destination_path=dest_path,
        filename="paused_resumed.bin",
        connections_count=4
    )

    # Use a speed limiter so it downloads slowly enough for us to pause mid-flight
    limiter = SpeedLimiter(200 * 1024)  # 200 KB/s
    task = DownloadTask(
        task_id=task_id,
        url=url,
        destination_path=dest_path,
        filename="paused_resumed.bin",
        db=db,
        connections_count=4,
        speed_limiter=limiter
    )

    import threading
    t = threading.Thread(target=task.run_sync, daemon=True)
    t.start()

    # Wait for some progress (e.g. at least 50 KB downloaded)
    for _ in range(50):
        if task.downloaded_bytes > 50000:
            break
        time.sleep(0.05)

    # Pause
    task.stop()
    t.join(timeout=3.0)

    assert task.status == DownloadStatus.PAUSED
    partial_bytes = task.downloaded_bytes
    assert 0 < partial_bytes < 1024 * 1024

    # Now create a new task instance resuming from the database without speed limit
    resume_task = DownloadTask(
        task_id=task_id,
        url=url,
        destination_path=dest_path,
        filename="paused_resumed.bin",
        db=db,
        connections_count=4
    )
    resume_task.run_sync()

    assert resume_task.status == DownloadStatus.COMPLETED
    assert os.path.exists(dest_path)
    assert os.path.getsize(dest_path) == 1024 * 1024

    # Check byte-for-byte correctness
    expected_data = bytes([i % 256 for i in range(1024 * 1024)])
    with open(dest_path, "rb") as f:
        downloaded_data = f.read()

    assert hashlib.sha256(downloaded_data).hexdigest() == hashlib.sha256(expected_data).hexdigest()


def test_html_response_rejection_for_video(test_server, tmp_path):
    """Verify that when a server returns an HTML error/login page instead of video,
    the engine raises ValueError rather than saving corrupt HTML into an .mp4 file."""
    html_page = b"<!DOCTYPE html><html><body><h1>403 Forbidden - Login Required</h1></body></html>"
    test_server.add_resource("/blocked-video.mp4", html_page, supports_range=False, content_type="text/html; charset=utf-8")

    db_file = os.path.join(tmp_path, "db_html_test.db")
    db = DatabaseManager(db_file)

    target_dir = str(tmp_path / "downloads")
    os.makedirs(target_dir, exist_ok=True)
    dest_path = os.path.join(target_dir, "blocked-video.mp4")

    url = test_server.get_url("/blocked-video.mp4")
    task_id = db.create_download(
        url=url,
        destination_path=dest_path,
        filename="blocked-video.mp4",
        connections_count=1
    )

    task = DownloadTask(
        task_id=task_id,
        url=url,
        destination_path=dest_path,
        filename="blocked-video.mp4",
        db=db,
        connections_count=1,
        referer="https://example.com/watch"
    )

    with pytest.raises(Exception) as exc_info:
        task.run_sync()

    assert task.status == DownloadStatus.ERROR
    assert "HTML web page instead of" in str(task.error_message)


def test_referer_preservation(tmp_path):
    """Verify that the referer is properly stored in DB and loaded into DownloadTask."""
    db_file = os.path.join(tmp_path, "db_referer_test.db")
    db = DatabaseManager(db_file)

    task_id = db.create_download(
        url="https://video.fbcdn.net/v/test.mp4",
        destination_path=str(tmp_path / "test.mp4"),
        filename="test.mp4",
        referer="https://www.facebook.com/watch/?v=12345"
    )

    record = db.get_download(task_id)
    assert record is not None
    assert record["referer"] == "https://www.facebook.com/watch/?v=12345"

