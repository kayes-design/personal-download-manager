"""Qt Abstract Table Model for high-performance download list rendering."""

import datetime
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor


def format_bytes(num_bytes: int) -> str:
    """Format byte count into human-readable representation."""
    if num_bytes is None or num_bytes < 0:
        return "Unknown"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def format_speed(bps: float) -> str:
    """Format speed in bytes/sec to KB/s or MB/s."""
    if bps is None or bps <= 0:
        return ""
    if bps < 1024 * 1024:
        return f"{bps / 1024.0:.1f} KB/s"
    return f"{bps / (1024.0 * 1024.0):.2f} MB/s"


def format_eta(seconds: Optional[int]) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if seconds is None or seconds < 0:
        return ""
    if seconds > 86400 * 7:
        return "> 7 days"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class DownloadsTableModel(QAbstractTableModel):
    """Virtual table model for downloads configured with IDM default columns."""

    COLUMNS = [
        "File Name",
        "Q",
        "Size",
        "Status",
        "Time left",
        "Transfer rate",
        "Last Try...",
        "Description",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._downloads: List[Dict[str, Any]] = []
        self._sort_col: int = 0
        self._sort_order: Qt.SortOrder = Qt.AscendingOrder

        from pdm.gui.icons import (
            create_compressed_icon,
            create_document_icon,
            create_music_icon,
            create_programs_icon,
            create_video_icon,
            create_folder_icon,
            create_queue_icon,
        )
        self._icons = {
            "Video": create_video_icon(),
            "Music": create_music_icon(),
            "Compressed": create_compressed_icon(),
            "Documents": create_document_icon(),
            "Programs": create_programs_icon(),
            "Other": create_folder_icon(),
        }
        self._queue_icon = create_queue_icon()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._downloads)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLUMNS[section]
        return None

    def _apply_sort(self, items: List[Dict[str, Any]], column: int, order: Qt.SortOrder) -> List[Dict[str, Any]]:
        sorted_items = list(items)
        reverse = (order == Qt.DescendingOrder)
        if column == 0:  # File Name
            sorted_items.sort(key=lambda x: (x.get("filename") or "").lower(), reverse=reverse)
        elif column == 1:  # Q
            sorted_items.sort(
                key=lambda x: (1 if (x.get("queue_name") or x.get("status") == "Queued") else 0, (x.get("filename") or "").lower()),
                reverse=reverse
            )
        elif column == 2:  # Size
            sorted_items.sort(key=lambda x: x.get("total_bytes") or -1, reverse=reverse)
        elif column == 3:  # Status
            sorted_items.sort(key=lambda x: (x.get("status") or "").lower(), reverse=reverse)
        elif column == 4:  # Time left
            sorted_items.sort(
                key=lambda x: x.get("eta_seconds") if (x.get("eta_seconds") is not None and x.get("status") == "Downloading") else (999999999 if not reverse else -1),
                reverse=reverse
            )
        elif column == 5:  # Transfer rate
            sorted_items.sort(key=lambda x: x.get("current_speed") or 0.0, reverse=reverse)
        elif column == 6:  # Last Try...
            sorted_items.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=reverse)
        elif column == 7:  # Description
            sorted_items.sort(key=lambda x: (x.get("description") or x.get("url") or "").lower(), reverse=reverse)
        return sorted_items

    def set_data(self, downloads: List[Dict[str, Any]]):
        downloads_list = list(downloads)
        if self._sort_col != -1:
            downloads_list = self._apply_sort(downloads_list, self._sort_col, self._sort_order)

        current_ids = [d.get("id") for d in self._downloads]
        new_ids = [d.get("id") for d in downloads_list]

        if current_ids == new_ids and len(downloads_list) > 0:
            # Same rows! In-place update without resetting model -> PRESERVES SELECTION
            self._downloads = downloads_list
            top_left = self.index(0, 0)
            bottom_right = self.index(len(downloads_list) - 1, len(self.COLUMNS) - 1)
            self.dataChanged.emit(top_left, bottom_right)
            return

        # Rows added, removed, or structure changed
        self.beginResetModel()
        self._downloads = downloads_list
        self.endResetModel()

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder):
        self._sort_col = column
        self._sort_order = order
        self.layoutAboutToBeChanged.emit()
        self._downloads = self._apply_sort(self._downloads, column, order)
        self.layoutChanged.emit()

    def get_download_at(self, row: int) -> Optional[Dict[str, Any]]:
        if 0 <= row < len(self._downloads):
            return self._downloads[row]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._downloads)):
            return None

        item = self._downloads[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:  # File Name
                return item.get("filename", "")
            elif col == 1:  # Q
                q_name = item.get("queue_name")
                status = item.get("status")
                if q_name:
                    return q_name
                elif status == "Queued":
                    return "Q"
                return ""
            elif col == 2:  # Size
                return format_bytes(item.get("total_bytes", -1))
            elif col == 3:  # Status
                status = item.get("status", "")
                total = item.get("total_bytes", -1)
                dl = item.get("downloaded_bytes", 0)
                if status == "Downloading":
                    if total > 0:
                        pct = min(100.0, (dl / total) * 100.0)
                        return f"Downloading ({pct:.1f}%)"
                    return "Downloading"
                elif status == "Completed":
                    return "Complete"
                elif status == "Paused":
                    if total > 0 and dl > 0:
                        pct = min(100.0, (dl / total) * 100.0)
                        return f"Paused ({pct:.1f}%)"
                    return "Paused"
                elif status == "Queued":
                    return "Queued"
                elif status == "Error":
                    return item.get("error_message") or "Error"
                return status
            elif col == 4:  # Time left
                status = item.get("status", "")
                if status == "Downloading":
                    eta = format_eta(item.get("eta_seconds"))
                    return eta if eta else "--"
                return ""
            elif col == 5:  # Transfer rate
                status = item.get("status", "")
                if status == "Downloading":
                    spd = format_speed(item.get("current_speed", 0.0))
                    return spd if spd else "--"
                return ""
            elif col == 6:  # Last Try...
                dt = item.get("updated_at") or item.get("created_at") or ""
                return str(dt)[:19] if dt else ""
            elif col == 7:  # Description
                return item.get("description") or item.get("url") or ""

        elif role == Qt.DecorationRole:
            if col == 0:
                cat = item.get("category") or "Other"
                return self._icons.get(cat, self._icons["Other"])
            elif col == 1:
                if item.get("queue_name") or item.get("status") == "Queued":
                    return self._queue_icon

        elif role == Qt.TextAlignmentRole:
            if col == 1:
                return int(Qt.AlignCenter)
            elif col in (2, 4, 5):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        elif role == Qt.ForegroundRole:
            status = item.get("status", "")
            if col == 3:  # Status
                if status == "Completed":
                    return QColor("#22c55e")  # Green
                elif status == "Downloading":
                    return QColor("#3b82f6")  # Blue
                elif status == "Error":
                    return QColor("#ef4444")  # Red
                elif status == "Paused":
                    return QColor("#f59e0b")  # Amber
                elif status == "Queued":
                    return QColor("#a855f7")  # Purple
            elif col == 1 and (item.get("queue_name") or status == "Queued"):
                return QColor("#f59e0b")  # Amber

        return None
