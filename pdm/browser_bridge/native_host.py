"""Chrome / Edge / Firefox Native Messaging Host supporting instant and queued downloads."""

import json
import os
import struct
import subprocess
import sys
import time
from typing import BinaryIO, Dict, List, Optional, Tuple

import psutil

from pdm.core.engine import DownloadStatus
from pdm.core.security import (
    extract_filename_from_url,
    resolve_safe_filepath,
    sanitize_filename,
    validate_url,
)
from pdm.main import get_default_data_dir
from pdm.storage.db import DatabaseManager

# In-memory tracker for speed and ETA: task_id -> (timestamp, downloaded_bytes)
_speed_tracker: Dict[int, Tuple[float, int]] = {}


def read_message(stream: Optional[BinaryIO] = None) -> Optional[dict]:
    """Read a 32-bit length-prefixed message from binary stream."""
    if stream is None:
        stream = sys.stdin.buffer
    raw_length = stream.read(4)
    if not raw_length or len(raw_length) < 4:
        return None
    message_length = struct.unpack("@I", raw_length)[0]
    message_bytes = stream.read(message_length)
    return json.loads(message_bytes.decode("utf-8"))


def send_message(message: dict, stream: Optional[BinaryIO] = None):
    """Write a 32-bit length-prefixed JSON message to binary stream."""
    if stream is None:
        stream = sys.stdout.buffer
    content = json.dumps(message).encode("utf-8")
    stream.write(struct.pack("@I", len(content)))
    stream.write(content)
    stream.flush()


def _notify_pdm_pump():
    """Notify running PDM GUI instance to refresh table and pump queue."""
    try:
        from PySide6.QtNetwork import QLocalSocket
        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication.instance() or QCoreApplication([])
        sock = QLocalSocket()
        sock.connectToServer("PersonalDownloadManager_SingleInstance_IPC")
        if sock.waitForConnected(200):
            sock.write(b"PUMP|||")
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
    except Exception:
        pass


def _ensure_pdm_running():
    """Ensure PDM GUI is running in background/tray to process queue without popping window."""
    if sys.platform == "win32":
        try:
            import ctypes
            MUTEX_NAME = "Local\\PersonalDownloadManager_SingleInstance_Mutex"
            h = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, MUTEX_NAME)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                _notify_pdm_pump()
                return
        except Exception:
            pass

    pdm_running = False
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (p.info.get("name") or "").lower()
            cmdline = " ".join(p.info.get("cmdline") or []).lower()
            if "pdm/main.py" in cmdline or "pdm.exe" in name:
                pdm_running = True
                break
        except Exception:
            pass

    if pdm_running:
        _notify_pdm_pump()
        return

    # Locate real PDM executable
    exe_path = None
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
    else:
        appdata = os.environ.get("LOCALAPPDATA", "")
        installed_exe = os.path.join(appdata, "Programs", "PersonalDownloadManager", "app", "PDM.exe")
        if os.path.exists(installed_exe):
            exe_path = installed_exe
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            dev_exe = os.path.join(base_dir, "dist", "PDM", "PDM.exe")
            if os.path.exists(dev_exe):
                exe_path = dev_exe

    if exe_path and os.path.exists(exe_path):
        subprocess.Popen([exe_path, "--tray"], cwd=os.path.dirname(exe_path))
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        main_py = os.path.join(base_dir, "pdm", "main.py")
        if os.path.exists(main_py):
            subprocess.Popen([sys.executable, main_py, "--tray"], cwd=base_dir)

    time.sleep(0.3)
    _notify_pdm_pump()


def format_bytes_speed(bps: float) -> str:
    """Format speed in bps to human-readable string."""
    if bps <= 0:
        return "0 KB/s"
    if bps >= 1048576:
        return f"{bps / 1048576:.1f} MB/s"
    if bps >= 1024:
        return f"{bps / 1024:.0f} KB/s"
    return f"{bps:.0f} B/s"


def format_eta(seconds: int) -> str:
    """Format ETA seconds to readable string."""
    if seconds <= 0:
        return "0s"
    if seconds >= 3600:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"
    if seconds >= 60:
        m = seconds // 60
        s = seconds % 60
        return f"{m}m {s}s"
    return f"{seconds}s"


