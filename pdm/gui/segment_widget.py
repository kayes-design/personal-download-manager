"""Custom-painted segment visualization widget inspired by IDM dynamic segment view."""

from typing import List, Optional
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from pdm.core.engine import SegmentInfo


class SegmentVisualizerWidget(QWidget):
    """Visualizes multi-connection byte segments in real-time."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.total_bytes: int = 0
        self.segments: List[SegmentInfo] = []
        self.setFixedHeight(36)
        self.setMinimumWidth(300)

    def set_data(self, total_bytes: int, segments: List[SegmentInfo]):
        self.total_bytes = max(0, total_bytes)
        self.segments = segments
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # Background track
        bg_rect = QRectF(0, 0, w, h)
        painter.setBrush(QColor("#1e293b"))
        painter.setPen(QPen(QColor("#334155"), 1))
        painter.drawRoundedRect(bg_rect, 6, 6)

        if self.total_bytes <= 0 or not self.segments:
            painter.setPen(QColor("#64748b"))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(bg_rect, Qt.AlignCenter, "Waiting for stream / Connecting...")
            return

        # Paint each segment
        for seg in self.segments:
            seg_start_ratio = seg.start_byte / self.total_bytes
            seg_end_ratio = (seg.end_byte + 1) / self.total_bytes

            seg_x = seg_start_ratio * w
            seg_w = max(1.0, (seg_end_ratio - seg_start_ratio) * w)

            # Draw segment slot background
            seg_rect = QRectF(seg_x, 2, seg_w, h - 4)
            painter.setBrush(QColor("#0f172a"))
            painter.setPen(Qt.NoPen)
            painter.drawRect(seg_rect)

            # Draw downloaded portion
            if seg.downloaded_bytes > 0:
                dl_ratio = seg.downloaded_bytes / max(1, (seg.end_byte - seg.start_byte + 1))
                dl_w = max(1.0, seg_w * dl_ratio)
                dl_rect = QRectF(seg_x, 2, dl_w, h - 4)
                painter.setBrush(QColor("#3b82f6"))  # Accent blue
                painter.drawRect(dl_rect)

            # Draw separator divider line
            painter.setPen(QPen(QColor("#334155"), 1.5))
            painter.drawLine(int(seg_x), 2, int(seg_x), h - 2)

        # Outer border
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#475569"), 1.5))
        painter.drawRoundedRect(bg_rect, 6, 6)
