"""Dialog to update/refresh the download address for expired or changed URLs."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from pdm.core.security import validate_url
from pdm.storage.db import DatabaseManager


class RefreshAddressDialog(QDialog):
    """Refresh download address dialog matching IDM with auto-clipboard and browser launch."""

    def __init__(self, task_data: dict, db: DatabaseManager, coordinator, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.db = db
        self.coordinator = coordinator
        self.setWindowTitle(f"Refresh Download Address - {task_data.get('filename', 'File')}")
        self.resize(540, 200)

        self._setup_ui()
        self._auto_detect_clipboard()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        info_label = QLabel(
            "If the download link has expired or the server returned HTTP 403/410, "
            "paste the new download address below to continue downloading without losing existing progress:"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        form = QFormLayout()
        form.setSpacing(10)

        # Original URL
        self.old_url_edit = QLineEdit(self.task_data.get("url", ""))
        self.old_url_edit.setReadOnly(True)
        form.addRow("Original Address:", self.old_url_edit)

        # New URL
        self.new_url_edit = QLineEdit()
        self.new_url_edit.setPlaceholderText("Paste new download URL here (http:// or https://)...")
        form.addRow("New Address:", self.new_url_edit)

        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()

        # Browser button to re-visit original page
        open_page_btn = QPushButton("🌐 Open Web Page in Browser")
        open_page_btn.setObjectName("secondaryBtn")
        open_page_btn.setToolTip("Open the source webpage in your browser to generate a fresh download link")
        open_page_btn.clicked.connect(self._open_webpage)
        btn_layout.addWidget(open_page_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        update_btn = QPushButton("Update & Resume")
        update_btn.clicked.connect(self._apply_refresh)
        btn_layout.addWidget(update_btn)

        layout.addLayout(btn_layout)

    def _auto_detect_clipboard(self):
        """Auto-populate new URL if clipboard holds a valid HTTP/HTTPS link different from original."""
        try:
            clip_text = QApplication.clipboard().text().strip()
            old_url = (self.task_data.get("url") or "").strip()
            if clip_text.startswith(("http://", "https://")) and clip_text != old_url:
                ok, _ = validate_url(clip_text)
                if ok:
                    self.new_url_edit.setText(clip_text)
        except Exception:
            pass

    def _open_webpage(self):
        """Open source webpage in browser so user can grab fresh link/cookies."""
        page_url = (self.task_data.get("referer") or self.task_data.get("url") or "").strip()
        if page_url.startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(page_url))
        else:
            QMessageBox.information(
                self,
                "No Webpage Available",
                "No referer webpage URL found for this download."
            )

    def _apply_refresh(self):
        new_url = self.new_url_edit.text().strip()
        ok, valid_url = validate_url(new_url)
        if not ok:
            QMessageBox.warning(self, "Invalid URL", f"Please enter a valid HTTP/HTTPS URL:\n{valid_url}")
            return

        task_id = self.task_data["id"]
        # Update URL in database using clean atomic helper
        self.db.update_download_address(task_id, valid_url)

        # Stop existing engine worker if running
        self.coordinator.pause_download(task_id)
        # Resume with new URL (existing byte segments preserved)
        self.coordinator.start_download(task_id)

        QMessageBox.information(
            self,
            "Address Updated",
            "Download address has been refreshed successfully.\nThe download has resumed from existing byte positions."
        )
        self.accept()
