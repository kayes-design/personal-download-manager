"""Add URL Download Dialog with clipboard auto-fill and IDM-style file details."""

import os
from typing import Optional, Tuple
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QPixmap
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
    QStyle,
    QToolButton,
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
    create_picture_icon,
    create_programs_icon,
    create_video_icon,
)

# Extension to category mapping
CATEGORY_EXTENSIONS = {
    "Compressed": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"},
    "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".epub"},
    "Music": {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a"},
    "Pictures": {
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".tif",
        ".tiff", ".ico", ".heic", ".avif", ".raw", ".cr2", ".nef",
    },
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
    if "picture" in cat or fn.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".tif", ".tiff", ".ico", ".heic", ".avif")):
        return create_picture_icon()
    if "compressed" in cat or fn.endswith((".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso")):
        return create_compressed_icon()
    if "document" in cat or fn.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".epub")):
        return create_document_icon()
    if "program" in cat or fn.endswith((".exe", ".msi", ".bat", ".cmd", ".ps1", ".dmg", ".apk", ".appimage")):
        return create_programs_icon()
    return create_folder_icon()


DIALOG_STYLESHEET = """
QDialog {
    background-color: #f5f6f7;
    color: #252525;
    font-size: 9pt;
}
QLabel {
    color: #333333;
}
QLabel#fieldLabel {
    color: #333333;
    font-size: 9pt;
}
QLineEdit, QComboBox, QSpinBox {
    background: #ffffff;
    border: 1px solid #c8cdd2;
    border-radius: 4px;
    padding: 5px 8px;
    color: #222222;
    selection-background-color: #1683c4;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #1683c4;
}
QComboBox::drop-down {
    border-left: 1px solid #d5d9dd;
    width: 25px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #222222;
    selection-background-color: #1683c4;
    selection-color: #ffffff;
}
QPushButton, QToolButton {
    min-height: 30px;
    padding: 3px 14px;
    background: #f8f8f8;
    border: 1px solid #c6cbd0;
    border-radius: 4px;
    color: #252525;
}
QPushButton:hover, QToolButton:hover {
    background: #eaf3f9;
    border-color: #5da7d2;
}
QPushButton#startBtn {
    background: #1683c4;
    border-color: #0876b5;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#startBtn:hover {
    background: #0876b5;
}
QPushButton#startBtn:pressed {
    background: #06669e;
}
QPushButton#laterBtn {
    font-weight: 600;
}
QPushButton#cancelBtn {
    color: #b04444;
}
QToolButton#advancedBtn {
    min-height: 22px;
    border: none;
    background: transparent;
    color: #4c6575;
    text-align: left;
    padding-left: 0;
}
QLabel#fileSizeLabel {
    color: #1679b4;
    font-weight: 600;
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
        proxy: str = "",
        cookie_jar: str = "",
        file_size: int = 0
    ):
        super().__init__(parent)
        self.setWindowTitle("Download File Info")
        self.setMinimumWidth(560)
        self.resize(600, 310)
        self.setStyleSheet(DIALOG_STYLESHEET)
        self.setFont(QFont("Arial", 9))

        app = QApplication.instance()
        if app and app.windowIcon():
            self.setWindowIcon(app.windowIcon())

        self.default_save_dir = default_save_dir
        self.db = db
        self.playlist_items = []
        self.playlist_dir = ""
        self.playlist_cat = ""
        self.cookies = cookies
        self.cookie_jar = cookie_jar
        self.file_size = max(0, int(file_size or 0))
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
        root_layout.setContentsMargins(18, 14, 18, 14)
        root_layout.setSpacing(9)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.setColumnMinimumWidth(0, 52)

        def make_label(text: str) -> QLabel:
            label = QLabel(text)
            label.setObjectName("fieldLabel")
            return label

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/file.zip")
        self.url_input.textChanged.connect(self._on_url_changed)
        form.addWidget(make_label("URL:"), 0, 0)
        form.addWidget(self.url_input, 0, 1, 1, 2)

        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText("Auto-detected from URL")
        self.filename_input.textChanged.connect(self._update_file_icon)
        form.addWidget(make_label("Name:"), 1, 0)
        form.addWidget(self.filename_input, 1, 1, 1, 2)

        self.file_size_label = QLabel(
            self._format_file_size(self.file_size) if self.file_size else "Unknown"
        )
        self.file_size_label.setObjectName("fileSizeLabel")
        form.addWidget(make_label("Size:"), 2, 0)
        form.addWidget(self.file_size_label, 2, 1, 1, 2)

        self.category_combo = QComboBox()
        self.category_combo.addItems(
            ["Other", "Video", "Pictures", "Music", "Programs", "Compressed", "Documents"]
        )
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        form.addWidget(make_label("Cat:"), 3, 0)
        form.addWidget(self.category_combo, 3, 1, 1, 2)

        self.save_to_combo = QComboBox()
        self.save_to_combo.setEditable(True)
        self.save_to_combo.setInsertPolicy(QComboBox.NoInsert)
        self.save_to_combo.setMinimumContentsLength(36)
        self._populate_save_directories()
        self.dir_input = self.save_to_combo.lineEdit()
        self.dir_input.setObjectName("saveDirectoryInput")
        self.dir_input.setText(self.default_save_dir)
        self.browse_btn = QToolButton()
        self.browse_btn.setObjectName("browseBtn")
        self.browse_btn.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
        self.browse_btn.setToolTip("Browse for download folder")
        self.browse_btn.clicked.connect(self._on_browse_dir)
        save_to_layout = QHBoxLayout()
        save_to_layout.setContentsMargins(0, 0, 0, 0)
        save_to_layout.setSpacing(6)
        save_to_layout.addWidget(self.save_to_combo, 1)
        save_to_layout.addWidget(self.browse_btn)
        form.addWidget(make_label("Save To:"), 4, 0)
        form.addLayout(save_to_layout, 4, 1, 1, 2)
        root_layout.addLayout(form)

        self.advanced_btn = QToolButton()
        self.advanced_btn.setObjectName("advancedBtn")
        self.advanced_btn.setText("More options")
        self.advanced_btn.setCheckable(True)
        self.advanced_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.advanced_btn.setArrowType(Qt.RightArrow)
        self.advanced_btn.toggled.connect(self._toggle_advanced_options)
        root_layout.addWidget(self.advanced_btn, alignment=Qt.AlignLeft)

        self.advanced_panel = QWidget()
        advanced_layout = QHBoxLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.addWidget(make_label("Connections:"))
        self.connections_spin = QSpinBox()
        self.connections_spin.setRange(1, 32)
        default_conns = int(self.db.get_setting("default_connections", "8")) if self.db else 8
        self.connections_spin.setValue(default_conns)
        advanced_layout.addWidget(self.connections_spin)
        self.remember_folder_cb = QCheckBox("Remember this folder as default for this category")
        advanced_layout.addWidget(self.remember_folder_cb)
        advanced_layout.addStretch()
        self.advanced_panel.setVisible(False)
        root_layout.addWidget(self.advanced_panel)

        self.start_immediately_cb = QCheckBox("Start download immediately")
        self.start_immediately_cb.setChecked(True)
        self.start_immediately_cb.setVisible(False)

        self.playlist_btn = QPushButton("📑 Playlist Detected! Click to inspect & select items")
        self.playlist_btn.setObjectName("startBtn")
        self.playlist_btn.setVisible(False)
        self.playlist_btn.clicked.connect(self._open_playlist_dialog)
        root_layout.addWidget(self.playlist_btn)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #b04444; font-size: 9pt;")
        root_layout.addWidget(self.error_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.later_btn = QPushButton("Download Later")
        self.later_btn.setObjectName("laterBtn")
        self.later_btn.clicked.connect(self._on_download_later)

        self.start_btn = QPushButton("Start Download")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setDefault(True)
        self.start_btn.clicked.connect(self._on_start_download)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.later_btn)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(cancel_btn)
        root_layout.addSpacing(2)
        root_layout.addLayout(btn_layout)

    @staticmethod
    def _format_file_size(size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024

    def _populate_save_directories(self):
        directories = [self.default_save_dir]
        if self.db:
            for key in (
                "default_dir",
                "save_dir_other",
                "save_dir_video",
                "save_dir_pictures",
                "save_dir_music",
                "save_dir_programs",
                "save_dir_compressed",
                "save_dir_documents",
            ):
                value = self.db.get_setting(key, "")
                if value:
                    directories.append(value)
        for directory in dict.fromkeys(os.path.normpath(path) for path in directories if path):
            self.save_to_combo.addItem(directory)

    def _toggle_advanced_options(self, expanded: bool):
        self.advanced_panel.setVisible(expanded)
        self.advanced_btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

    def _update_file_icon(self):
        """Update the selected category icon from the filename and category."""
        cat = self.category_combo.currentText() if hasattr(self, "category_combo") else "Other"
        fn = self.filename_input.text().strip() if hasattr(self, "filename_input") else ""
        icon = get_category_icon(cat, fn)
        if icon and not icon.isNull() and hasattr(self, "category_combo"):
            self.category_combo.setItemIcon(self.category_combo.currentIndex(), icon)

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
            chosen = os.path.abspath(chosen)
            if self.save_to_combo.findText(chosen) < 0:
                self.save_to_combo.addItem(chosen)
            self.dir_input.setText(chosen)

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
