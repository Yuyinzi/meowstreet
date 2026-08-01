import httpx
import pytest

from app.data_sources.tracked_commodities import (
    MARKET_SERIES,
    _normalize_method_price,
    _parse_investing_html,
    fetch_commodity_observations,
    parse_commodity_csv,
    parse_investing_history_payload,
)


def test_method_market_registry_preserves_the_six_workbook_urls():
    assert list(MARKET_SERIES) == [
        "copper_comex",
        "copper_lme",
        "copper_shanghai",
        "lumber",
        "iron_ore_62_cfr_china",
        "iron_ore_dce",
    ]
    assert MARKET_SERIES["copper_lme"]["price_page_url"].endswith("cid=959211")
    assert MARKET_SERIES["iron_ore_62_cfr_china"]["price_page_url"].endswith(
        "iron-ore-62-cfr-futures-historical-data"
    )
    assert "price_page_url" not in MARKET_SERIES["iron_ore_dce"]


def test_dce_iron_ore_registry_uses_the_sina_i0_temporary_contract():
    dce = MARKET_SERIES["iron_ore_dce"]

    assert dce["source"] == "sina_finance"
    assert dce["source_class"] == "vendor_free_market_data"
    assert dce["access_adapter"] == "akshare"
    assert dce["source_identifier"] == "I0"
    assert dce["instrument"] == "DCE Iron Ore continuous series (I0)"


def test_method_market_series_includes_units():
    for sid, meta in MARKET_SERIES.items():
        assert "units" in meta, f"{sid} missing units"


def test_normalized_method_price_preserves_non_official_provenance():
    row = {"date": "2026-07-24", "price": 5.7}
    result = _normalize_method_price(
        row,
        "copper_comex",
        "https://www.investing.com/commodities/copper-historical-data",
        "2026-07-30T12:00:00",
    )
    assert result["source"] == "investing.com"
    assert result["source_class"] == "free_web"
    assert result["source_identifier"] == "copper_comex"
    assert result["date"] == "2026-07-24"
    assert result["value"] == 5.7


_SAMPLE_HTML = """
<table class="common-table">
  <thead>
    <tr><th>Date</th><th>Price</th><th>Open</th><th>High</th><th>Low</th><th>Vol.</th><th>Change %</th></tr>
  </thead>
  <tbody>
    <tr><td>Jul 24, 2026</td><td>5.700</td><td>5.710</td><td>5.720</td><td>5.680</td><td>12.5K</td><td>0.35%</td></tr>
    <tr><td>Jul 23, 2026</td><td>5.680</td><td>5.690</td><td>5.700</td><td>5.660</td><td>15.2K</td><td>-0.18%</td></tr>
  </tbody>
</table>
"""


def test_fetcher_parses_price_column_and_page_market_label():
    def handler(request):
        return httpx.Response(200, content=_SAMPLE_HTML.encode("utf-8"))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    payload = fetch_commodity_observations(http_client=client)
    copper = payload["iron_ore_62_cfr_china"]
    assert copper["series"]["source"] == "investing.com"
    assert copper["series"]["source_class"] == "free_web"
    assert copper["observations"] == [
        {
            "date": "2026-07-23",
            "value": 5.68,
            "source": "investing.com",
            "source_url": "https://www.investing.com/commodities/iron-ore-62-cfr-futures-historical-data",
            "source_identifier": "iron_ore_62_cfr_china",
            "source_class": "free_web",
            "retrieved_at": copper["observations"][0]["retrieved_at"],
        },
        {
            "date": "2026-07-24",
            "value": 5.7,
            "source": "investing.com",
            "source_url": "https://www.investing.com/commodities/iron-ore-62-cfr-futures-historical-data",
            "source_identifier": "iron_ore_62_cfr_china",
            "source_class": "free_web",
            "retrieved_at": copper["observations"][0]["retrieved_at"],
        },
    ]


def test_fetcher_reports_empty_observations_on_http_error():
    def handler(request):
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    payload = fetch_commodity_observations(http_client=client)
    assert payload["iron_ore_62_cfr_china"]["observations"] == []


