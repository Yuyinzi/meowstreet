import io
import zipfile
from pathlib import Path

from app.data_sources import usd
from app.db import macro_indicators
from app.services import cyclical_commodities_import

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
COT_FIXTURE = FIXTURE_DIR / "cftc_disaggregated_futures_only_2026.txt"


class FakeFredClient:
    def __init__(self, cache_dir):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def csv_path(self, series_id):
        return self.cache_dir / f"{series_id}.csv"

    def fetch_csvs(self, series_ids):
        for sid in series_ids:
            self.csv_path(sid).write_text(
                f"observation_date,{sid}\n2026-07-21,120.0\n2026-07-20,119.5\n"
            )


def _make_fake_cot_zip(target_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("fut_disagg_2026.txt", COT_FIXTURE.read_text())
    target_path.write_bytes(buf.getvalue())


def test_refresh_official_fetches_cot_and_all_three_usd_series(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    _make_fake_cot_zip(cache_dir / "cftc-disaggregated-futures-only-2026.zip")

    con = macro_indicators.connect(tmp_path / ".sqlite")

    usd_series = list(usd.USD_SERIES) + list(usd.INFLATION_SERIES)
    fake_fred = FakeFredClient(cache_dir)
    fake_fred.fetch_csvs(usd_series)

    result = cyclical_commodities_import.import_cached_official_(
        con, cache_dir, [2026]
    )

    assert result["cot_observations"] == 2
    assert result["usd_observations"] > 0
    loaded_cot = macro_indicators.load_cot_observations(con)
    assert len(loaded_cot) == 2
