"""Dialogs for moving and renaming downloaded or queued files."""

import os
import shutil
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from pdm.core.security import sanitize_filename
from pdm.storage.db import DatabaseManager


class RenameDialog(QDialog):
    """Dialog exclusively for renaming a file (F2 / Rename)."""

    def __init__(self, task_data: dict, db: DatabaseManager, coordinator=None, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.db = db
        self.coordinator = coordinator
        self.current_filename = task_data.get("filename", "")
        self.current_path = task_data.get("destination_path", "")
        self.current_dir = os.path.dirname(self.current_path)

        self.setWindowTitle(f"Rename - {self.current_filename}")
        self.resize(460, 140)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.name_edit = QLineEdit(self.current_filename)
        stem, _ = os.path.splitext(self.current_filename)
        self.name_edit.setSelection(0, len(stem))
        form.addRow("New File Name:", self.name_edit)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QPushButton("Rename")
        ok_btn.clicked.connect(self._apply_rename)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def _apply_rename(self):
        new_name = sanitize_filename(self.name_edit.text().strip())
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "Please provide a valid file name.")
            return

        if new_name == self.current_filename:
            self.accept()
            return

        new_filepath = os.path.join(self.current_dir, new_name)
        old_filepath = self.current_path
        task_id = self.task_data["id"]

        was_downloading = (self.task_data.get("status") == "Downloading")
        if was_downloading and self.coordinator:
            self.coordinator.pause_download(task_id)

        if os.path.exists(old_filepath):
            try:
                if os.path.exists(new_filepath):
                    QMessageBox.warning(self, "File Exists", f"A file already exists with this name:\n{new_filepath}")
                    return
                shutil.move(old_filepath, new_filepath)
            except Exception as e:
                QMessageBox.critical(self, "Rename Failed", f"Could not rename file:\n{e}")
                return

        for i in range(32):
            old_part = f"{old_filepath}.pdmpart{i}"
            new_part = f"{new_filepath}.pdmpart{i}"
            if os.path.exists(old_part):
                try:
                    shutil.move(old_part, new_part)
                except Exception:
                    pass

        with self.db._lock, self.db._get_connection() as conn:
            cur = conn.execute("SELECT id, temp_filepath FROM segments WHERE download_id = ?", (task_id,))
            for seg_id, t_path in cur.fetchall():
                if t_path and old_filepath in t_path:
                    updated_t_path = t_path.replace(old_filepath, new_filepath)
                    conn.execute("UPDATE segments SET temp_filepath = ? WHERE id = ?", (updated_t_path, seg_id))

            conn.execute(
                """
                UPDATE downloads
                SET filename = ?, destination_path = ?
                WHERE id = ?
                """,
                (new_name, new_filepath, task_id),
            )

        if was_downloading and self.coordinator:
            self.coordinator.start_download(task_id)

        self.accept()


