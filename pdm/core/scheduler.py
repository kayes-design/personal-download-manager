"""Queue scheduler and optional system shutdown controller."""

import datetime
import subprocess
import threading
from typing import Callable, Optional

from pdm.core.coordinator import DownloadCoordinator
from pdm.core.engine import DownloadStatus


class QueueScheduler:
    """Monitors scheduled time slots and orchestrates start, stop, and PC shutdown."""

    def __init__(self, coordinator: DownloadCoordinator):
        self.coordinator = coordinator
        self.db = coordinator.db

        self.enabled = self.db.get_setting("sched_enabled", "0") == "1"
        self.start_time_str: Optional[str] = self.db.get_setting("sched_start", "02:00")
        self.stop_time_str: Optional[str] = self.db.get_setting("sched_stop", "06:00")
        self.shutdown_when_done = self.db.get_setting("sched_shutdown", "0") == "1"

        self._lock = threading.Lock()
        self._running = True
        self._stop_event = threading.Event()
        self._last_triggered_start_date = None
        self._last_triggered_stop_date = None

        self.on_shutdown_countdown_started: Optional[Callable[[int], None]] = None

        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True, name="PDM-Scheduler")
        self._thread.start()

    def set_config(
        self,
        enabled: bool,
        start_time: Optional[str] = None,
        stop_time: Optional[str] = None,
        shutdown_when_done: bool = False
    ):
        with self._lock:
            self.enabled = enabled
            self.start_time_str = start_time
            self.stop_time_str = stop_time
            self.shutdown_when_done = shutdown_when_done

            self.db.set_setting("sched_enabled", "1" if enabled else "0")
            if start_time:
                self.db.set_setting("sched_start", start_time)
            if stop_time:
                self.db.set_setting("sched_stop", stop_time)
            self.db.set_setting("sched_shutdown", "1" if shutdown_when_done else "0")

    def _scheduler_loop(self):
        while self._running:
            try:
                self._check_schedule()
            except Exception:
                pass
            self._stop_event.wait(5)

    def _check_schedule(self):
        with self._lock:
            if not self.enabled:
                return

            now = datetime.datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            current_hm = now.strftime("%H:%M")

            # Check start time trigger
            if self.start_time_str and current_hm == self.start_time_str:
                if self._last_triggered_start_date != today_str:
                    self._last_triggered_start_date = today_str
                    self.coordinator.resume_all()

            # Check stop time trigger
            if self.stop_time_str and current_hm == self.stop_time_str:
                if self._last_triggered_stop_date != today_str:
                    self._last_triggered_stop_date = today_str
                    self.coordinator.pause_all()

            # Check queue completion for auto-shutdown
            if self.shutdown_when_done:
                active_count = len(self.coordinator.list_active_tasks())
                queued_count = len(self.db.list_downloads(status=DownloadStatus.QUEUED.value))
                if active_count == 0 and queued_count == 0:
                    # Queue drained, initiate shutdown callback if callback assigned
                    if self.on_shutdown_countdown_started:
                        self.shutdown_when_done = False  # Trigger once
                        self.on_shutdown_countdown_started(60)

    def trigger_system_shutdown(self):
        """Execute Windows shutdown command."""
        try:
            subprocess.run(["shutdown.exe", "/s", "/t", "0"], check=False)
        except Exception:
            pass

    def cancel_system_shutdown(self):
        """Abort Windows shutdown command if in progress."""
        try:
            subprocess.run(["shutdown.exe", "/a"], check=False)
        except Exception:
            pass

    def stop(self):
        self._running = False
        self._stop_event.set()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=1)
