"""Queue Scheduler configuration dialog."""

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
)

from pdm.core.scheduler import QueueScheduler


class SchedulerDialog(QDialog):
    """Configuration dialog for time-based queue scheduling and auto-shutdown."""

    def __init__(self, scheduler: QueueScheduler, parent=None):
        super().__init__(parent)
        self.scheduler = scheduler
        self.setWindowTitle("Queue Scheduler & Auto-Shutdown")
        self.resize(440, 240)

        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.enable_cb = QCheckBox("Enable automated queue scheduling")
        self.enable_cb.toggled.connect(self._toggle_fields)
        layout.addWidget(self.enable_cb)

        form = QFormLayout()
        form.setSpacing(10)

        self.start_time_edit = QTimeEdit()
        self.start_time_edit.setDisplayFormat("HH:mm")
        self.start_time_edit.setTime(QTime(2, 0))  # Default 02:00 AM
        form.addRow("Start queue at:", self.start_time_edit)

        self.stop_time_edit = QTimeEdit()
        self.stop_time_edit.setDisplayFormat("HH:mm")
        self.stop_time_edit.setTime(QTime(6, 0))   # Default 06:00 AM
        form.addRow("Stop queue at:", self.stop_time_edit)

        self.shutdown_cb = QCheckBox("Turn off computer when queue completes")
        form.addRow("", self.shutdown_cb)

        layout.addLayout(form)

        info_lbl = QLabel(
            "Note: If auto-shutdown is enabled, a 60-second warning countdown\n"
            "will be displayed before shutdown, allowing you to cancel."
        )
        info_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(info_lbl)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save Schedule")
        save_btn.clicked.connect(self._save_config)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def _toggle_fields(self, checked: bool):
        self.start_time_edit.setEnabled(checked)
        self.stop_time_edit.setEnabled(checked)
        self.shutdown_cb.setEnabled(checked)

    def _load_config(self):
        db = self.scheduler.db
        enabled = db.get_setting("sched_enabled", "0") == "1"
        self.enable_cb.setChecked(enabled)
        self._toggle_fields(enabled)

        start_str = db.get_setting("sched_start", "02:00")
        stop_str = db.get_setting("sched_stop", "06:00")

        self.start_time_edit.setTime(QTime.fromString(start_str, "HH:mm"))
        self.stop_time_edit.setTime(QTime.fromString(stop_str, "HH:mm"))
        self.shutdown_cb.setChecked(db.get_setting("sched_shutdown", "0") == "1")

    def _save_config(self):
        enabled = self.enable_cb.isChecked()
        start_str = self.start_time_edit.time().toString("HH:mm")
        stop_str = self.stop_time_edit.time().toString("HH:mm")
        shutdown = self.shutdown_cb.isChecked()

        self.scheduler.set_config(
            enabled=enabled,
            start_time=start_str,
            stop_time=stop_str,
            shutdown_when_done=shutdown
        )
        self.accept()
