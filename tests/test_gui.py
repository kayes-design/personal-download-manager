"""Unit and component tests for GUI models and widgets."""

import os
import sys
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pdm.core.coordinator import DownloadCoordinator
from pdm.core.engine import SegmentInfo
from pdm.gui.add_dialog import AddDownloadDialog, detect_category
from pdm.gui.integrity_dialog import IntegrityCheckDialog
from pdm.gui.main_window import MainWindow
from pdm.gui.models import DownloadsTableModel, format_bytes, format_eta, format_speed
from pdm.gui.segment_widget import SegmentVisualizerWidget
from pdm.storage.db import DatabaseManager


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_format_helpers():
    assert format_bytes(500) == "500.0 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1048576) == "1.0 MB"
    assert format_bytes(1073741824) == "1.0 GB"
    assert format_bytes(-1) == "Unknown"

    assert format_speed(0) == ""
    assert format_speed(512000) == "500.0 KB/s"
    assert format_speed(2097152) == "2.00 MB/s"

    assert format_eta(None) == ""
    assert format_eta(45) == "00:45"
    assert format_eta(125) == "02:05"
    assert format_eta(3665) == "01:01:05"


def test_detect_category():
    assert detect_category("archive.zip") == "Compressed"
    assert detect_category("archive.7z") == "Compressed"
    assert detect_category("document.pdf") == "Documents"
    assert detect_category("song.mp3") == "Music"
    assert detect_category("movie.mkv") == "Video"
    assert detect_category("installer.exe") == "Programs"
    assert detect_category("unknown.xyz") == "Other"


def test_table_model(qapp):
    model = DownloadsTableModel()
    sample_data = [
        {
            "id": 1,
            "filename": "test.zip",
            "total_bytes": 1048576,
            "downloaded_bytes": 524288,
            "status": "Downloading",
            "current_speed": 102400.0,
            "eta_seconds": 5,
            "category": "Compressed",
            "created_at": "2026-10-30 12:00:00",
            "description": "Test file download"
        }
    ]
    model.set_data(sample_data)
    assert model.rowCount() == 1
    assert model.columnCount() == 8

    # Verify IDM column headers
    assert model.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "File Name"
    assert model.headerData(1, Qt.Horizontal, Qt.DisplayRole) == "Q"
    assert model.headerData(2, Qt.Horizontal, Qt.DisplayRole) == "Size"
    assert model.headerData(3, Qt.Horizontal, Qt.DisplayRole) == "Status"
    assert model.headerData(4, Qt.Horizontal, Qt.DisplayRole) == "Time left"
    assert model.headerData(5, Qt.Horizontal, Qt.DisplayRole) == "Transfer rate"
    assert model.headerData(6, Qt.Horizontal, Qt.DisplayRole) == "Last Try..."
    assert model.headerData(7, Qt.Horizontal, Qt.DisplayRole) == "Description"

    # Verify cell data
    assert model.data(model.index(0, 0), Qt.DisplayRole) == "test.zip"
    assert model.data(model.index(0, 1), Qt.DisplayRole) == ""
    assert model.data(model.index(0, 2), Qt.DisplayRole) == "1.0 MB"
    assert model.data(model.index(0, 3), Qt.DisplayRole) == "Downloading (50.0%)"
    assert model.data(model.index(0, 4), Qt.DisplayRole) == "00:05"
    assert model.data(model.index(0, 5), Qt.DisplayRole) == "100.0 KB/s"
    assert model.data(model.index(0, 6), Qt.DisplayRole) == "2026-10-30 12:00:00"
    assert model.data(model.index(0, 7), Qt.DisplayRole) == "Test file download"

    # Verify File Name icon decoration
    icon = model.data(model.index(0, 0), Qt.DecorationRole)
    assert icon is not None and not icon.isNull()


def test_segment_widget(qapp):
    widget = SegmentVisualizerWidget()
    segs = [
        SegmentInfo(segment_id=1, segment_index=0, start_byte=0, end_byte=499, downloaded_bytes=500),
        SegmentInfo(segment_id=2, segment_index=1, start_byte=500, end_byte=999, downloaded_bytes=250),
    ]
    widget.set_data(1000, segs)
    # Trigger repaint in offscreen mode
    widget.repaint()
    assert widget.total_bytes == 1000
    assert len(widget.segments) == 2


def test_main_window_and_filtering(qapp, tmp_path):
    db_file = os.path.join(tmp_path, "gui_test.db")
    db = DatabaseManager(db_file)
    db.create_download("https://example.com/movie.mp4", "C:/tmp/movie.mp4", "movie.mp4", category="Video")
    db.create_download("https://example.com/archive.zip", "C:/tmp/archive.zip", "archive.zip", category="Compressed")

    coord = DownloadCoordinator(db=db)
    window = MainWindow(coord)

    # Initial view shows all
    assert window.table_model.rowCount() == 2

    # Filter to Video
    window.current_category = "Video"
    window._refresh_table()
    assert window.table_model.rowCount() == 1
    assert window.table_model.get_download_at(0)["filename"] == "movie.mp4"

    # Search filter
    window.current_category = "All"
    window.search_query = "archive"
    window._refresh_table()
    assert window.table_model.rowCount() == 1
    assert window.table_model.get_download_at(0)["filename"] == "archive.zip"

    # Status filter: Unfinished vs Finished
    window.search_query = ""
    window.current_status = "Unfinished"
    window._refresh_table()
    assert window.table_model.rowCount() == 2

    db.update_download_progress(1, 1000, status="Completed")
    window.current_status = "Finished"
    window._refresh_table()
    assert window.table_model.rowCount() == 1
    assert window.table_model.get_download_at(0)["filename"] == "movie.mp4"

    window.current_status = "Unfinished"
    window._refresh_table()
    assert window.table_model.rowCount() == 1
    assert window.table_model.get_download_at(0)["filename"] == "archive.zip"

    coord.shutdown()
    window.close()


