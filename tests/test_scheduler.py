"""Unit tests for QueueScheduler configuration and trigger logic."""

import os
import pytest
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
    coordinator.shutdown()
