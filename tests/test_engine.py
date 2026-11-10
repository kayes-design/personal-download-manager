"""Integration tests for the download engine and coordinator."""

import hashlib
import os
import time
import httpx
import pytest
from pdm.core import engine as engine_module
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


def test_maximum_connection_download_integrity(test_server, tmp_path):
    content = bytes(range(256)) * (4 * 1024 * 1024 // 256)
    test_server.add_resource("/max-connections.bin", content, supports_range=True)

    db = DatabaseManager(str(tmp_path / "max-connections.db"))
    destination_path = str(tmp_path / "max-connections.bin")
    url = test_server.get_url("/max-connections.bin")
    task_id = db.create_download(
        url=url,
        destination_path=destination_path,
        filename="max-connections.bin",
        connections_count=32,
    )
    task = DownloadTask(
        task_id=task_id,
        url=url,
        destination_path=destination_path,
        filename="max-connections.bin",
        db=db,
        connections_count=32,
    )

    task.run_sync()

    with open(destination_path, "rb") as downloaded:
        assert downloaded.read() == content
    assert task.status == DownloadStatus.COMPLETED
    assert len(task.segments) == 32


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


def test_probe_fallback_closes_without_reading_response_body(monkeypatch, tmp_path):
    class TrackingStream(httpx.SyncByteStream):
        def __init__(self):
            self.iterated = False
            self.closed = False

        def __iter__(self):
            self.iterated = True
            yield b"probe body"

        def close(self):
            self.closed = True

    stream = TrackingStream()

    def handler(request):
        if request.method == "HEAD":
            return httpx.Response(405, request=request)
        return httpx.Response(
            200,
            headers={"Content-Length": "10", "Content-Type": "application/octet-stream"},
            stream=stream,
            request=request,
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        engine_module.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    db = DatabaseManager(str(tmp_path / "probe.db"))
    task_id = db.create_download(
        url="https://example.com/large-file.bin",
        destination_path=str(tmp_path / "large-file.bin"),
        filename="large-file.bin",
    )
    task = DownloadTask(
        task_id=task_id,
        url="https://example.com/large-file.bin",
        destination_path=str(tmp_path / "large-file.bin"),
        filename="large-file.bin",
        db=db,
    )

    task._probe_server()

    assert stream.iterated is False
    assert stream.closed is True
    assert task.total_bytes == 10


def test_resume_restarts_when_remote_file_validator_changes(test_server, tmp_path):
    old_content = b"A" * (1024 * 1024)
    new_content = bytes(index % 251 for index in range(len(old_content)))
    test_server.add_resource("/changed-between-resume.bin", old_content, etag='"old"')

    db = DatabaseManager(str(tmp_path / "changed-resume.db"))
    destination_path = str(tmp_path / "changed-between-resume.bin")
    url = test_server.get_url("/changed-between-resume.bin")
    task_id = db.create_download(
        url=url,
        destination_path=destination_path,
        filename="changed-between-resume.bin",
        connections_count=4,
    )

    db.update_download_metadata(
        task_id,
        len(old_content),
        '"old"',
        "Wed, 21 Oct 2026 07:28:00 GMT",
        True,
    )
    part_path = f"{destination_path}.pdm_part_0"
    with open(part_path, "wb") as part_file:
        part_file.write(old_content[:200_000])
    db.create_segment(task_id, 0, 0, len(old_content) - 1, part_path)
    db.update_download_progress(task_id, 200_000)

    test_server.add_resource("/changed-between-resume.bin", new_content, etag='"new"')
    task = DownloadTask(
        task_id=task_id,
        url=url,
        destination_path=destination_path,
        filename="changed-between-resume.bin",
        db=db,
        connections_count=4,
    )

    task.run_sync()

    with open(destination_path, "rb") as downloaded:
        assert downloaded.read() == new_content


def test_resume_migrates_legacy_visible_part_into_staging(test_server, tmp_path):
    content = bytes(index % 251 for index in range(512 * 1024))
    test_server.add_resource("/legacy-part.bin", content, supports_range=True)

    db = DatabaseManager(str(tmp_path / "legacy-part.db"))
    destination_path = str(tmp_path / "legacy-part.bin")
    url = test_server.get_url("/legacy-part.bin")
    task_id = db.create_download(
        url=url,
        destination_path=destination_path,
        filename="legacy-part.bin",
        connections_count=1,
    )
    db.update_download_metadata(
        task_id,
        len(content),
        '"default-etag-1"',
        "Wed, 21 Oct 2026 07:28:00 GMT",
        True,
    )
    legacy_part_path = f"{destination_path}.pdm_part_0"
    with open(legacy_part_path, "wb") as partial:
        partial.write(content[:100_000])
    db.create_segment(task_id, 0, 0, len(content) - 1, legacy_part_path)

    task = DownloadTask(
        task_id=task_id,
        url=url,
        destination_path=destination_path,
        filename="legacy-part.bin",
        db=db,
        connections_count=1,
    )
    task.run_sync()

    assert task.status == DownloadStatus.COMPLETED
    assert not os.path.exists(legacy_part_path)
    with open(destination_path, "rb") as downloaded:
        assert downloaded.read() == content


def test_media_stream_progress_does_not_overwrite_download_status(monkeypatch, tmp_path):
    db = DatabaseManager(str(tmp_path / "media-progress.db"))
    destination_path = str(tmp_path / "media.mp4")
    task_id = db.create_download(
        url="https://example.com/media.mp4",
        destination_path=destination_path,
        filename="media.mp4",
    )
    task = DownloadTask(
        task_id=task_id,
        url="https://example.com/media.mp4",
        destination_path=destination_path,
        filename="media.mp4",
        db=db,
    )
    observed_statuses = []
    published_path_was_hidden_during_transfer = []

    class FakeMediaDownloader:
        def download(self, **kwargs):
            staged_path = kwargs["destination_path"]
            with open(staged_path, "wb") as media_file:
                media_file.write(b"01234")
            kwargs["progress_callback"](5, 10, 1.0, 5)
            observed_statuses.append(db.get_download(task_id)["status"])
            published_path_was_hidden_during_transfer.append(not os.path.exists(destination_path))
            with open(staged_path, "ab") as media_file:
                media_file.write(b"56789")
            return staged_path

    monkeypatch.setattr(engine_module, "MediaStreamDownloader", FakeMediaDownloader)
    task._set_status(DownloadStatus.DOWNLOADING)

    task._download_stream()

    assert observed_statuses == [DownloadStatus.DOWNLOADING.value]
    assert published_path_was_hidden_during_transfer == [True]
    assert os.path.exists(destination_path)
    with open(destination_path, "rb") as media_file:
        assert media_file.read() == b"0123456789"
    assert not os.path.exists(os.path.join(tmp_path, ".pdm-incomplete", str(task_id)))
    assert db.get_download(task_id)["status"] == DownloadStatus.COMPLETED.value


def test_incomplete_http_download_is_staged_until_completion(test_server, tmp_path):
    content = b"staged-download-content-" * 65536
    test_server.add_resource("/staged-download.bin", content, supports_range=True)

    db = DatabaseManager(str(tmp_path / "staged-download.db"))
    destination_path = str(tmp_path / "staged-download.bin")
    url = test_server.get_url("/staged-download.bin")
    task_id = db.create_download(
        url=url,
        destination_path=destination_path,
        filename="staged-download.bin",
        connections_count=1,
    )
    task = DownloadTask(
        task_id=task_id,
        url=url,
        destination_path=destination_path,
        filename="staged-download.bin",
        db=db,
        connections_count=1,
    )

    import threading
    assembly_started = threading.Event()
    allow_assembly = threading.Event()
    assemble_file = task._assemble_file

    def wait_before_assembly():
        assembly_started.set()
        assert allow_assembly.wait(timeout=5)
        assemble_file()

    task._assemble_file = wait_before_assembly
    worker = threading.Thread(target=task.run_sync, daemon=True)
    worker.start()

    assert assembly_started.wait(timeout=10)
    assert task.downloaded_bytes == len(content)
    assert not os.path.exists(destination_path)
    segments = db.get_segments(task_id)
    assert segments
    assert all(
        os.path.commonpath((str(tmp_path / ".pdm-incomplete"), segment["temp_filepath"]))
        == str(tmp_path / ".pdm-incomplete")
        for segment in segments
    )
    assert any(os.path.getsize(segment["temp_filepath"]) > 0 for segment in segments)

    allow_assembly.set()
    worker.join(timeout=10)

    assert not worker.is_alive()
    assert task.status == DownloadStatus.COMPLETED
    with open(destination_path, "rb") as downloaded:
        assert downloaded.read() == content
    assert not os.path.exists(os.path.join(tmp_path, ".pdm-incomplete", str(task_id)))


def test_range_server_that_ignores_requests_falls_back_to_single_stream(monkeypatch, tmp_path):
    content = bytes(index % 251 for index in range(512 * 1024))

    def handler(request):
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(len(content)),
            "Content-Type": "application/octet-stream",
            "ETag": '"unchanged"',
        }
        if request.method == "HEAD":
            return httpx.Response(200, headers=headers, request=request)
        return httpx.Response(200, headers=headers, content=content, request=request)

    real_client = httpx.Client
    monkeypatch.setattr(
        engine_module.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    db = DatabaseManager(str(tmp_path / "ignored-range.db"))
    destination_path = str(tmp_path / "ignored-range.bin")
    task_id = db.create_download(
        url="https://example.com/ignored-range.bin",
        destination_path=destination_path,
        filename="ignored-range.bin",
        connections_count=4,
    )
    task = DownloadTask(
        task_id=task_id,
        url="https://example.com/ignored-range.bin",
        destination_path=destination_path,
        filename="ignored-range.bin",
        db=db,
        connections_count=4,
    )

    task.run_sync()

    with open(destination_path, "rb") as downloaded:
        assert downloaded.read() == content
    assert task.supports_range is False
    assert task.status == DownloadStatus.COMPLETED
