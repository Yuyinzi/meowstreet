from datetime import datetime

import pytest

from app.db import macro_indicators
from app.services import macro_refresh_audit
from app.services.macro_data_freshness_catalog import load_catalog
from app.services.macro_refresh_resources import ArtifactStore


SERIES = 'oil_petroleum_products_supplied'
AS_OF = datetime.fromisoformat('2026-11-19T12:00:00+00:00')


def payload(period='2026-11-13', value=20376):
    return {SERIES: {'series': {'series_id': SERIES, 'title': 'Petroleum products supplied', 'units': 'MBBL/D', 'source': 'eia'}, 'observations': [{'date': period, 'value': value, 'source': 'eia'}]}}


def put_points(path, data):
    con = macro_indicators.connect(path)
    for item in data.values():
        macro_indicators.merge_macro_indicator_observations(con, item['series'], item['observations'])
    con.close()


def audited_task(path, store, operation, name='oil_import', as_of=AS_OF):
    catalog = load_catalog()
    catalog['datasets'] = [r for r in catalog['datasets'] if r['id'] == f'macro:{SERIES}']
    tasks = [{'name': name, 'func': operation}]
    macro_refresh_audit.attach_audits(tasks, store, db_path=path, catalog=catalog, clock=lambda: as_of)
    return tasks[0]


def test_stale_source_is_preserved_as_successful_execution_with_warning(tmp_path):
    path = tmp_path / 'm.sqlite'
    old = payload('2026-11-06', 19759)
    put_points(path, old)
    store = ArtifactStore()
    store.put('commodities.oil', old)
    task = audited_task(path, store, lambda argv: put_points(path, old))
    assert task['func']([]) is None
    audit = task['data_audit'][0]
    assert audit['returned_period'] == audit['stored_period'] == '2026-11-06'
    assert audit['expected_period'] == '2026-11-13'
    assert audit['inserted'] == audit['updated'] == 0
    assert audit['issue'] == 'source_behind'
    assert audit['warning'] is True


def test_fresh_source_not_written_is_identified_as_persistence_mismatch(tmp_path):
    path = tmp_path / 'm.sqlite'
    put_points(path, payload('2026-11-06', 19759))
    store = ArtifactStore()
    store.put('commodities.oil', payload())
    task = audited_task(path, store, lambda argv: 0)
    assert task['func']([]) == 0
    audit = task['data_audit'][0]
    assert audit['returned_period'] == '2026-11-13'
    assert audit['stored_period'] == '2026-11-06'
    assert audit['issue'] == 'persistence_mismatch'


def test_fresh_repeat_is_successful_without_warning_and_revisions_are_counted(tmp_path):
    path = tmp_path / 'm.sqlite'
    put_points(path, payload())
    store = ArtifactStore()
    store.put('commodities.oil', payload(value=20377))
    task = audited_task(path, store, lambda argv: put_points(path, payload(value=20377)))
    task['func']([])
    audit = task['data_audit'][0]
    assert audit['updated'] == 1
    assert audit['inserted'] == 0
    assert audit['warning'] is False
    task['func']([])
    assert task['data_audit'][0]['updated'] == 0
    assert task['data_audit'][0]['warning'] is False


def test_fetch_records_returned_dates_without_treating_preimport_storage_as_failure(tmp_path):
    path = tmp_path / 'm.sqlite'
    store = ArtifactStore()
    task = audited_task(path, store, lambda argv: store.put('commodities.oil', payload()), name='oil_fetch')
    task['func']([])
    assert task['data_audit'][0]['returned_period'] == '2026-11-13'
    assert task['data_audit'][0]['returned_rows'] == 1
    assert task['data_audit'][0]['warning'] is False


def test_provider_exception_is_preserved_with_returned_and_stored_evidence(tmp_path):
    path = tmp_path / 'm.sqlite'
    put_points(path, payload('2026-11-06'))
    store = ArtifactStore()
    store.put('commodities.oil', payload())
    def fail(argv):
        raise ValueError('provider failed')
    task = audited_task(path, store, fail)
    with pytest.raises(ValueError, match='provider failed'):
        task['func']([])
    assert task['data_audit'][0]['returned_period'] == '2026-11-13'
    assert task['data_audit'][0]['stored_period'] == '2026-11-06'


