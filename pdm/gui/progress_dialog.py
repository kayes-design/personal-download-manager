"""Active download details and segment visualization dialog."""

from typing import Optional
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from pdm.core.coordinator import DownloadCoordinator
from pdm.core.engine import DownloadStatus, DownloadTask
from pdm.gui.models import format_bytes, format_eta, format_speed
from pdm.gui.segment_widget import SegmentVisualizerWidget


PROGRESS_STYLESHEET = """
QDialog {
    background-color: #0f172a;
    color: #f8fafc;
    font-family: "Segoe UI", -apple-system, sans-serif;
}
#progressCard {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
}
QLabel {
    color: #94a3b8;
    font-size: 12px;
}
QLabel#fieldVal {
    color: #f8fafc;
    font-size: 12px;
    font-weight: 500;
}
QLabel#fieldTitle {
    color: #94a3b8;
    font-size: 12px;
    font-weight: 600;
}
QProgressBar {
    background-color: #0b1120;
    border: 1px solid #334155;
    border-radius: 6px;
    text-align: center;
    color: #f8fafc;
    font-weight: bold;
    font-size: 11px;
    height: 18px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #06b6d4);
    border-radius: 5px;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #1d4ed8);
    color: #ffffff;
    border: none;
    border-radius: 6px;
    font-weight: 600;
    font-size: 12px;
    padding: 7px 18px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb);
}
QPushButton:pressed {
    background-color: #1d4ed8;
}
QPushButton#secondaryBtn {
    background-color: #1e293b;
    border: 1px solid #334155;
    color: #cbd5e1;
    font-weight: 500;
}
QPushButton#secondaryBtn:hover {
    background-color: #334155;
    border-color: #475569;
    color: #ffffff;
}
QPushButton#secondaryBtn:pressed {
    background-color: #0f172a;
}
"""


