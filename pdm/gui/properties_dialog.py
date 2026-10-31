"""Download task properties dialog."""

import hashlib
import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QMessageBox,
)


def format_bytes(size: int) -> str:
    """Format bytes to human readable string."""
    if size < 0:
        return "Unknown"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


class PropertiesDialog(QDialog):
    """IDM-style Download Properties dialog."""

    def __init__(self, task_data: dict, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.setWindowTitle(f"Properties - {task_data.get('filename', 'Download')}")
        self.resize(520, 460)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        # File Name
        self.name_edit = QLineEdit(self.task_data.get("filename", ""))
        self.name_edit.setReadOnly(True)
        form.addRow("File Name:", self.name_edit)

        # Category
        cat_label = QLabel(self.task_data.get("category", "General"))
        form.addRow("Category:", cat_label)

        # Status
        status_label = QLabel(self.task_data.get("status", "Unknown"))
        status_label.setStyleSheet("font-weight: bold; color: #3b82f6;")
        form.addRow("Status:", status_label)

        # File Size
        total = self.task_data.get("total_bytes", 0) or 0
        downloaded = self.task_data.get("downloaded_bytes", 0) or 0
        size_str = f"{format_bytes(total)} ({total:,} bytes)" if total > 0 else "Unknown (Server did not specify)"
        form.addRow("File Size:", QLabel(size_str))

        # Downloaded
        pct = (downloaded / total * 100) if total > 0 else 0
        dl_str = f"{format_bytes(downloaded)} ({pct:.1f}%)"
        form.addRow("Downloaded:", QLabel(dl_str))

        # Range / Resume capability
        range_support = self.task_data.get("supports_range", 1)
        range_text = "Yes" if range_support else "No (Server does not support range requests)"
        range_label = QLabel(range_text)
        range_label.setStyleSheet("color: #10b981;" if range_support else "color: #ef4444;")
        form.addRow("Resume Support:", range_label)

        # Connections
        conns = self.task_data.get("connections_count", 4)
        form.addRow("Connections:", QLabel(str(conns)))

        # URL + Copy
        url_layout = QHBoxLayout()
        self.url_edit = QLineEdit(self.task_data.get("url", ""))
        self.url_edit.setReadOnly(True)
        copy_url_btn = QPushButton("Copy")
        copy_url_btn.setObjectName("secondaryBtn")
        copy_url_btn.clicked.connect(self._copy_url)
        url_layout.addWidget(self.url_edit)
        url_layout.addWidget(copy_url_btn)
        form.addRow("Download URL:", url_layout)

        # Save Path + Open Folder
        path_layout = QHBoxLayout()
        dest_path = self.task_data.get("destination_path", "")
        self.path_edit = QLineEdit(dest_path)
        self.path_edit.setReadOnly(True)
        open_folder_btn = QPushButton("Open Folder")
        open_folder_btn.setObjectName("secondaryBtn")
        open_folder_btn.clicked.connect(self._open_folder)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(open_folder_btn)
        form.addRow("Save Location:", path_layout)

        # Date Created
        created_at = self.task_data.get("created_at", "")
        if created_at:
            form.addRow("Date Added:", QLabel(str(created_at)))

        # Checksum / Hash Calculation
        hash_layout = QHBoxLayout()
        self.hash_edit = QLineEdit()
        self.hash_edit.setReadOnly(True)
        self.hash_edit.setPlaceholderText("Click button to calculate file hash")
        calc_sha_btn = QPushButton("SHA-256")
        calc_sha_btn.setObjectName("secondaryBtn")
        calc_sha_btn.clicked.connect(self._calc_sha256)
        calc_md5_btn = QPushButton("MD5")
        calc_md5_btn.setObjectName("secondaryBtn")
        calc_md5_btn.clicked.connect(self._calc_md5)
        hash_layout.addWidget(self.hash_edit)
        hash_layout.addWidget(calc_sha_btn)
        hash_layout.addWidget(calc_md5_btn)
        form.addRow("Checksum:", hash_layout)

        layout.addLayout(form)

        # Close Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _copy_url(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.url_edit.text())
        QMessageBox.information(self, "Copied", "Download URL copied to clipboard.")

    def _open_folder(self):
        import subprocess
        dest_path = self.path_edit.text()
        if os.path.exists(dest_path):
            subprocess.run(["explorer", "/select,", os.path.normpath(dest_path)])
        else:
            folder = os.path.dirname(dest_path)
            if folder and os.path.exists(folder):
                subprocess.run(["explorer", os.path.normpath(folder)])
            else:
                QMessageBox.warning(self, "Folder Not Found", "Destination folder does not exist.")

    def _calc_sha256(self):
        dest_path = self.path_edit.text()
        if not os.path.exists(dest_path):
            QMessageBox.warning(self, "File Not Found", "The downloaded file does not exist on disk.")
            return
        self.hash_edit.setText("Calculating SHA-256...")
        self.repaint()
        h = hashlib.sha256()
        with open(dest_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        self.hash_edit.setText(f"SHA-256: {h.hexdigest()}")

    def _calc_md5(self):
        dest_path = self.path_edit.text()
        if not os.path.exists(dest_path):
            QMessageBox.warning(self, "File Not Found", "The downloaded file does not exist on disk.")
            return
        self.hash_edit.setText("Calculating MD5...")
        self.repaint()
        h = hashlib.md5()
        with open(dest_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        self.hash_edit.setText(f"MD5: {h.hexdigest()}")
