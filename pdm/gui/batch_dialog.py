"""Batch and Pattern URL download dialog."""

import os
from typing import List, Tuple
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from pdm.core.batch import parse_batch_input
from pdm.gui.add_dialog import detect_category


class BatchDownloadDialog(QDialog):
    """Dialog for bulk adding URLs or range pattern links."""

    def __init__(self, default_save_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch & Pattern Download")
        self.resize(580, 420)
        self.default_save_dir = default_save_dir

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        info_label = QLabel(
            "Paste one or more URLs (one per line). Wildcard ranges like [01-20] are supported:\n"
            "e.g. https://example.com/chapter_[01-10].pdf"
        )
        info_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(info_label)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("https://example.com/file1.zip\nhttps://example.com/part_[01-10].rar")
        self.text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.text_edit)

        form = QFormLayout()
        form.setSpacing(10)

        # Save Directory
        dir_layout = QHBoxLayout()
        self.dir_input = QLineEdit(self.default_save_dir)
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self._browse_dir)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(browse_btn)
        form.addRow("Save To:", dir_layout)

        # Connections per download
        self.conns_spin = QSpinBox()
        self.conns_spin.setRange(1, 16)
        self.conns_spin.setValue(4)
        form.addRow("Connections / File:", self.conns_spin)

        layout.addLayout(form)

        # Summary count label
        self.summary_label = QLabel("0 valid URLs detected.")
        self.summary_label.setStyleSheet("font-weight: 500;")
        layout.addWidget(self.summary_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)

        self.add_btn = QPushButton("Add to Queue")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self.accept)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.add_btn)
        layout.addLayout(btn_layout)

    def _browse_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Select Save Directory", self.dir_input.text())
        if chosen:
            self.dir_input.setText(os.path.abspath(chosen))

    def _on_text_changed(self):
        text = self.text_edit.toPlainText()
        valid, invalid = parse_batch_input(text)
        cnt = len(valid)
        self.add_btn.setEnabled(cnt > 0)
        msg = f"{cnt} valid download(s) detected."
        if invalid:
            msg += f" ({len(invalid)} invalid/malformed lines ignored)"
        self.summary_label.setText(msg)

    def get_urls_and_config(self) -> Tuple[List[str], str, int]:
        """Return (valid_urls, save_directory, connections)."""
        valid, _ = parse_batch_input(self.text_edit.toPlainText())
        return valid, self.dir_input.text().strip(), self.conns_spin.value()
