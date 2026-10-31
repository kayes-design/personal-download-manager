"""Add URL Download Dialog with clipboard auto-fill and category detection."""

import os
from typing import Optional, Tuple
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from pdm.core.security import (
    extract_filename_from_url,
    sanitize_filename,
    validate_url,
)

# Extension to category mapping
CATEGORY_EXTENSIONS = {
    "Compressed": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"},
    "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".epub"},
    "Music": {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a"},
    "Video": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv"},
    "Programs": {".exe", ".msi", ".bat", ".cmd", ".ps1", ".dmg", ".apk", ".appimage"}
}


def detect_category(filename: str) -> str:
    _, ext = os.path.splitext(filename.lower())
    for cat, exts in CATEGORY_EXTENSIONS.items():
        if ext in exts:
            return cat
    return "Other"


class AddDownloadDialog(QDialog):
    """Dialog to input and configure a new download."""

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
        self.resize(540, 310)
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

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        # URL Input
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/file.zip")
        self.url_input.textChanged.connect(self._on_url_changed)
        form_layout.addRow("URL:", self.url_input)

        # Filename Input
        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText("Auto-detected from URL")
        form_layout.addRow("File Name:", self.filename_input)

        # Category
        self.category_combo = QComboBox()
        self.category_combo.addItems(["Other", "Video", "Music", "Compressed", "Documents", "Programs"])
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        form_layout.addRow("Category:", self.category_combo)

        # Save Directory
        dir_layout = QHBoxLayout()
        self.dir_input = QLineEdit(self.default_save_dir)
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self._on_browse_dir)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(browse_btn)
        form_layout.addRow("Save To:", dir_layout)

        # Remember folder for this category
        self.remember_folder_cb = QCheckBox("Remember this folder as default for this category")
        self.remember_folder_cb.setStyleSheet("color: #94a3b8; font-size: 11px;")
        form_layout.addRow("", self.remember_folder_cb)

        # Connections
        self.connections_spin = QSpinBox()
        self.connections_spin.setRange(1, 16)
        self.connections_spin.setValue(4)
        form_layout.addRow("Max Connections:", self.connections_spin)

        # Immediate Start Checkbox (hidden, controlled by action buttons)
        self.start_immediately_cb = QCheckBox("Start download immediately")
        self.start_immediately_cb.setChecked(True)
        self.start_immediately_cb.setVisible(False)

        layout.addLayout(form_layout)

        # Playlist detection action button
        self.playlist_btn = QPushButton("📑 Playlist Detected! Click to inspect & select items")
        self.playlist_btn.setObjectName("secondaryBtn")
        self.playlist_btn.setStyleSheet("background-color: #0369a1; color: #ffffff; font-weight: bold; padding: 6px; border-radius: 6px;")
        self.playlist_btn.setVisible(False)
        self.playlist_btn.clicked.connect(self._open_playlist_dialog)
        layout.addWidget(self.playlist_btn)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ef4444; font-size: 11px;")
        layout.addWidget(self.error_label)

        # Action Buttons (IDM Authentic: Cancel | Download Later | Start Download)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)

        self.later_btn = QPushButton("Download Later")
        self.later_btn.setObjectName("secondaryBtn")
        self.later_btn.clicked.connect(self._on_download_later)

        self.start_btn = QPushButton("Start Download")
        self.start_btn.clicked.connect(self._on_start_download)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.later_btn)
        btn_layout.addWidget(self.start_btn)
        layout.addLayout(btn_layout)

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