class DownloadProgressDialog(QDialog):
    """Detailed progress dialog with real-time segment visualization."""

    def __init__(self, task_id: int, coordinator: DownloadCoordinator, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.coordinator = coordinator

        self.setWindowTitle("Download Progress")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)
        self.setFixedSize(560, 360)
        self.setStyleSheet(PROGRESS_STYLESHEET)

        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and app.windowIcon():
            self.setWindowIcon(app.windowIcon())

        self._setup_ui()

        # Update timer (100ms interval for smooth 10fps animation)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_ui)
        self._timer.start(100)

        self._refresh_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName("progressCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)

        form = QFormLayout()
        form.setSpacing(8)

        def make_row_title(txt: str) -> QLabel:
            lbl = QLabel(txt)
            lbl.setObjectName("fieldTitle")
            return lbl

        self.filename_label = QLabel("Loading...")
        self.filename_label.setObjectName("fieldVal")
        self.filename_label.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
        form.addRow(make_row_title("File:"), self.filename_label)

        self.status_label = QLabel("Queued")
        self.status_label.setObjectName("fieldVal")
        form.addRow(make_row_title("Status:"), self.status_label)

        self.size_label = QLabel("0 B / 0 B")
        self.size_label.setObjectName("fieldVal")
        form.addRow(make_row_title("File Size:"), self.size_label)

        self.quality_label = QLabel("Auto (Highest Available)")
        self.quality_label.setStyleSheet("color: #06b6d4; font-weight: 600;")
        form.addRow(make_row_title("Resolution / Quality:"), self.quality_label)

        self.speed_label = QLabel("0 KB/s")
        self.speed_label.setObjectName("fieldVal")
        form.addRow(make_row_title("Transfer Rate:"), self.speed_label)

        self.eta_label = QLabel("--")
        self.eta_label.setObjectName("fieldVal")
        form.addRow(make_row_title("Time Left:"), self.eta_label)

        self.resume_label = QLabel("Unknown")
        self.resume_label.setObjectName("fieldVal")
        form.addRow(make_row_title("Resume Support:"), self.resume_label)

        card_layout.addLayout(form)
        layout.addWidget(card)

        # Overall progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Dynamic Segment Visualizer
        seg_label = QLabel("Connection Segments:")
        seg_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(seg_label)

        self.segment_widget = SegmentVisualizerWidget()
        layout.addWidget(self.segment_widget)

        # Action Buttons
        btn_layout = QHBoxLayout()

        self.refresh_addr_btn = QPushButton("🔄 Refresh Address")
        self.refresh_addr_btn.setToolTip("Update expired link and resume downloading without losing progress")
        self.refresh_addr_btn.setVisible(False)
        self.refresh_addr_btn.clicked.connect(self._open_refresh_dialog)
        btn_layout.addWidget(self.refresh_addr_btn)

        btn_layout.addStretch()

        self.pause_resume_btn = QPushButton("Pause")
        self.pause_resume_btn.clicked.connect(self._toggle_pause_resume)
        btn_layout.addWidget(self.pause_resume_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryBtn")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _refresh_ui(self):
        task = self.coordinator.get_active_task(self.task_id)
        if task:
            self.filename_label.setText(task.filename)
            self.status_label.setText(task.status.value)
            self.resume_label.setText("Yes" if task.supports_range else "No")

            dl_str = format_bytes(task.downloaded_bytes)
            tot_str = format_bytes(task.total_bytes) if task.total_bytes > 0 else "Unknown"
            self.size_label.setText(f"{dl_str} of {tot_str}")

            res = getattr(task, "resolution", None)
            if not res:
                u = (task.url or "").lower()
                fn = (task.filename or "").lower()
                combined = f"{u} {fn}"
                if "2160" in combined or "4k" in combined:
                    res = "4K Ultra HD (2160p)"
                elif "1440" in combined or "2k" in combined:
                    res = "1440p 2K QHD"
                elif "1080" in combined:
                    res = "1080p Full HD"
                elif "720" in combined:
                    res = "720p HD"
                elif "480" in combined:
                    res = "480p SD"
                elif "360" in combined:
                    res = "360p"
                elif task.category == "Video":
                    res = "Auto (Highest Available)"
            if res:
                self.quality_label.setText(res)

            self.speed_label.setText(format_speed(task.current_speed))
            self.eta_label.setText(format_eta(task.eta_seconds))

            if task.total_bytes > 0:
                pct = int((task.downloaded_bytes / task.total_bytes) * 100)
                self.progress_bar.setValue(min(100, max(0, pct)))
                self.setWindowTitle(f"{pct}% - {task.filename}")
            else:
                self.progress_bar.setValue(0)
                self.setWindowTitle(f"{task.filename}")

            # Update segment widget
            self.segment_widget.set_data(task.total_bytes, task.segments)

            if task.status == DownloadStatus.DOWNLOADING:
                self.pause_resume_btn.setText("Pause")
                self.pause_resume_btn.setEnabled(True)
                self.refresh_addr_btn.setVisible(False)
            elif task.status == DownloadStatus.PAUSED:
                self.pause_resume_btn.setText("Resume")
                self.pause_resume_btn.setEnabled(True)
                self.refresh_addr_btn.setVisible(False)
            elif task.status == DownloadStatus.ERROR:
                self.pause_resume_btn.setText("Resume")
                self.pause_resume_btn.setEnabled(True)
                self.refresh_addr_btn.setVisible(True)
                if task.error_message:
                    self.status_label.setText(f"Error: {task.error_message[:45]}..." if len(task.error_message) > 45 else f"Error: {task.error_message}")
                    self.status_label.setStyleSheet("color: #ef4444; font-weight: bold;")
            elif task.status == DownloadStatus.COMPLETED:
                self.pause_resume_btn.setEnabled(False)
                self.pause_resume_btn.setText("Completed")
                self.refresh_addr_btn.setVisible(False)
                if self.coordinator.db.get_setting("auto_close_progress", "1") == "1":
                    self.close()
        else:
            # Task not active in memory, query DB
            record = self.coordinator.db.get_download(self.task_id)
            if record:
                self.filename_label.setText(record["filename"])
                self.status_label.setText(record["status"])
                dl_str = format_bytes(record["downloaded_bytes"])
                tot_str = format_bytes(record["total_bytes"])
                self.size_label.setText(f"{dl_str} of {tot_str}")
                self.speed_label.setText("")
                self.eta_label.setText("")
                if record["total_bytes"] > 0:
                    pct = int((record["downloaded_bytes"] / record["total_bytes"]) * 100)
                    self.progress_bar.setValue(min(100, max(0, pct)))

                if record["status"] == "Paused":
                    self.pause_resume_btn.setText("Resume")
                    self.pause_resume_btn.setEnabled(True)
                    self.refresh_addr_btn.setVisible(False)
                elif record["status"] == "Error":
                    self.pause_resume_btn.setText("Resume")
                    self.pause_resume_btn.setEnabled(True)
                    self.refresh_addr_btn.setVisible(True)
                    err_msg = record.get("error_message") or ""
                    if err_msg:
                        self.status_label.setText(f"Error: {err_msg[:45]}..." if len(err_msg) > 45 else f"Error: {err_msg}")
                        self.status_label.setStyleSheet("color: #ef4444; font-weight: bold;")
                elif record["status"] == "Completed":
                    self.pause_resume_btn.setText("Completed")
                    self.pause_resume_btn.setEnabled(False)
                    self.refresh_addr_btn.setVisible(False)

    def _open_refresh_dialog(self):
        """Open dialog to refresh expired or broken download link without losing progress."""
        record = self.coordinator.db.get_download(self.task_id)
        if record:
            from pdm.gui.refresh_address_dialog import RefreshAddressDialog
            dlg = RefreshAddressDialog(record, self.coordinator.db, self.coordinator, self)
            dlg.exec()

    def _toggle_pause_resume(self):
        task = self.coordinator.get_active_task(self.task_id)
        if task and task.status == DownloadStatus.DOWNLOADING:
            self.coordinator.pause_download(self.task_id)
        else:
            self.coordinator.start_download(self.task_id)

    def _on_cancel(self):
        self.coordinator.cancel_download(self.task_id, delete_files=False)
        self.close()

    def closeEvent(self, event):
        self._timer.stop()
        event.accept()
