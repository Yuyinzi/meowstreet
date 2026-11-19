from datetime import datetime

from app.services.macro_data_freshness_catalog import load_catalog
from app.tools.macro_refresh_audit import build_audit_records


def test_weekly_storage_label_is_distinct_from_source_date():
    catalog = load_catalog()
    row = next(row for row in catalog['datasets'] if row['id'] == 'macro:cpi_yoy')
    evidence = {'availability': 'available', 'current_period': '2026-11-15', 'source_observation_date': '2026-09-01', 'lineage_basis': 'captured_at_import'}
    records = build_audit_records([row], {}, {}, {row['id']: evidence}, {}, catalog, datetime.fromisoformat('2026-11-19T12:00:00Z'), True)
    assert records[0]['stored_period'] == '2026-11-15'
    assert records[0]['source_period'] == '2026-09-01'
    assert records[0]['warning'] is True


def test_benchmark_expected_period_comes_from_verified_session_calendar():
    catalog = load_catalog()
    row = next(row for row in catalog['datasets'] if row['id'] == 'benchmark:us_sp500')
    evidence = {'availability': 'available', 'current_period': '2026-11-18'}
    records = build_audit_records([row], {}, {}, {row['id']: evidence}, {}, catalog, datetime.fromisoformat('2026-11-19T15:00:00Z'), True)
    assert records[0]['expected_period'] == '2026-11-18'