class MoveToDialog(QDialog):
    """Dialog exclusively for moving a file to a new folder (Move to...)."""

    def __init__(self, task_data: dict, db: DatabaseManager, coordinator=None, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.db = db
        self.coordinator = coordinator
        self.current_filename = task_data.get("filename", "")
        self.current_path = task_data.get("destination_path", "")
        self.current_dir = os.path.dirname(self.current_path)

        self.setWindowTitle(f"Move to Folder - {self.current_filename}")
        self.resize(520, 180)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        file_label = QLabel(self.current_filename)
        file_label.setStyleSheet("font-weight: bold;")
        form.addRow("File:", file_label)

        cur_dir_label = QLabel(self.current_dir)
        form.addRow("Current Folder:", cur_dir_label)

        folder_layout = QHBoxLayout()
        self.folder_edit = QLineEdit(self.current_dir)
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(browse_btn)
        form.addRow("Move to Folder:", folder_layout)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QPushButton("Move")
        ok_btn.clicked.connect(self._apply_move)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder", self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)

    def _apply_move(self):
        new_dir = os.path.abspath(self.folder_edit.text().strip())
        if not os.path.isdir(new_dir):
            try:
                os.makedirs(new_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not create folder:\n{e}")
                return

        if os.path.normpath(new_dir) == os.path.normpath(self.current_dir):
            self.accept()
            return

        new_filepath = os.path.join(new_dir, self.current_filename)
        old_filepath = self.current_path
        task_id = self.task_data["id"]

        was_downloading = (self.task_data.get("status") == "Downloading")
        if was_downloading and self.coordinator:
            self.coordinator.pause_download(task_id)

        if os.path.exists(old_filepath):
            try:
                if os.path.exists(new_filepath):
                    QMessageBox.warning(self, "File Exists", f"A file already exists at target location:\n{new_filepath}")
                    return
                shutil.move(old_filepath, new_filepath)
            except Exception as e:
                QMessageBox.critical(self, "Move Failed", f"Could not move file:\n{e}")
                return

        for i in range(32):
            old_part = f"{old_filepath}.pdmpart{i}"
            new_part = f"{new_filepath}.pdmpart{i}"
            if os.path.exists(old_part):
                try:
                    shutil.move(old_part, new_part)
                except Exception:
                    pass

        with self.db._lock, self.db._get_connection() as conn:
            cur = conn.execute("SELECT id, temp_filepath FROM segments WHERE download_id = ?", (task_id,))
            for seg_id, t_path in cur.fetchall():
                if t_path and old_filepath in t_path:
                    updated_t_path = t_path.replace(old_filepath, new_filepath)
                    conn.execute("UPDATE segments SET temp_filepath = ? WHERE id = ?", (updated_t_path, seg_id))

            conn.execute(
                """
                UPDATE downloads
                SET destination_path = ?
                WHERE id = ?
                """,
                (new_filepath, task_id),
            )

        if was_downloading and self.coordinator:
            self.coordinator.start_download(task_id)

        self.accept()


class MoveRenameDialog(QDialog):
    """Combined Move / Rename dialog for compatibility."""

    def __init__(self, task_data: dict, db: DatabaseManager, coordinator=None, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.db = db
        self.coordinator = coordinator
        self.setWindowTitle(f"Move/Rename - {task_data.get('filename', 'File')}")
        self.resize(500, 200)

        self.current_filename = task_data.get("filename", "")
        self.current_path = task_data.get("destination_path", "")
        self.current_dir = os.path.dirname(self.current_path)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.name_edit = QLineEdit(self.current_filename)
        form.addRow("New File Name:", self.name_edit)

        folder_layout = QHBoxLayout()
        self.folder_edit = QLineEdit(self.current_dir)
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(browse_btn)
        form.addRow("New Destination Folder:", folder_layout)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._apply_move_rename)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder", self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)

    def _apply_move_rename(self):
        new_name = sanitize_filename(self.name_edit.text().strip())
        new_dir = os.path.abspath(self.folder_edit.text().strip())

        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "Please provide a valid file name.")
            return

        if not os.path.isdir(new_dir):
            try:
                os.makedirs(new_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not create folder:\n{e}")
                return

        new_filepath = os.path.join(new_dir, new_name)
        old_filepath = self.current_path
        task_id = self.task_data["id"]

        if os.path.normpath(old_filepath) == os.path.normpath(new_filepath):
            self.accept()
            return

        was_downloading = (self.task_data.get("status") == "Downloading")
        if was_downloading and self.coordinator:
            self.coordinator.pause_download(task_id)

        if os.path.exists(old_filepath):
            try:
                if os.path.exists(new_filepath):
                    QMessageBox.warning(self, "File Exists", f"A file already exists at:\n{new_filepath}")
                    return
                shutil.move(old_filepath, new_filepath)
            except Exception as e:
                QMessageBox.critical(self, "Move Failed", f"Could not move/rename file on disk:\n{e}")
                return

        for i in range(32):
            old_part = f"{old_filepath}.pdmpart{i}"
            new_part = f"{new_filepath}.pdmpart{i}"
            if os.path.exists(old_part):
                try:
                    shutil.move(old_part, new_part)
                except Exception:
                    pass

        with self.db._lock, self.db._get_connection() as conn:
            cur = conn.execute("SELECT id, temp_filepath FROM segments WHERE download_id = ?", (task_id,))
            for seg_id, t_path in cur.fetchall():
                if t_path and old_filepath in t_path:
                    updated_t_path = t_path.replace(old_filepath, new_filepath)
                    conn.execute("UPDATE segments SET temp_filepath = ? WHERE id = ?", (updated_t_path, seg_id))

            conn.execute(
                """
                UPDATE downloads
                SET filename = ?, destination_path = ?
                WHERE id = ?
                """,
                (new_name, new_filepath, task_id),
            )

        if was_downloading and self.coordinator:
            self.coordinator.start_download(task_id)

        self.accept()
