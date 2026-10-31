"""Extreme stress and edge-case security test suite for PDM."""

import os
import sys
import threading
import time
import tempfile
import pytest

from pdm.core.security import (
    sanitize_filename,
    validate_url,
    resolve_safe_filepath,
    parse_content_disposition,
    extract_filename_from_url,
)
from pdm.core.limiter import SpeedLimiter
from pdm.core.batch import expand_url_pattern
from pdm.core.media_downloader import is_media_stream_url, normalize_media_url
from pdm.storage.db import DatabaseManager
from pdm.browser_bridge.native_host import handle_download_item


class TestExtremeSecurity:
    """Extreme security tests against malicious input, path traversal, and injections."""

    def test_path_traversal_variations(self):
        traversals = [
            "../../../../../../Windows/System32/cmd.exe",
            "..\\..\\..\\..\\Windows\\System32\\cmd.exe",
            "/etc/passwd",
            "C:\\boot.ini",
            "..%2F..%2F..%2Fcalc.exe",
            "..%5C..%5Ccalc.exe",
            "%252e%252e%252f%252e%252e%252fcalc.exe",
            "..%252f..%252fcalc.exe",
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            for bad_name in traversals:
                safe_name = sanitize_filename(bad_name)
                # Must not contain path separators
                assert "/" not in safe_name
                assert "\\" not in safe_name
                assert ".." not in safe_name
                # Must stay strictly inside temp_dir
                resolved = resolve_safe_filepath(temp_dir, safe_name)
                assert os.path.dirname(resolved) == temp_dir

    def test_windows_reserved_device_names(self):
        reserved = [
            "CON", "con", "Prn", "AUX", "NUL",
            "com1", "COM9", "lpt1", "LPT9",
            "CON.txt", "aux.mp4", "nul.bin", "COM1.exe"
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            for r in reserved:
                cleaned = sanitize_filename(r)
                assert cleaned.upper() not in ("CON", "PRN", "AUX", "NUL", "COM1", "LPT1")
                # On Windows, stem must be protected
                stem = os.path.splitext(cleaned)[0]
                assert stem.upper() not in ("CON", "PRN", "AUX", "NUL", "COM1", "LPT1")
                resolved = resolve_safe_filepath(temp_dir, cleaned)
                assert os.path.dirname(resolved) == temp_dir

    def test_null_byte_and_control_chars(self):
        bad_names = [
            "innocent.mp4\x00malicious.exe",
            "test\x01\x02\x03\x1f\x7fname.mkv",
            "file\r\nwith\r\nnewlines.mp4",
            "weird\t\b\f\vtab.zip",
        ]
        for bad in bad_names:
            cleaned = sanitize_filename(bad)
            assert "\x00" not in cleaned
            assert "\r" not in cleaned
            assert "\n" not in cleaned
            assert "\t" not in cleaned

    def test_extreme_filename_length(self):
        huge_name = "A" * 1000 + ".mp4"
        cleaned = sanitize_filename(huge_name)
        assert len(cleaned) <= 245
        assert cleaned.endswith(".mp4")

    def test_url_security_rejections(self):
        malicious_urls = [
            "javascript:alert(document.cookie)",
            "javascript://%0aalert(1)",
            "file:///C:/Windows/System32/cmd.exe",
            "file:///etc/shadow",
            "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
            "vbscript:msgbox(1)",
            "about:blank",
            "chrome://extensions",
            "",
            None,
            "ftp://example.com/file.bin",
            "ssh://admin@example.com",
            "gopher://ancient.net",
        ]
        for url in malicious_urls:
            valid, msg = validate_url(url)
            assert valid is False, f"URL should be rejected: {url}"

    def test_valid_http_https_urls(self):
        valid_urls = [
            "http://example.com/file.zip",
            "https://sub.domain.org/path/video.mp4?token=123&expire=999",
            "https://cdn.fbcdn.net/v/t39.1234/vid.mp4?_nc_cat=101",
            "http://192.168.1.100:8080/download.iso",
        ]
        for url in valid_urls:
            valid, norm = validate_url(url)
            assert valid is True, f"URL should be accepted: {url}"
            assert norm == url

    def test_native_host_arbitrary_destination_dir_ignored(self):
        """Verify native host ignores client-provided destination_dir to prevent arbitrary folder drop."""
        import gc
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")
            db = DatabaseManager(db_path)

            malicious_item = {
                "url": "https://example.com/payload.exe",
                "filename": "payload.exe",
                "destination_dir": "C:\\Windows\\System32",  # Attempted arbitrary folder drop
                "auto_start": False,
            }

            safe_default = os.path.join(temp_dir, "Downloads")
            tid = handle_download_item(db, safe_default, 4, malicious_item)
            assert tid is not None

            rec = db.get_download(tid)
            assert "System32" not in rec["destination_path"]
            assert temp_dir in rec["destination_path"]
            del db
            gc.collect()


class TestExtremeEngineAndConcurrency:
    """Extreme concurrency and stress tests on engine components."""

    def test_speed_limiter_multithreaded_stress(self):
        """Stress test SpeedLimiter with 20 parallel threads."""
        limiter = SpeedLimiter(500_000)  # 500 KB/s limit
        threads = []
        errors = []

        def worker():
            try:
                for _ in range(10):
                    limiter.acquire(10_000)
            except Exception as e:
                errors.append(e)

        for _ in range(20):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5.0)

        assert len(errors) == 0

    def test_database_concurrent_read_write(self):
        """Stress test SQLite database with 30 concurrent readers and writers."""
        import gc
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "stress.db")
            db = DatabaseManager(db_path)
            errors = []

            def writer(thread_id):
                try:
                    for i in range(15):
                        tid = db.create_download(
                            url=f"https://example.com/file_{thread_id}_{i}.bin",
                            destination_path=os.path.join(temp_dir, f"file_{thread_id}_{i}.bin"),
                            filename=f"file_{thread_id}_{i}.bin"
                        )
                        db.update_download_progress(tid, i * 100, 1500)
                        db.set_download_status(tid, "Downloading")
                except Exception as e:
                    errors.append(e)

            def reader():
                try:
                    for _ in range(15):
                        db.list_downloads()
                        db.get_setting("max_concurrent", "3")
                except Exception as e:
                    errors.append(e)

            threads = []
            for i in range(15):
                threads.append(threading.Thread(target=writer, args=(i,)))
                threads.append(threading.Thread(target=reader))

            for t in threads:
                t.start()

            for t in threads:
                t.join(timeout=10.0)

            assert len(errors) == 0
            items = db.list_downloads()
            assert len(items) == 15 * 15
            del db
            gc.collect()


class TestBatchPatternExtreme:
    """Extreme tests for batch pattern generation."""

    def test_numeric_ranges(self):
        items = expand_url_pattern("https://example.com/ep[01-12].mp4")
        assert len(items) == 12
        assert items[0] == "https://example.com/ep01.mp4"
        assert items[-1] == "https://example.com/ep12.mp4"

    def test_letter_ranges(self):
        items = expand_url_pattern("https://example.com/doc_[a-e].pdf")
        assert len(items) == 5
        assert items == [
            "https://example.com/doc_a.pdf",
            "https://example.com/doc_b.pdf",
            "https://example.com/doc_c.pdf",
            "https://example.com/doc_d.pdf",
            "https://example.com/doc_e.pdf",
        ]

    def test_single_url_passthrough(self):
        items = expand_url_pattern("https://example.com/single.zip")
        assert len(items) == 1
        assert items[0] == "https://example.com/single.zip"
