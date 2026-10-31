"""File integrity verification dialog (SHA-256 / MD5 / SHA-1)."""

import hashlib
import os
import threading
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


class IntegrityCheckDialog(QDialog):
    """Computes and compares cryptographic hashes of a downloaded file."""

    def __init__(self, filepath: str, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.setWindowTitle("Verify File Integrity")
        self.resize(520, 260)

        self.sha256_hash = ""
        self.md5_hash = ""
        self.is_hashing = False

        self._setup_ui()
        self._start_hash_calculation()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(8)

        fn = os.path.basename(self.filepath)
        form.addRow("File:", QLabel(fn))

        self.sha256_field = QLineEdit()
        self.sha256_field.setReadOnly(True)
        form.addRow("SHA-256:", self.sha256_field)

        self.md5_field = QLineEdit()
        self.md5_field.setReadOnly(True)
        form.addRow("MD5:", self.md5_field)

        self.compare_input = QLineEdit()
        self.compare_input.setPlaceholderText("Paste expected hash to compare...")
        self.compare_input.textChanged.connect(self._compare_hash)
        form.addRow("Compare Hash:", self.compare_input)

        self.match_status_label = QLabel("")
        self.match_status_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        form.addRow("Result:", self.match_status_label)

        layout.addLayout(form)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryBtn")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _start_hash_calculation(self):
        if not os.path.exists(self.filepath):
            self.match_status_label.setText("Error: File not found.")
            return

        self.is_hashing = True
        t = threading.Thread(target=self._compute_hashes, daemon=True)
        t.start()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_hashing_progress)
        self._timer.start(100)

    def _compute_hashes(self):
        sha256 = hashlib.sha256()
        md5 = hashlib.md5()
        total_size = os.path.getsize(self.filepath)
        read_bytes = 0

        with open(self.filepath, "rb") as f:
            while chunk := f.read(1024 * 1024):
                sha256.update(chunk)
                md5.update(chunk)
                read_bytes += len(chunk)
                if total_size > 0:
                    self._progress = int((read_bytes / total_size) * 100)

        self.sha256_hash = sha256.hexdigest().lower()
        self.md5_hash = md5.hexdigest().lower()
        self.is_hashing = False

    def _check_hashing_progress(self):
        if hasattr(self, "_progress"):
            self.progress_bar.setValue(self._progress)

        if not self.is_hashing:
            self._timer.stop()
            self.progress_bar.setValue(100)
            self.sha256_field.setText(self.sha256_hash)
            self.md5_field.setText(self.md5_hash)
            self._compare_hash()

    def _compare_hash(self):
        expected = self.compare_input.text().strip().lower()
        if not expected:
            self.match_status_label.setText("")
            return

        if expected in (self.sha256_hash, self.md5_hash):
            self.match_status_label.setText(" MATCH: Integrity Verified!")
            self.match_status_label.setStyleSheet("color: #22c55e; font-weight: bold;")
        else:
            self.match_status_label.setText(" MISMATCH: Hashes do not match!")
            self.match_status_label.setStyleSheet("color: #ef4444; font-weight: bold;")
