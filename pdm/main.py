"""Application entrypoint for Personal Download Manager."""

import argparse
import os
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from pdm.core.coordinator import DownloadCoordinator
from pdm.gui.main_window import MainWindow
from pdm.storage.db import DatabaseManager


def get_default_data_dir() -> str:
    """Return local app data directory for PDM."""
    app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    pdm_dir = os.path.join(app_data, "PersonalDownloadManager")
    os.makedirs(pdm_dir, exist_ok=True)
    return pdm_dir


def main():
    parser = argparse.ArgumentParser(description="Personal Download Manager (PDM)")
    parser.add_argument("-d", "--url", type=str, help="Download a URL immediately")
    parser.add_argument("-p", "--path", type=str, help="Directory to save file")
    parser.add_argument("-f", "--name", type=str, help="Custom filename")
    parser.add_argument("--tray", action="store_true", help="Start minimized to system tray")
    parser.add_argument("--portable", action="store_true", help="Store DB in current working directory")
    args = parser.parse_args()

    # Determine DB location
    if args.portable:
        db_path = os.path.abspath("downloads.db")
    else:
        db_path = os.path.join(get_default_data_dir(), "downloads.db")

    # 0. Single-Instance Check via Windows Named Mutex
    mutex = None
    if sys.platform == "win32":
        try:
            import ctypes
            MUTEX_NAME = "Local\\PersonalDownloadManager_SingleInstance_Mutex"
            ERROR_ALREADY_EXISTS = 183
            mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
            if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
                # If command-line download URL was provided, route to existing instance via DB
                if args.url:
                    from pdm.storage.db import DatabaseManager
                    temp_db = DatabaseManager(db_path)
                    default_dir = args.path or temp_db.get_setting(
                        "default_dir", os.path.join(os.path.expanduser("~"), "Downloads")
                    )
                    temp_db.add_incoming_request(
                        url=args.url,
                        filename=args.name or "",
                        auto_start=True
                    )

                # Restore and focus existing PDM window
                hwnd = ctypes.windll.user32.FindWindowW(None, "Personal Download Manager")
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    ctypes.windll.user32.SetForegroundWindow(hwnd)

                sys.exit(0)
        except Exception:
            pass

    # Qt Application Setup with High DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Windows Taskbar Icon & App Identity (AppUserModelID)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "pdm.personal.download.manager.app"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Personal Download Manager")
    app.setOrganizationName("PersonalDownloadManager")

    # Set Application Icon
    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_candidates = [
        os.path.join(base_dir, "gui", "resources", "icon.ico"),
        os.path.join(base_dir, "gui", "resources", "app_icon.png"),
        os.path.join(os.path.dirname(base_dir), "icon.ico"),
        os.path.join(getattr(sys, "_MEIPASS", ""), "icon.ico"),
        os.path.join(getattr(sys, "_MEIPASS", ""), "pdm", "gui", "resources", "icon.ico"),
        os.path.join(os.path.dirname(sys.executable), "icon.ico"),
        os.path.join(os.path.dirname(sys.executable), "_internal", "icon.ico"),
    ]
    for p in icon_candidates:
        if p and os.path.exists(p):
            ico = QIcon(p)
            if not ico.isNull():
                app.setWindowIcon(ico)
                break

    # Storage & Coordinator
    db = DatabaseManager(db_path)
    max_conns = int(db.get_setting("max_concurrent", "3"))
    speed_limit = int(db.get_setting("global_speed_limit", "0"))

    coordinator = DownloadCoordinator(
        db=db,
        max_concurrent_downloads=max_conns,
        global_speed_limit_bps=speed_limit
    )

    # Main Window
    window = MainWindow(coordinator)

    # Handle command-line download request
    if args.url:
        default_dir = args.path or db.get_setting(
            "default_dir", os.path.join(os.path.expanduser("~"), "Downloads")
        )
        try:
            coordinator.add_download(
                url=args.url,
                destination_dir=default_dir,
                filename=args.name,
                auto_start=True
            )
        except Exception as e:
            print(f"Error adding download: {e}", file=sys.stderr)

    if not args.tray:
        window.show()

    exit_code = app.exec()
    if window.tray_icon:
        window.tray_icon.hide()
    coordinator.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
