from datetime import UTC, datetime

from app.db import job_notifications, macro_indicators
from app.db.macro_data_freshness import load_observations, load_task_history
from app.services.macro_data_freshness_catalog import load_catalog
from app.tools.macro_data_freshness import build_overview


def get_overview(*, db_path=None, notification_db_path=None, as_of=None, catalog_path=None):
    catalog = load_catalog(catalog_path)
    observations = load_observations(catalog["datasets"], db_path or macro_indicators.DEFAULT_DB_PATH)
    tasks = load_task_history(catalog["datasets"], notification_db_path or job_notifications.DEFAULT_DB_PATH)
    return build_overview(catalog, observations, tasks, as_of or datetime.now(UTC))
