import hashlib
from pathlib import Path


REPORT_TYPE = "disaggregated_futures_only"

COT_COMMODITY_REGISTRY = {
    "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE": "crude_oil_wti",
    "CRUDE OIL, BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE": "crude_oil_brent",
    "HEATING OIL - NEW YORK MERCANTILE EXCHANGE": "heating_oil",
    "NATURAL GAS - NEW YORK MERCANTILE EXCHANGE": "natural_gas",
    "PALLADIUM - NEW YORK MERCANTILE EXCHANGE": "palladium",
    "PLATINUM - NEW YORK MERCANTILE EXCHANGE": "platinum",
    "SILVER - COMMODITY EXCHANGE INC.": "silver",
    "GOLD - COMMODITY EXCHANGE INC.": "gold",
    "COPPER - GRADE #1 - COMMODITY EXCHANGE INC.": "copper",
    "LME ALUMINUM ALLOY - COMMODITY EXCHANGE INC.": "aluminium",
    "STEEL HRC FUTURES - NEW YORK MERCANTILE EXCHANGE": "steel",
}

REPORT_URL_TEMPLATE = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"

COLUMNS = [
    "market_and_exchange_names",
    "as_of_date",
    "open_interest",
    "prod_merchant_long",
    "prod_merchant_short",
    "swap_dealer_long",
    "swap_dealer_short",
    "swap_dealer_spread",
    "manager_long",
    "manager_short",
    "manager_spread",
    "other_reportable_long",
    "other_reportable_short",
    "other_reportable_spread",
    "total_reportable_long",
    "total_reportable_short",
    "non_reportable_long",
    "non_reportable_short",
]

_COLUMN_INDEX = {name: i for i, name in enumerate(COLUMNS)}


def _hash_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _parse_row(row, source_url, publication_date, source_hash):
    fields = row.split("|")
    raw_market = fields[_COLUMN_INDEX["market_and_exchange_names"]].strip().upper()
    commodity_id = COT_COMMODITY_REGISTRY.get(raw_market)
    if commodity_id is None:
        return None

    report_date = fields[_COLUMN_INDEX["as_of_date"]].strip()

    raw_manager_longs = fields[_COLUMN_INDEX["manager_long"]].strip()
    raw_manager_shorts = fields[_COLUMN_INDEX["manager_short"]].strip()
    raw_open_interest = fields[_COLUMN_INDEX["open_interest"]].strip()

    if not raw_manager_longs or not raw_manager_shorts or not raw_open_interest:
        missing = []
        if not raw_manager_longs:
            missing.append("manager long")
        if not raw_manager_shorts:
            missing.append("manager short")
        if not raw_open_interest:
            missing.append("open interest")
        raise ValueError(
            f"cftc row {commodity_id} is missing required field(s): {', '.join(missing)}"
        )

    manager_longs = float(raw_manager_longs)
    manager_shorts = float(raw_manager_shorts)
    open_interest = float(raw_open_interest)

    if manager_longs < 0 or manager_shorts < 0 or open_interest < 0:
        raise ValueError(
            f"cftc row has negative values for {commodity_id}: "
            f"longs={manager_longs} shorts={manager_shorts} oi={open_interest}"
        )

    return {
        "commodity_id": commodity_id,
        "report_date": report_date,
        "manager_longs": manager_longs,
        "manager_shorts": manager_shorts,
        "open_interest": open_interest,
        "publication_date": publication_date,
        "report_type": REPORT_TYPE,
        "source_url": source_url,
        "source_hash": source_hash,
    }


def parse_disaggregated_futures_only(text, source_url, publication_date):
    source_hash = hashlib.sha256(text.encode()).hexdigest()
    rows = []
    seen = set()
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("Market and Exchange Names"):
            continue
        result = _parse_row(line, source_url, publication_date, source_hash)
        if result is not None:
            key = (result["commodity_id"], result["report_date"])
            if key in seen:
                raise ValueError(
                    f"cftc row is duplicated for {result['commodity_id']} on {result['report_date']}"
                )
            seen.add(key)
            if result["manager_longs"] == 0.0 and result["manager_shorts"] == 0.0:
                raise ValueError(
                    f"cftc row {result['commodity_id']} has zero manager long and short"
                )
            if result["manager_shorts"] > result["open_interest"]:
                raise ValueError(
                    f"cftc row {result['commodity_id']} manager short exceeds open interest"
                )
            if result["manager_longs"] > result["open_interest"]:
                raise ValueError(
                    f"cftc row {result['commodity_id']} manager long exceeds open interest"
                )
            rows.append(result)
    return rows


def historical_report_url(year):
    return REPORT_URL_TEMPLATE.format(year=year)


def fetch_historical_report(year, cache_dir):
    import urllib.request

    url = historical_report_url(year)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"cftc-disaggregated-futures-only-{year}.zip"
    urllib.request.urlretrieve(url, str(dest))
    return dest
