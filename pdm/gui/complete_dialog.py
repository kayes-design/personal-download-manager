"""Download Complete Popup Notification Dialog (IDM style with modern finish)."""

import os
import subprocess
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pdm.gui.icons import (
    create_compressed_icon,
    create_document_icon,
    create_folder_icon,
    create_music_icon,
    create_programs_icon,
    create_video_icon,
)
from pdm.gui.models import format_bytes
from pdm.storage.db import DatabaseManager


def create_check_badge() -> QIcon:
    """Render a crisp, high-contrast green circle badge with a white checkmark."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    # Green circle background
    p.setBrush(QColor("#16a34a"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, 28, 28)

    # White checkmark
    p.setPen(QPen(QColor("#ffffff"), 3.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    path = QPainterPath()
    path.moveTo(9, 16)
    path.lineTo(14, 21)
    path.lineTo(23, 11)
    p.drawPath(path)

    p.end()
    return QIcon(pix)


class DownloadCompleteDialog(QDialog):
    """Sleek, modern 'Download Complete' popup dialog with Open, Open Folder, and Don't Show Again."""

    def __init__(self, item: dict, db: DatabaseManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.item = item
        self.db = db
        self.filename = item.get("filename") or "download"
        self.filepath = item.get("destination_path") or ""
        self.total_bytes = item.get("total_bytes", 0)
        self.category = item.get("category") or "Other"

        self.setWindowTitle("Download Complete")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)
        self.setFixedSize(500, 240)

        app = QApplication.instance()
        if app and app.windowIcon():
            self.setWindowIcon(app.windowIcon())

        self._setup_ui()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 16, 18, 16)
        root_layout.setSpacing(14)

        # 1. Header Banner
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        badge_lbl = QLabel()
        badge_lbl.setPixmap(create_check_badge().pixmap(28, 28))
        header_layout.addWidget(badge_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        title_lbl = QLabel("Download Complete!")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #f8fafc;")

        status_lbl = QLabel(f"Finished downloading • {format_bytes(self.total_bytes)}")
        status_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")

        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(status_lbl)
        header_layout.addLayout(title_vbox)
        header_layout.addStretch()

        root_layout.addLayout(header_layout)

        # 2. File Card Surface
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(14)

        # Icon based on category / extension
        icon_lbl = QLabel()
        cat_icon = self._get_file_icon()
        icon_lbl.setPixmap(cat_icon.pixmap(36, 36))
        card_layout.addWidget(icon_lbl)

        # File details
        details_layout = QVBoxLayout()
        details_layout.setSpacing(4)

        fn_lbl = QLabel(self.filename)
        fn_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #f1f5f9;")
        fn_lbl.setWordWrap(True)

        folder_dir = os.path.dirname(self.filepath) if self.filepath else ""
        path_lbl = QLabel(f"Saved to: {folder_dir}")
        path_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        path_lbl.setWordWrap(True)

        details_layout.addWidget(fn_lbl)
        details_layout.addWidget(path_lbl)
        card_layout.addLayout(details_layout)

        root_layout.addWidget(card)

        # 3. Checkbox Option ("Don't show this dialog again")
        self.dont_show_cb = QCheckBox("Don't show this dialog again")
        self.dont_show_cb.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.dont_show_cb.setChecked(self.db.get_setting("show_complete_dlg", "1") == "0")
        self.dont_show_cb.toggled.connect(self._on_toggle_dont_show)
        root_layout.addWidget(self.dont_show_cb)

        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.open_btn = QPushButton("Open")
        self.open_btn.setDefault(True)
        self.open_btn.clicked.connect(self._on_open_file)

        self.folder_btn = QPushButton("Open Folder")
        self.folder_btn.setObjectName("secondaryBtn")
        self.folder_btn.clicked.connect(self._on_open_folder)

        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("secondaryBtn")
        self.close_btn.clicked.connect(self.accept)

        btn_layout.addWidget(self.open_btn)
        btn_layout.addWidget(self.folder_btn)
        btn_layout.addWidget(self.close_btn)

        root_layout.addLayout(btn_layout)

    def _get_file_icon(self) -> QIcon:
        cat = self.category.lower()
        if "video" in cat or self.filename.lower().endswith((".mp4", ".mkv", ".avi", ".mov", ".webm")):
            return create_video_icon()
        elif "music" in cat or self.filename.lower().endswith((".mp3", ".wav", ".flac", ".aac", ".ogg")):
            return create_music_icon()
        elif "doc" in cat or self.filename.lower().endswith((".pdf", ".doc", ".docx", ".txt", ".xlsx")):
            return create_document_icon()
        elif "comp" in cat or self.filename.lower().endswith((".zip", ".rar", ".7z", ".tar", ".gz")):
            return create_compressed_icon()
        elif "prog" in cat or self.filename.lower().endswith((".exe", ".msi", ".apk")):
            return create_programs_icon()
        return create_folder_icon()

    def _on_toggle_dont_show(self, checked: bool):
        # If checked, disable show_complete_dlg ("0"), if unchecked, enable it ("1")
        self.db.set_setting("show_complete_dlg", "0" if checked else "1")

    def _on_open_file(self):
        if self.filepath and os.path.exists(self.filepath):
            try:
                os.startfile(self.filepath)
            except Exception:
                pass
        self.accept()

    def _on_open_folder(self):
        if self.filepath and os.path.exists(self.filepath):
            try:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(self.filepath)])
            except Exception:
                pass
        else:
            folder = os.path.dirname(self.filepath)
            if folder and os.path.exists(folder):
                try:
                    subprocess.Popen(["explorer", os.path.normpath(folder)])
                except Exception:
                    pass
        self.accept()
