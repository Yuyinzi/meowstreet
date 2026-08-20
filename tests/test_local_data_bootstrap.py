import sqlite3

from app.services import local_data_bootstrap


OBSERVATION_TABLES = (
    "prices",
    "benchmark_prices",
    "macro_indicator_points",
    "economic_confirmation_vintages",
    "ism_report_snapshots",
    "answer_traces",
    "assistant_conversations",
)


def test_bootstrap_creates_database_and_imports_only_reference_rows(tmp_path):
    db_path = tmp_path / "nested" / "market_data.sqlite"

    result = local_data_bootstrap.bootstrap_local_data(db_path)

    assert result["db_path"] == str(db_path)
    assert result["reference_version"] == "gics_reference_v1"
    assert result["schemas_initialized"] == 9
    assert result["industries"] == 69
    assert result["aliases"] == 151
    assert result["market_observations"] == 0
    assert db_path.is_file()

    con = sqlite3.connect(db_path)
    try:
        assert con.execute("select count(*) from gics_industry_tags").fetchone()[0] == 69
        assert con.execute("select count(*) from industry_aliases").fetchone()[0] == 151
        for table in OBSERVATION_TABLES:
            assert con.execute(f"select count(*) from {table}").fetchone()[0] == 0
    finally:
        con.close()


def test_bootstrap_is_idempotent(tmp_path):
    db_path = tmp_path / "market_data.sqlite"

    first = local_data_bootstrap.bootstrap_local_data(db_path)
    second = local_data_bootstrap.bootstrap_local_data(db_path)

    assert second == first
