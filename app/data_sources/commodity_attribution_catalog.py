import re
from pathlib import Path

from pypdf import PdfReader

SOURCE_REF = "cyclical_commodities_demand_supply"
STATUS_CATALOGED = "cataloged"

VALID_COMMODITY_IDS = frozenset({"oil", "copper", "lumber", "iron_ore"})
VALID_SOURCE_TYPES = frozenset(
    {"official_data", "industry_body", "reference_market_data"}
)

COVERAGE_VOCABULARY = frozenset(
    {
        "prices",
        "reserves",
        "production",
        "refining",
        "processing",
        "imports",
        "exports",
        "movements",
        "stocks",
        "consumption",
        "sales",
        "upstream_investment",
        "downstream_capacity",
        "market_indicators",
        "trade",
        "final_consumption",
        "sector_consumption",
        "market_reports",
        "industry_surveys",
        "publications",
        "usage",
        "forecasts",
        "mining_production",
        "refined_inventories",
        "production_sales",
        "inventories",
        "semis_production",
        "demand",
        "end_use",
        "statistics_digest",
        "statistics_releases",
        "industry_activity_indicators",
    }
)

_SECTION_HEADINGS = {
    "Oil": "oil",
    "Copper": "copper",
    "Lumber": "lumber",
    "Iron Ore": "iron_ore",
}

_URL_RE = re.compile(r"https?://[^\s]+")

_TRADE_TABLE_PREFIXES = ("Top Suppliers", "Top Consumers")

_SOURCE_DEFINITIONS = [
    {
        "source_name": "Energy Information Administration",
        "source_type": "official_data",
        "coverage": [
            "prices",
            "reserves",
            "production",
            "refining",
            "processing",
            "imports",
            "exports",
            "movements",
            "stocks",
            "consumption",
            "sales",
        ],
    },
    {
        "source_name": "OPEC",
        "source_type": "industry_body",
        "coverage": [
            "reserves",
            "upstream_investment",
            "downstream_capacity",
            "market_indicators",
            "production",
        ],
    },
    {
        "source_name": "International Energy Agency",
        "source_type": "official_data",
        "coverage": [
            "production",
            "trade",
            "final_consumption",
            "sector_consumption",
            "stocks",
            "market_reports",
        ],
    },
    {
        "source_name": "BP World Energy",
        "source_type": "reference_market_data",
        "coverage": [
            "reserves",
            "production",
            "consumption",
            "prices",
            "refining",
            "trade",
        ],
    },
    {
        "source_name": "World Bank Commodity Markets",
        "source_type": "reference_market_data",
        "coverage": ["prices"],
    },
    {
        "source_name": "US Geological Survey",
        "source_type": "official_data",
        "coverage": ["industry_surveys", "publications"],
    },
    {
        "source_name": "International Copper Study Group",
        "source_type": "industry_body",
        "coverage": ["production", "usage", "stocks", "forecasts"],
    },
    {
        "source_name": "Chilean Copper Commission",
        "source_type": "official_data",
        "coverage": [
            "mining_production",
            "refined_inventories",
            "prices",
            "production_sales",
            "inventories",
        ],
    },
    {
        "source_name": "International Wrought Copper Council",
        "source_type": "industry_body",
        "coverage": ["semis_production", "demand", "end_use"],
    },
    {
        "source_name": "Kitco Metals",
        "source_type": "reference_market_data",
        "coverage": ["inventories"],
    },
    {
        "source_name": "Food and Agriculture Organization of the United Nations",
        "source_type": "official_data",
        "coverage": ["production", "imports", "exports"],
    },
    {
        "source_name": "International Tropical Timber Organization",
        "source_type": "industry_body",
        "coverage": ["production", "trade"],
    },
    {
        "source_name": "Joint Forest Sector Questionnaire",
        "source_type": "official_data",
        "coverage": ["production", "trade"],
    },
    {
        "source_name": "Government of Western Australia",
        "source_type": "official_data",
        "coverage": [
            "statistics_digest",
            "statistics_releases",
            "industry_activity_indicators",
        ],
    },
]


