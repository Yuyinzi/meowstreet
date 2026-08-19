import pytest

from app.db import ticker_context as ticker_context_db
from app.services import ticker_industry_context as service


def seed_reference_data(db_path):
    con = ticker_context_db.connect(db_path)
    ticker_context_db.save_industry_tags(
        con,
        [
            {
                "industry": "Semiconductors & Semi Conductor Equipment",
                "sector": "Information Technology",
                "industry_group": "Semiconductors & Semi Conductor Equipment",
                "official_industry": "Semiconductors & Semiconductor Equipment",
                "cycle_tag": "cyclical",
                "tag_source": "method_workbook",
                "source_vintage": "2021-gics",
            }
        ],
    )
    ticker_context_db.save_industry_aliases(
        con,
        [
            {
                "source": "yahoo",
                "source_industry": "Semiconductors",
                "gics_industry": "Semiconductors & Semi Conductor Equipment",
            }
        ],
    )
    con.close()


def yahoo_profile(symbol):
    return {
        "symbol": symbol,
        "company_name": "NVIDIA Corporation",
        "provider": "yahoo",
        "provider_sector": "Technology",
        "provider_industry": "Semiconductors",
    }


def test_fetch_miss_calls_provider_and_persists(tmp_path, monkeypatch):
    db_path = tmp_path / "ticker_context.sqlite"
    seed_reference_data(db_path)
    calls = []
    monkeypatch.setattr(
        service.yahoo_asset_profile,
        "fetch_asset_profile",
        lambda symbol, http_client=None: calls.append(symbol) or yahoo_profile(symbol),
    )

    payload = service.get_ticker_industry_context("nvda", db_path=db_path)

    assert calls == ["NVDA"]
    assert payload["status"] == "resolved"
    assert payload["resolution"] == "provider"
    assert payload["cycle_tag"] == "cyclical"
    con = ticker_context_db.connect(db_path)
    assert ticker_context_db.load_ticker_profile(con, "NVDA") is not None
    con.close()


def test_cache_hit_skips_provider(tmp_path, monkeypatch):
    db_path = tmp_path / "ticker_context.sqlite"
    seed_reference_data(db_path)
    calls = []
    monkeypatch.setattr(
        service.yahoo_asset_profile,
        "fetch_asset_profile",
        lambda symbol, http_client=None: calls.append(symbol) or yahoo_profile(symbol),
    )
    service.get_ticker_industry_context("NVDA", db_path=db_path)

    payload = service.get_ticker_industry_context("NVDA", db_path=db_path)

    assert calls == ["NVDA"]
    assert payload["status"] == "resolved"


def test_unmapped_industry_when_alias_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "ticker_context.sqlite"
    seed_reference_data(db_path)
    monkeypatch.setattr(
        service.yahoo_asset_profile,
        "fetch_asset_profile",
        lambda symbol, http_client=None: dict(
            yahoo_profile(symbol), provider_industry="Obscure Industry"
        ),
    )

    payload = service.get_ticker_industry_context("XYZ", db_path=db_path)

    assert payload["status"] == "unmapped_industry"
    assert payload["cycle_tag"] is None
    assert payload["provider_industry"] == "Obscure Industry"


def test_manual_override_resolves_without_provider(tmp_path, monkeypatch):
    db_path = tmp_path / "ticker_context.sqlite"
    seed_reference_data(db_path)
    monkeypatch.setattr(
        service.yahoo_asset_profile,
        "fetch_asset_profile",
        lambda symbol, http_client=None: (_ for _ in ()).throw(AssertionError("provider called")),
    )

    payload = service.get_ticker_industry_context(
        "NVDA",
        industry_override="Semiconductors & Semi Conductor Equipment",
        db_path=db_path,
    )

    assert payload["status"] == "resolved"
    assert payload["resolution"] == "manual_override"
    assert payload["cycle_tag"] == "cyclical"
    assert payload["provider"] == "manual"


def test_manual_override_rejects_unknown_industry(tmp_path):
    db_path = tmp_path / "ticker_context.sqlite"
    seed_reference_data(db_path)

    with pytest.raises(ValueError, match="gics industry Nowhere is unknown"):
        service.get_ticker_industry_context(
            "NVDA", industry_override="Nowhere", db_path=db_path
        )


def test_regime_bias_is_unknown_with_explanation(tmp_path, monkeypatch):
    db_path = tmp_path / "ticker_context.sqlite"
    seed_reference_data(db_path)
    monkeypatch.setattr(
        service.yahoo_asset_profile,
        "fetch_asset_profile",
        lambda symbol, http_client=None: yahoo_profile(symbol),
    )

    payload = service.get_ticker_industry_context("NVDA", db_path=db_path)

    assert payload["regime_bias"] == "unknown"
    assert payload["side_support"] == "unknown"
    assert "GDP growth forecast" in payload["regime_note"]


def test_list_gics_industries_returns_tag_rows(tmp_path):
    db_path = tmp_path / "ticker_context.sqlite"
    seed_reference_data(db_path)

    rows = service.list_gics_industries(db_path=db_path)

    assert [row["industry"] for row in rows] == [
        "Semiconductors & Semi Conductor Equipment"
    ]
