from pathlib import Path

from app.data_sources.fred import parse_fred_csv


USD_SERIES = {
    "DTWEXBGS": ("usd_broad", "Trade-Weighted USD Broad"),
    "DTWEXAFEGS": ("usd_afe", "Trade-Weighted USD AFE"),
    "DTWEXEMEGS": ("usd_eme", "Trade-Weighted USD EME"),
}

INFLATION_SERIES = {
    "CPIAUCSL": ("cpi_all_items", "CPI All Items"),
    "CPILFESL": ("core_cpi", "CPI All Items Less Food and Energy"),
    "PPIACO": ("ppi_all_commodities", "PPI All Commodities"),
}

FRED_GRAPH_URL = "https://fred.stlouisfed.org/series/{}"


def _build_observations(cache_dir, series_map, units):
    cache_dir = Path(cache_dir)
    result = {}
    for fred_id, (id, title) in series_map.items():
        csv_path = cache_dir / f"{fred_id}.csv"
        if not csv_path.exists():
            result[id] = {
                "series_id": id,
                "title": title,
                "units": units,
                "source": "fred",
                "observations": [],
            }
            continue
        parsed = parse_fred_csv(csv_path, fred_id)
        observations = [
            {
                "date": date_val,
                "value": value,
                "source": "fred",
                "revision_status": "official_current_history",
                "source_url": FRED_GRAPH_URL.format(fred_id),
                "source_identifier": fred_id,
            }
            for date_val, value in parsed.items()
        ]
        observations.sort(key=lambda o: o["date"])
        result[id] = {
            "series_id": id,
            "title": title,
            "units": units,
            "source": "fred",
            "observations": observations,
        }
    return result


def parse_usd_csvs(cache_dir):
    usd_result = _build_observations(cache_dir, USD_SERIES, "index")
    inflation_result = _build_observations(cache_dir, INFLATION_SERIES, "index")
    return {**usd_result, **inflation_result}
