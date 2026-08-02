import hashlib

import pytest

from app.data_sources import federal_reserve_g17

SOURCE_URL = "https://www.federalreserve.gov/releases/g17/Current/default.htm"


def g17_payload():
    return {
        "release_date": "2026-06-16",
        "csv": (
            '"Description:","Unit:","Multiplier:","Currency:","Unique Identifier:",'
            '"Series Name:",2025-12,2026-01,2026-02,2026-03,2026-04,2026-05,2026-06\n'
            '"Total index; s.a. IP","Index:_2017_100","1","NA",'
            '"G17/IP_MARKET_GROUPS/IP.B50001.S","IP.B50001.S",'
            "101.4941,101.0388,101.9263,101.6172,102.4196,102.5606,102.6395\n"
            '"Manufacturing (SIC); s.a. IP","Index:_2017_100","1","NA",'
            '"G17/IP_MAJOR_INDUSTRY_GROUPS/IP.B00004.S","IP.B00004.S",'
            "96.2473,96.2586,96.9490,97.1426,97.8276,97.9534,97.9258\n"
            '"Total index; s.a. CAPUTL","Percentage","1","NA",'
            '"G17/CAPUTL/CAPUTL.B50001.S","CAPUTL.B50001.S",'
            "75.6422,75.2420,75.8299,75.5313,76.0625,76.1019,76.0937\n"
        ),
    }


def _parse(payload=None):
    return federal_reserve_g17.parse_g17_release(payload or g17_payload(), SOURCE_URL)


def test_parse_g17_release_extracts_three_series():
    result = _parse()
    by_id = {obs["series_id"]: obs for obs in result["observations"]}

    assert result["source_url"] == SOURCE_URL
    assert result["release_date"] == "2026-06-16"
    assert result["reference_period"] == "2026-06"
    assert result["method_status"] == "pending_approval"
    assert result["data_status"] == "available"

    assert by_id["manufacturing_production"]["reference_period"] == "2026-06"
    assert by_id["manufacturing_production"]["value_at_release"] == 97.9258
    assert (
        by_id["manufacturing_production"]["seasonal_adjustment"]
        == "seasonally_adjusted"
    )
    assert by_id["manufacturing_production"]["vintage_id"] == (
        "manufacturing_production:2026-06:2026-06-16"
    )

    assert by_id["total_industrial_production"]["value_at_release"] == 102.6395
    assert by_id["capacity_utilization"]["value_at_release"] == 76.0937

    expected_order = [
        "manufacturing_production",
        "total_industrial_production",
        "capacity_utilization",
    ]
    assert [obs["series_id"] for obs in result["observations"]] == expected_order


def test_parse_g17_release_accepts_bytes_csv():
    payload = g17_payload()
    payload["csv"] = payload["csv"].encode("utf-8")
    result = _parse(payload)
    by_id = {obs["series_id"]: obs for obs in result["observations"]}
    assert by_id["total_industrial_production"]["value_at_release"] == 102.6395


def test_parse_g17_release_sets_source_hash():
    payload = g17_payload()
    result = _parse(payload)
    expected = hashlib.sha256(payload["csv"].encode("utf-8")).hexdigest()
    assert result["observations"][0]["source_hash"] == expected


@pytest.mark.parametrize(
    "series_name,series_id",
    [
        ("IP.B50001.S", "total_industrial_production"),
        ("IP.B00004.S", "manufacturing_production"),
        ("CAPUTL.B50001.S", "capacity_utilization"),
    ],
)
def test_parse_g17_release_rejects_missing_series(series_name, series_id):
    payload = g17_payload()
    lines = [line for line in payload["csv"].splitlines() if series_name not in line]
    payload["csv"] = "\n".join(lines)
    with pytest.raises(ValueError, match=f"missing {series_id}"):
        _parse(payload)


def test_parse_g17_release_rejects_missing_release_date():
    payload = g17_payload()
    del payload["release_date"]
    with pytest.raises(ValueError, match="missing release date"):
        _parse(payload)


def test_parse_g17_release_rejects_invalid_release_date():
    payload = g17_payload()
    payload["release_date"] = "not-a-date"
    with pytest.raises(ValueError, match="invalid release date"):
        _parse(payload)


def test_parse_g17_release_rejects_missing_csv():
    payload = {"release_date": "2026-06-16"}
    with pytest.raises(ValueError, match="missing csv"):
        _parse(payload)


def test_parse_g17_release_rejects_non_object_payload():
    with pytest.raises(ValueError, match="not an object"):
        federal_reserve_g17.parse_g17_release(["not", "a", "dict"], SOURCE_URL)


def test_parse_g17_release_rejects_invalid_value():
    payload = g17_payload()
    payload["csv"] = payload["csv"].replace("102.6395", "abc")
    with pytest.raises(ValueError, match="invalid value"):
        _parse(payload)


def test_parse_g17_release_rejects_missing_series_value():
    payload = g17_payload()
    payload["csv"] = (
        payload["csv"].replace("102.6395", "").replace(",,101.0388", ",,101.0388")
    )
    with pytest.raises(ValueError, match="invalid value"):
        _parse(payload)


def test_parse_g17_release_rejects_no_month_columns():
    payload = g17_payload()
    payload["csv"] = (
        '"Description:","Series Name:",2026/06\n'
        '"Total index; s.a. IP","IP.B50001.S",102.6395\n'
    )
    with pytest.raises(ValueError, match="no month columns"):
        _parse(payload)
