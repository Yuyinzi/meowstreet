from sqlite3 import connect

import pytest

from app.db.macro_source_lineage import replace_lineage


def lineage():
    return {"date": "2026-11-15", "value": 3.0, "source_date": "2026-10-01", "source_series_id": "CPIAUCSL", "source_hash": "a" * 64}


def test_lineage_is_bound_to_observation_date_value_and_source(tmp_path):
    con = connect(tmp_path / "data.sqlite")
    assert replace_lineage(con, "macro:cpi_yoy", [lineage()], "captured_at_import") == 1
    row = con.execute("select dataset_id,observation_date,value,source_date,basis from macro_source_lineage").fetchone()
    assert row == ("macro:cpi_yoy", "2026-11-15", 3, "2026-10-01", "captured_at_import")
    assert replace_lineage(con, "macro:cpi_yoy", [], "captured_at_import") == 0
    assert con.execute("select count(*) from macro_source_lineage").fetchone()[0] == 0
    con.close()


@pytest.mark.parametrize("mutation", [lambda r: r.update(source_date="2026-12-01"), lambda r: r.update(value=float("nan")), lambda r: r.update(source_hash="")])
def test_lineage_rejects_invalid_or_future_relative_sources(tmp_path, mutation):
    con = connect(tmp_path / "data.sqlite")
    row = lineage()
    mutation(row)
    with pytest.raises(ValueError):
        replace_lineage(con, "macro:cpi_yoy", [row], "captured_at_import")
    con.close()
