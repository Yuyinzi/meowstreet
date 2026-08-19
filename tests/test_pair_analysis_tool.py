import pytest

from app.tools import pair_analysis


def workbook_rows():
    return [
        ("2014-11-07", 19.110001, 61.560001),
        ("2014-11-10", 18.42, 61.849998),
        ("2014-11-11", 18.51, 61.509998),
        ("2014-11-12", 18.299999, 61.82),
        ("2014-11-13", 18.209999, 61.990002),
        ("2014-11-14", 18.84, 62.060001),
        ("2014-11-17", 19.200001, 61.470001),
        ("2014-11-18", 19.450001, 61.990002),
        ("2014-11-19", 18.700001, 62.630001),
        ("2014-11-20", 17.59, 65.870003),
    ]


WORKBOOK_RATIOS = [
    0.3104288611041446,
    0.2978173095494684,
    0.3009266883734901,
    0.2960206890973795,
    0.2937570319807378,
    0.30357717847925914,
    0.3123474977656174,
    0.3137602899254625,
    0.29857896697143593,
    0.26704112948044045,
]

WORKBOOK_CEW_INDEX = [
    0.3104288611041446,
    0.3040933800631873,
    0.3056721058174881,
    0.30316786623973474,
    0.3020055229859319,
    0.30705916777135217,
    0.31145245703265795,
    0.31216278749698123,
    0.3045328049542501,
    0.2876174135460469,
]


def aligned_fixture():
    long_rows = [
        {"date": date_value, "adjusted_close": long_close}
        for date_value, long_close, _ in workbook_rows()
    ]
    short_rows = [
        {"date": date_value, "adjusted_close": short_close}
        for date_value, _, short_close in workbook_rows()
    ]
    return pair_analysis.align_price_series(long_rows, short_rows)


def test_align_price_series_joins_on_common_dates():
    long_rows = [
        {"date": "2024-01-01", "adjusted_close": 10.0},
        {"date": "2024-01-02", "adjusted_close": 11.0},
        {"date": "2024-01-03", "adjusted_close": 12.0},
    ]
    short_rows = [
        {"date": "2024-01-02", "adjusted_close": 20.0},
        {"date": "2024-01-03", "adjusted_close": 21.0},
        {"date": "2024-01-04", "adjusted_close": 22.0},
    ]

    aligned = pair_analysis.align_price_series(long_rows, short_rows)

    assert aligned == {
        "dates": ["2024-01-02", "2024-01-03"],
        "long_close": [11.0, 12.0],
        "short_close": [20.0, 21.0],
    }


def test_align_price_series_requires_two_common_sessions():
    with pytest.raises(ValueError, match="fewer than 2 common trading sessions"):
        pair_analysis.align_price_series(
            [{"date": "2024-01-01", "adjusted_close": 10.0}],
            [{"date": "2024-01-02", "adjusted_close": 20.0}],
        )


def test_ratio_series_matches_workbook():
    ratios = pair_analysis.ratio_series(aligned_fixture())

    assert ratios == pytest.approx(WORKBOOK_RATIOS, abs=1e-12)


def test_spread_series():
    spreads = pair_analysis.spread_series(aligned_fixture())

    assert spreads[0] == pytest.approx(19.110001 - 61.560001)
    assert spreads[-1] == pytest.approx(17.59 - 65.870003)


def test_cew_index_series_matches_workbook():
    aligned = aligned_fixture()

    index = pair_analysis.cew_index_series(
        aligned["long_close"], aligned["short_close"], WORKBOOK_RATIOS[0]
    )

    assert index == pytest.approx(WORKBOOK_CEW_INDEX, abs=1e-9)


def test_window_outperformance_uses_equal_weight_return_difference():
    aligned = aligned_fixture()

    result = pair_analysis.window_outperformance(aligned, 5)

    assert result["sessions"] == 5
    assert result["start_date"] == "2014-11-14"
    assert result["end_date"] == "2014-11-20"
    assert result["long_return"] == pytest.approx(17.59 / 18.84 - 1)
    assert result["short_return"] == pytest.approx(65.870003 / 62.060001 - 1)
    assert result["outperformance"] == pytest.approx(
        result["long_return"] - result["short_return"]
    )


def test_window_outperformance_rejects_tiny_windows():
    with pytest.raises(ValueError, match="sessions window 1 is too small"):
        pair_analysis.window_outperformance(aligned_fixture(), 1)


def context(symbol, sector, status="resolved"):
    return {
        "symbol": symbol,
        "status": status,
        "sector": sector if status == "resolved" else None,
    }


def test_classify_pair_same_sector_is_intra_sector_with_stock_risk():
    result = pair_analysis.classify_pair(
        context("LULU", "Consumer Discretionary"),
        context("UA", "Consumer Discretionary"),
    )

    assert result == {
        "pair_type": "intra_sector_constituent",
        "retained_risks": ["stock"],
        "missing": [],
    }


def test_classify_pair_different_sectors_keeps_sector_and_stock_risk():
    result = pair_analysis.classify_pair(
        context("LULU", "Consumer Discretionary"),
        context("CL", "Consumer Staples"),
    )

    assert result == {
        "pair_type": "cross_sector_constituent",
        "retained_risks": ["sector", "stock"],
        "missing": [],
    }


@pytest.mark.parametrize("long_status,short_status,missing", [
    ("unmapped_industry", "resolved", ["AAA"]),
    ("resolved", "unclassified", ["BBB"]),
    ("unmapped_industry", "unclassified", ["AAA", "BBB"]),
])
def test_classify_pair_unclassifiable_when_either_leg_unresolved(
    long_status, short_status, missing
):
    result = pair_analysis.classify_pair(
        context("AAA", "Consumer Discretionary", long_status),
        context("BBB", "Consumer Staples", short_status),
    )

    assert result["pair_type"] == "unclassifiable"
    assert result["retained_risks"] == []
    assert result["missing"] == missing