def test_parse_investing_html_deduplicates_dates():
    html = """
    <table class="common-table">
      <tbody>
        <tr><td>Jul 24, 2026</td><td>5.700</td><td></td><td></td><td></td><td></td><td></td></tr>
        <tr><td>Jul 24, 2026</td><td>5.710</td><td></td><td></td><td></td><td></td><td></td></tr>
        <tr><td>Jul 23, 2026</td><td>5.680</td><td></td><td></td><td></td><td></td><td></td></tr>
      </tbody>
    </table>
    """
    parsed = _parse_investing_html(html, "copper_comex", "", "")
    assert len(parsed) == 2
    assert parsed[0]["date"] == "2026-07-23"
    assert parsed[-1]["date"] == "2026-07-24"


def test_fetcher_filters_by_date_range():
    html = """
    <table class="common-table">
      <tbody>
        <tr><td>Jul 24, 2026</td><td>5.700</td><td></td><td></td><td></td><td></td><td></td></tr>
        <tr><td>Jul 23, 2026</td><td>5.680</td><td></td><td></td><td></td><td></td><td></td></tr>
        <tr><td>Jul 22, 2026</td><td>5.660</td><td></td><td></td><td></td><td></td><td></td></tr>
      </tbody>
    </table>
    """

    def handler(request):
        return httpx.Response(200, content=html.encode("utf-8"))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    payload = fetch_commodity_observations(
        http_client=client, start_date="2026-07-23"
    )
    assert len(payload["iron_ore_62_cfr_china"]["observations"]) == 2


def test_fetcher_honours_markets_filter():
    def handler(request):
        return httpx.Response(200, content=_SAMPLE_HTML.encode("utf-8"))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    payload = fetch_commodity_observations(
        http_client=client, markets=["iron_ore_62_cfr_china"]
    )
    assert list(payload) == ["iron_ore_62_cfr_china"]


def test_fetcher_reports_diagnostic_on_empty_page():
    def handler(request):
        return httpx.Response(200, content=b"<html><body>no data here</body></html>")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    payload = fetch_commodity_observations(
        http_client=client, markets=["iron_ore_62_cfr_china"]
    )
    item = payload["iron_ore_62_cfr_china"]
    assert item["observations"] == []
    assert "_fetch_diagnostic" in item
    assert "no table rows" in item["_fetch_diagnostic"]["error"]


def test_fetcher_reports_http_error_diagnostic():
    def handler(request):
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    payload = fetch_commodity_observations(
        http_client=client, markets=["iron_ore_62_cfr_china"]
    )
    item = payload["iron_ore_62_cfr_china"]
    assert item["observations"] == []
    assert "_fetch_diagnostic" in item
    assert "503" in item["_fetch_diagnostic"]["error"]


def test_fetcher_falls_back_to_any_tablerows_outside_table():
    html = """
    <div class="historical-data-table">
      <tr><td>Jul 24, 2026</td><td>5.700</td><td>5.710</td><td>5.720</td><td>5.680</td><td>12.5K</td><td>0.35%</td></tr>
      <tr><td>Jul 23, 2026</td><td>5.680</td><td>5.690</td><td>5.700</td><td>5.660</td><td>15.2K</td><td>-0.18%</td></tr>
    </div>
    """

    def handler(request):
        return httpx.Response(200, content=html.encode("utf-8"))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    payload = fetch_commodity_observations(
        http_client=client, markets=["iron_ore_62_cfr_china"]
    )
    assert len(payload["iron_ore_62_cfr_china"]["observations"]) == 2


def test_fetcher_series_includes_units():
    def handler(request):
        return httpx.Response(200, content=_SAMPLE_HTML.encode("utf-8"))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    payload = fetch_commodity_observations(http_client=client)
    assert payload["iron_ore_62_cfr_china"]["series"]["units"] == "USD/tonne"


_SAMPLE_CSV = 'Date,Price,Open,High,Low,Vol.,Change %\n"Jul 24, 2026",5.700,5.710,5.720,5.680,12.5K,0.35%\n"Jul 23, 2026",5.680,5.690,5.700,5.660,15.2K,-0.18%\n'

_SAMPLE_CSV_HOOK = "Date,Price,Open,High,Low,Vol.,Change %\nJul 24 2026,5.700,,,,,,,,\n"