def test_expired_calendar_does_not_invent_staleness(tmp_path):
    path = tmp_path / 'm.sqlite'
    put_points(path, payload())
    task = audited_task(path, ArtifactStore(), lambda argv: 0, as_of=datetime.fromisoformat('2027-02-01T00:00:00Z'))
    task['func']([])
    assert task['data_audit'][0]['freshness'] == 'unknown'
    assert task['data_audit'][0]['warning'] is False
    assert task['data_audit'][0]['returned_period'] is None


def test_real_executor_copies_keep_audit_and_concurrent_lanes_separate(tmp_path):
    from app.services.macro_refresh_executor import execute_tasks
    from app.services.macro_refresh_plan import make_task
    path = tmp_path / 'm.sqlite'
    put_points(path, payload())
    store = ArtifactStore()
    store.put('commodities.oil', payload())
    task = audited_task(path, store, lambda argv: 0)
    real = make_task('oil_import', 'eia', 'persist', task['func'])
    real['data_audit'] = task['data_audit']
    other = make_task('unrelated', 'yahoo', 'fetch', lambda argv: 0)
    results = execute_tasks([real, other])
    assert results[0]['data_audit'][0]['stored_period'] == '2026-11-13'
    assert results[1]['data_audit'] == []


def test_before_snapshot_failure_is_visible_without_masking_provider_result(tmp_path, monkeypatch):
    def unavailable(*args):
        raise OSError('private path')
    monkeypatch.setattr(macro_refresh_audit, 'load_point_snapshots', unavailable)
    task = audited_task(tmp_path / 'm.sqlite', ArtifactStore(), lambda argv: 7)
    assert task['func']([]) == 7
    assert task['data_audit'][-1]['issue'] == 'audit_unavailable'
    assert 'private path' not in str(task['data_audit'])


def test_inserted_rows_count_actual_change(tmp_path):
    path = tmp_path / 'm.sqlite'
    put_points(path, payload('2026-11-06'))
    store = ArtifactStore()
    store.put('commodities.oil', payload())
    task = audited_task(path, store, lambda argv: put_points(path, payload()))
    task['func']([])
    assert task['data_audit'][0]['inserted'] == 1
    assert task['data_audit'][0]['updated'] == 0
    assert task['data_audit'][0]['warning'] is False


def test_investing_cron_records_date_audit_and_warning_in_same_notification(tmp_path):
    from app.db import job_notifications as notification_db
    from app.services import job_notifications
    path = tmp_path / 'm.sqlite'
    con = macro_indicators.connect(path)
    con.close()
    notification_path = tmp_path / 'n.sqlite'
    handle = job_notifications.start_run('investing_refresh', db_path=notification_path)
    with job_notifications.bind_run(handle):
        result = macro_refresh_audit.audit_job_operation('investing_refresh', lambda: {'ok': True}, db_path=path, clock=lambda: AS_OF)
    assert result == {'ok': True}
    handle.finish(0)
    con = notification_db.connect(notification_path)
    run = notification_db.load_run(con, handle.run_id)
    assert run['status'] == 'completed_with_warnings'
    assert len(run['children'][0]['data_audit']) == 3
    assert run['children'][0]['data_audit'][0]['freshness'] == 'missing'
    con.close()


def test_successful_import_with_unreadable_observations_warns_instead_of_claiming_a_check(tmp_path, monkeypatch):
    monkeypatch.setattr(macro_refresh_audit, 'load_observations', lambda rows, path: {r['id']: {'availability': 'unavailable'} for r in rows})
    task = audited_task(tmp_path / 'm.sqlite', ArtifactStore(), lambda argv: 0)
    assert task['func']([]) == 0
    assert task['data_audit'][0]['issue'] == 'audit_unavailable'
    assert task['data_audit'][0]['warning'] is True
