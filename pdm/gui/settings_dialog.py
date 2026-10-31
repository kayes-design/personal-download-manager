"""Full IDM-parity Options & Configuration Dialog with multi-tab structure."""

import os
import sys
from typing import List, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pdm.storage.db import DatabaseManager

DEFAULT_FILE_TYPES = (
    "3GP 7Z AAC ACE AIF ARJ ASF AVI BIN BZ2 EXE GZ GZIP IMG ISO LZH "
    "M4A M4V MKV MOV MP3 MP4 MPA MPE MPEG MPG MSI MSU OGG OGV PDF "
    "PLJ PPS PPT PPTX QT R0* R1* RA RAR RM RMVB SEA SIT SITX TAR "
    "TIF TIFF WAV WMA WMV Z ZIP"
)


def is_startup_enabled() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )
        val, _ = winreg.QueryValueEx(key, "PersonalDownloadManager")
        winreg.CloseKey(key)
        return bool(val)
    except Exception:
        return False


def set_startup_enabled(enable: bool, exe_path: str):
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        if enable:
            winreg.SetValueEx(key, "PersonalDownloadManager", 0, winreg.REG_SZ, f'"{exe_path}"')
        else:
            try:
                winreg.DeleteValue(key, "PersonalDownloadManager")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


def register_browser_hosts(manifest_json_path: str) -> List[str]:
    import winreg
    targets = [
        (r"Software\Google\Chrome\NativeMessagingHosts\com.pdm.native_host", "Google Chrome"),
        (r"Software\Microsoft\Edge\NativeMessagingHosts\com.pdm.native_host", "Microsoft Edge"),
        (r"Software\Opera Software\Opera GX Stable\NativeMessagingHosts\com.pdm.native_host", "Opera GX"),
        (r"Software\Opera Software\Opera Stable\NativeMessagingHosts\com.pdm.native_host", "Opera"),
        (r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.pdm.native_host", "Brave"),
    ]
    registered = []
    for reg_path, name in targets:
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path)
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, manifest_json_path)
            winreg.CloseKey(key)
            registered.append(name)
        except Exception:
            pass
    return registered


