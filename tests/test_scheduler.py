"""Unit tests for QueueScheduler configuration and trigger logic."""

import os
import datetime
import pytest
from pdm.core import scheduler as scheduler_module
from pdm.core.coordinator import DownloadCoordinator
from pdm.core.scheduler import QueueScheduler
from pdm.storage.db import DatabaseManager


def test_scheduler_config(tmp_path):
    db_file = os.path.join(tmp_path, "sched_test.db")
    db = DatabaseManager(db_file)
    coordinator = DownloadCoordinator(db=db)
    scheduler = QueueScheduler(coordinator)

    scheduler.set_config(
        enabled=True,
        start_time="02:30",
        stop_time="06:30",
        shutdown_when_done=True
    )

    assert scheduler.enabled is True
    assert scheduler.start_time_str == "02:30"
    assert scheduler.stop_time_str == "06:30"
    assert scheduler.shutdown_when_done is True

    # Check persistence in DB
    assert db.get_setting("sched_enabled") == "1"
    assert db.get_setting("sched_start") == "02:30"
    assert db.get_setting("sched_stop") == "06:30"
    assert db.get_setting("sched_shutdown") == "1"

    scheduler.stop()
    restored_scheduler = QueueScheduler(coordinator)
    assert restored_scheduler.enabled is True
    assert restored_scheduler.start_time_str == "02:30"
    assert restored_scheduler.stop_time_str == "06:30"
    assert restored_scheduler.shutdown_when_done is True
    restored_scheduler.stop()
    coordinator.shutdown()


def test_scheduler_triggers_once_per_day_and_shutdown_once(monkeypatch, tmp_path):
    class FixedDateTime(datetime.datetime):
        current = datetime.datetime(2026, 11, 2, 2, 30)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(scheduler_module.datetime, "datetime", FixedDateTime)
    db = DatabaseManager(str(tmp_path / "scheduler-triggers.db"))
    coordinator = DownloadCoordinator(db)
    actions = []
    coordinator.resume_all = lambda: actions.append("start")
    coordinator.pause_all = lambda: actions.append("stop")
    scheduler = QueueScheduler(coordinator)
    scheduler.enabled = True
    scheduler.start_time_str = "02:30"
    scheduler.stop_time_str = "02:30"
    scheduler.shutdown_when_done = True
    scheduler.on_shutdown_countdown_started = lambda seconds: actions.append(("shutdown", seconds))

    scheduler._check_schedule()
    scheduler._check_schedule()

    assert actions == ["start", "stop", ("shutdown", 60)]
    assert scheduler.shutdown_when_done is False

    scheduler.stop()
    coordinator.shutdown()
