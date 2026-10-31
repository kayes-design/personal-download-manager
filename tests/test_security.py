"""Tests for security validation and sanitization primitives."""

import os
import pytest
from pdm.core.security import (
    validate_url,
    sanitize_filename,
    extract_filename_from_url,
    parse_content_disposition,
    resolve_safe_filepath,
)


def test_validate_url():
    # Valid URLs
    ok, res = validate_url("https://example.com/file.zip")
    assert ok is True
    assert res == "https://example.com/file.zip"

    ok, _ = validate_url("http://127.0.0.1:8080/test")
    assert ok is True

    # Invalid schemes
    ok, err = validate_url("ftp://example.com/file.zip")
    assert ok is False
    assert "Unsupported scheme" in err

    ok, err = validate_url("file:///C:/Windows/notepad.exe")
    assert ok is False

    ok, err = validate_url("javascript:alert(1)")
    assert ok is False

    # Empty / malformed
    ok, err = validate_url("")
    assert ok is False

    ok, err = validate_url("   ")
    assert ok is False


def test_sanitize_filename():
    # Path traversal attack
    assert sanitize_filename("../../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\Windows\\System32\\cmd.exe") == "cmd.exe"

    # Windows reserved device names
    assert sanitize_filename("CON") == "_CON"
    assert sanitize_filename("con.txt") == "_con.txt"
    assert sanitize_filename("NUL.zip") == "_NUL.zip"
    assert sanitize_filename("com1.png") == "_com1.png"

    # Illegal Windows characters
    assert sanitize_filename('my<file>:name"test|?.bin') == "my_file__name_test__.bin"

    # Trailing dots and spaces
    assert sanitize_filename("test_file...   ") == "test_file"

    # Empty fallback
    assert sanitize_filename("", "fallback.bin") == "fallback.bin"
    assert sanitize_filename("   ", "fallback.bin") == "fallback.bin"
    assert sanitize_filename("...", "fallback.bin") == "fallback.bin"


def test_extract_filename_from_url():
    assert extract_filename_from_url("https://example.com/downloads/setup_v1.0.exe") == "setup_v1.0.exe"
    assert extract_filename_from_url("https://example.com/path/archive.tar.gz?token=12345") == "archive.tar.gz"
    assert extract_filename_from_url("https://example.com/") == "download.bin"


def test_parse_content_disposition():
    # Standard attachment
    header = 'attachment; filename="document_v2.pdf"'
    assert parse_content_disposition(header) == "document_v2.pdf"

    # Unquoted
    header = "attachment; filename=image.png"
    assert parse_content_disposition(header) == "image.png"

    # RFC 5987 UTF-8 encoding
    header = "attachment; filename*=UTF-8''%E6%B8%AC%E8%A9%A6%E6%AA%94%E6%A1%88.zip"
    assert parse_content_disposition(header) == "測試檔案.zip"


def test_resolve_safe_filepath(tmp_path):
    target_dir = str(tmp_path)

    # First file
    path1 = resolve_safe_filepath(target_dir, "report.pdf")
    assert os.path.basename(path1) == "report.pdf"
    with open(path1, "w") as f:
        f.write("content 1")

    # Colliding file 2 -> (1)
    path2 = resolve_safe_filepath(target_dir, "report.pdf")
    assert os.path.basename(path2) == "report (1).pdf"
    with open(path2, "w") as f:
        f.write("content 2")

    # Colliding file 3 -> (2)
    path3 = resolve_safe_filepath(target_dir, "report.pdf")
    assert os.path.basename(path3) == "report (2).pdf"

    # Path traversal attempt should be contained inside target_dir
    path_traversal = resolve_safe_filepath(target_dir, "../../../secret.txt")
    assert os.path.dirname(path_traversal) == target_dir
    assert os.path.basename(path_traversal) == "secret.txt"
