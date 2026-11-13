# pytest discovers the local package via pyproject.toml pythonpath.

import pytest

from app.db import job_notifications


@pytest.fixture(autouse=True)
def isolate_job_notification_database(tmp_path, monkeypatch):
    monkeypatch.setattr(job_notifications, "DEFAULT_DB_PATH", tmp_path / "job_notifications.sqlite")
