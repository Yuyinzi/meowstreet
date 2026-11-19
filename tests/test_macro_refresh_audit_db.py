from app.db import macro_indicators
from app.db.macro_refresh_audit import load_point_snapshots


def test_numeric_snapshots_are_read_only_and_preserve_point_values(tmp_path):
    path = tmp_path / 'm.sqlite'
    rows = [{'id': 'macro:test', 'storage': {'kind': 'macro', 'key': 'test'}}, {'id': 'report:test', 'storage': {'kind': 'ism_report', 'key': 'test'}}]
    assert load_point_snapshots(rows, path) == {'macro:test': {}}
    assert not path.exists()
    con = macro_indicators.connect(path)
    macro_indicators.merge_macro_indicator_points(con, {'series_id': 'test', 'title': 'Test', 'units': 'index', 'source': 'test'}, [{'date': '2026-11-13', 'value': 3, 'source': 'test'}])
    con.close()
    assert load_point_snapshots(rows, path) == {'macro:test': {'2026-11-13': 3}}
