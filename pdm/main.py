"""Application entrypoint for Personal Download Manager."""

import argparse
import os
import sys

# Ensure repository root is on sys.path so direct script execution works
_repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_dir not in sys.path:
    sys.path.insert(0, _repo_dir)

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
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
    parser.add_argument("--native-host", action="store_true", help="Run as browser native messaging host")
    args = parser.parse_args()

    # Browser Native Messaging stdio mode
    if args.native_host:
        from pdm.browser_bridge.native_host import main as native_host_main
        native_host_main()
        sys.exit(0)

    # Determine DB location
    if args.portable:
        db_path = os.path.abspath("downloads.db")
    else:
        db_path = os.path.join(get_default_data_dir(), "downloads.db")

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

    # 0. Single-Instance Check via Qt Local IPC Socket
    SOCKET_NAME = "PersonalDownloadManager_SingleInstance_IPC"
    ipc_socket = QLocalSocket()
    ipc_socket.connectToServer(SOCKET_NAME)
    connected = ipc_socket.waitForConnected(400)
    if connected:
        # Existing instance is running!
        # If launched by user without --tray, request the running instance to show its window
        cmd = "TRAY" if args.tray else "SHOW"
        payload = f"{cmd}|{args.url or ''}|{args.path or ''}|{args.name or ''}"
        ipc_socket.write(payload.encode("utf-8"))
        ipc_socket.waitForBytesWritten(1000)
        ipc_socket.disconnectFromServer()
        sys.exit(0)

    # Primary instance: Remove any stale socket file and listen
    QLocalServer.removeServer(SOCKET_NAME)
    ipc_server = QLocalServer()
    listened = ipc_server.listen(SOCKET_NAME)

    # Maintain Windows Kernel Mutex for non-Qt callers
    mutex = None
    if sys.platform == "win32":
        try:
            import ctypes
            MUTEX_NAME = "Local\\PersonalDownloadManager_SingleInstance_Mutex"
            mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        except Exception:
            pass

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
    theme = db.get_setting("theme", "dark")
    from pdm.gui.theme import DARK_THEME_QSS, LIGHT_THEME_QSS
    app.setStyleSheet(LIGHT_THEME_QSS if theme == "light" else DARK_THEME_QSS)

    max_conns = int(db.get_setting("max_concurrent", "3"))
    speed_limit = int(db.get_setting("global_speed_limit", "0"))

    coordinator = DownloadCoordinator(
        db=db,
        max_concurrent_downloads=max_conns,
        global_speed_limit_bps=speed_limit
    )

    # Main Window
    window = MainWindow(coordinator)

    # Handle incoming IPC messages from future instances
    def on_ipc_connection():
        client = ipc_server.nextPendingConnection()
        if not client:
            return
        if client.bytesAvailable() == 0:
            client.waitForReadyRead(1000)
        data = client.readAll().data().decode("utf-8", errors="ignore").strip()
        parts = data.split("|")
        cmd = parts[0] if parts else "SHOW"

        if cmd in ("SHOW", "ACTIVATE") or cmd.startswith("URL:"):
            window._show_window()

            cli_url = None
            cli_dir = None
            cli_fn = None

            if cmd.startswith("URL:"):
                cli_url = cmd[4:]
                if len(parts) > 1 and parts[1]:
                    cli_dir = parts[1]
                if len(parts) > 2 and parts[2]:
                    cli_fn = parts[2]
            elif len(parts) > 1 and parts[1]:
                cli_url = parts[1]
                cli_dir = parts[2] if len(parts) > 2 and parts[2] else None
                cli_fn = parts[3] if len(parts) > 3 and parts[3] else None

            if cli_url:
                target_dir = cli_dir or db.get_setting(
                    "default_dir", os.path.join(os.path.expanduser("~"), "Downloads")
                )
                try:
                    coordinator.add_download(
                        url=cli_url,
                        destination_dir=target_dir,
                        filename=cli_fn or "",
                        auto_start=True
                    )
                except Exception as e:
                    print(f"Error adding download from IPC: {e}", file=sys.stderr)
        elif cmd == "PUMP":
            coordinator._pump_queue()
            window.table_model.refresh()
        client.disconnectFromServer()

    ipc_server.newConnection.connect(on_ipc_connection)

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
    ipc_server.close()
    QLocalServer.removeServer(SOCKET_NAME)
    if window.tray_icon:
        window.tray_icon.hide()
    coordinator.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
