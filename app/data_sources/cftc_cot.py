import csv
import hashlib
import io
from pathlib import Path

from app.http_client import HttpClient


REPORT_TYPE = "disaggregated_futures_only"

COT_COMMODITY_REGISTRY = {
    "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE": "crude_oil_wti",
    "BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE": "crude_oil_brent",
    "NY HARBOR ULSD - NEW YORK MERCANTILE EXCHANGE": "heating_oil",
    "NATURAL GAS INDEX: EP SAN JUAN - ICE FUTURES ENERGY DIV": "natural_gas",
    "NAT GAS NYME - NEW YORK MERCANTILE EXCHANGE": "us_natural_gas",
    "PALLADIUM - NEW YORK MERCANTILE EXCHANGE": "palladium",
    "PLATINUM - NEW YORK MERCANTILE EXCHANGE": "platinum",
    "SILVER - COMMODITY EXCHANGE INC.": "silver",
    "GOLD - COMMODITY EXCHANGE INC.": "gold",
    "COPPER- #1 - COMMODITY EXCHANGE INC.": "copper",
    "ALUMINUM - COMMODITY EXCHANGE INC.": "aluminium",
    "STEEL-HRC - COMMODITY EXCHANGE INC.": "steel",
}

REPORT_URL_TEMPLATE = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"

HEADER_MAPPING = {
    "Market_and_Exchange_Names": "market_name",
    "Report_Date_as_YYYY-MM-DD": "report_date",
    "CFTC_Contract_Market_Code": "cftc_contract_market_code",
    "Open_Interest_All": "open_interest",
    "M_Money_Positions_Long_All": "manager_long",
    "M_Money_Positions_Short_All": "manager_short",
}


def _hash_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


_REQUIRED_HEADERS = [
    "Market_and_Exchange_Names",
    "Report_Date_as_YYYY-MM-DD",
    "CFTC_Contract_Market_Code",
    "Open_Interest_All",
    "M_Money_Positions_Long_All",
    "M_Money_Positions_Short_All",
]


def _validate_headers(reader):
    actual = reader.fieldnames or []
    missing = [h for h in _REQUIRED_HEADERS if h not in actual]
    if missing:
        raise ValueError(
            f"cftc csv is missing required headers: {', '.join(missing)}. "
            f"Actual headers ({len(actual)}): {actual[:5]}..."
        )


def parse_disaggregated_futures_only(
    text, source_url, publication_date, code_registry=None
):
    source_hash = _hash_text(text)
    reader = csv.DictReader(io.StringIO(text))
    _validate_headers(reader)
    rows = []
    seen = set()
    for raw in reader:
        if "Market_and_Exchange_Names" not in raw:
            continue
        market_name = raw["Market_and_Exchange_Names"].strip()
        contract_code = raw.get("CFTC_Contract_Market_Code", "").strip()
        commodity_id = COT_COMMODITY_REGISTRY.get(market_name)
        if commodity_id is None:
            if code_registry and contract_code in code_registry:
                commodity_id = code_registry[contract_code]
            else:
                continue

        report_date = raw.get("Report_Date_as_YYYY-MM-DD", "").strip()
        raw_longs = raw.get("M_Money_Positions_Long_All", "").strip()
        raw_shorts = raw.get("M_Money_Positions_Short_All", "").strip()
        raw_oi = raw.get("Open_Interest_All", "").strip()

        if (
            not raw_longs
            or not raw_shorts
            or not raw_oi
            or not report_date
            or not contract_code
        ):
            missing = []
            if not raw_longs:
                missing.append("manager long")
            if not raw_shorts:
                missing.append("manager short")
            if not raw_oi:
                missing.append("open interest")
            if not report_date:
                missing.append("report_date")
            if not contract_code:
                missing.append("cftc contract market code")
            raise ValueError(
                f"cftc row {commodity_id} is missing required field(s): {', '.join(missing)}"
            )

        manager_longs = float(raw_longs)
        manager_shorts = float(raw_shorts)
        open_interest = float(raw_oi)

        if manager_longs < 0 or manager_shorts < 0 or open_interest < 0:
            raise ValueError(
                f"cftc row has negative values for {commodity_id}: "
                f"longs={manager_longs} shorts={manager_shorts} oi={open_interest}"
            )
        if manager_shorts > open_interest:
            raise ValueError(
                f"cftc row {commodity_id} manager short exceeds open interest"
            )
        if manager_longs > open_interest:
            raise ValueError(
                f"cftc row {commodity_id} manager long exceeds open interest"
            )

        key = (commodity_id, report_date)
        if key in seen:
            raise ValueError(
                f"cftc row is duplicated for {commodity_id} on {report_date}"
            )
        seen.add(key)

        rows.append(
            {
                "commodity_id": commodity_id,
                "market_name": market_name,
                "report_date": report_date,
                "cftc_contract_market_code": contract_code,
                "manager_longs": manager_longs,
                "manager_shorts": manager_shorts,
                "open_interest": open_interest,
                "publication_date": publication_date,
                "report_type": REPORT_TYPE,
                "source_url": source_url,
                "source_hash": source_hash,
            }
        )
    return rows


def historical_report_url(year):
    return REPORT_URL_TEMPLATE.format(year=year)


def fetch_historical_report(year, cache_dir, http_client=None):
    url = historical_report_url(year)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"cftc-disaggregated-futures-only-{year}.zip"
    client = http_client or HttpClient()
    response = client.request("GET", url, timeout=30)
    dest.write_bytes(response.content)
    return dest
