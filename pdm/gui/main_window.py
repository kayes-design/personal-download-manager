"""Main application window for Personal Download Manager with drag-and-drop and power features."""

import os
import subprocess
import sys
from typing import Optional
from PySide6.QtCore import QItemSelection, QItemSelectionModel, QPoint, QRect, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QDrag, QIcon, QKeySequence, QMouseEvent, QPainter, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QRubberBand,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QTableView,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pdm.core.coordinator import DownloadCoordinator
from pdm.core.media_downloader import is_media_stream_url
from pdm.core.engine import DownloadStatus, DownloadTask
from pdm.core.scheduler import QueueScheduler
from pdm.core.security import extract_filename_from_url, validate_url
from pdm.gui.add_dialog import AddDownloadDialog
from pdm.gui.batch_dialog import BatchDownloadDialog
from pdm.gui.complete_dialog import DownloadCompleteDialog
from pdm.gui.icons import create_idm_sort_arrow
from pdm.gui.integrity_dialog import IntegrityCheckDialog
from pdm.gui.models import DownloadsTableModel, format_bytes, format_speed
from pdm.gui.move_rename_dialog import MoveRenameDialog, MoveToDialog, RenameDialog
from pdm.gui.progress_dialog import DownloadProgressDialog
from pdm.gui.properties_dialog import PropertiesDialog
from pdm.gui.refresh_address_dialog import RefreshAddressDialog
from pdm.gui.scheduler_dialog import SchedulerDialog
from pdm.gui.settings_dialog import SettingsDialog
from pdm.gui.theme import DARK_THEME_QSS, LIGHT_THEME_QSS

# Extensions that trigger automatic clipboard detection
DOWNLOADABLE_EXTENSIONS = {
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso",
    ".exe", ".msi", ".apk", ".dmg", ".bin",
    ".mp4", ".mkv", ".avi", ".webm", ".mov",
    ".mp3", ".flac", ".wav", ".aac", ".ogg",
    ".pdf", ".epub", ".doc", ".docx", ".xls", ".xlsx"
}


class DownloadsTableView(QTableView):
    """Custom table view supporting multi-row mouse drag, rubberband selection, and Explorer drag."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rubber_band: Optional[QRubberBand] = None
        self._origin: QPoint = QPoint()
        self._is_rubber_banding: bool = False
        self._alt_drag_start: Optional[QPoint] = None

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self._origin = pos
            idx = self.indexAt(pos)

            # If user holds Alt while clicking on an item, prepare for Explorer drag
            if (event.modifiers() & Qt.AltModifier) and idx.isValid():
                self._alt_drag_start = pos
            else:
                self._alt_drag_start = None

            # If clicked in empty space below or beside rows -> start rubber band selection
            if not idx.isValid():
                self._is_rubber_banding = True
                if not self._rubber_band:
                    self._rubber_band = QRubberBand(QRubberBand.Rectangle, self.viewport())
                self._rubber_band.setGeometry(QRect(self._origin, self._origin))
                self._rubber_band.show()
                if not (event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                    self.clearSelection()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

        # 1. Rubber band box selection
        if self._is_rubber_banding and self._rubber_band and (event.buttons() & Qt.LeftButton):
            rect = QRect(self._origin, pos).normalized()
            self._rubber_band.setGeometry(rect)

            sel = QItemSelection()
            m = self.model()
            vp_width = self.viewport().width()
            for r in range(m.rowCount()):
                v_rect = self.visualRect(m.index(r, 0))
                row_box = QRect(0, v_rect.top(), vp_width, v_rect.height())
                if rect.intersects(row_box):
                    sel.select(m.index(r, 0), m.index(r, m.columnCount() - 1))

            self.selectionModel().select(sel, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
            return

        # 2. Alt+Drag to export files to Windows Explorer
        if self._alt_drag_start and (event.buttons() & Qt.LeftButton):
            dist = (pos - self._alt_drag_start).manhattanLength()
            if dist >= QApplication.startDragDistance():
                self._alt_drag_start = None
                self._start_drag()
                return

        # 3. Standard smooth multi-row drag selection (native Qt)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._is_rubber_banding and self._rubber_band:
            self._is_rubber_banding = False
            self._rubber_band.hide()
            return
        super().mouseReleaseEvent(event)

    def _start_drag(self):
        indexes = self.selectionModel().selectedRows()
        if not indexes:
            return
        model: DownloadsTableModel = self.model()
        urls = []
        for idx in indexes:
            item = model.get_download_at(idx.row())
            if item and item.get("status") == "Completed":
                file_path = item.get("destination_path")
                if file_path and os.path.exists(file_path):
                    urls.append(QUrl.fromLocalFile(os.path.normpath(file_path)))
        if not urls:
            return

        from PySide6.QtCore import QMimeData

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setUrls(urls)
        drag.setMimeData(mime_data)
        drag.exec(Qt.CopyAction)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            parent = self.window()
            if hasattr(parent, "_delete_selected"):
                parent._delete_selected()
                return
        elif event.key() == Qt.Key_Space:
            parent = self.window()
            if hasattr(parent, "_toggle_pause_resume_selected"):
                parent._toggle_pause_resume_selected()
                return
        super().keyPressEvent(event)


class IDMHeaderView(QHeaderView):
    """Custom table header that renders IDM's signature green curved sort arrow next to column text."""

    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setHighlightSections(True)
        self.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._down_arrow = create_idm_sort_arrow("down")
        self._up_arrow = create_idm_sort_arrow("up")

    def paintSection(self, painter: QPainter, rect, logicalIndex: int):
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()

        # If this section is the sorted column, draw IDM's green curved arrow
        if self.isSortIndicatorShown() and self.sortIndicatorSection() == logicalIndex:
            model = self.model()
            if not model:
                return
            text = str(model.headerData(logicalIndex, self.orientation(), Qt.DisplayRole) or "")
            fm = self.fontMetrics()
            text_width = fm.horizontalAdvance(text)

            if logicalIndex == 1:
                # Column 1 ('Q') is centered
                arrow_x = rect.left() + (rect.width() + text_width) // 2 + 3
            elif logicalIndex in (2, 4, 5):
                # Numeric columns are right-aligned
                arrow_x = rect.right() - text_width - 20
            else:
                # Left-aligned columns
                arrow_x = rect.left() + 8 + text_width + 5

            arrow_y = rect.top() + (rect.height() - 13) // 2

            if rect.left() <= arrow_x and arrow_x + 13 <= rect.right():
                arrow = self._down_arrow if self.sortIndicatorOrder() == Qt.DescendingOrder else self._up_arrow
                painter.drawPixmap(arrow_x, arrow_y, arrow)


class ShutdownCountdownDialog(QDialog):
    """60-second cancelable warning dialog before automated PC shutdown, sleep, or exit."""

    def __init__(self, scheduler: Optional[QueueScheduler] = None, parent=None, action: str = "shutdown"):
        super().__init__(parent)
        self.scheduler = scheduler
        self.action = action  # "shutdown", "sleep", or "exit"

        action_title = "Shutdown" if self.action == "shutdown" else ("Sleep" if self.action == "sleep" else "Exit")
        self.setWindowTitle(f"Auto-{action_title} Warning")
        self.resize(380, 160)
        self.countdown = 60

        action_verb = "shut down" if self.action == "shutdown" else ("sleep" if self.action == "sleep" else "close")
        layout = QVBoxLayout(self)
        self.label = QLabel(f"All downloads completed.\nComputer will {action_verb} in {self.countdown} seconds.")
        self.label.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton(f"Cancel {action_title}")
        cancel_btn.clicked.connect(self._cancel_action)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self):
        self.countdown -= 1
        action_verb = "shut down" if self.action == "shutdown" else ("sleep" if self.action == "sleep" else "close")
        if self.countdown <= 0:
            self._timer.stop()
            self.label.setText("Executing now...")
            self._execute_action()
            self.accept()
        else:
            self.label.setText(f"All downloads completed.\nComputer will {action_verb} in {self.countdown} seconds.")

    def _execute_action(self):
        if self.action == "sleep":
            try:
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=False)
            except Exception:
                pass
        elif self.action == "shutdown":
            if self.scheduler:
                self.scheduler.trigger_system_shutdown()
            else:
                try:
                    subprocess.run(["shutdown.exe", "/s", "/t", "0"], check=False)
                except Exception:
                    pass
        elif self.action == "exit":
            parent = self.parent()
            if parent and hasattr(parent, "_on_exit"):
                parent._on_exit()
            else:
                QApplication.quit()

    def _cancel_action(self):
        self._timer.stop()
        if self.scheduler:
            self.scheduler.cancel_system_shutdown()
        self.reject()


