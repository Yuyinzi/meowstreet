# pytest discovers the local package via pyproject.toml pythonpath.

import pytest

from app.db import job_notifications


@pytest.fixture(autouse=True)
def isolate_job_notification_database(tmp_path, monkeypatch):
    notification_path = tmp_path / "job_notifications.sqlite"
    monkeypatch.setenv("MEOWSTREET_NOTIFICATION_DB_PATH", str(notification_path))
    monkeypatch.setattr(job_notifications, "DEFAULT_DB_PATH", notification_path)