def find_completed_download(db: DatabaseManager, default_dir: str, item: dict) -> Optional[dict]:
    raw_url = item.get("url")
    ok, valid_url = validate_url(raw_url)
    if not ok:
        return None

    raw_filename = item.get("filename") or extract_filename_from_url(valid_url)
    clean_filename = sanitize_filename(raw_filename)

    with db._lock, db._get_connection() as conn:
        # Check if exact URL has been completed and exists on disk
        cur = conn.execute(
            "SELECT id, filename, destination_path, total_bytes FROM downloads WHERE url = ? AND status = 'Completed' ORDER BY id DESC LIMIT 1",
            (valid_url,)
        )
        row = cur.fetchone()
        if row and row[2] and os.path.exists(row[2]):
            return {
                "id": row[0],
                "filename": row[1] or clean_filename,
                "filepath": row[2],
                "total_bytes": row[3] or 0
            }

    return None


def handle_download_item(db: DatabaseManager, default_dir: str, default_conns: int, item: dict) -> Optional[int]:
    raw_url = item.get("url")
    ok, valid_url = validate_url(raw_url)
    if not ok:
        return None

    raw_filename = item.get("filename") or extract_filename_from_url(valid_url)
    clean_filename = sanitize_filename(raw_filename)

    auto_start = item.get("auto_start", True)
    # Direct queue/start: If auto_start is true, start downloading immediately!
    status_to_insert = DownloadStatus.QUEUED.value if auto_start else DownloadStatus.PAUSED.value

    # Auto-detect category
    ext = os.path.splitext(clean_filename)[1].lower()
    cat = item.get("category")
    if not cat:
        if ext in (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".7zip", ".cab", ".tgz", ".wim"):
            cat = "Compressed"
        elif ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".epub", ".csv", ".rtf"):
            cat = "Documents"
        elif ext in (".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".opus", ".wma", ".mka"):
            cat = "Music"
        elif ext in (".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".bat", ".cmd", ".appimage"):
            cat = "Programs"
        elif ext in (".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".wmv", ".ts", ".m4v", ".3gp", ".m3u8", ".mpd"):
            cat = "Video"
        else:
            name_lower = clean_filename.lower()
            if any(k in name_lower for k in ("s0", "s1", "s2", "e0", "e1", "e2", "episode", "season", "movie", "video", "1080p", "720p", "480p")):
                cat = "Video"
            else:
                cat = "Other"

    cat_key = f"save_dir_{cat.lower()}"
    default_cat_dir = os.path.join(default_dir, cat) if cat != "Other" else default_dir
    target_dir = db.get_setting(cat_key, default_cat_dir)

    os.makedirs(target_dir, exist_ok=True)
    final_path = resolve_safe_filepath(target_dir, clean_filename)

    cookies = item.get("cookies", "")
    referer = item.get("referer", "")
    user_agent = item.get("user_agent", "")
    origin = item.get("origin", "")
    proxy = item.get("proxy", "")

    with db._lock, db._get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO downloads (url, destination_path, filename, category, connections_count, status, cookies, referer, user_agent, origin, proxy)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (valid_url, final_path, os.path.basename(final_path), cat, default_conns, status_to_insert, cookies, referer, user_agent, origin, proxy)
        )
        dl_id = cur.lastrowid

    return dl_id


def get_task_progress(db: DatabaseManager, task_id: int) -> dict:
    with db._lock, db._get_connection() as conn:
        cur = conn.execute(
            "SELECT id, status, downloaded_bytes, total_bytes, destination_path, filename, error_message FROM downloads WHERE id = ?",
            (task_id,)
        )
        row = cur.fetchone()

    if not row:
        return {"status": "error", "error": "Task not found"}

    tid, status_val, downloaded, total, path, fname, err = row
    status_lower = (status_val or "queued").lower()

    # Calculate real-time speed and ETA
    now = time.time()
    speed_bps = 0.0
    eta_seconds = 0

    if task_id in _speed_tracker:
        last_time, last_bytes = _speed_tracker[task_id]
        dt = now - last_time
        if dt > 0.1:
            delta_bytes = max(0, (downloaded or 0) - last_bytes)
            speed_bps = delta_bytes / dt
            _speed_tracker[task_id] = (now, downloaded or 0)
    else:
        _speed_tracker[task_id] = (now, downloaded or 0)

    if total and total > 0 and speed_bps > 0 and downloaded < total:
        remaining_bytes = total - downloaded
        eta_seconds = int(remaining_bytes / speed_bps)

    progress = 0.0
    if total and total > 0:
        progress = round(min(100.0, (downloaded / total) * 100.0), 1)
    elif status_lower == "completed":
        progress = 100.0

    return {
        "status": "ok",
        "task": {
            "id": tid,
            "status": status_lower,
            "downloaded": downloaded or 0,
            "total": total or 0,
            "progress": progress,
            "speed_bps": speed_bps,
            "speed_formatted": format_bytes_speed(speed_bps),
            "eta_seconds": eta_seconds,
            "eta_formatted": format_eta(eta_seconds),
            "filename": fname,
            "filepath": path,
            "error": err or ""
        }
    }


def main():
    db_path = os.path.join(get_default_data_dir(), "downloads.db")
    db = DatabaseManager(db_path)

    while True:
        try:
            msg = read_message()
            if msg is None:
                break

            action = msg.get("action")
            if action == "ping":
                send_message({"status": "ok", "message": "pong"})

            elif action in ("download", "batch_download"):
                default_dir = db.get_setting(
                    "default_dir", os.path.join(os.path.expanduser("~"), "Downloads")
                )
                default_conns = int(db.get_setting("default_connections", "8"))

                items = msg.get("items") or [msg]

                # Check duplicate if single download and not force_redownload
                if len(items) == 1 and not items[0].get("force_redownload"):
                    dup = find_completed_download(db, default_dir, items[0])
                    if dup:
                        send_message({
                            "status": "duplicate",
                            "existing_task": dup
                        })
                        continue

                created_ids = []

                for item in items:
                    tid = handle_download_item(db, default_dir, default_conns, item)
                    if tid:
                        created_ids.append(tid)

                _ensure_pdm_running()
                send_message({"status": "ok", "count": len(created_ids), "task_ids": created_ids})

            elif action == "get_progress":
                task_id = int(msg.get("task_id", 0))
                send_message(get_task_progress(db, task_id))

            elif action == "pause_task":
                task_id = int(msg.get("task_id", 0))
                with db._lock, db._get_connection() as conn:
                    conn.execute("UPDATE downloads SET status = 'Paused', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
                _notify_pdm_pump()
                send_message({"status": "ok"})

            elif action == "resume_task":
                task_id = int(msg.get("task_id", 0))
                with db._lock, db._get_connection() as conn:
                    conn.execute("UPDATE downloads SET status = 'Queued', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
                _ensure_pdm_running()
                _notify_pdm_pump()
                send_message({"status": "ok"})

            elif action == "cancel_task":
                task_id = int(msg.get("task_id", 0))
                with db._lock, db._get_connection() as conn:
                    conn.execute("UPDATE downloads SET status = 'Canceled', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
                _notify_pdm_pump()
                send_message({"status": "ok"})

            elif action == "open_file":
                task_id = int(msg.get("task_id", 0))
                filepath = msg.get("filepath", "")
                target = None
                if filepath and os.path.exists(filepath):
                    target = filepath
                elif task_id > 0:
                    with db._lock, db._get_connection() as conn:
                        cur = conn.execute("SELECT destination_path FROM downloads WHERE id = ?", (task_id,))
                        row = cur.fetchone()
                    if row and row[0] and os.path.exists(row[0]):
                        target = row[0]
                if target:
                    os.startfile(target)
                    send_message({"status": "ok"})
                else:
                    send_message({"status": "error", "error": "File not found"})

            elif action == "open_folder":
                task_id = int(msg.get("task_id", 0))
                with db._lock, db._get_connection() as conn:
                    cur = conn.execute("SELECT destination_path FROM downloads WHERE id = ?", (task_id,))
                    row = cur.fetchone()
                if row and row[0]:
                    target = os.path.normpath(row[0])
                    if os.path.exists(target):
                        subprocess.Popen(["explorer.exe", f"/select,{target}"])
                    else:
                        parent = os.path.dirname(target)
                        if os.path.exists(parent):
                            os.startfile(parent)
                    send_message({"status": "ok"})
                else:
                    send_message({"status": "error", "error": "Folder not found"})

            else:
                send_message({"status": "error", "error": f"Unknown action: {action}"})

        except Exception as e:
            send_message({"status": "error", "error": str(e)})


if __name__ == "__main__":
    main()
