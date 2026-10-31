"""Playlist & Batch Media Downloader Dialog."""

import os
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pdm.core.media_downloader import extract_playlist_entries
from pdm.storage.db import DatabaseManager


class PlaylistFetcherThread(QThread):
    """Background thread to extract playlist entries without freezing UI."""

    finished_signal = Signal(list)
    error_signal = Signal(str)

    def __init__(self, url: str, cookies: str = ""):
        super().__init__()
        self.url = url
        self.cookies = cookies

    def run(self):
        try:
            entries = extract_playlist_entries(self.url, cookies=self.cookies)
            self.finished_signal.emit(entries)
        except Exception as e:
            self.error_signal.emit(str(e))


class PlaylistDialog(QDialog):
    """Interactive IDM-style dialog for inspecting and downloading full or partial media playlists."""

    def __init__(
        self,
        url: str,
        default_save_dir: str,
        db: Optional[DatabaseManager] = None,
        cookies: str = "",
        auto_fetch: bool = True,
        parent=None
    ):
        super().__init__(parent)
        self.url = url
        self.default_save_dir = default_save_dir
        self.db = db
        self.cookies = cookies
        self.entries: List[Dict[str, Any]] = []
        self.fetcher: Optional[PlaylistFetcherThread] = None

        self.setWindowTitle("Playlist & Media Batch Downloader")
        self.resize(750, 480)

        self._setup_ui()
        if auto_fetch:
            self._start_fetching()

    def closeEvent(self, event):
        if self.fetcher and self.fetcher.isRunning():
            self.fetcher.terminate()
            self.fetcher.wait(500)
        super().closeEvent(event)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header info
        self.status_label = QLabel(f"Fetching playlist: {self.url[:70]}...")
        self.status_label.setStyleSheet("color: #38bdf8; font-weight: 500;")
        layout.addWidget(self.status_label)

        # Table of playlist items
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["", "#", "Title", "Duration"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 36)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 45)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        # Selection Control Row
        sel_row = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.setObjectName("secondaryBtn")
        select_all_btn.clicked.connect(self._select_all)
        sel_row.addWidget(select_all_btn)

        select_none_btn = QPushButton("Select None")
        select_none_btn.setObjectName("secondaryBtn")
        select_none_btn.clicked.connect(self._select_none)
        sel_row.addWidget(select_none_btn)

        self.count_label = QLabel("0 items selected")
        self.count_label.setStyleSheet("color: #94a3b8;")
        sel_row.addWidget(self.count_label)
        sel_row.addStretch()

        layout.addLayout(sel_row)

        # Folder Destination Row
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Save Folder:"))
        self.dir_input = QLineEdit(self.default_save_dir)
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(self.dir_input)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        # Category Row
        cat_row = QHBoxLayout()
        cat_row.addWidget(QLabel("Category:"))
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(["Video", "Music", "Other"])
        cat_row.addWidget(self.cat_combo)
        cat_row.addStretch()
        layout.addLayout(cat_row)

        # Dialog Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self.download_btn = QPushButton("Download Selected (0)")
        self.download_btn.setObjectName("primaryBtn")
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.download_btn)

        layout.addLayout(btn_row)

    def _start_fetching(self):
        self.fetcher = PlaylistFetcherThread(self.url, cookies=self.cookies)
        self.fetcher.finished_signal.connect(self._on_entries_fetched)
        self.fetcher.error_signal.connect(self._on_fetch_error)
        self.fetcher.start()

    def _on_entries_fetched(self, entries: List[Dict[str, Any]]):
        self.entries = entries
        if not entries:
            self.status_label.setText("No playable entries found in this playlist or link.")
            self.status_label.setStyleSheet("color: #ef4444;")
            return

        self.status_label.setText(f"Found {len(entries)} items in playlist:")
        self.status_label.setStyleSheet("color: #10b981; font-weight: 500;")

        self.table.setRowCount(len(entries))
        for row_idx, item in enumerate(entries):
            # Checkbox column
            cb_item = QTableWidgetItem()
            cb_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            cb_item.setCheckState(Qt.Checked)
            self.table.setItem(row_idx, 0, cb_item)

            # Index column
            idx_item = QTableWidgetItem(str(item.get("index", row_idx + 1)))
            idx_item.setTextAlignment(Qt.AlignCenter)
            idx_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row_idx, 1, idx_item)

            # Title column
            title_item = QTableWidgetItem(item.get("title", f"Item {row_idx + 1}"))
            title_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row_idx, 2, title_item)

            # Duration column
            dur_sec = item.get("duration") or 0
            dur_str = f"{dur_sec // 60:02d}:{dur_sec % 60:02d}" if dur_sec > 0 else "--:--"
            dur_item = QTableWidgetItem(dur_str)
            dur_item.setTextAlignment(Qt.AlignCenter)
            dur_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row_idx, 3, dur_item)

        self.table.itemChanged.connect(self._update_selection_count)
        self._update_selection_count()

    def _on_fetch_error(self, err_msg: str):
        self.status_label.setText(f"Failed to load playlist: {err_msg}")
        self.status_label.setStyleSheet("color: #ef4444;")

    def _update_selection_count(self):
        count = sum(
            1 for row in range(self.table.rowCount())
            if self.table.item(row, 0) and self.table.item(row, 0).checkState() == Qt.Checked
        )
        self.count_label.setText(f"{count} items selected")
        self.download_btn.setText(f"Download Selected ({count})")
        self.download_btn.setEnabled(count > 0)

    def _select_all(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)

    def _select_none(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)

    def _browse_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Save Directory", self.dir_input.text())
        if folder:
            self.dir_input.setText(folder)

    def get_selected_items(self) -> List[Dict[str, Any]]:
        """Return list of selected playlist entry dictionaries."""
        selected = []
        for row in range(self.table.rowCount()):
            cb_item = self.table.item(row, 0)
            if cb_item and cb_item.checkState() == Qt.Checked:
                if row < len(self.entries):
                    selected.append(self.entries[row])
        return selected

    def get_save_directory(self) -> str:
        return self.dir_input.text().strip()

    def get_category(self) -> str:
        return self.cat_combo.currentText()