class SettingsDialog(QDialog):
    """Complete IDM-parity Options configuration dialog."""

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Personal Download Manager - Configuration & Options")
        self.resize(580, 480)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(12)

        self.tabs = QTabWidget()

        # Build IDM Tabs
        self._build_general_tab()
        self._build_file_types_tab()
        self._build_save_to_tab()
        self._build_connection_tab()
        self._build_downloads_tab()
        self._build_sounds_tab()

        root_layout.addWidget(self.tabs)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("OK")
        save_btn.clicked.connect(self._save_settings)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        root_layout.addLayout(btn_layout)

    # ----------------- 1. General Tab -----------------
    def _build_general_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)

        # Startup & Monitoring
        grp = QGroupBox("System Integration & Monitoring")
        grp_layout = QVBoxLayout(grp)
        grp_layout.setSpacing(10)

        self.startup_cb = QCheckBox("Launch Personal Download Manager on Windows startup")
        self.browser_integ_cb = QCheckBox("Capture downloads from web browsers (Chrome, Edge, Opera GX, Brave)")
        self.clipboard_cb = QCheckBox("Automatically detect download URLs copied to Clipboard")

        grp_layout.addWidget(self.startup_cb)
        grp_layout.addWidget(self.browser_integ_cb)
        grp_layout.addWidget(self.clipboard_cb)
        layout.addWidget(grp)

        # Browser Integration One-Click Registration
        browser_grp = QGroupBox("Browser Native Messaging Integration")
        b_layout = QVBoxLayout(browser_grp)
        b_layout.setSpacing(8)

        lbl = QLabel(
            "Enables floating video download buttons and automatic download interception in Chrome, Edge, and Opera."
        )
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        b_layout.addWidget(lbl)

        btn_reg = QPushButton("Register / Repair Browser Integration")
        btn_reg.setObjectName("secondaryBtn")
        btn_reg.clicked.connect(self._on_repair_browser_integration)
        b_layout.addWidget(btn_reg)
        layout.addWidget(browser_grp)

        # Theme
        theme_grp = QGroupBox("Interface Appearance")
        t_layout = QFormLayout(theme_grp)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark (Windows 11 Slate)", "Light"])
        t_layout.addRow("Interface Theme:", self.theme_combo)
        layout.addWidget(theme_grp)

        layout.addStretch()
        self.tabs.addTab(tab, "General")

    # ----------------- 2. File Types Tab -----------------
    def _build_file_types_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        lbl_ext = QLabel("Automatically start downloading the following file types:")
        lbl_ext.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl_ext)

        self.ext_input = QPlainTextEdit()
        self.ext_input.setMaximumHeight(90)
        self.ext_input.setPlaceholderText("e.g. MP4 MKV ZIP RAR EXE ISO PDF")
        layout.addWidget(self.ext_input)

        lbl_ign = QLabel("Don't start downloading automatically from following addresses / sites:")
        lbl_ign.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl_ign)

        self.ignore_sites_input = QPlainTextEdit()
        self.ignore_sites_input.setPlaceholderText("One address per line, e.g.:\n*.update.microsoft.com\n*.windowsupdate.com")
        layout.addWidget(self.ignore_sites_input)

        self.tabs.addTab(tab, "File Types")

    # ----------------- 3. Save To Tab -----------------
    def _build_save_to_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        # Default Directory
        def_grp = QGroupBox("Default Download Directory")
        def_layout = QHBoxLayout(def_grp)
        self.dir_input = QLineEdit()
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(lambda: self._browse_dir(self.dir_input))
        def_layout.addWidget(self.dir_input)
        def_layout.addWidget(browse_btn)
        layout.addWidget(def_grp)

        # Category Folders
        cat_grp = QGroupBox("Category-Specific Save Folders")
        cat_form = QFormLayout(cat_grp)
        cat_form.setSpacing(8)

        self.cat_dirs = {}
        for cat in ["Video", "Music", "Compressed", "Documents", "Programs"]:
            row_layout = QHBoxLayout()
            le = QLineEdit()
            b = QPushButton("Browse...")
            b.setObjectName("secondaryBtn")
            b.clicked.connect(lambda _, target=le: self._browse_dir(target))
            row_layout.addWidget(le)
            row_layout.addWidget(b)
            cat_form.addRow(f"{cat}:", row_layout)
            self.cat_dirs[cat] = le

        layout.addWidget(cat_grp)

        # Temporary segment files directory
        temp_grp = QGroupBox("Temporary Directory (for multi-segmented .pdmpart files)")
        temp_layout = QHBoxLayout(temp_grp)
        self.temp_dir_input = QLineEdit()
        temp_browse = QPushButton("Browse...")
        temp_browse.setObjectName("secondaryBtn")
        temp_browse.clicked.connect(lambda: self._browse_dir(self.temp_dir_input))
        temp_layout.addWidget(self.temp_dir_input)
        temp_layout.addWidget(temp_browse)
        layout.addWidget(temp_grp)

        self.tabs.addTab(tab, "Save To")

    # ----------------- 4. Connection Tab -----------------
    def _build_connection_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)

        conn_grp = QGroupBox("Connection & Speed Tuning")
        conn_form = QFormLayout(conn_grp)
        conn_form.setSpacing(10)

        # Connection type
        self.conn_type_combo = QComboBox()
        self.conn_type_combo.addItems([
            "High speed (Direct connection / Broadband / Wi-Fi)",
            "Medium speed",
            "Low speed (Mobile / 2G / 3G)"
        ])
        conn_form.addRow("Connection Type / Speed:", self.conn_type_combo)

        # Max connections per file (up to 32 parallel segments)
        self.conns_combo = QComboBox()
        self.conns_combo.addItems(["1", "2", "4", "8", "16", "24", "32"])
        conn_form.addRow("Max. Connection Number / File:", self.conns_combo)

        # Max concurrent tasks
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(3)
        conn_form.addRow("Max. Concurrent Active Downloads:", self.concurrent_spin)

        layout.addWidget(conn_grp)

        # Speed Limiter & Smart Idle
        lim_grp = QGroupBox("Speed Limiter & Smart Idle Boost")
        lim_form = QFormLayout(lim_grp)
        self.limiter_enabled_cb = QCheckBox("Enable Speed Limiter by default")
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(10, 500000)
        self.speed_spin.setSuffix(" KB/s")
        self.speed_spin.setValue(500)
        lim_form.addRow(self.limiter_enabled_cb)
        lim_form.addRow("Maximum Download Speed:", self.speed_spin)

        self.smart_idle_cb = QCheckBox("⚡ Smart Idle Boost: Auto-unthrottle to maximum speed when PC is idle")
        self.smart_idle_timeout_spin = QSpinBox()
        self.smart_idle_timeout_spin.setRange(10, 600)
        self.smart_idle_timeout_spin.setSuffix(" seconds")
        self.smart_idle_timeout_spin.setValue(60)
        lim_form.addRow(self.smart_idle_cb)
        lim_form.addRow("Inactivity Trigger Timeout:", self.smart_idle_timeout_spin)
        layout.addWidget(lim_grp)

        layout.addStretch()
        self.tabs.addTab(tab, "Connection")

    # ----------------- 5. Downloads Tab -----------------
    def _build_downloads_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)

        diag_grp = QGroupBox("Dialog Options")
        d_layout = QVBoxLayout(diag_grp)
        d_layout.setSpacing(8)

        self.show_start_dlg_cb = QCheckBox("Show start download dialog (Add URL confirmation)")
        self.show_progress_dlg_cb = QCheckBox("Show download progress dialog (compact card)")
        self.show_complete_dlg_cb = QCheckBox("Show download complete dialog")
        self.auto_close_progress_cb = QCheckBox("Automatically close download progress dialog on completion")

        d_layout.addWidget(self.show_start_dlg_cb)
        d_layout.addWidget(self.show_progress_dlg_cb)
        d_layout.addWidget(self.show_complete_dlg_cb)
        d_layout.addWidget(self.auto_close_progress_cb)
        layout.addWidget(diag_grp)

        conflict_grp = QGroupBox("File Name Conflict Resolution")
        c_layout = QFormLayout(conflict_grp)
        self.conflict_combo = QComboBox()
        self.conflict_combo.addItems([
            "Auto-rename file (e.g. filename(1).ext)",
            "Overwrite existing file",
            "Ask user every time"
        ])
        c_layout.addRow("When file already exists:", self.conflict_combo)
        layout.addWidget(conflict_grp)

        layout.addStretch()
        self.tabs.addTab(tab, "Downloads")

    # ----------------- 6. Sounds Tab -----------------
    def _build_sounds_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)

        snd_grp = QGroupBox("Audio Notifications")
        s_layout = QVBoxLayout(snd_grp)
        s_layout.setSpacing(10)

        self.sound_complete_cb = QCheckBox("Play sound when a download completes")
        self.sound_error_cb = QCheckBox("Play sound when a download fails / errors")
        self.sound_queue_cb = QCheckBox("Play sound when download queue finishes")

        s_layout.addWidget(self.sound_complete_cb)
        s_layout.addWidget(self.sound_error_cb)
        s_layout.addWidget(self.sound_queue_cb)

        test_btn = QPushButton("🔊 Test Notification Chime")
        test_btn.setObjectName("secondaryBtn")
        test_btn.clicked.connect(self._test_sound)
        s_layout.addWidget(test_btn)

        layout.addWidget(snd_grp)
        layout.addStretch()
        self.tabs.addTab(tab, "Sounds")

    # ----------------- Helpers & Load/Save -----------------
    def _browse_dir(self, target_line_edit: QLineEdit):
        chosen = QFileDialog.getExistingDirectory(self, "Select Directory", target_line_edit.text())
        if chosen:
            target_line_edit.setText(os.path.abspath(chosen))

    def _test_sound(self):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception as e:
            QMessageBox.information(self, "Sound Test", f"Could not play sound: {e}")

    def _on_repair_browser_integration(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        manifest_path = os.path.join(base_dir, "pdm", "browser_bridge", "com.pdm.native_host.json")
        if not os.path.exists(manifest_path):
            QMessageBox.warning(self, "Manifest Not Found", f"Cannot find host manifest at:\n{manifest_path}")
            return

        browsers = register_browser_hosts(manifest_path)
        if browsers:
            QMessageBox.information(
                self,
                "Integration Repaired",
                f"Successfully registered PDM Native Messaging Host for:\n• " + "\n• ".join(browsers) +
                "\n\nBrowser extension is now fully connected."
            )
        else:
            QMessageBox.warning(self, "Registration Error", "Could not register native host in Windows Registry.")

    def _load_settings(self):
        # 1. General
        self.startup_cb.setChecked(is_startup_enabled())
        self.browser_integ_cb.setChecked(self.db.get_setting("browser_integration", "1") == "1")
        self.clipboard_cb.setChecked(self.db.get_setting("clipboard_monitor", "1") == "1")

        theme = self.db.get_setting("theme", "Dark")
        if "light" in theme.lower():
            self.theme_combo.setCurrentIndex(1)
        else:
            self.theme_combo.setCurrentIndex(0)

        # 2. File Types
        self.ext_input.setPlainText(self.db.get_setting("file_types", DEFAULT_FILE_TYPES))
        self.ignore_sites_input.setPlainText(self.db.get_setting("ignore_sites", ""))

        # 3. Save To
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        self.dir_input.setText(self.db.get_setting("default_dir", default_dir))
        for cat, le in self.cat_dirs.items():
            cat_def = os.path.join(default_dir, cat)
            le.setText(self.db.get_setting(f"save_dir_{cat.lower()}", cat_def))
        self.temp_dir_input.setText(self.db.get_setting("temp_dir", os.path.join(default_dir, ".pdmtemp")))

        # 4. Connection
        conns = self.db.get_setting("default_connections", "8")
        idx = self.conns_combo.findText(conns)
        if idx >= 0:
            self.conns_combo.setCurrentIndex(idx)
        else:
            self.conns_combo.setCurrentIndex(3)  # 8

        self.concurrent_spin.setValue(int(self.db.get_setting("max_concurrent", "3")))
        lim_enabled = self.db.get_setting("speed_limiter_enabled", "0") == "1"
        self.limiter_enabled_cb.setChecked(lim_enabled)
        limit_kb = int(self.db.get_setting("global_speed_limit", "0")) // 1024
        self.speed_spin.setValue(max(50, limit_kb if limit_kb > 0 else 500))
        self.smart_idle_cb.setChecked(self.db.get_setting("smart_idle_boost", "1") == "1")
        self.smart_idle_timeout_spin.setValue(int(self.db.get_setting("smart_idle_timeout_sec", "60")))

        # 5. Downloads
        self.show_start_dlg_cb.setChecked(self.db.get_setting("show_start_dlg", "1") == "1")
        self.show_progress_dlg_cb.setChecked(self.db.get_setting("show_progress_dlg", "1") == "1")
        self.show_complete_dlg_cb.setChecked(self.db.get_setting("show_complete_dlg", "1") == "1")
        self.auto_close_progress_cb.setChecked(self.db.get_setting("auto_close_progress", "1") == "1")
        conflict_idx = int(self.db.get_setting("conflict_action", "0"))
        self.conflict_combo.setCurrentIndex(min(max(0, conflict_idx), 2))

        # 6. Sounds
        self.sound_complete_cb.setChecked(self.db.get_setting("sound_complete", "1") == "1")
        self.sound_error_cb.setChecked(self.db.get_setting("sound_error", "1") == "1")
        self.sound_queue_cb.setChecked(self.db.get_setting("sound_queue", "1") == "1")

    def _save_settings(self):
        # 1. General
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        exe_path = os.path.join(base_dir, "dist", "PDM", "PDM.exe")
        set_startup_enabled(self.startup_cb.isChecked(), exe_path)

        self.db.set_setting("browser_integration", "1" if self.browser_integ_cb.isChecked() else "0")
        self.db.set_setting("clipboard_monitor", "1" if self.clipboard_cb.isChecked() else "0")
        theme_str = "Light" if self.theme_combo.currentIndex() == 1 else "Dark"
        self.db.set_setting("theme", theme_str)

        # 2. File Types
        self.db.set_setting("file_types", self.ext_input.toPlainText().strip() or DEFAULT_FILE_TYPES)
        self.db.set_setting("ignore_sites", self.ignore_sites_input.toPlainText().strip())

        # 3. Save To
        self.db.set_setting("default_dir", self.dir_input.text().strip())
        for cat, le in self.cat_dirs.items():
            self.db.set_setting(f"save_dir_{cat.lower()}", le.text().strip())
        self.db.set_setting("temp_dir", self.temp_dir_input.text().strip())

        # 4. Connection
        self.db.set_setting("default_connections", self.conns_combo.currentText())
        self.db.set_setting("max_concurrent", str(self.concurrent_spin.value()))
        self.db.set_setting("speed_limiter_enabled", "1" if self.limiter_enabled_cb.isChecked() else "0")
        limit_val = (self.speed_spin.value() * 1024) if self.limiter_enabled_cb.isChecked() else 0
        self.db.set_setting("global_speed_limit", str(limit_val))
        self.db.set_setting("smart_idle_boost", "1" if self.smart_idle_cb.isChecked() else "0")
        self.db.set_setting("smart_idle_timeout_sec", str(self.smart_idle_timeout_spin.value()))

        # 5. Downloads
        self.db.set_setting("show_start_dlg", "1" if self.show_start_dlg_cb.isChecked() else "0")
        self.db.set_setting("show_progress_dlg", "1" if self.show_progress_dlg_cb.isChecked() else "0")
        self.db.set_setting("show_complete_dlg", "1" if self.show_complete_dlg_cb.isChecked() else "0")
        self.db.set_setting("auto_close_progress", "1" if self.auto_close_progress_cb.isChecked() else "0")
        self.db.set_setting("conflict_action", str(self.conflict_combo.currentIndex()))

        # 6. Sounds
        self.db.set_setting("sound_complete", "1" if self.sound_complete_cb.isChecked() else "0")
        self.db.set_setting("sound_error", "1" if self.sound_error_cb.isChecked() else "0")
        self.db.set_setting("sound_queue", "1" if self.sound_queue_cb.isChecked() else "0")

        self.accept()
