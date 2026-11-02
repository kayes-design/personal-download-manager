"""Add URL Download Dialog with clipboard auto-fill, category detection and premium modern dark styling."""

import os
from typing import Optional, Tuple
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pdm.core.security import (
    extract_filename_from_url,
    sanitize_filename,
    validate_url,
)
from pdm.gui.icons import (
    create_compressed_icon,
    create_document_icon,
    create_folder_icon,
    create_music_icon,
    create_programs_icon,
    create_video_icon,
)

# Extension to category mapping
CATEGORY_EXTENSIONS = {
    "Compressed": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"},
    "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".epub"},
    "Music": {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a"},
    "Video": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v"},
    "Programs": {".exe", ".msi", ".bat", ".cmd", ".ps1", ".dmg", ".apk", ".appimage"}
}


def detect_category(filename: str) -> str:
    _, ext = os.path.splitext(filename.lower())
    for cat, exts in CATEGORY_EXTENSIONS.items():
        if ext in exts:
            return cat
    return "Other"


def get_category_icon(category: str, filename: str = "") -> QIcon:
    cat = (category or "").lower()
    fn = (filename or "").lower()
    if "video" in cat or fn.endswith((".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v")):
        return create_video_icon()
    if "music" in cat or fn.endswith((".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a")):
        return create_music_icon()
    if "compressed" in cat or fn.endswith((".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso")):
        return create_compressed_icon()
    if "document" in cat or fn.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".epub")):
        return create_document_icon()
    if "program" in cat or fn.endswith((".exe", ".msi", ".bat", ".cmd", ".ps1", ".dmg", ".apk", ".appimage")):
        return create_programs_icon()
    return create_folder_icon()


DIALOG_STYLESHEET = """
QDialog {
    background-color: #0f172a;
    color: #f8fafc;
    font-family: "Segoe UI", -apple-system, sans-serif;
}
#mainCard {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
}
#iconBadgeFrame {
    background-color: #0b1120;
    border: 1px solid #334155;
    border-radius: 8px;
}
QLabel {
    color: #94a3b8;
    font-size: 12px;
}
QLabel#headerTitle {
    color: #f8fafc;
    font-size: 15px;
    font-weight: 700;
}
QLabel#headerSub {
    color: #64748b;
    font-size: 11px;
}
QLabel#fieldLabel {
    color: #cbd5e1;
    font-size: 12px;
    font-weight: 600;
}
QLineEdit {
    background-color: #0b1120;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 7px 10px;
    color: #f8fafc;
    font-size: 12px;
    selection-background-color: #2563eb;
}
QLineEdit:focus {
    border-color: #38bdf8;
    background-color: #030712;
}
QComboBox {
    background-color: #0b1120;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f8fafc;
    font-size: 12px;
    min-width: 130px;
}
QComboBox:focus {
    border-color: #38bdf8;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #1e293b;
    border: 1px solid #334155;
    selection-background-color: #2563eb;
    color: #f8fafc;
    outline: none;
    padding: 4px;
}
QSpinBox {
    background-color: #0b1120;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f8fafc;
    font-size: 12px;
    min-width: 70px;
}
QSpinBox:focus {
    border-color: #38bdf8;
}
QCheckBox {
    color: #94a3b8;
    font-size: 11px;
    spacing: 6px;
}
QCheckBox:hover {
    color: #cbd5e1;
}
QPushButton#browseBtn {
    background-color: #334155;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 7px 14px;
    color: #f8fafc;
    font-weight: 600;
    font-size: 12px;
}
QPushButton#browseBtn:hover {
    background-color: #475569;
    border-color: #64748b;
}
QPushButton#cancelBtn {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 18px;
    color: #94a3b8;
    font-weight: 500;
    font-size: 12px;
}
QPushButton#cancelBtn:hover {
    background-color: #334155;
    color: #f1f5f9;
}
QPushButton#laterBtn {
    background-color: #334155;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 8px 20px;
    color: #f8fafc;
    font-weight: 600;
    font-size: 12px;
}
QPushButton#laterBtn:hover {
    background-color: #475569;
    border-color: #64748b;
}
QPushButton#startBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #0284c7);
    border: 1px solid #38bdf8;
    border-radius: 6px;
    padding: 8px 24px;
    color: #ffffff;
    font-weight: 700;
    font-size: 13px;
}
QPushButton#startBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #0369a1);
}
QPushButton#startBtn:pressed {
    background-color: #1e40af;
}
"""