def parse_commodity_attribution_text(text, source_path):
    if not text or not text.strip():
        raise ValueError(f"commodities attribution text is empty for {source_path}")
    normalized = _join_url_line_wraps(text)
    records = _parse_records(normalized)
    if not records:
        raise ValueError(f"no commodities attribution resources found in {source_path}")
    return _validate_records(records)


def parse_commodity_attribution_pdf(path):
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise ValueError(f"commodities attribution pdf does not exist: {pdf_path}")
    try:
        reader = PdfReader(str(pdf_path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise ValueError(f"commodities attribution pdf could not be read: {pdf_path}") from exc
    if not text.strip():
        raise ValueError(f"commodities attribution pdf contains no text: {pdf_path}")
    return parse_commodity_attribution_text(text, pdf_path)


def _join_url_line_wraps(text):
    return text.replace("-\n", "-")


def _parse_records(text):
    records = []
    current_commodity = None
    current_source = None
    in_trade_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in _SECTION_HEADINGS:
            current_commodity = _SECTION_HEADINGS[stripped]
            current_source = None
            in_trade_table = False
            continue
        if current_commodity is None:
            continue
        if in_trade_table:
            continue
        if stripped.startswith(_TRADE_TABLE_PREFIXES):
            in_trade_table = True
            continue
        urls = list(_URL_RE.finditer(line))
        if urls:
            heading = line[: urls[0].start()].strip()
            matched = _match_source_name(heading)
            if matched:
                current_source = matched
            if current_source is not None:
                for url_match in urls:
                    records.append(
                        _build_record(
                            current_commodity,
                            current_source,
                            url_match.group(0).rstrip(".,;"),
                        )
                    )
        else:
            heading = stripped.rstrip(" -–")
            matched = _match_source_name(heading)
            if matched:
                current_source = matched
    return records


def _match_source_name(heading):
    for definition in _SOURCE_DEFINITIONS:
        if definition["source_name"] in heading:
            return definition["source_name"]
    return None


def _build_record(commodity_id, source_name, source_url):
    definition = _definition_for(source_name)
    return {
        "commodity_id": commodity_id,
        "source_name": source_name,
        "source_url": source_url,
        "source_type": definition["source_type"],
        "coverage": list(definition["coverage"]),
        "source_ref": SOURCE_REF,
        "status": STATUS_CATALOGED,
    }


def _definition_for(source_name):
    for definition in _SOURCE_DEFINITIONS:
        if definition["source_name"] == source_name:
            return definition
    raise ValueError(f"commodities attribution source {source_name} is not cataloged")


def _validate_records(records):
    seen = set()
    for record in records:
        _validate_record(record)
        key = (record["commodity_id"], record["source_url"])
        if key in seen:
            raise ValueError(
                f"duplicate commodities attribution url {record['source_url']} for {record['commodity_id']}"
            )
        seen.add(key)
    return records


def _validate_record(record):
    if not record["source_name"]:
        raise ValueError("commodities attribution record has an empty source name")
    if not record["source_url"]:
        raise ValueError("commodities attribution record has an empty source url")
    if record["commodity_id"] not in VALID_COMMODITY_IDS:
        raise ValueError(
            f"commodities attribution commodity {record['commodity_id']} is not a valid commodity"
        )
    if record["source_type"] not in VALID_SOURCE_TYPES:
        raise ValueError(
            f"commodities attribution source type {record['source_type']} is not a valid source type"
        )
    if not record["coverage"]:
        raise ValueError(
            f"commodities attribution coverage is empty for {record['source_name']}"
        )
    unknown = [
        token for token in record["coverage"] if token not in COVERAGE_VOCABULARY
    ]
    if unknown:
        raise ValueError(
            f"commodities attribution coverage {unknown} is not in the method vocabulary"
        )
    if record["source_ref"] != SOURCE_REF:
        raise ValueError("commodities attribution source_ref is not the source pdf path")
    if record["status"] != STATUS_CATALOGED:
        raise ValueError(f"commodities attribution status {record['status']} is not cataloged")