class MainWindow(QMainWindow):
    """Primary desktop interface for PDM."""

    download_started_signal = Signal(int)
    download_completed_signal = Signal(dict)

    def __init__(self, coordinator: DownloadCoordinator):
        super().__init__()
        self.coordinator = coordinator
        self.db = coordinator.db
        self.scheduler = QueueScheduler(coordinator)

        self.setWindowTitle("Personal Download Manager")
        self.resize(1050, 620)

        self.current_category = "All"
        self.current_status = "All"
        self.search_query = ""
        self._last_clipboard_url = ""
        self._active_popups = []
        self._active_progress_dialogs = {}

        # Set Window and Tray Icon
        self.app_icon = self._load_app_icon()
        if self.app_icon:
            self.setWindowIcon(self.app_icon)

        self._setup_ui()
        self._setup_tray()
        self._setup_clipboard_monitor()
        self._apply_theme()

        # Connect callbacks
        self.coordinator.on_status_changed = self._on_task_status_changed
        self.download_started_signal.connect(self._on_download_started_gui)
        self.download_completed_signal.connect(self._on_download_completed_gui)
        self.scheduler.on_shutdown_countdown_started = self._show_shutdown_warning

        # Periodic UI table refresh (250ms)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_table)
        self._refresh_timer.start(250)

        self._refresh_table()

    def _setup_ui(self):
        # 0. IDM Menu Bar
        self._setup_menu_bar()

        # 1. Main Toolbar
        toolbar = QToolBar("Main Controls")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        add_act = toolbar.addAction("+ Add URL")
        add_act.setShortcut(QKeySequence("Ctrl+N"))
        add_act.triggered.connect(self._open_add_dialog)

        batch_act = toolbar.addAction("📋 Batch / Pattern")
        batch_act.setShortcut(QKeySequence("Ctrl+B"))
        batch_act.triggered.connect(self._open_batch_dialog)

        toolbar.addSeparator()

        self.resume_act = toolbar.addAction("▶ Resume")
        self.resume_act.triggered.connect(self._resume_selected)

        self.resume_all_act = toolbar.addAction("▶▶ Resume All")
        self.resume_all_act.triggered.connect(self.coordinator.resume_all)

        self.stop_act = toolbar.addAction("⏹ Stop")
        self.stop_act.triggered.connect(self._pause_selected)

        self.stop_all_act = toolbar.addAction("✋ Stop All")
        self.stop_all_act.triggered.connect(self.coordinator.pause_all)

        self.del_act = toolbar.addAction("🗑 Delete")
        self.del_act.triggered.connect(self._delete_selected)

        self.del_completed_act = toolbar.addAction("🧹 Delete Completed")
        self.del_completed_act.triggered.connect(self._delete_completed)

        toolbar.addSeparator()

        sched_act = toolbar.addAction("⏰ Scheduler")
        sched_act.triggered.connect(self._open_scheduler)

        self.start_q_btn = toolbar.addAction("▶ Start Queue")
        self.start_q_btn.setToolTip("Start downloading the main queue")
        self.start_q_btn.triggered.connect(self.coordinator.resume_all)

        self.stop_q_btn = toolbar.addAction("⏹ Stop Queue")
        self.stop_q_btn.setToolTip("Stop downloading the queue")
        self.stop_q_btn.triggered.connect(self.coordinator.pause_all)

        toolbar.addSeparator()

        verify_act = toolbar.addAction("🔍 Verify Hash")
        verify_act.triggered.connect(self._verify_selected_hash)

        settings_act = toolbar.addAction("⚙ Options")
        settings_act.triggered.connect(self._open_settings)

        toolbar.addSeparator()

        self.toggle_cat_act = toolbar.addAction("📁 Categories")
        self.toggle_cat_act.setCheckable(True)
        self.toggle_cat_act.setChecked(True)
        self.toggle_cat_act.triggered.connect(self._toggle_sidebar)

        # 2. Main Central Layout with Splitter
        main_splitter = QSplitter(Qt.Horizontal)

        # 2.1 Left Sidebar: Category Tree Container
        self.sidebar_container = QWidget()
        sidebar_layout = QVBoxLayout(self.sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Header bar (matching IDM's 'Categories' header with 'X' close button)
        header_widget = QWidget()
        header_widget.setObjectName("sidebarHeader")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 4, 6, 4)

        title_label = QLabel("Categories")
        title_label.setObjectName("sidebarTitle")
        title_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setObjectName("sidebarCloseBtn")
        close_btn.setFixedSize(20, 20)
        close_btn.setToolTip("Hide Categories")
        close_btn.clicked.connect(self._hide_sidebar)
        header_layout.addWidget(close_btn)
        sidebar_layout.addWidget(header_widget)

        # Category Tree Widget with branch decoration and icons
        self.category_tree = QTreeWidget()
        self.category_tree.setHeaderHidden(True)
        self.category_tree.setRootIsDecorated(True)
        self.category_tree.setAnimated(True)
        self.category_tree.setIndentation(16)
        self.category_tree.setAllColumnsShowFocus(True)
        self.sidebar_container.setFixedWidth(200)

        self._populate_category_tree()
        self.category_tree.itemClicked.connect(self._on_category_clicked)
        sidebar_layout.addWidget(self.category_tree)

        main_splitter.addWidget(self.sidebar_container)

        # 2.2 Right Content Area
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(6)

        # Search bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search downloads by filename or URL...")
        self.search_bar.textChanged.connect(self._on_search_changed)
        right_layout.addWidget(self.search_bar)

        # Download Table View (with Drag-and-Drop and IDM-style Header)
        self.table_view = DownloadsTableView()
        self.header_view = IDMHeaderView(Qt.Horizontal, self.table_view)
        self.table_view.setHorizontalHeader(self.header_view)
        self.table_model = DownloadsTableModel()
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setSelectionMode(QTableView.ExtendedSelection)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setShowGrid(True)

        for i in range(len(DownloadsTableModel.COLUMNS)):
            self.header_view.setSectionResizeMode(i, QHeaderView.Interactive)

        self.table_view.setColumnWidth(0, 260)  # File Name
        self.table_view.setColumnWidth(1, 35)   # Q
        self.table_view.setColumnWidth(2, 90)   # Size
        self.table_view.setColumnWidth(3, 140)  # Status
        self.table_view.setColumnWidth(4, 85)   # Time left
        self.table_view.setColumnWidth(5, 105)  # Transfer rate
        self.table_view.setColumnWidth(6, 130)  # Last Try...
        self.table_view.setColumnWidth(7, 180)  # Description

        self.table_view.doubleClicked.connect(self._on_row_double_clicked)
        self.table_view.setSortingEnabled(True)
        self.header_view.setSortIndicator(0, Qt.AscendingOrder)
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)

        # Move (Ctrl+M) and Rename (F2) shortcuts
        self.move_shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        self.move_shortcut.activated.connect(self._move_selected)

        self.rename_shortcut = QShortcut(QKeySequence("F2"), self)
        self.rename_shortcut.activated.connect(self._rename_selected)

        right_layout.addWidget(self.table_view)
        main_splitter.addWidget(right_container)

        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)

        self.setCentralWidget(main_splitter)

        # 3. Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        cur_comp = self.db.get_setting("on_completion_action", "none")
        comp_label = "Do Nothing"
        if cur_comp == "sleep":
            comp_label = "Sleep"
        elif cur_comp == "shutdown":
            comp_label = "Shutdown"
        elif cur_comp == "exit":
            comp_label = "Exit PDM"

        self.completion_btn = QPushButton(f"⚡ On finish: {comp_label}")
        self.completion_btn.setFlat(True)
        self.completion_btn.setCursor(Qt.PointingHandCursor)
        self.completion_btn.setStyleSheet("color: #38bdf8; font-size: 11px; padding: 2px 8px; border: 1px solid #334155; border-radius: 4px; background: #1e293b;")
        self.completion_btn.clicked.connect(self._show_completion_popup_menu)

        self.speed_status_label = QLabel("Speed: 0 KB/s")
        self.active_status_label = QLabel("Active: 0")
        self.status_bar.addPermanentWidget(self.completion_btn)
        self.status_bar.addPermanentWidget(self.active_status_label)
        self.status_bar.addPermanentWidget(self.speed_status_label)

    def _setup_menu_bar(self):
        menubar = self.menuBar()

        # 1. Tasks Menu
        tasks_menu = menubar.addMenu("&Tasks")
        add_act = tasks_menu.addAction("&Add new download...")
        add_act.setShortcut(QKeySequence("Ctrl+N"))
        add_act.triggered.connect(self._open_add_dialog)

        batch_act = tasks_menu.addAction("Add &batch download...")
        batch_act.setShortcut(QKeySequence("Ctrl+B"))
        batch_act.triggered.connect(self._open_batch_dialog)

        tasks_menu.addSeparator()

        export_act = tasks_menu.addAction("&Export to text file...")
        export_act.triggered.connect(self._export_urls)

        import_act = tasks_menu.addAction("&Import from text file...")
        import_act.triggered.connect(self._import_urls)

        tasks_menu.addSeparator()

        exit_act = tasks_menu.addAction("E&xit")
        exit_act.setShortcut(QKeySequence("Alt+F4"))
        exit_act.triggered.connect(self._on_exit)

        # 2. File Menu
        file_menu = menubar.addMenu("&File")
        resume_act = file_menu.addAction("&Resume download")
        resume_act.triggered.connect(self._resume_selected)

        stop_act = file_menu.addAction("&Stop download")
        stop_act.triggered.connect(self._pause_selected)

        file_menu.addSeparator()

        resume_all_act = file_menu.addAction("Resume &all")
        resume_all_act.triggered.connect(self.coordinator.resume_all)

        stop_all_act = file_menu.addAction("Stop a&ll")
        stop_all_act.triggered.connect(self.coordinator.pause_all)

        file_menu.addSeparator()

        move_act = file_menu.addAction("&Move to folder...")
        move_act.setShortcut(QKeySequence("Ctrl+M"))
        move_act.triggered.connect(self._move_selected)

        rename_act = file_menu.addAction("Re&name...")
        rename_act.setShortcut(QKeySequence("F2"))
        rename_act.triggered.connect(self._rename_selected)

        file_menu.addSeparator()

        redownload_act = file_menu.addAction("Re&download")
        redownload_act.triggered.connect(self._redownload_selected)

        del_act = file_menu.addAction("&Delete from list")
        del_act.triggered.connect(self._delete_selected_from_list)

        del_disk_act = file_menu.addAction("Delete &file from disk")
        del_disk_act.triggered.connect(self._delete_selected_with_file)

        del_comp_act = file_menu.addAction("Delete &completed")
        del_comp_act.triggered.connect(self._delete_completed)

        # 3. Downloads Menu
        dl_menu = menubar.addMenu("&Downloads")
        settings_act = dl_menu.addAction("&Options...")
        settings_act.triggered.connect(self._open_settings)

        speed_menu = dl_menu.addMenu("Speed &Limiter")
        lim_on_act = speed_menu.addAction("Turn on")
        lim_on_act.triggered.connect(lambda: self._set_speed_limiter(True))
        lim_off_act = speed_menu.addAction("Turn off")
        lim_off_act.triggered.connect(lambda: self._set_speed_limiter(False))
        speed_menu.addSeparator()
        lim_cfg_act = speed_menu.addAction("Settings...")
        lim_cfg_act.triggered.connect(self._open_settings)

        dl_menu.addSeparator()

        sched_act = dl_menu.addAction("&Scheduler...")
        sched_act.triggered.connect(self._open_scheduler)

        finish_menu = dl_menu.addMenu("On &Completion")
        self.finish_group = QActionGroup(self)
        self.finish_group.setExclusive(True)
        cur_comp = self.db.get_setting("on_completion_action", "none")

        for text_opt, val in [
            ("Do Nothing", "none"),
            ("Sleep Computer", "sleep"),
            ("Shut Down Computer", "shutdown"),
            ("Exit Personal Download Manager", "exit")
        ]:
            act = finish_menu.addAction(text_opt)
            act.setCheckable(True)
            act.setChecked(cur_comp == val)
            label = text_opt.replace("Computer", "").replace("Personal Download Manager", "PDM").strip()
            act.triggered.connect(lambda checked, v=val, l=label: self._set_completion_action(v, l))
            self.finish_group.addAction(act)

        dl_menu.addSeparator()

        start_q_act = dl_menu.addAction("&Start Queue")
        start_q_act.triggered.connect(self.coordinator.resume_all)

        stop_q_act = dl_menu.addAction("S&top Queue")
        stop_q_act.triggered.connect(self.coordinator.pause_all)

        dl_menu.addSeparator()

        self.progress_dlg_menu_act = dl_menu.addAction("Show Download &Progress Dialog")
        self.progress_dlg_menu_act.setCheckable(True)
        self.progress_dlg_menu_act.setChecked(self.db.get_setting("show_progress_dlg", "1") == "1")
        self.progress_dlg_menu_act.toggled.connect(self._toggle_progress_dlg)

        self.complete_dlg_menu_act = dl_menu.addAction("Show Download &Complete Dialog")
        self.complete_dlg_menu_act.setCheckable(True)
        self.complete_dlg_menu_act.setChecked(self.db.get_setting("show_complete_dlg", "1") == "1")
        self.complete_dlg_menu_act.toggled.connect(self._toggle_complete_dlg)

        # 4. View Menu
        view_menu = menubar.addMenu("&View")
        self.menu_cat_act = view_menu.addAction("&Categories Tree")
        self.menu_cat_act.setCheckable(True)
        self.menu_cat_act.setChecked(True)
        self.menu_cat_act.triggered.connect(self._toggle_sidebar)

        view_menu.addSeparator()

        theme_menu = view_menu.addMenu("&Theme")
        dark_act = theme_menu.addAction("&Dark Mode (Windows 11 Slate)")
        dark_act.triggered.connect(lambda: self._change_theme("dark"))
        light_act = theme_menu.addAction("&Light Mode")
        light_act.triggered.connect(lambda: self._change_theme("light"))

        # 5. Help Menu
        help_menu = menubar.addMenu("&Help")
        about_act = help_menu.addAction("&About Personal Download Manager...")
        about_act.triggered.connect(self._show_about)

    def _load_app_icon(self) -> Optional[QIcon]:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(base_dir, "gui", "resources", "icon.ico"),
            os.path.join(base_dir, "gui", "resources", "app_icon.png"),
            os.path.join(os.path.dirname(base_dir), "icon.ico"),
            os.path.join(getattr(sys, "_MEIPASS", ""), "icon.ico"),
            os.path.join(getattr(sys, "_MEIPASS", ""), "pdm", "gui", "resources", "icon.ico"),
        ]
        for p in candidates:
            if p and os.path.exists(p):
                ico = QIcon(p)
                if not ico.isNull():
                    return ico
        return None

    def _show_window(self):
        """Restore and bring main window to the foreground."""
        self.show()
        self.setWindowState(Qt.WindowActive)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                ctypes.windll.user32.ShowWindow(hwnd, 9) # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass

    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        if self.app_icon and not self.app_icon.isNull():
            self.tray_icon.setIcon(self.app_icon)
        else:
            self.tray_icon.setIcon(self.style().standardIcon(QApplication.style().StandardPixmap.SP_ArrowDown))

        tray_menu = QMenu()
        show_act = tray_menu.addAction("Show PDM")
        show_act.triggered.connect(self._show_window)

        add_act = tray_menu.addAction("Add URL...")
        add_act.triggered.connect(self._open_add_dialog)

        batch_act = tray_menu.addAction("Batch / Pattern...")
        batch_act.triggered.connect(self._open_batch_dialog)

        tray_menu.addSeparator()
        pause_act = tray_menu.addAction("Pause All")
        pause_act.triggered.connect(self.coordinator.pause_all)

        resume_act = tray_menu.addAction("Resume All")
        resume_act.triggered.connect(self.coordinator.resume_all)

        tray_menu.addSeparator()
        quit_act = tray_menu.addAction("Exit")
        quit_act.triggered.connect(self._on_exit)

        self.tray_icon.setContextMenu(tray_menu)

        def on_tray_activated(reason):
            if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
                self._show_window()

        self.tray_icon.activated.connect(on_tray_activated)
        self.tray_icon.show()

    def _setup_clipboard_monitor(self):
        """Monitor clipboard and trigger only on valid downloadable file extensions."""
        clipboard = QApplication.clipboard()
        clipboard.dataChanged.connect(self._on_clipboard_data_changed)

    def _on_clipboard_data_changed(self):
        enabled = self.db.get_setting("clipboard_monitor", "1") == "1"
        if not enabled:
            return

        text = QApplication.clipboard().text().strip()
        if not text or text == self._last_clipboard_url:
            return

        ok, valid_url = validate_url(text)
        if not ok:
            return

        # Check if URL ends with a known downloadable extension OR is a media stream/portal OR cloud drive
        fn = extract_filename_from_url(valid_url).lower()
        _, ext = os.path.splitext(fn)
        is_known_ext = ext in DOWNLOADABLE_EXTENSIONS
        is_media = is_media_stream_url(valid_url)
        is_cloud = any(k in valid_url.lower() for k in (
            "drive.google.com", "mediafire.com", "dropbox.com", "mega.nz", 
            "archive.org", "github.com", "/download", "download=", "dl=", "?dl=1"
        ))

        if is_known_ext or is_media or is_cloud:
            self._last_clipboard_url = text
            self.showNormal()
            self.activateWindow()
            self._open_add_dialog(prefill_url=valid_url)

    def _apply_theme(self):
        theme = self.db.get_setting("theme", "Dark")
        if theme == "Light":
            self.setStyleSheet(LIGHT_THEME_QSS)
        else:
            self.setStyleSheet(DARK_THEME_QSS)

    def _populate_category_tree(self):
        """Populate hierarchical IDM-style categories with icons and sub-groups."""
        from pdm.gui.icons import (
            create_compressed_icon,
            create_document_icon,
            create_folder_icon,
            create_music_icon,
            create_programs_icon,
            create_video_icon,
        )

        sub_categories = [
            ("Compressed", "Compressed", create_compressed_icon()),
            ("Documents", "Documents", create_document_icon()),
            ("Music", "Music", create_music_icon()),
            ("Programs", "Programs", create_programs_icon()),
            ("Video", "Video", create_video_icon()),
        ]

        # 1. All Downloads (Parent, Expanded by default with [-])
        all_root = QTreeWidgetItem(["All Downloads"])
        all_root.setIcon(0, create_folder_icon())
        all_root.setData(0, Qt.UserRole, ("All", "All"))
        self.category_tree.addTopLevelItem(all_root)

        for label, cat_key, icon in sub_categories:
            child = QTreeWidgetItem([label])
            child.setIcon(0, icon)
            child.setData(0, Qt.UserRole, ("All", cat_key))
            all_root.addChild(child)

        all_root.setExpanded(True)

        # 2. Unfinished (Parent, Collapsed by default with [+])
        unfin_root = QTreeWidgetItem(["Unfinished"])
        unfin_root.setIcon(0, create_folder_icon(badge="down"))
        unfin_root.setData(0, Qt.UserRole, ("Unfinished", "All"))
        self.category_tree.addTopLevelItem(unfin_root)

        for label, cat_key, icon in sub_categories:
            child = QTreeWidgetItem([label])
            child.setIcon(0, icon)
            child.setData(0, Qt.UserRole, ("Unfinished", cat_key))
            unfin_root.addChild(child)

        unfin_root.setExpanded(False)

        # 3. Finished (Parent, Collapsed by default with [+])
        fin_root = QTreeWidgetItem(["Finished"])
        fin_root.setIcon(0, create_folder_icon(badge="check"))
        fin_root.setData(0, Qt.UserRole, ("Finished", "All"))
        self.category_tree.addTopLevelItem(fin_root)

        for label, cat_key, icon in sub_categories:
            child = QTreeWidgetItem([label])
            child.setIcon(0, icon)
            child.setData(0, Qt.UserRole, ("Finished", cat_key))
            fin_root.addChild(child)

        fin_root.setExpanded(False)

        self.category_tree.setCurrentItem(all_root)

    def _hide_sidebar(self):
        self.sidebar_container.setVisible(False)
        self.toggle_cat_act.setChecked(False)

    def _toggle_sidebar(self, checked: bool):
        self.sidebar_container.setVisible(checked)

    def _on_category_clicked(self, item: QTreeWidgetItem):
        data = item.data(0, Qt.UserRole)
        if isinstance(data, tuple):
            self.current_status, self.current_category = data
        elif isinstance(data, str):
            self.current_category = data
            self.current_status = "All"
        self._refresh_table()

    def _on_search_changed(self, text: str):
        self.search_query = text.strip()
        self._refresh_table()

    def _refresh_table(self):
        items = self.db.list_downloads(
            category=self.current_category,
            status=self.current_status,
            search=self.search_query
        )

        total_speed = 0.0
        active_count = 0

        for item in items:
            tid = item["id"]
            active_task = self.coordinator.get_active_task(tid)
            if active_task:
                item["current_speed"] = active_task.current_speed
                item["eta_seconds"] = active_task.eta_seconds
                item["downloaded_bytes"] = active_task.downloaded_bytes
                item["status"] = active_task.status.value
                total_speed += active_task.current_speed
                if active_task.status == DownloadStatus.DOWNLOADING:
                    active_count += 1
            else:
                item["current_speed"] = 0.0
                item["eta_seconds"] = None

        # Preserve selection across table refreshes
        prev_selected_ids = {it["id"] for it in self._get_selected_tasks()}

        self.table_model.set_data(items)

        # Restore selection if it changed or cleared
        if prev_selected_ids:
            cur_selected = {it["id"] for it in self._get_selected_tasks()}
            if cur_selected != prev_selected_ids:
                sel_model = self.table_view.selectionModel()
                flags = QItemSelectionModel.Select | QItemSelectionModel.Rows
                for r in range(self.table_model.rowCount()):
                    d = self.table_model.get_download_at(r)
                    if d and d["id"] in prev_selected_ids:
                        idx = self.table_model.index(r, 0)
                        sel_model.select(idx, flags)
        self.speed_status_label.setText(f"Speed: {format_speed(total_speed)}")
        self.active_status_label.setText(f"Active: {active_count}")

        # Dynamic button enablement (IDM behavior)
        selected_tasks = self._get_selected_tasks()
        if selected_tasks:
            can_resume = any(it.get("status") in ("Paused", "Queued", "Error") for it in selected_tasks)
            can_stop = any(it.get("status") == "Downloading" for it in selected_tasks)
            self.resume_act.setEnabled(can_resume)
            self.stop_act.setEnabled(can_stop)
            self.del_act.setEnabled(True)
        else:
            self.resume_act.setEnabled(False)
            self.stop_act.setEnabled(False)
            self.del_act.setEnabled(False)

        self.stop_all_act.setEnabled(active_count > 0)
        has_paused = any(it.get("status") in ("Paused", "Queued") for it in items)
        self.resume_all_act.setEnabled(has_paused)
        has_completed = any(it.get("status") == "Completed" for it in items)
        self.del_completed_act.setEnabled(has_completed)

        # Check for incoming download requests from browser extension
        self._check_incoming_browser_requests()

    def _check_incoming_browser_requests(self):
        if getattr(self, "_is_showing_add_dialog", False):
            return

        try:
            incoming = self.db.fetch_unprocessed_incoming_requests()
            if not incoming:
                return

            self._is_showing_add_dialog = True
            default_dir = self.db.get_setting(
                "default_dir", os.path.join(os.path.expanduser("~"), "Downloads")
            )
            default_conns = int(self.db.get_setting("default_connections", "4"))
            show_start_dlg = self.db.get_setting("show_start_dlg", "1") == "1"

            for req in incoming:
                self.db.mark_incoming_request_processed(req["id"])

                dl_id = req.get("download_id", 0)
                rec = self.db.get_download(dl_id) if dl_id else None

                url = req.get("url") or (rec.get("url") if rec else "")
                if not url:
                    continue
                filename = (rec.get("filename") if rec else None) or req.get("filename") or extract_filename_from_url(url)
                cat = (rec.get("category") if rec else None) or req.get("category", "Other")
                cookies = req.get("cookies", "") or (rec.get("cookies") if rec else "")
                referer = req.get("referer", "") or (rec.get("referer") if rec else "")
                user_agent = req.get("user_agent", "") or (rec.get("user_agent") if rec else "")
                origin = req.get("origin", "") or (rec.get("origin") if rec else "")
                proxy = req.get("proxy", "") or (rec.get("proxy") if rec else "")
                auto_start = bool(req.get("auto_start", 1))

                if show_start_dlg:
                    # Pop up the IDM-style Download File Info Dialog in the foreground
                    dlg = AddDownloadDialog(
                        default_save_dir=default_dir,
                        db=self.db,
                        parent=None,
                        prefill_url=url,
                        prefill_filename=filename,
                        prefill_category=cat,
                        cookies=cookies,
                        referer=referer,
                        user_agent=user_agent,
                        origin=origin,
                        proxy=proxy
                    )
                    dlg.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowStaysOnTopHint)
                    dlg.show()
                    dlg.showNormal()
                    dlg.raise_()
                    dlg.activateWindow()
                    if sys.platform == "win32":
                        try:
                            import ctypes
                            hwnd = int(dlg.winId())
                            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002) # HWND_TOPMOST
                            ctypes.windll.user32.ShowWindow(hwnd, 9) # SW_RESTORE
                            ctypes.windll.user32.SetForegroundWindow(hwnd)
                        except Exception:
                            pass

                    if dlg.exec():
                        dl_url, save_dir, dl_fn, dl_cat, conns, dl_auto = dlg.get_data()
                        if dl_id and rec:
                            new_path = resolve_safe_filepath(save_dir, dl_fn)
                            self.db.update_download(
                                dl_id,
                                destination_path=new_path,
                                filename=dl_fn,
                                category=dl_cat,
                                connections_count=conns
                            )
                            if dl_auto:
                                self.coordinator.resume_download(dl_id)
                                if self.db.get_setting("show_progress_dlg", "1") == "1":
                                    self._on_download_started_gui(dl_id)
                        else:
                            tid = self.coordinator.add_download(
                                url=dl_url,
                                destination_dir=save_dir,
                                filename=dl_fn,
                                category=dl_cat,
                                connections_count=conns,
                                auto_start=dl_auto,
                                cookies=dlg.cookies,
                                referer=dlg.referer,
                                user_agent=dlg.user_agent,
                                origin=dlg.origin,
                                proxy=dlg.proxy
                            )
                            if dl_auto and self.db.get_setting("show_progress_dlg", "1") == "1":
                                self._on_download_started_gui(tid)
                    else:
                        if dl_id and rec:
                            self.coordinator.delete_download(dl_id, delete_files=False)
                else:
                    if dl_id and rec and auto_start:
                        self.coordinator.resume_download(dl_id)
                        if self.db.get_setting("show_progress_dlg", "1") == "1":
                            self._on_download_started_gui(dl_id)

        except Exception:
            pass
        finally:
            self._is_showing_add_dialog = False

    def _get_selected_tasks(self) -> list:
        indexes = self.table_view.selectionModel().selectedRows()
        results = []
        for idx in indexes:
            item = self.table_model.get_download_at(idx.row())
            if item:
                results.append(item)
        return results

    def _get_selected_task(self) -> Optional[dict]:
        tasks = self._get_selected_tasks()
        return tasks[0] if tasks else None

    def _open_add_dialog(self, prefill_url: str = ""):
        default_dir = self.db.get_setting(
            "default_dir", os.path.join(os.path.expanduser("~"), "Downloads")
        )
        dialog = AddDownloadDialog(default_dir, self.db, self, prefill_url=prefill_url)
        if dialog.exec():
            if getattr(dialog, "playlist_items", None):
                target_dir = dialog.playlist_dir or default_dir
                cat = dialog.playlist_cat or "Video"
                added_count = 0
                for item in dialog.playlist_items:
                    try:
                        self.coordinator.add_download(
                            url=item["url"],
                            destination_dir=target_dir,
                            filename=f"{item.get('title', 'video')}.mp4",
                            category=cat,
                            connections_count=4,
                            auto_start=True
                        )
                        added_count += 1
                    except Exception:
                        pass
                self._refresh_table()
                QMessageBox.information(
                    self,
                    "Playlist Added",
                    f"Successfully queued {added_count} video(s) from playlist into {target_dir}."
                )
                return

            url, save_dir, filename, category, conns, auto_start = dialog.get_data()

            # IDM-style duplicate check
            with self.db._lock, self.db._get_connection() as conn:
                cur = conn.execute(
                    "SELECT id, filename, destination_path FROM downloads WHERE url = ? AND status = 'Completed' ORDER BY id DESC LIMIT 1",
                    (url,)
                )
                dup_row = cur.fetchone()

            if dup_row and dup_row[2] and os.path.exists(dup_row[2]):
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("File Already Downloaded")
                msg_box.setText(f"This file has already been downloaded with PDM:\n\n{dup_row[2]}\n\nWould you like to open it or download it again?")
                open_btn = msg_box.addButton("Open File", QMessageBox.ButtonRole.ActionRole)
                redl_btn = msg_box.addButton("Download Again", QMessageBox.ButtonRole.AcceptRole)
                cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                msg_box.setDefaultButton(open_btn)
                msg_box.exec()

                clicked = msg_box.clickedButton()
                if clicked == open_btn:
                    os.startfile(dup_row[2])
                    return
                elif clicked == cancel_btn:
                    return

            try:
                task_id = self.coordinator.add_download(
                    url=url,
                    destination_dir=save_dir,
                    filename=filename,
                    category=category,
                    connections_count=conns,
                    auto_start=auto_start
                )
                self._refresh_table()
                if auto_start:
                    self._on_download_started_gui(task_id)
            except Exception as e:
                QMessageBox.critical(self, "Error Adding Download", str(e))

    def _open_batch_dialog(self):
        default_dir = self.db.get_setting(
            "default_dir", os.path.join(os.path.expanduser("~"), "Downloads")
        )
        dialog = BatchDownloadDialog(default_dir, self)
        if dialog.exec():
            urls, save_dir, conns = dialog.get_urls_and_config()
            added = 0
            for u in urls:
                try:
                    self.coordinator.add_download(
                        url=u,
                        destination_dir=save_dir,
                        connections_count=conns,
                        auto_start=True
                    )
                    added += 1
                except Exception:
                    pass
            self._refresh_table()
            QMessageBox.information(
                self, "Batch Complete", f"Successfully queued {added} download(s)."
            )

    def _open_scheduler(self):
        dlg = SchedulerDialog(self.scheduler, self)
        dlg.exec()

    def _show_shutdown_warning(self, seconds: int):
        dlg = ShutdownCountdownDialog(self.scheduler, self)
        dlg.exec()

    def _resume_selected(self):
        items = self._get_selected_tasks()
        for item in items:
            self.coordinator.start_download(item["id"])
        self._refresh_table()

    def _pause_selected(self):
        items = self._get_selected_tasks()
        for item in items:
            self.coordinator.pause_download(item["id"])
        self._refresh_table()

    def _delete_selected(self):
        items = self._get_selected_tasks()
        if not items:
            return

        count = len(items)
        name_str = f"'{items[0]['filename']}'" if count == 1 else f"{count} selected downloads"
        reply = QMessageBox.question(
            self,
            "Delete Download(s)",
            f"Are you sure you want to remove {name_str} from the download list?\n\n"
            "Click 'Yes' to remove from list only, or 'Discard' to also delete file(s) from disk.",
            QMessageBox.Yes | QMessageBox.Discard | QMessageBox.Cancel
        )

        if reply == QMessageBox.Yes:
            for it in items:
                self.coordinator.delete_download(it["id"], delete_files=False)
            self._refresh_table()
        elif reply == QMessageBox.Discard:
            for it in items:
                self.coordinator.delete_download(it["id"], delete_files=True)
            self._refresh_table()

    def _delete_completed(self):
        completed_items = self.db.list_downloads(status="Completed")
        count = len(completed_items)
        if count == 0:
            QMessageBox.information(
                self, "Delete Completed", "There are no completed downloads to remove."
            )
            return

        reply = QMessageBox.question(
            self,
            "Delete Completed Downloads",
            f"Are you sure you want to remove all {count} completed downloads from the list?\n\n"
            "Click 'Yes' to remove from list only, or 'Discard' to also delete the files from disk.",
            QMessageBox.Yes | QMessageBox.Discard | QMessageBox.Cancel
        )

        if reply == QMessageBox.Yes:
            self.coordinator.delete_completed(delete_files=False)
            self._refresh_table()
        elif reply == QMessageBox.Discard:
            self.coordinator.delete_completed(delete_files=True)
            self._refresh_table()

    def _verify_selected_hash(self):
        item = self._get_selected_task()
        if not item:
            QMessageBox.information(self, "Verify Hash", "Please select a completed download first.")
            return

        dest = item["destination_path"]
        if not os.path.exists(dest):
            QMessageBox.warning(self, "Verify Hash", "File does not exist on disk.")
            return

        dlg = IntegrityCheckDialog(dest, self)
        dlg.exec()

    def _open_settings(self):
        dlg = SettingsDialog(self.db, self)
        if dlg.exec():
            limit_bps = int(self.db.get_setting("global_speed_limit", "0"))
            self.coordinator.set_global_speed_limit(limit_bps)
            max_concurrent = int(self.db.get_setting("max_concurrent", "3"))
            self.coordinator.max_concurrent_downloads = max_concurrent
            self._apply_theme()
            if hasattr(self, "complete_dlg_menu_act"):
                self.complete_dlg_menu_act.setChecked(self.db.get_setting("show_complete_dlg", "1") == "1")
            if hasattr(self, "progress_dlg_menu_act"):
                self.progress_dlg_menu_act.setChecked(self.db.get_setting("show_progress_dlg", "1") == "1")

    def _on_row_double_clicked(self, index):
        item = self.table_model.get_download_at(index.row())
        if not item:
            return

        action = self.db.get_setting("double_click_action", "default")
        dest = item.get("destination_path", "")
        status = item.get("status")

        if action == "folder":
            self._open_folder(dest)
        elif action == "details":
            dlg = DownloadProgressDialog(item["id"], self.coordinator, parent=None)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
        elif action == "properties":
            self._show_properties(item)
        else:  # default: open file if completed, else progress details
            if status == "Completed":
                if dest and os.path.exists(dest):
                    self._open_file(dest)
                else:
                    QMessageBox.information(self, "File Not Found", f"File does not exist on disk:\n{dest}")
            else:
                dlg = DownloadProgressDialog(item["id"], self.coordinator, parent=None)
                dlg.show()
                dlg.raise_()
                dlg.activateWindow()

    def _show_context_menu(self, pos):
        item = self._get_selected_task()
        if not item:
            return

        menu = QMenu(self)
        status = item.get("status")
        dest = item.get("destination_path", "")
        dest_exists = bool(dest and os.path.exists(dest))

        # 1. Open
        open_act = menu.addAction("Open")
        open_act.setEnabled(dest_exists)
        open_act.triggered.connect(lambda: self._open_file(dest))

        # 2. Open with...
        open_with_act = menu.addAction("Open with...")
        open_with_act.setEnabled(dest_exists)
        open_with_act.triggered.connect(lambda: self._open_file_with(dest))

        # 3. Open folder
        open_folder_act = menu.addAction("Open folder")
        folder_exists = dest_exists or bool(dest and os.path.exists(os.path.dirname(dest)))
        open_folder_act.setEnabled(folder_exists)
        open_folder_act.triggered.connect(lambda: self._open_folder(dest))

        menu.addSeparator()

        # 4. Separate Move and Rename options
        move_act = menu.addAction("Move to...")
        move_act.triggered.connect(self._move_selected)

        rename_act = menu.addAction("Rename (F2)")
        rename_act.triggered.connect(self._rename_selected)

        # 5. Redownload
        redownload_act = menu.addAction("Redownload")
        redownload_act.triggered.connect(lambda: self._redownload_task(item))

        menu.addSeparator()

        # 6. Resume Download
        resume_act = menu.addAction("Resume Download")
        resume_act.setEnabled(status in ("Paused", "Queued", "Error"))
        resume_act.triggered.connect(self._resume_selected)

        # 7. Stop Download
        stop_act = menu.addAction("Stop Download")
        stop_act.setEnabled(status in ("Downloading", "Queued"))
        stop_act.triggered.connect(self._pause_selected)

        menu.addSeparator()

        # 8. Refresh download address
        refresh_act = menu.addAction("Refresh download address...")
        refresh_act.setEnabled(status in ("Paused", "Error", "Downloading"))
        refresh_act.triggered.connect(lambda: self._refresh_download_address(item))

        # Checksum / Verify Hash
        hash_act = menu.addAction("Calculate / Verify Checksum (Hash)...")
        hash_act.setEnabled(dest_exists)
        hash_act.triggered.connect(self._verify_selected_hash)

        menu.addSeparator()

        # 9. Remove
        remove_menu = menu.addMenu("Remove")
        del_list_act = remove_menu.addAction("Remove from list")
        del_list_act.triggered.connect(self._delete_selected_from_list)
        del_disk_act = remove_menu.addAction("Delete file from disk")
        del_disk_act.triggered.connect(self._delete_selected_with_file)

        menu.addSeparator()

        # 10. Add to queue >
        queue_menu = menu.addMenu("Add to queue")
        main_queue_act = queue_menu.addAction("Main download queue")
        main_queue_act.setEnabled(status in ("Paused", "Error"))
        main_queue_act.triggered.connect(lambda: self._queue_task(item["id"]))

        # 11. Delete from queue
        del_queue_act = menu.addAction("Delete from queue")
        del_queue_act.setEnabled(status in ("Queued", "Downloading"))
        del_queue_act.triggered.connect(lambda: self._unqueue_task(item["id"]))

        menu.addSeparator()

        # 12. On Double click >
        dbl_menu = menu.addMenu("On Double click")
        cur_dbl = self.db.get_setting("double_click_action", "default")
        ag = QActionGroup(self)
        ag.setExclusive(True)

        dbl_open_act = dbl_menu.addAction("Open file / progress")
        dbl_open_act.setCheckable(True)
        dbl_open_act.setChecked(cur_dbl == "default")
        dbl_open_act.triggered.connect(lambda: self.db.set_setting("double_click_action", "default"))
        ag.addAction(dbl_open_act)

        dbl_folder_act = dbl_menu.addAction("Open containing folder")
        dbl_folder_act.setCheckable(True)
        dbl_folder_act.setChecked(cur_dbl == "folder")
        dbl_folder_act.triggered.connect(lambda: self.db.set_setting("double_click_action", "folder"))
        ag.addAction(dbl_folder_act)

        dbl_details_act = dbl_menu.addAction("View progress details")
        dbl_details_act.setCheckable(True)
        dbl_details_act.setChecked(cur_dbl == "details")
        dbl_details_act.triggered.connect(lambda: self.db.set_setting("double_click_action", "details"))
        ag.addAction(dbl_details_act)

        dbl_prop_act = dbl_menu.addAction("Properties")
        dbl_prop_act.setCheckable(True)
        dbl_prop_act.setChecked(cur_dbl == "properties")
        dbl_prop_act.triggered.connect(lambda: self.db.set_setting("double_click_action", "properties"))
        ag.addAction(dbl_prop_act)

        menu.addSeparator()

        # 13. Properties
        prop_act = menu.addAction("Properties")
        prop_act.triggered.connect(lambda: self._show_properties(item))

        menu.exec(self.table_view.viewport().mapToGlobal(pos))

    def _open_file(self, filepath: str):
        if filepath and os.path.exists(filepath):
            try:
                os.startfile(filepath)
            except Exception as e:
                QMessageBox.warning(self, "Open File", f"Could not launch file: {e}")
        else:
            QMessageBox.information(self, "File Not Found", f"File does not exist on disk:\n{filepath}")

    def _open_file_with(self, filepath: str):
        if not filepath or not os.path.exists(filepath):
            QMessageBox.information(self, "File Not Found", f"File does not exist on disk:\n{filepath}")
            return
        try:
            import ctypes
            res = ctypes.windll.shell32.ShellExecuteW(None, "openas", filepath, None, None, 1)
            if res <= 32:
                subprocess.run(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", filepath])
        except Exception:
            subprocess.run(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", filepath])

    def _open_folder(self, filepath: str):
        if filepath and os.path.exists(filepath):
            subprocess.run(["explorer", "/select,", os.path.normpath(filepath)])
        else:
            folder = os.path.dirname(filepath) if filepath else ""
            if folder and os.path.exists(folder):
                subprocess.run(["explorer", os.path.normpath(folder)])
            else:
                QMessageBox.warning(self, "Folder Not Found", "Containing folder does not exist.")

    def _move_selected(self):
        item = self._get_selected_task()
        if not item:
            QMessageBox.information(self, "Move to Folder", "Please select a download to move.")
            return
        fresh = self.db.get_download(item["id"]) or item
        dlg = MoveToDialog(fresh, self.db, self.coordinator, self)
        if dlg.exec():
            self._refresh_table()

    def _rename_selected(self):
        item = self._get_selected_task()
        if not item:
            QMessageBox.information(self, "Rename File", "Please select a download to rename.")
            return
        fresh = self.db.get_download(item["id"]) or item
        dlg = RenameDialog(fresh, self.db, self.coordinator, self)
        if dlg.exec():
            self._refresh_table()

    def _move_rename_selected(self):
        self._rename_selected()

    def _redownload_task(self, item: dict):
        reply = QMessageBox.question(
            self,
            "Redownload File",
            f"Are you sure you want to re-download '{item.get('filename')}' from the beginning?\n"
            "This will delete any previously downloaded data and start fresh.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        task_id = item["id"]
        self.coordinator.pause_download(task_id)

        dest_path = item.get("destination_path")
        if dest_path and os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass

        with self.db._lock, self.db._get_connection() as conn:
            cur = conn.execute("SELECT temp_filepath FROM segments WHERE download_id = ?", (task_id,))
            for (p,) in cur.fetchall():
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            conn.execute("DELETE FROM segments WHERE download_id = ?", (task_id,))
            conn.execute(
                """
                UPDATE downloads
                SET downloaded_bytes = 0, speed_bytes_per_sec = 0,
                    status = 'Queued', error_message = NULL
                WHERE id = ?
                """,
                (task_id,)
            )

        self.coordinator.start_download(task_id)
        self._refresh_table()

    def _refresh_download_address(self, item: dict):
        fresh = self.db.get_download(item["id"]) or item
        dlg = RefreshAddressDialog(fresh, self.db, self.coordinator, self)
        if dlg.exec():
            self._refresh_table()

    def _delete_selected_from_list(self):
        items = self._get_selected_tasks()
        if not items:
            return
        count = len(items)
        name_str = f"'{items[0]['filename']}'" if count == 1 else f"{count} selected download(s)"
        reply = QMessageBox.question(
            self,
            "Remove from List",
            f"Are you sure you want to remove {name_str} from the download list?\n(The file on disk will NOT be deleted)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            for it in items:
                self.coordinator.delete_download(it["id"], delete_files=False)
            self._refresh_table()

    def _delete_selected_with_file(self):
        items = self._get_selected_tasks()
        if not items:
            return
        count = len(items)
        name_str = f"'{items[0]['filename']}'" if count == 1 else f"{count} selected download(s)"
        reply = QMessageBox.question(
            self,
            "Delete File from Disk",
            f"Are you sure you want to permanently delete {name_str} and the file(s) from disk?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for it in items:
                self.coordinator.delete_download(it["id"], delete_files=True)
            self._refresh_table()

    def _queue_task(self, task_id: int):
        with self.db._lock, self.db._get_connection() as conn:
            conn.execute("UPDATE downloads SET status = 'Queued' WHERE id = ?", (task_id,))
        self.coordinator.start_download(task_id)
        self._refresh_table()

    def _unqueue_task(self, task_id: int):
        self.coordinator.pause_download(task_id)
        with self.db._lock, self.db._get_connection() as conn:
            conn.execute("UPDATE downloads SET status = 'Paused' WHERE id = ?", (task_id,))
        self._refresh_table()

    def _show_properties(self, item: dict):
        fresh = self.db.get_download(item["id"]) or item
        dlg = PropertiesDialog(fresh, self)
        dlg.exec()

    def _redownload_selected(self):
        item = self._get_selected_task()
        if item:
            self._redownload_task(item)

    def _toggle_pause_resume_selected(self):
        items = self._get_selected_tasks()
        if not items:
            return
        has_downloading = any(it.get("status") == "Downloading" for it in items)
        if has_downloading:
            self._pause_selected()
        else:
            self._resume_selected()

    def _set_speed_limiter(self, enable: bool):
        if enable:
            limit = int(self.db.get_setting("global_speed_limit", "0"))
            if limit <= 0:
                limit = 500 * 1024  # Default 500 KB/s
                self.db.set_setting("global_speed_limit", str(limit))
            self.coordinator.set_global_speed_limit(limit)
            QMessageBox.information(self, "Speed Limiter", f"Speed Limiter turned ON ({format_speed(limit)}).")
        else:
            self.coordinator.set_global_speed_limit(0)
            self.db.set_setting("global_speed_limit", "0")
            QMessageBox.information(self, "Speed Limiter", "Speed Limiter turned OFF (Unlimited speed).")

    def _change_theme(self, theme_name: str):
        self.db.set_setting("theme", theme_name)
        self._apply_theme()

    def _export_urls(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Export Download URLs", "", "Text Files (*.txt);;All Files (*.*)")
        if filename:
            with open(filename, "w", encoding="utf-8") as f:
                for item in self.db.list_downloads():
                    f.write(f"{item['url']}\n")
            QMessageBox.information(self, "Export Complete", f"Successfully exported download links to:\n{filename}")

    def _import_urls(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Import Download URLs", "", "Text Files (*.txt);;All Files (*.*)")
        if filename and os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip().startswith(("http://", "https://"))]
            if urls:
                default_dir = self.db.get_setting("default_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
                for u in urls:
                    try:
                        self.coordinator.add_download(u, destination_dir=default_dir, auto_start=False)
                    except Exception:
                        pass
                self._refresh_table()
                QMessageBox.information(self, "Import Complete", f"Imported {len(urls)} URLs into download list.")
            else:
                QMessageBox.warning(self, "Import", "No valid URLs found in file.")

    def _show_about(self):
        QMessageBox.about(
            self,
            "About Personal Download Manager",
            "<h3>Personal Download Manager (PDM)</h3>"
            "<p><b>Independent Windows-Native Download Accelerator</b></p>"
            "<p>Version 2.0.0 (Production Replica)</p>"
            "<ul>"
            "<li>Multi-connection dynamic chunk slicing engine</li>"
            "<li>Zero-popup instant background browser downloads</li>"
            "<li>Floating HTML5 video grabber & batch link scanner</li>"
            "<li>Full IDM context menu, menu bar, and category hierarchy</li>"
            "<li>SQLite WAL high-concurrency transaction storage</li>"
            "</ul>"
            "<p>© 2026 Personal Download Manager Team</p>"
        )

    def _toggle_progress_dlg(self, enabled: bool):
        self.db.set_setting("show_progress_dlg", "1" if enabled else "0")

    def _toggle_complete_dlg(self, enabled: bool):
        self.db.set_setting("show_complete_dlg", "1" if enabled else "0")

    def _on_task_status_changed(self, task: DownloadTask, new_status: DownloadStatus):
        if new_status == DownloadStatus.DOWNLOADING:
            if self.db.get_setting("show_progress_dlg", "1") == "1":
                self.download_started_signal.emit(task.task_id)
        elif new_status == DownloadStatus.COMPLETED:
            item_info = {
                "id": task.task_id,
                "filename": task.filename,
                "destination_path": task.destination_path,
                "total_bytes": task.total_bytes,
                "url": task.url,
            }
            self.download_completed_signal.emit(item_info)
        elif new_status == DownloadStatus.ERROR:
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONHAND)
            except Exception:
                pass

    def _on_download_started_gui(self, task_id: int):
        # Don't pop up more than 3 dialogs simultaneously during mass batch downloads
        if len(self._active_progress_dialogs) >= 3:
            return

        if task_id in self._active_progress_dialogs:
            dlg = self._active_progress_dialogs[task_id]
            if dlg.isVisible():
                dlg.raise_()
                dlg.activateWindow()
                return

        dlg = DownloadProgressDialog(task_id, self.coordinator, parent=None)
        dlg.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)
        self._active_progress_dialogs[task_id] = dlg
        dlg.finished.connect(lambda: self._active_progress_dialogs.pop(task_id, None))
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_download_completed_gui(self, item_info: dict):
        task_id = item_info.get("id")
        if task_id in self._active_progress_dialogs:
            if self.db.get_setting("auto_close_progress", "1") == "1":
                dlg = self._active_progress_dialogs.pop(task_id, None)
                if dlg and dlg.isVisible():
                    dlg.close()

        if self.db.get_setting("sound_complete", "1") == "1":
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

        show_complete_dlg = self.db.get_setting("show_complete_dlg", "1") == "1"

        if show_complete_dlg:
            rec = self.db.get_download(item_info.get("id"))
            data = rec if rec else item_info
            dlg = DownloadCompleteDialog(data, self.db, parent=None)
            self._active_popups.append(dlg)
            dlg.finished.connect(lambda: self._active_popups.remove(dlg) if dlg in self._active_popups else None)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

        if hasattr(self, "tray_icon") and self.tray_icon.isVisible():
            fn = item_info.get("filename") or "File"
            self.tray_icon.showMessage(
                "Personal Download Manager",
                f"Download completed: {fn}",
                QSystemTrayIcon.MessageIcon.Information,
                3500
            )

        # Check if all downloads completed and on-completion action is active
        comp_action = self.db.get_setting("on_completion_action", "none")
        if comp_action in ("sleep", "shutdown", "exit"):
            active = len(self.coordinator.list_active_tasks())
            queued = len(self.db.list_downloads(status=DownloadStatus.QUEUED.value))
            if active == 0 and queued == 0:
                dlg = ShutdownCountdownDialog(scheduler=self.scheduler, parent=self, action=comp_action)
                dlg.exec()

    def _set_completion_action(self, val: str, label: str):
        self.db.set_setting("on_completion_action", val)
        if hasattr(self, "completion_btn"):
            self.completion_btn.setText(f"⚡ On finish: {label}")

    def _show_completion_popup_menu(self):
        menu = QMenu(self)
        cur_comp = self.db.get_setting("on_completion_action", "none")

        for text_opt, val in [
            ("Do Nothing", "none"),
            ("Sleep Computer", "sleep"),
            ("Shut Down Computer", "shutdown"),
            ("Exit Personal Download Manager", "exit")
        ]:
            act = menu.addAction(text_opt)
            act.setCheckable(True)
            act.setChecked(cur_comp == val)
            label = text_opt.replace("Computer", "").replace("Personal Download Manager", "PDM").strip()
            act.triggered.connect(lambda checked, v=val, l=label: self._set_completion_action(v, l))

        pos = self.completion_btn.mapToGlobal(QPoint(0, -menu.sizeHint().height()))
        menu.exec(pos)

    def _on_exit(self):
        if self.tray_icon:
            self.tray_icon.hide()
        self.scheduler.stop()
        self.coordinator.shutdown()
        QApplication.quit()

    def closeEvent(self, event):
        if self.tray_icon and self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            self.scheduler.stop()
            self.coordinator.shutdown()
            event.accept()
