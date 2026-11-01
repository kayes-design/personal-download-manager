"""Personal Download Manager - Standalone Setup & Installer Wizard."""

import os
import sys
import zipfile
import subprocess
import winreg
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


INSTALLER_STYLESHEET = """
QDialog {
    background-color: #0f172a;
    color: #f8fafc;
    font-family: "Segoe UI", -apple-system, sans-serif;
}
#mainCard {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
}
QLabel {
    color: #94a3b8;
    font-size: 12px;
}
QLabel#titleLabel {
    color: #f8fafc;
    font-size: 18px;
    font-weight: 700;
}
QLabel#subLabel {
    color: #64748b;
    font-size: 12px;
}
QLabel#sectionTitle {
    color: #cbd5e1;
    font-size: 13px;
    font-weight: 600;
}
QLineEdit {
    background-color: #0b1120;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 12px;
    color: #f8fafc;
    font-size: 12px;
}
QLineEdit:focus {
    border-color: #38bdf8;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #1d4ed8);
    color: #ffffff;
    border: none;
    border-radius: 6px;
    font-weight: 600;
    font-size: 13px;
    padding: 9px 22px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb);
}
QPushButton:pressed {
    background-color: #1d4ed8;
}
QPushButton#secondaryBtn {
    background-color: #334155;
    border: 1px solid #475569;
    color: #cbd5e1;
    font-weight: 500;
    font-size: 12px;
    padding: 7px 14px;
}
QPushButton#secondaryBtn:hover {
    background-color: #475569;
    border-color: #64748b;
    color: #ffffff;
}
QProgressBar {
    background-color: #0b1120;
    border: 1px solid #334155;
    border-radius: 6px;
    text-align: center;
    color: #f8fafc;
    font-weight: bold;
    font-size: 11px;
    height: 20px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #06b6d4);
    border-radius: 5px;
}
QCheckBox {
    color: #cbd5e1;
    font-size: 12px;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #475569;
    border-radius: 4px;
    background-color: #0b1120;
}
QCheckBox::indicator:checked {
    background-color: #2563eb;
    border-color: #38bdf8;
}
"""


def get_default_install_dir() -> str:
    app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    return os.path.join(app_data, "Programs", "PersonalDownloadManager")


def get_payload_zip_path() -> Optional[str]:
    candidates = [
        os.path.join(getattr(sys, "_MEIPASS", ""), "payload.zip"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "payload.zip"),
        os.path.join(os.path.dirname(sys.executable), "payload.zip"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


class InstallWorker(QThread):
    progress = Signal(int, str)
    finished_success = Signal()
    error_occurred = Signal(str)

    def __init__(self, target_dir: str, create_desktop_shortcut: bool, register_browsers: bool):
        super().__init__()
        self.target_dir = target_dir
        self.create_desktop_shortcut = create_desktop_shortcut
        self.register_browsers = register_browsers

    def run(self):
        try:
            # 1. Stop any running PDM process
            self.progress.emit(5, "Checking for running instances...")
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", 'Get-Process | Where-Object { $_.ProcessName -match "pdm" } | Stop-Process -Force -ErrorAction SilentlyContinue'],
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    timeout=5
                )
            except Exception:
                pass

            # 2. Extract payload.zip
            self.progress.emit(15, "Extracting application components...")
            payload_path = get_payload_zip_path()
            if not payload_path or not os.path.exists(payload_path):
                raise RuntimeError("Setup payload.zip not found! Please run installer with payload bundled.")

            os.makedirs(self.target_dir, exist_ok=True)

            with zipfile.ZipFile(payload_path, "r") as z:
                total_files = len(z.infolist())
                extracted = 0
                for info in z.infolist():
                    z.extract(info, self.target_dir)
                    extracted += 1
                    pct = 15 + int((extracted / total_files) * 60)
                    if extracted % 25 == 0 or extracted == total_files:
                        self.progress.emit(pct, f"Extracting: {os.path.basename(info.filename) or 'components'}...")

            app_dir = os.path.join(self.target_dir, "app")
            ext_dir = os.path.join(self.target_dir, "extension")
            exe_path = os.path.join(app_dir, "PDM.exe")

            # 3. Create pdm_host.exe and native host json
            self.progress.emit(80, "Configuring Browser Integration Bridge...")
            host_exe_path = os.path.join(self.target_dir, "pdm_host.exe")
            host_bat_path = os.path.join(self.target_dir, "pdm_host.bat")
            with open(host_bat_path, "w", encoding="utf-8") as f:
                f.write('@echo off\ncd /d "%~dp0app"\nPDM.exe --native-host\n')

            target_host_binary = host_exe_path if os.path.exists(host_exe_path) else host_bat_path
            escaped_host_binary = target_host_binary.replace("\\", "\\\\")
            json_manifest_path = os.path.join(self.target_dir, "com.pdm.native_host.json")
            json_content = f'''{{
  "name": "com.pdm.native_host",
  "description": "Personal Download Manager Native Messaging Host",
  "path": "{escaped_host_binary}",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://jdkngeepecifohmmoeldklojellkdgmm/",
    "chrome-extension://flgedopgbfolfficdllcjacamhgkhkga/",
    "chrome-extension://ekmmelpnmfdegjhnmadddcfjcahpajnm/",
    "chrome-extension://ngpampappnmepgilojfohadhhmbhlaek/",
    "chrome-extension://piegnlcflnnmndgaajegakkfppnddabe/"
  ]
}}'''
            with open(json_manifest_path, "w", encoding="utf-8") as f:
                f.write(json_content)

            # 4. Register in Windows Registry
            if self.register_browsers and sys.platform == "win32":
                self.progress.emit(88, "Registering Chrome, Edge, and Opera GX integration...")
                browser_keys = [
                    r"Software\Google\Chrome\NativeMessagingHosts\com.pdm.native_host",
                    r"Software\Microsoft\Edge\NativeMessagingHosts\com.pdm.native_host",
                    r"Software\Opera Software\NativeMessagingHosts\com.pdm.native_host",
                    r"Software\Opera Software\Opera Stable\NativeMessagingHosts\com.pdm.native_host",
                    r"Software\Opera Software\Opera GX Stable\NativeMessagingHosts\com.pdm.native_host",
                    r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.pdm.native_host",
                    r"Software\Vivaldi\NativeMessagingHosts\com.pdm.native_host",
                ]
                for k in browser_keys:
                    try:
                        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, k) as reg_key:
                            winreg.SetValueEx(reg_key, "", 0, winreg.REG_SZ, json_manifest_path)
                    except Exception:
                        pass

            # 5. Create Desktop and Start Menu Shortcuts
            if sys.platform == "win32":
                self.progress.emit(94, "Creating shortcuts...")
                icon_path = os.path.join(app_dir, "icon.ico")
                if not os.path.exists(icon_path):
                    icon_path = os.path.join(app_dir, "_internal", "icon.ico")

                def create_shortcut(lnk_path, target_exe, work_dir, ico):
                    ps_cmd = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{lnk_path}")
