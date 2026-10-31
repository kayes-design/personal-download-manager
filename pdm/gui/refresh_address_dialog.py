"""Dialog to update/refresh the download address for expired or changed URLs."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
    """Refresh download address dialog matching IDM."""

    def __init__(self, task_data: dict, db: DatabaseManager, coordinator, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.db = db
        self.coordinator = coordinator
        self.setWindowTitle(f"Refresh Download Address - {task_data.get('filename', 'File')}")
        self.resize(520, 180)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        info_label = QLabel(
            "If the download link has expired or the server returned 403/410, "
            "paste the new download address below to continue downloading:"
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
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)

        update_btn = QPushButton("Update & Resume")
        update_btn.clicked.connect(self._apply_refresh)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(update_btn)
        layout.addLayout(btn_layout)

    def _apply_refresh(self):
        new_url = self.new_url_edit.text().strip()
        ok, valid_url = validate_url(new_url)
        if not ok:
            QMessageBox.warning(self, "Invalid URL", f"Please enter a valid HTTP/HTTPS URL:\n{valid_url}")
            return

        task_id = self.task_data["id"]
        # Update URL in database
        with self.db._lock, self.db._get_connection() as conn:
            conn.execute(
                """
                UPDATE downloads
                SET url = ?, error_message = NULL, status = 'Queued'
                WHERE id = ?
                """,
                (valid_url, task_id),
            )

        # Stop existing engine if running
        self.coordinator.pause_download(task_id)
        # Resume with new URL
        self.coordinator.start_download(task_id)

        QMessageBox.information(
            self,
            "Address Updated",
            "Download address has been refreshed successfully.\nThe download has resumed with the new URL."
        )
        self.accept()
