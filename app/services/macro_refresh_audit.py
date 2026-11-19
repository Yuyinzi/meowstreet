from datetime import UTC, datetime
from functools import wraps

from app.db import macro_indicators
from app.db.macro_data_freshness import load_observations
from app.db.macro_refresh_audit import load_point_snapshots
from app.services import job_notifications
from app.services.macro_data_freshness_catalog import load_catalog
from app.tools.macro_refresh_audit import build_audit_records


def _returned_points(store, task_name):
    if task_name not in {'oil_fetch', 'oil_import'}:
        return {}
    try:
        payload = store.get('commodities.oil')
    except ValueError:
        return {}
    return {f'macro:{key}': {point['date']: point['value'] for point in item['observations']} for key, item in payload.items()}


def _attach(task, rows, store, path, catalog, clock, *, importing=None):
    operation = task['func']
    if importing is None:
        importing = any(t['persist'] == task['name'] for row in rows for t in row['tasks'])

    records = []
    task['data_audit'] = records

    @wraps(operation)
    def audited(argv):
        records.clear()
        before = {}
        audit_error = False
        try:
            before = load_point_snapshots(rows, path) if importing else {}
        except Exception:
            audit_error = True
        try:
            return operation(argv)
        finally:
            try:
                observations = load_observations(rows, path)
                after = load_point_snapshots(rows, path) if importing else {}
                records.extend(build_audit_records(rows, before, after, observations, _returned_points(store, task['name']), catalog, clock(), importing))
                if audit_error:
                    records.append({'name': 'Data audit', 'warning': True, 'issue': 'audit_unavailable', 'reason': 'Before-import evidence could not be recorded'})
            except Exception:
                records.append({'name': 'Data audit', 'warning': True, 'issue': 'audit_unavailable', 'reason': 'Data audit evidence could not be recorded'})
    task['func'] = audited


def attach_audits(tasks, store, *, db_path=None, catalog=None, clock=None):
    catalog = catalog or load_catalog()
    path = db_path or macro_indicators.DEFAULT_DB_PATH
    clock = clock or (lambda: datetime.now(UTC))
    for task in tasks:
        rows = [row for row in catalog['datasets'] if any(task['name'] in {t['fetch'], t['persist']} for t in row['tasks'] if t['job_id'] == 'macro_refresh')]
        if rows:
            _attach(task, rows, store, path, catalog, clock)
    return tasks


def audit_job_operation(job_id, operation, *, db_path=None, clock=None):
    catalog = load_catalog()
    rows = [row for row in catalog['datasets'] if any(task['job_id'] == job_id for task in row['tasks'])]
    task = {'name': 'data_refresh', 'func': lambda argv: operation()}
    _attach(task, rows, {}, db_path or macro_indicators.DEFAULT_DB_PATH, catalog, clock or (lambda: datetime.now(UTC)), importing=True)
    status = 'failed'
    try:
        result = task['func']([])
        status = 'ok'
        return result
    finally:
        job_notifications.record_event({'type': 'task_finished', 'task': {'name': task['name']}, 'result': {'status': status, 'data_audit': task['data_audit']}})
