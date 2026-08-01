import csv
from bisect import bisect_right
from datetime import date
from datetime import datetime
from datetime import timedelta
from pathlib import Path

from app.http_client import HttpClient


FRED_CSV_BASE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
_QUARTER_END_MONTH_DAY = {
    1: (3, 31),
    4: (6, 30),
    7: (9, 30),
    10: (12, 31),
}


class FredClient:
    def __init__(self, cache_dir, http_client=None):
        self.cache_dir = Path(cache_dir)
        self._http_client = http_client

    def csv_path(self, series_id):
        return self.cache_dir / f"{series_id}.csv"

    def csv_url(self, series_id):
        normalized = str(series_id or "").strip().upper()
        if not normalized:
            raise ValueError("fred series id is required")
        return f"{FRED_CSV_BASE_URL}{normalized}"

    def fetch_csv(self, series_id):
        path = self.csv_path(series_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        client = self._http_client or HttpClient()
        response = client.request("GET", self.csv_url(series_id), timeout=30)
        path.write_bytes(response.content)
        return path

    def fetch_csvs(self, series_ids):
        return {series_id: self.fetch_csv(series_id) for series_id in series_ids}

    def parse_csv(self, series_id):
        return parse_fred_csv(self.csv_path(series_id), series_id)


def float_or_none(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == ".":
        return None
    return float(text)


def date_from_iso(date_iso):
    return datetime.strptime(str(date_iso), "%Y-%m-%d").date()


def date_iso(date_value):
    return date_value.isoformat()


def quarter_end_for_date(value):
    parsed = date_from_iso(value)
    quarter_month = ((parsed.month - 1) // 3) * 3 + 1
    end_month, end_day = _QUARTER_END_MONTH_DAY[quarter_month]
    return date(parsed.year, end_month, end_day).isoformat()


def next_sunday(date_value):
    days_until_sunday = (6 - date_value.weekday()) % 7
    return date_value + timedelta(days=days_until_sunday)


def parse_fred_csv(csv_path, series_id):
    path = Path(csv_path)
    if not path.exists():
        raise ValueError(f"fred csv does not exist: {path}")
    rows = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            value = float_or_none(row.get(series_id))
            observation_date = row.get("observation_date")
            if observation_date and value is not None:
                rows[observation_date] = value
    return dict(sorted(rows.items()))


def resample_to_weekly_sundays(rows, start_date=None, end_date=None):
    filtered_rows = {
        date_key: value for date_key, value in rows.items() if value is not None
    }
    dated_rows = sorted(
        (date_from_iso(date_key), value) for date_key, value in filtered_rows.items()
    )
    if not dated_rows:
        return []
    dates = [date_value for date_value, _ in dated_rows]
    values = {date_value: value for date_value, value in dated_rows}
    sunday = date_from_iso(start_date) if start_date else next_sunday(dates[0])
    last_sunday = date_from_iso(end_date) if end_date else dates[-1]
    points = []
    while sunday <= last_sunday:
        index = bisect_right(dates, sunday) - 1
        if index >= 0:
            source_date = dates[index]
            points.append({"date": date_iso(sunday), "value": values[source_date]})
        sunday = sunday + timedelta(days=7)
    return points


def compute_yoy(rows):
    dated_rows = {
        date_from_iso(date_key): value
        for date_key, value in rows.items()
        if value is not None
    }
    computed = {}
    for date_value, value in sorted(dated_rows.items()):
        prior_date = date_value.replace(year=date_value.year - 1)
        prior_value = dated_rows.get(prior_date)
        computed[date_iso(date_value)] = (
            round(((value / prior_value) - 1) * 100, 2) if prior_value else None
        )
    return computed
