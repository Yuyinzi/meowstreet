import sqlite3

from app.db import ticker_context
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


def test_bootstrap_upserts_bundled_reference_without_deleting_local_rows(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    local_data_bootstrap.bootstrap_local_data(db_path)
    con = ticker_context.connect(db_path)
    try:
        ticker_context.save_industry_tags(
            con,
            [
                {
                    "industry": "Local Research",
                    "sector": "Local Sector",
                    "industry_group": "Local Group",
                    "official_industry": "Local Research",
                    "cycle_tag": "both",
                    "tag_source": "local_maintenance",
                    "source_vintage": "local-v1",
                },
                {
                    "industry": "Media",
                    "sector": "Stale Sector",
                    "industry_group": "Stale Group",
                    "official_industry": "Stale Media",
                    "cycle_tag": "defensive",
                    "tag_source": "stale_import",
                    "source_vintage": "stale-v1",
                },
            ],
        )
        ticker_context.save_industry_aliases(
            con,
            [
                {
                    "source": "local",
                    "source_industry": "Research Providers",
                    "gics_industry": "Local Research",
                },
                {
                    "source": "yahoo",
                    "source_industry": "Advertising Agencies",
                    "gics_industry": "Local Research",
                },
            ],
        )
    finally:
        con.close()

    local_data_bootstrap.bootstrap_local_data(db_path)
    local_data_bootstrap.bootstrap_local_data(db_path)

    con = ticker_context.connect(db_path)
    try:
        assert ticker_context.load_industry_tag(con, "Local Research") == {
            "industry": "Local Research",
            "sector": "Local Sector",
            "industry_group": "Local Group",
            "official_industry": "Local Research",
            "cycle_tag": "both",
            "tag_source": "local_maintenance",
            "source_vintage": "local-v1",
        }
        assert ticker_context.load_industry_alias(
            con, "local", "Research Providers"
        ) == {
            "source": "local",
            "source_industry": "Research Providers",
            "gics_industry": "Local Research",
        }
        assert ticker_context.load_industry_tag(con, "Media") == {
            "industry": "Media",
            "sector": "Communication Services",
            "industry_group": "Media & Entertainment",
            "official_industry": "Media",
            "cycle_tag": "cyclical",
            "tag_source": "method_workbook",
            "source_vintage": "2021-gics",
        }
        assert ticker_context.load_industry_alias(
            con, "yahoo", "Advertising Agencies"
        ) == {
            "source": "yahoo",
            "source_industry": "Advertising Agencies",
            "gics_industry": "Media",
        }
    finally:
        con.close()
