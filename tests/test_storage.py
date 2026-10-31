"""Unit tests for SQLite database manager."""

import os
import pytest
from pdm.storage.db import DatabaseManager


@pytest.fixture
def db(tmp_path):
    db_file = os.path.join(tmp_path, "test_downloads.db")
    return DatabaseManager(db_file)


def test_download_crud(db):
    task_id = db.create_download(
        url="https://example.com/test.zip",
        destination_path="C:/Downloads/test.zip",
        filename="test.zip",
        category="Compressed",
        connections_count=8
    )
    assert task_id > 0

    item = db.get_download(task_id)
    assert item is not None
    assert item["url"] == "https://example.com/test.zip"
    assert item["status"] == "Queued"
    assert item["category"] == "Compressed"
    assert item["connections_count"] == 8

    # Update metadata
    db.update_download_metadata(task_id, 1024000, '"etag-123"', 'Wed, 21 Oct 2026 07:28:00 GMT', True)
    item = db.get_download(task_id)
    assert item["total_bytes"] == 1024000
    assert item["etag"] == '"etag-123"'
    assert item["supports_range"] == 1

    # Update progress and status
    db.update_download_progress(task_id, 512000, "Downloading")
    item = db.get_download(task_id)
    assert item["downloaded_bytes"] == 512000
    assert item["status"] == "Downloading"

    # Filtered list
    results = db.list_downloads(category="Compressed")
    assert len(results) == 1
    assert results[0]["id"] == task_id

    empty_results = db.list_downloads(category="Music")
    assert len(empty_results) == 0

    # Search
    search_res = db.list_downloads(search="test")
    assert len(search_res) == 1

    # Delete
    db.delete_download(task_id)
    assert db.get_download(task_id) is None


def test_segment_management(db):
    task_id = db.create_download(
        url="https://example.com/movie.mp4",
        destination_path="C:/Downloads/movie.mp4",
        filename="movie.mp4",
        category="Video"
    )

    s1 = db.create_segment(task_id, 0, 0, 499, "movie.mp4.part0")
    s2 = db.create_segment(task_id, 1, 500, 999, "movie.mp4.part1")

    segments = db.get_segments(task_id)
    assert len(segments) == 2
    assert segments[0]["start_byte"] == 0
    assert segments[0]["end_byte"] == 499
    assert segments[1]["start_byte"] == 500

    # Progress
    db.update_segment_progress(s1, 500, "Completed")
    updated_segs = db.get_segments(task_id)
    assert updated_segs[0]["downloaded_bytes"] == 500
    assert updated_segs[0]["status"] == "Completed"

    # Cascade on delete download
    db.delete_download(task_id)
    assert len(db.get_segments(task_id)) == 0


def test_settings_storage(db):
    db.set_setting("max_connections", "8")
    assert db.get_setting("max_connections") == "8"

    # Overwrite
    db.set_setting("max_connections", "16")
    assert db.get_setting("max_connections") == "16"

    # Default fallback
    assert db.get_setting("non_existent", "default_val") == "default_val"


def test_delete_completed(db):
    id1 = db.create_download("https://example.com/1.zip", "C:/tmp/1.zip", "1.zip")
    id2 = db.create_download("https://example.com/2.zip", "C:/tmp/2.zip", "2.zip")
    id3 = db.create_download("https://example.com/3.zip", "C:/tmp/3.zip", "3.zip")

    db.set_download_status(id1, "Completed")
    db.set_download_status(id2, "Downloading")
    db.set_download_status(id3, "Completed")

    deleted = db.delete_completed()
    assert len(deleted) == 2
    assert db.get_download(id1) is None
    assert db.get_download(id3) is None
    assert db.get_download(id2) is not None
    assert db.get_download(id2)["status"] == "Downloading"


def test_update_download_address(db):
    task_id = db.create_download("https://example.com/expired-token-123", "C:/tmp/file.iso", "file.iso")
    db.set_download_status(task_id, "Error", "HTTP 403 Forbidden")

    # Refresh URL with new token
    db.update_download_address(task_id, "https://example.com/new-valid-token-456", cookies="session=abc", referer="https://example.com")
    updated = db.get_download(task_id)
    assert updated["url"] == "https://example.com/new-valid-token-456"
    assert updated["status"] == "Queued"
    assert updated["error_message"] is None
    assert updated["cookies"] == "session=abc"
    assert updated["referer"] == "https://example.com"


def test_download_proxy_support(db):
    task_id = db.create_download(
        url="https://example.com/vpn-geo-locked.zip",
        destination_path="C:/tmp/vpn-geo-locked.zip",
        filename="vpn-geo-locked.zip",
        proxy="http://127.0.0.1:8080"
    )
    task = db.get_download(task_id)
    assert task["proxy"] == "http://127.0.0.1:8080"