def test_parse_commodity_csv_parses_investing_download():
    observations = parse_commodity_csv(
        _SAMPLE_CSV,
        "copper_comex",
        source_url="https://example.com",
        retrieved_at="2026-07-30T12:00:00",
    )
    assert len(observations) == 2
    assert observations[0]["date"] == "2026-07-23"
    assert observations[0]["value"] == 5.68
    assert observations[1]["date"] == "2026-07-24"
    assert observations[1]["value"] == 5.7
    assert all(o["source"] == "investing.com" for o in observations)
    assert all(o["source_class"] == "free_web" for o in observations)
    assert all(o["source_identifier"] == "copper_comex" for o in observations)


def test_parse_commodity_csv_parses_investing_download_with_utf8_bom():
    observations = parse_commodity_csv(
        "\ufeff" + _SAMPLE_CSV,
        "copper_lme",
        retrieved_at="2026-07-30T12:00:00",
    )

    assert [(item["date"], item["value"]) for item in observations] == [
        ("2026-07-23", 5.68),
        ("2026-07-24", 5.7),
    ]


def test_parse_commodity_csv_rejects_missing_columns():
    with pytest.raises(ValueError, match="missing required Date/Price columns"):
        parse_commodity_csv(
            "Foo,Bar\n1,2\n",
            "copper_comex",
        )


def test_parse_commodity_csv_deduplicates_dates():
    csv_text = (
        "Date,Price,Open,High,Low,Vol.,Change %\n"
        '"Jul 24, 2026",5.700,,,,,,\n'
        '"Jul 24, 2026",5.710,,,,,,\n'
        '"Jul 23, 2026",5.680,,,,,,\n'
    )
    observations = parse_commodity_csv(csv_text, "copper_comex")
    assert len(observations) == 2
    assert observations[0]["date"] == "2026-07-23"


def test_method_market_registry_marks_shanghai_as_shfe_official():
    shanghai = MARKET_SERIES["copper_shanghai"]
    assert shanghai["source"] == "shfe"
    assert shanghai["source_class"] == "official_exchange"
    assert shanghai["access_adapter"] == "akshare"
    assert shanghai["source_identifier"] == "SHFE:CU"
    assert "instrument_id" not in shanghai
    assert "price_page_url" not in shanghai


def test_free_web_import_rejects_archived_lumber():
    from app.data_sources import tracked_commodities

    with pytest.raises(
        ValueError, match="lumber is not an Investing method market"
    ):
        tracked_commodities.validate_free_web_markets(["lumber"])


def test_lme_copper_is_active_method_investing_market():
    from app.data_sources.tracked_commodities import (
        ACTIVE_MARKET_SERIES,
        ARCHIVED_MARKET_SERIES,
        free_web_series,
    )

    assert "copper_lme" not in ARCHIVED_MARKET_SERIES
    assert "copper_lme" in ACTIVE_MARKET_SERIES
    assert "copper_lme" in free_web_series()


def test_comex_copper_is_active_method_investing_market():
    from app.data_sources.tracked_commodities import (
        ACTIVE_MARKET_SERIES,
        ARCHIVED_MARKET_SERIES,
        free_web_series,
    )

    assert "copper_comex" not in ARCHIVED_MARKET_SERIES
    assert "copper_comex" in ACTIVE_MARKET_SERIES
    assert "copper_comex" in free_web_series()


def test_method_market_registry_has_investing_instrument_ids():
    assert all(
        meta.get("instrument_id")
        for meta in MARKET_SERIES.values()
        if meta.get("source_class", "free_web") == "free_web"
    )


def test_parse_investing_history_payload_normalizes_and_deduplicates_dates():
    payload = {
        "data": [
            {"rowDate": "2026-07-29", "last_close": 4.5},
            {"rowDate": "2026-07-29", "last_close": 4.6},
            {"rowDate": "2026-07-28", "last_close": 4.4},
        ],
    }
    observations = parse_investing_history_payload(
        payload,
        "copper_comex",
        retrieved_at="2026-07-30T00:00:00+00:00",
    )
    assert [(item["date"], item["value"]) for item in observations] == [
        ("2026-07-28", 4.4),
        ("2026-07-29", 4.5),
    ]
    assert observations[0]["source_class"] == "free_web"
    assert observations[0]["source_identifier"] == "copper_comex"
