import csv
from pathlib import Path

from app.resources import resource_path


GICS_REFERENCE_PATH = resource_path("gics_reference")
FIELDNAMES = (
    "record_type",
    "source",
    "source_value",
    "industry",
    "industry_group",
    "sector",
    "official_industry",
    "cycle_tag",
    "tag_source",
    "source_vintage",
    "resource_version",
)
_VALID_CYCLE_TAGS = {"cyclical", "defensive", "both"}
_INDUSTRY_FIELDS = (
    "industry",
    "industry_group",
    "sector",
    "official_industry",
    "cycle_tag",
    "tag_source",
    "source_vintage",
)


def load_gics_reference(path=GICS_REFERENCE_PATH):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDNAMES:
            raise ValueError("gics reference csv headers are invalid")
        rows = list(reader)
    return _normalize_rows(rows)


def _normalize_rows(rows):
    if any(None in row for row in rows):
        raise ValueError("gics reference csv row fields are invalid")
    normalized_rows = [
        {key: (value or "").strip() for key, value in row.items()} for row in rows
    ]
    versions = {row["resource_version"] for row in normalized_rows if row["resource_version"]}
    if len(versions) != 1:
        raise ValueError("gics reference versions are inconsistent")

    industries = {}
    for row in normalized_rows:
        record_type = row["record_type"]
        if record_type not in {"industry", "alias"}:
            raise ValueError(f"gics reference record type {record_type} is invalid")
        if record_type != "industry":
            continue
        if any(not row[field] for field in _INDUSTRY_FIELDS):
            raise ValueError("gics reference industry is required")
        industry = row["industry"]
        if row["cycle_tag"] not in _VALID_CYCLE_TAGS:
            raise ValueError(
                f"gics reference cycle tag {row['cycle_tag']} is invalid for {industry}"
            )
        if industry in industries:
            raise ValueError(f"gics reference industry {industry} is duplicated")
        industries[industry] = {
            "industry": industry,
            "industry_group": row["industry_group"],
            "sector": row["sector"],
            "official_industry": row["official_industry"],
            "cycle_tag": row["cycle_tag"],
            "tag_source": row["tag_source"],
            "source_vintage": row["source_vintage"],
        }

    aliases = {}
    for row in normalized_rows:
        if row["record_type"] != "alias":
            continue
        source = row["source"]
        source_value = row["source_value"]
        industry = row["industry"]
        if not source or not source_value or not industry:
            raise ValueError("gics reference alias fields are required")
        alias_key = (source, source_value)
        if alias_key in aliases:
            raise ValueError(f"gics reference alias {source} {source_value} is duplicated")
        if industry not in industries:
            raise ValueError(f"gics reference alias industry {industry} is unknown")
        aliases[alias_key] = {
            "source": source,
            "source_industry": source_value,
            "gics_industry": industry,
        }

    return {
        "version": versions.pop(),
        "industries": sorted(
            industries.values(),
            key=lambda row: (row["sector"], row["industry_group"], row["industry"]),
        ),
        "aliases": sorted(
            aliases.values(),
            key=lambda row: (row["source"], row["source_industry"]),
        ),
    }
