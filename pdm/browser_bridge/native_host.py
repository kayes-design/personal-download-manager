"""Chrome / Edge / Firefox Native Messaging Host supporting instant and queued downloads."""

import json
import os
import struct
import subprocess
import sys
from typing import BinaryIO, List, Optional

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


def _ensure_pdm_running():
    """Ensure PDM GUI is running in background/tray to process queue without popping window."""
    if sys.platform == "win32":
        try:
            import ctypes
            MUTEX_NAME = "Local\\PersonalDownloadManager_SingleInstance_Mutex"
            h = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, MUTEX_NAME)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
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

    if not pdm_running:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        exe_path = os.path.join(base_dir, "dist", "PDM", "PDM.exe")
        if os.path.exists(exe_path):
            subprocess.Popen([exe_path, "--tray"], cwd=os.path.dirname(exe_path))
        else:
            main_py = os.path.join(base_dir, "pdm", "main.py")
            subprocess.Popen([sys.executable, main_py, "--tray"], cwd=base_dir)


def handle_download_item(db: DatabaseManager, default_dir: str, default_conns: int, item: dict) -> Optional[int]:
    raw_url = item.get("url")
    ok, valid_url = validate_url(raw_url)
    if not ok:
        return None

    raw_filename = item.get("filename") or extract_filename_from_url(valid_url)
    clean_filename = sanitize_filename(raw_filename)

    auto_start = item.get("auto_start", True)
    initial_status = DownloadStatus.QUEUED.value if auto_start else DownloadStatus.PAUSED.value

    # Auto-detect category based on file extension or filename hints
    ext = os.path.splitext(clean_filename)[1].lower()
    cat = item.get("category")
    if not cat:
        if ext in (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".7zip"):
            cat = "Compressed"
        elif ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".epub"):
            cat = "Documents"
        elif ext in (".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".opus", ".wma"):
            cat = "Music"
        elif ext in (".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".bat"):
            cat = "Programs"
        elif ext in (".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".wmv", ".ts", ".m4v", ".3gp"):
            cat = "Video"
        else:
            name_lower = clean_filename.lower()
            if any(k in name_lower for k in ("s0", "s1", "s2", "e0", "e1", "e2", "episode", "season", "movie", "video", "1080p", "720p", "480p")):
                cat = "Video"
            else:
                cat = "Other"

    # Select target destination directory (honor category specific folder e.g. save_dir_video)
    # Security: Ignore arbitrary destination_dir from browser input to prevent directory traversal
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

    show_start_dlg = db.get_setting("show_start_dlg", "1") == "1"

    with db._lock, db._get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO downloads (url, destination_path, filename, category, connections_count, status, cookies, referer, user_agent, origin, proxy)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (valid_url, final_path, os.path.basename(final_path), cat, default_conns, initial_status, cookies, referer, user_agent, origin, proxy)
        )
        dl_id = cur.lastrowid

    if show_start_dlg:
        db.add_incoming_request(
            url=valid_url,
            filename=clean_filename,
            category=cat,
            cookies=cookies,
            referer=referer,
            user_agent=user_agent,
            origin=origin,
            proxy=proxy,
            auto_start=auto_start,
            download_id=dl_id
        )

    return dl_id


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
                default_conns = int(db.get_setting("default_connections", "4"))

                items = msg.get("items") or [msg]
                created_ids = []

                for item in items:
                    tid = handle_download_item(db, default_dir, default_conns, item)
                    if tid:
                        created_ids.append(tid)

                _ensure_pdm_running()
                send_message({"status": "ok", "count": len(created_ids), "task_ids": created_ids})

            else:
                send_message({"status": "error", "error": f"Unknown action: {action}"})

        except Exception as e:
            send_message({"status": "error", "error": str(e)})


if __name__ == "__main__":
    main()