def test_idm_header_view(qapp):
    from pdm.gui.main_window import IDMHeaderView
    from PySide6.QtWidgets import QTableView
    table = QTableView()
    header = IDMHeaderView(Qt.Horizontal, table)
    table.setHorizontalHeader(header)
    assert not header._down_arrow.isNull()
    assert not header._up_arrow.isNull()
    header.setSortIndicator(0, Qt.DescendingOrder)
    assert header.sortIndicatorSection() == 0
    assert header.sortIndicatorOrder() == Qt.DescendingOrder


def test_add_download_dialog_video_folder(qapp, tmp_path):
    db_file = os.path.join(tmp_path, "add_dlg_test.db")
    db = DatabaseManager(db_file)
    custom_video_dir = os.path.join(tmp_path, "MyCustomVideos")
    os.makedirs(custom_video_dir, exist_ok=True)
    db.set_setting("save_dir_video", custom_video_dir)

    dlg = AddDownloadDialog(str(tmp_path), db=db)
    dlg.url_input.setText("https://example.com/awesome_video.mp4")
    # Verify auto category detection to Video
    assert dlg.category_combo.currentText() == "Video"
    # Verify save directory automatically switched to custom video folder
    assert os.path.normpath(dlg.dir_input.text()) == os.path.normpath(custom_video_dir)

    # Change to another custom folder and test remember folder setting
    new_custom = os.path.join(tmp_path, "NewVideoFolder")
    dlg.dir_input.setText(new_custom)
    dlg.remember_folder_cb.setChecked(True)
    dlg._on_submit()
    assert os.path.normpath(db.get_setting("save_dir_video")) == os.path.normpath(new_custom)


def test_download_complete_dialog(qapp, tmp_path):
    from pdm.gui.complete_dialog import DownloadCompleteDialog
    db_file = os.path.join(tmp_path, "complete_dlg_test.db")
    db = DatabaseManager(db_file)
    test_file = os.path.join(tmp_path, "completed_video.mp4")
    with open(test_file, "w") as f:
        f.write("dummy video data")

    item = {
        "id": 1,
        "filename": "completed_video.mp4",
        "destination_path": test_file,
        "total_bytes": 1024 * 1024 * 15,
        "category": "Video"
    }

    dlg = DownloadCompleteDialog(item, db)
    assert dlg.filename == "completed_video.mp4"
    assert dlg.category == "Video"
    assert not dlg.dont_show_cb.isChecked()

    # Toggle 'Don't show this dialog again'
    dlg.dont_show_cb.setChecked(True)
    assert db.get_setting("show_complete_dlg") == "0"

    dlg.dont_show_cb.setChecked(False)
    assert db.get_setting("show_complete_dlg") == "1"


def test_native_host_routes_video_folder(tmp_path):
    from pdm.browser_bridge.native_host import handle_download_item
    db_file = os.path.join(tmp_path, "host_test.db")
    db = DatabaseManager(db_file)

    custom_vid_dir = os.path.join(tmp_path, "VideoCollection")
    os.makedirs(custom_vid_dir, exist_ok=True)
    db.set_setting("save_dir_video", custom_vid_dir)

    item = {
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "filename": "Never Gonna Give You Up.mp4",
        "auto_start": True
    }
    tid = handle_download_item(db, str(tmp_path), 4, item)
    assert tid is not None
    rec = db.get_download(tid)
    assert rec["category"] == "Video"
    # Destination must be inside the specific custom Video folder!
    assert os.path.dirname(os.path.normpath(rec["destination_path"])) == os.path.normpath(custom_vid_dir)


def test_playlist_dialog_init(qapp, tmp_path):
    from pdm.gui.playlist_dialog import PlaylistDialog
    db_file = os.path.join(tmp_path, "playlist_test.db")
    db = DatabaseManager(db_file)

    dlg = PlaylistDialog(
        url="https://www.youtube.com/playlist?list=PL123456",
        default_save_dir=str(tmp_path),
        db=db,
        cookies="test_cookie=123",
        auto_fetch=False
    )
    assert dlg.url == "https://www.youtube.com/playlist?list=PL123456"
    assert dlg.cookies == "test_cookie=123"
    assert dlg.get_save_directory() == str(tmp_path)
    assert dlg.get_category() == "Video"

    # Simulate population
    entries = [
        {"index": 1, "title": "Track 1", "url": "https://example.com/t1", "duration": 180},
        {"index": 2, "title": "Track 2", "url": "https://example.com/t2", "duration": 210},
    ]
    dlg._on_entries_fetched(entries)
    assert dlg.table.rowCount() == 2
    assert len(dlg.get_selected_items()) == 2

    # Test Deselect All
    dlg._select_none()
    assert len(dlg.get_selected_items()) == 0

    # Test Select All
    dlg._select_all()
    assert len(dlg.get_selected_items()) == 2



