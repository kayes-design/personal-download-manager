"""Test that DownloadCoordinator falls back to yt_dlp title for filename when URL lacks a name.
"""
import sys
from types import SimpleNamespace
from unittest import mock

# Ensure the project root is on sys.path
sys.path.append('C:/Users/MrKayes/.gemini/antigravity/scratch/personal-download-manager')

from pdm.storage.db import DatabaseManager
from pdm.core.coordinator import DownloadCoordinator

def test_yt_dlp_title_fallback(monkeypatch, tmp_path):
    # Mock yt_dlp.YoutubeDL to return a title
    mock_info = {'title': 'sample_video'}
    class DummyYoutubeDL:
        def __init__(self, opts):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def extract_info(self, url, download=False):
            return mock_info
    monkeypatch.setitem(sys.modules, 'yt_dlp', SimpleNamespace(YoutubeDL=DummyYoutubeDL))

        # Use temporary file DB to ensure tables persist across connections
    db_path = tmp_path / 'test.db'
    db = DatabaseManager(str(db_path))
    coord = DownloadCoordinator(db)
    # URL with no filename
    url = 'https://example.com/video'
    dest_dir = tmp_path
    task_id = coord.add_download(url, destination_dir=str(dest_dir), filename=None, auto_start=False)
    record = db.get_download(task_id)
    # Expected filename: sample_video.mp4 (sanitized)
    assert record['filename'] == 'sample_video.mp4'
