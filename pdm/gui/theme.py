"""Modern theme styling for Personal Download Manager."""

DARK_THEME_QSS = """
QMainWindow, QDialog {
    background-color: #0f172a;
    color: #f8fafc;
    font-family: "Segoe UI", -apple-system, sans-serif;
    font-size: 13px;
}

QWidget {
    background-color: #0f172a;
    color: #f8fafc;
    font-family: "Segoe UI", -apple-system, sans-serif;
    font-size: 13px;
}

/* ToolBar */
QToolBar {
    background-color: #1e293b;
    border-bottom: 1px solid #334155;
    spacing: 6px;
    padding: 6px 10px;
}

QToolButton {
    background-color: #334155;
    color: #f8fafc;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 500;
}

QToolButton:hover {
    background-color: #475569;
    border-color: #64748b;
}

QToolButton:pressed {
    background-color: #1e293b;
}

QToolButton:disabled {
    background-color: #1e293b;
    color: #64748b;
    border-color: #334155;
}

/* Sidebar Header */
#sidebarHeader {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 2px 4px;
}
#sidebarTitle {
    color: #e2e8f0;
    font-weight: 600;
}
#sidebarCloseBtn {
    background: transparent;
    border: none;
    color: #94a3b8;
    font-size: 13px;
    font-weight: bold;
}
#sidebarCloseBtn:hover {
    color: #ef4444;
}

/* Category Sidebar / QTreeWidget */
QTreeWidget, QTreeView {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
    color: #f8fafc;
    padding: 2px 0px;
    outline: none;
    show-decoration-selected: 1;
}

QTreeWidget::item, QTreeView::item {
    padding: 6px 8px;
    border-radius: 0px;
    border: none;
}

QTreeWidget::item:hover, QTreeView::item:hover {
    background-color: #334155;
}

QTreeWidget::item:selected, QTreeView::item:selected {
    background-color: #2563eb;
    color: #ffffff;
    font-weight: 600;
}

QTreeWidget::branch:hover, QTreeView::branch:hover {
    background-color: #334155;
}

QTreeWidget::branch:selected, QTreeView::branch:selected {
    background-color: #2563eb;
}

/* Splitter */
QSplitter::handle:horizontal {
    width: 1px;
    background-color: #334155;
}

/* Central Table */
QTableView {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    color: #f8fafc;
    gridline-color: #334155;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    outline: none;
}

QTableView::item {
    padding: 6px 8px;
}

QTableView::item:selected {
    background-color: #2563eb;
}

QHeaderView::section {
    background-color: #0f172a;
    color: #94a3b8;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #334155;
    border-bottom: 1px solid #334155;
    font-weight: 600;
}

QHeaderView::down-arrow, QHeaderView::up-arrow {
    image: none;
    width: 0px;
    height: 0px;
}

/* Inputs & Search */
QLineEdit, QSpinBox, QComboBox {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f8fafc;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #3b82f6;
}

/* PushButtons */
QPushButton {
    background-color: #2563eb;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #1d4ed8;
}

QPushButton:pressed {
    background-color: #1e40af;
}

QPushButton:disabled {
    background-color: #334155;
    color: #64748b;
}

QPushButton#secondaryBtn {
    background-color: #334155;
    color: #f8fafc;
    border: 1px solid #475569;
}

QPushButton#secondaryBtn:hover {
    background-color: #475569;
}

/* Progress Bar */
QProgressBar {
    border: 1px solid #334155;
    border-radius: 5px;
    text-align: center;
    background-color: #0f172a;
    color: #f8fafc;
    font-size: 11px;
}

QProgressBar::chunk {
    background-color: #2563eb;
    border-radius: 4px;
}

/* Status Bar */
QStatusBar {
    background-color: #0f172a;
    color: #94a3b8;
    border-top: 1px solid #334155;
    font-size: 12px;
}

/* Context Menu */
QMenu {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 20px 6px 10px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}
"""

LIGHT_THEME_QSS = """
QMainWindow, QDialog {
    background-color: #f8fafc;
    color: #0f172a;
    font-family: "Segoe UI", -apple-system, sans-serif;
    font-size: 13px;
}

QWidget {
    background-color: #f8fafc;
    color: #0f172a;
    font-family: "Segoe UI", -apple-system, sans-serif;
    font-size: 13px;
}

/* ToolBar */
QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    spacing: 6px;
    padding: 6px 10px;
}

QToolButton {
    background-color: #f1f5f9;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 500;
}

QToolButton:hover {
    background-color: #e2e8f0;
}

QToolButton:pressed {
    background-color: #cbd5e1;
}

QToolButton:disabled {
    background-color: #f8fafc;
    color: #94a3b8;
    border-color: #e2e8f0;
}

/* Sidebar Header */
#sidebarHeader {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 2px 4px;
}
#sidebarTitle {
    color: #1e293b;
    font-weight: 600;
}
#sidebarCloseBtn {
    background: transparent;
    border: none;
    color: #64748b;
    font-size: 13px;
    font-weight: bold;
}
#sidebarCloseBtn:hover {
    color: #ef4444;
}

/* Category Sidebar / QTreeWidget */
QTreeWidget, QTreeView {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
    color: #0f172a;
    padding: 2px 0px;
    outline: none;
    show-decoration-selected: 1;
}

QTreeWidget::item, QTreeView::item {
    padding: 6px 8px;
    border-radius: 0px;
    border: none;
}

QTreeWidget::item:hover, QTreeView::item:hover {
    background-color: #f1f5f9;
}

QTreeWidget::item:selected, QTreeView::item:selected {
    background-color: #2563eb;
    color: #ffffff;
    font-weight: 600;
}

QTreeWidget::branch:hover, QTreeView::branch:hover {
    background-color: #f1f5f9;
}

QTreeWidget::branch:selected, QTreeView::branch:selected {
    background-color: #2563eb;
}

/* Splitter */
QSplitter::handle:horizontal {
    width: 1px;
    background-color: #e2e8f0;
}

/* Central Table */
QTableView {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    color: #0f172a;
    gridline-color: #f1f5f9;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    outline: none;
}

QTableView::item {
    padding: 6px 8px;
}

QTableView::item:selected {
    background-color: #2563eb;
}

QHeaderView::section {
    background-color: #f8fafc;
    color: #334155;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #cbd5e1;
    border-bottom: 1px solid #cbd5e1;
    font-weight: 600;
}

QHeaderView::down-arrow, QHeaderView::up-arrow {
    image: none;
    width: 0px;
    height: 0px;
}

/* Inputs & Search */
QLineEdit, QSpinBox, QComboBox {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 10px;
    color: #0f172a;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #2563eb;
}

/* PushButtons */
QPushButton {
    background-color: #2563eb;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #1d4ed8;
}

QPushButton:pressed {
    background-color: #1e40af;
}

QPushButton:disabled {
    background-color: #e2e8f0;
    color: #94a3b8;
}

QPushButton#secondaryBtn {
    background-color: #f1f5f9;
    color: #0f172a;
    border: 1px solid #cbd5e1;
}

QPushButton#secondaryBtn:hover {
    background-color: #e2e8f0;
}

/* Progress Bar */
QProgressBar {
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    text-align: center;
    background-color: #f1f5f9;
    color: #0f172a;
    font-size: 11px;
}

QProgressBar::chunk {
    background-color: #2563eb;
    border-radius: 4px;
}

/* Status Bar */
QStatusBar {
    background-color: #ffffff;
    color: #64748b;
    border-top: 1px solid #e2e8f0;
    font-size: 12px;
}

/* Context Menu */
QMenu {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 20px 6px 10px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}
"""
