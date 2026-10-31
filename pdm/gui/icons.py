"""Dynamic icon generation for PDM categories and tree structure (IDM-style)."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygon


def create_folder_icon(badge: str = None) -> QIcon:
    """Generate golden folder icon, optionally badged with green arrow or blue check."""
    pix = QPixmap(20, 20)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    # Folder back
    p.setBrush(QColor("#eab308"))
    p.setPen(QColor("#ca8a04"))
    p.drawRoundedRect(2, 4, 16, 13, 2, 2)
    # Folder tab
    p.drawRoundedRect(2, 2, 7, 5, 1, 1)
    # Folder front
    p.setBrush(QColor("#facc15"))
    p.drawRoundedRect(2, 6, 16, 11, 2, 2)

    if badge == "down":
        # Green downward arrow for 'Unfinished'
        p.setBrush(QColor("#16a34a"))
        p.setPen(QColor("#15803d"))
        poly = QPolygon([
            QPoint(13, 7), QPoint(15, 7), QPoint(15, 11),
            QPoint(18, 11), QPoint(14, 17), QPoint(10, 11),
            QPoint(13, 11)
        ])
        p.drawPolygon(poly)
    elif badge == "check":
        # Blue checkmark for 'Finished'
        p.setPen(QPen(QColor("#2563eb"), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(10, 13, 13, 16)
        p.drawLine(13, 16, 18, 9)

    p.end()
    return QIcon(pix)


def create_compressed_icon() -> QIcon:
    """Zipper archive icon."""
    pix = QPixmap(20, 20)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#fef08a"))
    p.setPen(QColor("#ca8a04"))
    p.drawRoundedRect(3, 2, 14, 16, 2, 2)
    p.setPen(QPen(QColor("#854d0e"), 1.5))
    for y in range(4, 16, 3):
        p.drawLine(9, y, 11, y + 1)
    p.end()
    return QIcon(pix)


def create_document_icon() -> QIcon:
    """Document sheet icon."""
    pix = QPixmap(20, 20)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#f8fafc"))
    p.setPen(QColor("#94a3b8"))
    path = QPainterPath()
    path.moveTo(4, 2)
    path.lineTo(12, 2)
    path.lineTo(16, 6)
    path.lineTo(16, 18)
    path.lineTo(4, 18)
    path.closeSubpath()
    p.drawPath(path)
    p.setPen(QColor("#cbd5e1"))
    p.drawLine(7, 8, 13, 8)
    p.drawLine(7, 11, 13, 11)
    p.drawLine(7, 14, 11, 14)
    p.end()
    return QIcon(pix)


def create_music_icon() -> QIcon:
    """Music eighth-notes icon in vibrant rose/magenta for optimal contrast on blue selection."""
    pix = QPixmap(20, 20)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#f43f5e"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(3, 12, 5, 4)
    p.drawEllipse(11, 10, 5, 4)
    p.setPen(QPen(QColor("#f43f5e"), 2, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(7, 14, 7, 5)
    p.drawLine(15, 12, 15, 3)
    p.drawLine(7, 5, 15, 3)
    p.end()
    return QIcon(pix)


def create_programs_icon() -> QIcon:
    """Software window icon."""
    pix = QPixmap(20, 20)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#ffffff"))
    p.setPen(QColor("#475569"))
    p.drawRoundedRect(2, 3, 16, 14, 2, 2)
    p.setBrush(QColor("#6366f1"))
    p.drawRoundedRect(2, 3, 16, 4, 1, 1)
    p.end()
    return QIcon(pix)


def create_video_icon() -> QIcon:
    """Film strip icon."""
    pix = QPixmap(20, 20)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#06b6d4"))
    p.setPen(QColor("#0891b2"))
    p.drawRoundedRect(2, 3, 16, 14, 2, 2)
    p.setBrush(QColor("#ffffff"))
    p.setPen(Qt.NoPen)
    for y in (5, 9, 13):
        p.drawRect(4, y, 2, 2)
        p.drawRect(14, y, 2, 2)
    p.end()
    return QIcon(pix)


def create_idm_sort_arrow(direction: str = "down") -> QPixmap:
    """Generate IDM's signature green curved sort arrow (as in IDM table header)."""
    pix = QPixmap(13, 13)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    green = QColor("#16a34a")
    light_green = QColor("#4ade80")
    dark_green = QColor("#15803d")

    if direction == "down":
        # Draw curved arc sweeping down
        path = QPainterPath()
        path.moveTo(11, 2)
        path.cubicTo(11, 5, 8, 7, 4, 7)
        p.setPen(QPen(green, 2.4, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)

        # Subtle highlight on top edge
        p.setPen(QPen(light_green, 1.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(8, 3, 11, 2)

        # Arrowhead pointing downwards
        arrow = QPolygon([QPoint(1, 5), QPoint(7, 5), QPoint(4, 11)])
        p.setBrush(green)
        p.setPen(QPen(dark_green, 0.6))
        p.drawPolygon(arrow)
    else:
        # Draw curved arc sweeping up
        path = QPainterPath()
        path.moveTo(11, 10)
        path.cubicTo(11, 7, 8, 5, 4, 5)
        p.setPen(QPen(green, 2.4, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)

        # Subtle highlight on bottom edge
        p.setPen(QPen(light_green, 1.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(8, 9, 11, 10)

        # Arrowhead pointing upwards
        arrow = QPolygon([QPoint(1, 7), QPoint(7, 7), QPoint(4, 1)])
        p.setBrush(green)
        p.setPen(QPen(dark_green, 0.6))
        p.drawPolygon(arrow)

    p.end()
    return pix


def create_queue_icon() -> QIcon:
    """Small IDM-style queue clock/folder icon for the Q column."""
    pix = QPixmap(16, 16)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    # Clock face in amber
    p.setBrush(QColor("#fef08a"))
    p.setPen(QPen(QColor("#ca8a04"), 1.4))
    p.drawEllipse(2, 2, 12, 12)

    # Clock hands
    p.setPen(QPen(QColor("#854d0e"), 1.6, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(8, 8, 8, 5)
    p.drawLine(8, 8, 11, 8)

    p.end()
    return QIcon(pix)

