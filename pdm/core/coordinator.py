"""Download coordinator managing queues, concurrency, and task lifecycles."""

import ctypes
import os
import sys
import threading
import time
from typing import Callable, Dict, List, Optional

from pdm.core.engine import DownloadStatus, DownloadTask
from pdm.core.limiter import SpeedLimiter
from pdm.core.security import (
    extract_filename_from_url,
    resolve_safe_filepath,
    sanitize_filename,
    validate_url,
)
from pdm.storage.db import DatabaseManager


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_system_idle_seconds() -> float:
    """Return seconds since user last interacted with keyboard or mouse on Windows."""
    if sys.platform != "win32":
        return 0.0
    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return max(0.0, millis / 1000.0)
    except Exception:
        pass
    return 0.0


class DownloadCoordinator:
    """Orchestrates multiple download tasks, enforcing concurrency and queue rules."""

    def __init__(
        self,
        db: DatabaseManager,
        max_concurrent_downloads: int = 3,
        global_speed_limit_bps: int = 0
    ):
        self.db = db
        self.max_concurrent_downloads = max_concurrent_downloads
        self.configured_speed_limit = global_speed_limit_bps
        self.global_limiter = SpeedLimiter(global_speed_limit_bps)
        self.is_idle_boosted = False
        self._last_idle_check = 0.0

        self._lock = threading.Lock()
        self._active_tasks: Dict[int, DownloadTask] = {}
        self._threads: Dict[int, threading.Thread] = {}

        # Callbacks for UI integration
        self.on_task_updated: Optional[Callable[[DownloadTask], None]] = None
        self.on_status_changed: Optional[Callable[[DownloadTask, DownloadStatus], None]] = None

        # Queue monitor thread
        self._running = True
        self._queue_thread = threading.Thread(
            target=self._queue_worker_loop, daemon=True, name="PDM-QueueWorker"
        )
        self._queue_thread.start()

    def shutdown(self):
        """Cleanly shutdown coordinator and pause all running tasks."""
        self._running = False
        self.pause_all()

    def set_global_speed_limit(self, bps: int):
        self.configured_speed_limit = bps
        if not self.is_idle_boosted:
            self.global_limiter.set_rate(bps)
        self.db.set_setting("global_speed_limit", str(bps))

    def add_download(
        self,
        url: str,
        destination_dir: str,
        filename: Optional[str] = None,
        category: str = "Other",
        connections_count: int = 4,
        auto_start: bool = True,
        cookies: str = "",
        referer: str = ""
    ) -> int:
        """Validate, register in DB, and optionally queue for download."""
        ok, valid_url = validate_url(url)
        if not ok:
            raise ValueError(f"Invalid URL: {valid_url}")

        if not filename:
            filename = extract_filename_from_url(valid_url)
        else:
            filename = sanitize_filename(filename)

        final_path = resolve_safe_filepath(destination_dir, filename)
        clean_filename = os.path.basename(final_path)

        task_id = self.db.create_download(
            url=valid_url,
            destination_path=final_path,
            filename=clean_filename,
            category=category,
            connections_count=connections_count,
            cookies=cookies,
            referer=referer
        )

        if auto_start:
            self.start_download(task_id)

        return task_id

    def start_download(self, task_id: int):
        """Mark task as Queued so queue pump can start it immediately."""
        with self._lock:
            if task_id in self._active_tasks:
                return  # Already running

            record = self.db.get_download(task_id)
            if not record or record["status"] in ("Completed", "Downloading"):
                return

            self.db.set_download_status(task_id, DownloadStatus.QUEUED.value)
        self._pump_queue()

    def resume_download(self, task_id: int):
        """Alias for start_download."""
        self.start_download(task_id)

    def pause_download(self, task_id: int):
        """Pause a currently downloading task."""
        with self._lock:
            task = self._active_tasks.get(task_id)
            if task:
                task.stop()
            else:
                record = self.db.get_download(task_id)
                if record and record["status"] == DownloadStatus.QUEUED.value:
                    self.db.set_download_status(task_id, DownloadStatus.PAUSED.value)

    def pause_all(self):
        """Pause all currently active and queued tasks."""
        with self._lock:
            for task in list(self._active_tasks.values()):
                task.stop()
            # Set queued items to paused
            queued = self.db.list_downloads(status=DownloadStatus.QUEUED.value)
            for item in queued:
                self.db.set_download_status(item["id"], DownloadStatus.PAUSED.value)

    def resume_all(self):
        """Resume all paused tasks."""
        paused = self.db.list_downloads(status=DownloadStatus.PAUSED.value)
        for item in paused:
            self.start_download(item["id"])

    def cancel_download(self, task_id: int, delete_files: bool = True):
        """Stop task and optionally clean up destination and part files."""
        self.pause_download(task_id)

        record = self.db.get_download(task_id)
        if record:
            self.db.set_download_status(task_id, DownloadStatus.CANCELED.value)

            if delete_files:
                # Remove final file if exists
                dest = record["destination_path"]
                if os.path.exists(dest):
                    try:
                        os.remove(dest)
                    except Exception:
                        pass
                # Remove part files
                segments = self.db.get_segments(task_id)
                for s in segments:
                    part_file = s["temp_filepath"]
                    if os.path.exists(part_file):
                        try:
                            os.remove(part_file)
                        except Exception:
                            pass
                self.db.clear_segments(task_id)

    def delete_download(self, task_id: int, delete_files: bool = False):
        """Remove task from DB completely."""
        self.cancel_download(task_id, delete_files=delete_files)
        self.db.delete_download(task_id)

    def delete_completed(self, delete_files: bool = False) -> int:
        """Remove all completed tasks from DB and optionally remove files from disk."""
        with self._lock:
            completed_records = self.db.delete_completed()
            if delete_files:
                for rec in completed_records:
                    dest = rec.get("destination_path")
                    if dest and os.path.exists(dest):
                        try:
                            os.remove(dest)
                        except Exception:
                            pass
            return len(completed_records)

    def get_active_task(self, task_id: int) -> Optional[DownloadTask]:
        with self._lock:
            return self._active_tasks.get(task_id)

    def list_active_tasks(self) -> List[DownloadTask]:
        with self._lock:
            return list(self._active_tasks.values())

    # ------------------- Queue Pump Loop -------------------

    def _queue_worker_loop(self):
        while self._running:
            try:
                self._check_smart_idle()
                self._pump_queue()
            except Exception:
                pass
            time.sleep(0.5)

    def _check_smart_idle(self):
        now = time.monotonic()
        if now - self._last_idle_check < 1.0:
            return
        self._last_idle_check = now

        smart_idle_enabled = self.db.get_setting("smart_idle_boost", "1") == "1"
        if not smart_idle_enabled or self.configured_speed_limit <= 0:
            if self.is_idle_boosted:
                self.is_idle_boosted = False
                self.global_limiter.set_rate(self.configured_speed_limit)
            return

        timeout_sec = float(self.db.get_setting("smart_idle_timeout_sec", "60"))
        idle_sec = get_system_idle_seconds()

        if idle_sec >= timeout_sec:
            if not self.is_idle_boosted:
                self.is_idle_boosted = True
                self.global_limiter.set_rate(0)  # Auto-unthrottle to maximum speed on PC idle
        else:
            if self.is_idle_boosted:
                self.is_idle_boosted = False
                self.global_limiter.set_rate(self.configured_speed_limit)  # Re-throttle when user is active

    def _pump_queue(self):
        with self._lock:
            # Clean up finished threads
            finished_ids = []
            for tid, t in self._threads.items():
                if not t.is_alive():
                    finished_ids.append(tid)

            for fid in finished_ids:
                self._threads.pop(fid, None)
                self._active_tasks.pop(fid, None)

            current_active = len(self._active_tasks)
            available_slots = self.max_concurrent_downloads - current_active

            if available_slots <= 0:
                return

            # Fetch pending queued downloads
            queued_items = self.db.list_downloads(status=DownloadStatus.QUEUED.value)
            for item in queued_items[:available_slots]:
                task_id = item["id"]
                if task_id in self._active_tasks:
                    continue

                proxy_mode = self.db.get_setting("proxy_mode", "auto")
                if proxy_mode == "direct":
                    effective_proxy = ""
                elif proxy_mode == "manual":
                    effective_proxy = self.db.get_setting("manual_proxy", "")
                else:  # auto
                    effective_proxy = item.get("proxy") or self.db.get_setting("manual_proxy", "")

                task = DownloadTask(
                    task_id=task_id,
                    url=item["url"],
                    destination_path=item["destination_path"],
                    filename=item["filename"],
                    db=self.db,
                    connections_count=item.get("connections_count", 4),
                    speed_limiter=self.global_limiter,
                    progress_callback=self._handle_task_progress,
                    status_callback=self._handle_task_status,
                    cookies=item.get("cookies", ""),
                    referer=item.get("referer", ""),
                    user_agent=item.get("user_agent", ""),
                    origin=item.get("origin", ""),
                    proxy=effective_proxy or None
                )
                self._active_tasks[task_id] = task

                thread = threading.Thread(
                    target=self._run_task_thread,
                    args=(task,),
                    daemon=True,
                    name=f"PDM-TaskRunner-{task_id}"
                )
                self._threads[task_id] = thread
                thread.start()

    def _run_task_thread(self, task: DownloadTask):
        try:
            task.run_sync()
        except Exception:
            pass

    def _handle_task_progress(self, task: DownloadTask):
        if self.on_task_updated:
            try:
                self.on_task_updated(task)
            except Exception:
                pass

    def _handle_task_status(self, task: DownloadTask, new_status: DownloadStatus):
        if self.on_status_changed:
            try:
                self.on_status_changed(task, new_status)
            except Exception:
                pass