$Shortcut.TargetPath = "{target_exe}"
$Shortcut.WorkingDirectory = "{work_dir}"
$Shortcut.IconLocation = "{ico}"
$Shortcut.Description = "Personal Download Manager (PDM)"
$Shortcut.Save()
'''
                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command", ps_cmd],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        timeout=5
                    )

                if self.create_desktop_shortcut:
                    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
                    lnk = os.path.join(desktop, "Personal Download Manager.lnk")
                    create_shortcut(lnk, exe_path, app_dir, icon_path)

                # Start Menu shortcut
                start_menu = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs")
                start_lnk = os.path.join(start_menu, "Personal Download Manager.lnk")
                create_shortcut(start_lnk, exe_path, app_dir, icon_path)

            self.progress.emit(100, "Installation Complete!")
            self.finished_success.emit()

        except Exception as e:
            self.error_occurred.emit(str(e))


class InstallerWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Personal Download Manager Setup")
        self.setFixedSize(580, 420)
        self.setStyleSheet(INSTALLER_STYLESHEET)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)

        # Set Window Icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header Card
        header_card = QFrame()
        header_card.setObjectName("mainCard")
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(16, 14, 16, 14)
        h_layout.setSpacing(14)

        # Icon
        icon_lbl = QLabel()
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            icon_lbl.setPixmap(QIcon(icon_path).pixmap(48, 48))
        else:
            icon_lbl.setText("⚡")
            icon_lbl.setStyleSheet("font-size: 32px;")
        h_layout.addWidget(icon_lbl)

        # Title
        t_layout = QVBoxLayout()
        t_layout.setSpacing(2)
        title_lbl = QLabel("Personal Download Manager")
        title_lbl.setObjectName("titleLabel")
        sub_lbl = QLabel("High-Speed Acceleration & Universal Media Grabber Setup")
        sub_lbl.setObjectName("subLabel")
        t_layout.addWidget(title_lbl)
        t_layout.addWidget(sub_lbl)
        h_layout.addLayout(t_layout)
        h_layout.addStretch()

        main_layout.addWidget(header_card)

        # Stacked Pages
        self.stack = QStackedWidget()

        # Page 1: Configuration
        self.page_config = QWidget()
        p1_layout = QVBoxLayout(self.page_config)
        p1_layout.setContentsMargins(0, 8, 0, 0)
        p1_layout.setSpacing(12)

        dir_title = QLabel("Installation Directory:")
        dir_title.setObjectName("sectionTitle")
        p1_layout.addWidget(dir_title)

        dir_box = QHBoxLayout()
        dir_box.setSpacing(8)
        self.dir_input = QLineEdit(get_default_install_dir())
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self._on_browse_dir)
        dir_box.addWidget(self.dir_input)
        dir_box.addWidget(browse_btn)
        p1_layout.addLayout(dir_box)

        p1_layout.addSpacing(6)
        opts_title = QLabel("Setup Options:")
        opts_title.setObjectName("sectionTitle")
        p1_layout.addWidget(opts_title)

        self.cb_desktop = QCheckBox("Create Desktop Shortcut")
        self.cb_desktop.setChecked(True)
        p1_layout.addWidget(self.cb_desktop)

        self.cb_browsers = QCheckBox("Automatically register integration for Chrome, Edge, and Opera GX")
        self.cb_browsers.setChecked(True)
        p1_layout.addWidget(self.cb_browsers)

        self.cb_launch = QCheckBox("Launch Personal Download Manager after setup")
        self.cb_launch.setChecked(True)
        p1_layout.addWidget(self.cb_launch)

        p1_layout.addStretch()

        # Button row 1
        b_row1 = QHBoxLayout()
        b_row1.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        self.install_btn = QPushButton("Install Now")
        self.install_btn.setDefault(True)
        self.install_btn.clicked.connect(self._start_install)
        b_row1.addWidget(cancel_btn)
        b_row1.addWidget(self.install_btn)
        p1_layout.addLayout(b_row1)

        self.stack.addWidget(self.page_config)

        # Page 2: Progress
        self.page_progress = QWidget()
        p2_layout = QVBoxLayout(self.page_progress)
        p2_layout.setContentsMargins(0, 20, 0, 0)
        p2_layout.setSpacing(14)

        self.status_lbl = QLabel("Installing...")
        self.status_lbl.setObjectName("sectionTitle")
        p2_layout.addWidget(self.status_lbl)

        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        p2_layout.addWidget(self.prog_bar)

        p2_layout.addStretch()
        self.stack.addWidget(self.page_progress)

        # Page 3: Success
        self.page_success = QWidget()
        p3_layout = QVBoxLayout(self.page_success)
        p3_layout.setContentsMargins(0, 16, 0, 0)
        p3_layout.setSpacing(12)

        succ_title = QLabel("✓ Installation Complete!")
        succ_title.setObjectName("titleLabel")
        succ_title.setStyleSheet("color: #10b981; font-size: 19px; font-weight: bold;")
        p3_layout.addWidget(succ_title)

        succ_desc = QLabel(
            "Personal Download Manager and its Browser Integration have been\n"
            "successfully installed and configured on your computer."
        )
        succ_desc.setStyleSheet("color: #cbd5e1; font-size: 13px; line-height: 1.5;")
        p3_layout.addWidget(succ_desc)

        ext_note = QLabel(
            "💡 Browser Tip: If you haven't enabled the extension in Chrome/Edge,\n"
            "simply visit chrome://extensions, turn on Developer Mode, and click 'Load unpacked'\n"
            "selecting the installed 'extension' folder."
        )
        ext_note.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 10px; color: #38bdf8; font-size: 11px;")
        p3_layout.addWidget(ext_note)

        p3_layout.addStretch()

        b_row3 = QHBoxLayout()
        b_row3.addStretch()
        self.open_ext_btn = QPushButton("Open Extensions Folder")
        self.open_ext_btn.setObjectName("secondaryBtn")
        self.open_ext_btn.clicked.connect(self._open_ext_folder)
        b_row3.addWidget(self.open_ext_btn)

        finish_btn = QPushButton("Finish")
        finish_btn.setDefault(True)
        finish_btn.clicked.connect(self._on_finish)
        b_row3.addWidget(finish_btn)
        p3_layout.addLayout(b_row3)

        self.stack.addWidget(self.page_success)

        main_layout.addWidget(self.stack)

    def _on_browse_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Select Install Directory", self.dir_input.text())
        if chosen:
            self.dir_input.setText(chosen)

    def _start_install(self):
        target = self.dir_input.text().strip()
        if not target:
            return

        self.stack.setCurrentWidget(self.page_progress)
        self.worker = InstallWorker(
            target_dir=target,
            create_desktop_shortcut=self.cb_desktop.isChecked(),
            register_browsers=self.cb_browsers.isChecked()
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_success.connect(self._on_success)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, val: int, msg: str):
        self.prog_bar.setValue(val)
        self.status_lbl.setText(msg)

    def _on_success(self):
        self.stack.setCurrentWidget(self.page_success)
        # Auto-popup browser extensions page and extensions folder side-by-side
        try:
            target = self.dir_input.text().strip()
            ext_dir = os.path.join(target, "extension")
            if os.path.exists(ext_dir):
                os.startfile(ext_dir)
            ps_cmd = 'Start-Process msedge "edge://extensions" -ErrorAction SilentlyContinue; if (!$?) { Start-Process chrome "chrome://extensions" }'
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps_cmd], creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass

    def _on_error(self, err: str):
        self.status_lbl.setText(f"Installation Error: {err}")
        self.status_lbl.setStyleSheet("color: #ef4444;")

    def _open_ext_folder(self):
        target = self.dir_input.text().strip()
        ext_dir = os.path.join(target, "extension")
        if os.path.exists(ext_dir):
            os.startfile(ext_dir)

    def _on_finish(self):
        if self.cb_launch.isChecked():
            target = self.dir_input.text().strip()
            exe_path = os.path.join(target, "app", "PDM.exe")
            if os.path.exists(exe_path):
                subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))
        self.accept()


def main():
    app = QApplication(sys.argv)
    win = InstallerWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