class AddDownloadDialog(QDialog):
    """Dialog to input and configure a new download with ultra-premium styling."""

    def __init__(
        self,
        default_save_dir: str,
        db=None,
        parent=None,
        prefill_url: str = "",
        prefill_filename: str = "",
        prefill_category: str = "",
        cookies: str = "",
        referer: str = "",
        user_agent: str = "",
        origin: str = "",
        proxy: str = ""
    ):
        super().__init__(parent)
        self.setWindowTitle("Download File Info")
        self.setMinimumWidth(560)
        self.resize(580, 420)
        self.setStyleSheet(DIALOG_STYLESHEET)

        app = QApplication.instance()
        if app and app.windowIcon():
            self.setWindowIcon(app.windowIcon())

        self.default_save_dir = default_save_dir
        self.db = db
        self.playlist_items = []
        self.playlist_dir = ""
        self.playlist_cat = ""
        self.cookies = cookies
        self.referer = referer
        self.user_agent = user_agent
        self.origin = origin
        self.proxy = proxy

        self._setup_ui()
        if prefill_url:
            self.url_input.setText(prefill_url)
            if prefill_filename:
                self.filename_input.setText(prefill_filename)
            if prefill_category:
                idx = self.category_combo.findText(prefill_category)
                if idx >= 0:
                    self.category_combo.setCurrentIndex(idx)
                    self._on_category_changed(prefill_category)
        else:
            self._check_clipboard()

        self._update_file_icon()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 16, 18, 16)
        root_layout.setSpacing(14)

        # 1. Header with dynamic icon badge
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        badge_frame = QFrame()
        badge_frame.setObjectName("iconBadgeFrame")
        badge_frame.setFixedSize(44, 44)
        badge_inner = QVBoxLayout(badge_frame)
        badge_inner.setContentsMargins(0, 0, 0, 0)
        badge_inner.setAlignment(Qt.AlignCenter)

        self.icon_badge_lbl = QLabel()
        self.icon_badge_lbl.setAlignment(Qt.AlignCenter)
        badge_inner.addWidget(self.icon_badge_lbl)
        header_layout.addWidget(badge_frame)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        title_lbl = QLabel("Download File Info")
        title_lbl.setObjectName("headerTitle")
        sub_lbl = QLabel("Configure destination folder and acceleration options")
        sub_lbl.setObjectName("headerSub")
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(sub_lbl)
        header_layout.addLayout(title_vbox)
        header_layout.addStretch()

        root_layout.addLayout(header_layout)

        # 2. Main Card Surface
        card = QFrame()
        card.setObjectName("mainCard")
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        # URL Input
        url_lbl = QLabel("URL:")
        url_lbl.setObjectName("fieldLabel")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/file.zip")
        self.url_input.textChanged.connect(self._on_url_changed)
        grid.addWidget(url_lbl, 0, 0)
        grid.addWidget(self.url_input, 0, 1, 1, 3)

        # Filename Input
        fn_lbl = QLabel("File Name:")
        fn_lbl.setObjectName("fieldLabel")
        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText("Auto-detected from URL")
        self.filename_input.textChanged.connect(self._update_file_icon)
        grid.addWidget(fn_lbl, 1, 0)
        grid.addWidget(self.filename_input, 1, 1, 1, 3)

        # Category and Connections in one row
        cat_lbl = QLabel("Category:")
        cat_lbl.setObjectName("fieldLabel")
        self.category_combo = QComboBox()
        self.category_combo.addItems(["Other", "Video", "Music", "Compressed", "Documents", "Programs"])
        self.category_combo.currentTextChanged.connect(self._on_category_changed)

        conn_lbl = QLabel("Max Connections:")
        conn_lbl.setObjectName("fieldLabel")
        self.connections_spin = QSpinBox()
        self.connections_spin.setRange(1, 32)
        default_conns = int(self.db.get_setting("default_connections", "8")) if self.db else 8
        self.connections_spin.setValue(default_conns)

        grid.addWidget(cat_lbl, 2, 0)
        grid.addWidget(self.category_combo, 2, 1)
        grid.addWidget(conn_lbl, 2, 2)
        grid.addWidget(self.connections_spin, 2, 3)

        # Save Directory
        dir_lbl = QLabel("Save To:")
        dir_lbl.setObjectName("fieldLabel")
        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(8)
        self.dir_input = QLineEdit(self.default_save_dir)
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("browseBtn")
        browse_btn.clicked.connect(self._on_browse_dir)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(browse_btn)

        grid.addWidget(dir_lbl, 3, 0)
        grid.addLayout(dir_layout, 3, 1, 1, 3)

        # Remember folder for this category
        self.remember_folder_cb = QCheckBox("Remember this folder as default for this category")
        grid.addWidget(self.remember_folder_cb, 4, 1, 1, 3)

        root_layout.addWidget(card)

        # Immediate Start Checkbox (hidden, controlled by action buttons)
        self.start_immediately_cb = QCheckBox("Start download immediately")
        self.start_immediately_cb.setChecked(True)
        self.start_immediately_cb.setVisible(False)
        root_layout.addWidget(self.start_immediately_cb)

        # Playlist detection action button
        self.playlist_btn = QPushButton("📑 Playlist Detected! Click to inspect & select items")
        self.playlist_btn.setObjectName("browseBtn")
        self.playlist_btn.setStyleSheet("background-color: #0284c7; color: #ffffff; font-weight: bold; padding: 7px; border-radius: 6px;")
        self.playlist_btn.setVisible(False)
        self.playlist_btn.clicked.connect(self._open_playlist_dialog)
        root_layout.addWidget(self.playlist_btn)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ef4444; font-size: 11px;")
        root_layout.addWidget(self.error_label)

        # Action Buttons (IDM Authentic: Cancel | Download Later | Start Download)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)

        self.later_btn = QPushButton("Download Later")
        self.later_btn.setObjectName("laterBtn")
        self.later_btn.clicked.connect(self._on_download_later)

        self.start_btn = QPushButton("Start Download")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setDefault(True)
        self.start_btn.clicked.connect(self._on_start_download)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.later_btn)
        btn_layout.addWidget(self.start_btn)
        root_layout.addLayout(btn_layout)

    def _update_file_icon(self):
        """Update top-left badge icon based on current category or filename."""
        cat = self.category_combo.currentText() if hasattr(self, "category_combo") else "Other"
        fn = self.filename_input.text().strip() if hasattr(self, "filename_input") else ""
        if not fn and hasattr(self, "url_input"):
            fn = extract_filename_from_url(self.url_input.text().strip())
        ico = get_category_icon(cat, fn)
        self.icon_badge_lbl.setPixmap(ico.pixmap(28, 28))

    def _on_start_download(self):
        self.start_immediately_cb.setChecked(True)
        self._on_submit()

    def _on_download_later(self):
        self.start_immediately_cb.setChecked(False)
        self._on_submit()

    def _check_clipboard(self):
        """Auto-populate URL if clipboard contains a valid URL."""
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            ok, valid_url = validate_url(text)
            if ok:
                self.url_input.setText(valid_url)

    def _on_url_changed(self, text: str):
        text = text.strip()
        ok, _ = validate_url(text)
        if ok:
            from pdm.core.media_downloader import is_playlist_url
            if is_playlist_url(text):
                self.playlist_btn.setVisible(True)
            else:
                self.playlist_btn.setVisible(False)

            fn = extract_filename_from_url(text)
            self.filename_input.setText(fn)
            cat = detect_category(fn)
            idx = self.category_combo.findText(cat)
            if idx >= 0:
                self.category_combo.setCurrentIndex(idx)
            self._on_category_changed(cat)
            self.error_label.setText("")
        else:
            self.playlist_btn.setVisible(False)
            if text:
                self.error_label.setText("Invalid URL (must start with http:// or https://)")
        self._update_file_icon()

    def _open_playlist_dialog(self):
        from pdm.gui.playlist_dialog import PlaylistDialog
        dlg = PlaylistDialog(
            url=self.url_input.text().strip(),
            default_save_dir=self.dir_input.text().strip(),
            db=self.db,
            parent=self
        )
        if dlg.exec():
            self.playlist_items = dlg.get_selected_items()
            self.playlist_dir = dlg.get_save_directory()
            self.playlist_cat = dlg.get_category()
            self.accept()

    def _on_category_changed(self, cat: str):
        self.remember_folder_cb.setText(f"Remember this folder as default for {cat}")
        if self.db:
            cat_dir = self.db.get_setting(
                f"save_dir_{cat.lower()}",
                os.path.join(self.default_save_dir, cat) if cat != "Other" else self.default_save_dir
            )
            self.dir_input.setText(cat_dir)
        elif cat != "Other":
            self.dir_input.setText(os.path.join(self.default_save_dir, cat))
        self._update_file_icon()

    def _on_browse_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Select Download Directory", self.dir_input.text())
        if chosen:
            self.dir_input.setText(os.path.abspath(chosen))

    def _on_submit(self):
        url = self.url_input.text().strip()
        ok, err = validate_url(url)
        if not ok:
            self.error_label.setText(err)
            return

        save_dir = self.dir_input.text().strip()
        if not save_dir:
            self.error_label.setText("Save directory cannot be empty.")
            return

        cat = self.category_combo.currentText()
        if self.remember_folder_cb.isChecked() and self.db:
            self.db.set_setting(f"save_dir_{cat.lower()}", save_dir)

        self.accept()

    def get_data(self) -> Tuple[str, str, str, str, int, bool]:
        """Return (url, save_dir, filename, category, connections, start_immediately)."""
        url = self.url_input.text().strip()
        save_dir = self.dir_input.text().strip()
        fn = self.filename_input.text().strip() or extract_filename_from_url(url)
        clean_fn = sanitize_filename(fn)
        cat = self.category_combo.currentText()
        conns = self.connections_spin.value()
        auto_start = self.start_immediately_cb.isChecked()
        return url, save_dir, clean_fn, cat, conns, auto_start
