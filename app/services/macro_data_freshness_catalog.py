from json import loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.resources import resource_path


class Storage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["macro", "rate", "benchmark", "regional", "gdp", "shfe", "cot", "economic", "ism_report", "ism_output", "fomc_calendar", "fomc_document", "fomc_extraction"]
    key: str = Field(min_length=1)
    region: str | None = None
    survey: str | None = None
    contract: str | None = None


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: Literal["macro_refresh", "investing_refresh"]
    fetch: str | None
    persist: str | None
    successful_check_supported: bool


class FreshnessPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["session", "max_age", "current_quarter"]
    timezone: str
    calendar_id: str | None = None
    max_age_days: int | None = Field(default=None, ge=1, le=31)


class MarketCalendar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str
    coverage_start: str
    coverage_end: str
    holidays: list[str]
    source_url: str
    verified_at: str


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_url: str
    storage: Storage
    lane: str
    tasks: list[Task] = Field(min_length=1)
    frequency: str
    storage_frequency: str
    period_basis: Literal["date", "month", "quarter", "weekly_resample"]
    schedule_id: str
    lineage_source: str | None = None
    lineage_transform: Literal["identity", "yoy"] = "identity"
    freshness_policy: FreshnessPolicy | None = None


class Release(BaseModel):
    model_config = ConfigDict(extra="forbid")
    at: str
    period: str
    precision: Literal["exact", "date", "window"]
    window_end: str | None = None
    version: str | None = None


class Schedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_url: str | None
    source_urls: list[str] = Field(default_factory=list)
    verified_at: str
    coverage_start: str | None
    coverage_end: str | None
    timezone: str | None
    note: str
    releases: list[Release]


class CollectionSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    label: str
    cadence: str
    timezone: str
    verified_at: str


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    datasets: list[Dataset] = Field(min_length=1)
    schedules: dict[str, Schedule]
    collection_schedules: list[CollectionSchedule]
    market_calendars: dict[str, MarketCalendar] = Field(default_factory=dict)


def load_catalog(path=None):
    payload = loads(Path(path or resource_path("macro_data_freshness")).read_text())
    if not payload.get("version"):
        raise ValueError("catalog version is required")
    try:
        catalog = Catalog.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise ValueError("freshness catalog is invalid") from exc
    seen = set()
    for row in catalog["datasets"]:
        if row["id"] in seen:
            raise ValueError(f"dataset id is duplicated: {row['id']}")
        seen.add(row["id"])
        if row["schedule_id"] not in catalog["schedules"]:
            raise ValueError(f"dataset schedule is unknown: {row['schedule_id']}")
        policy = row.get("freshness_policy")
        if policy and ((policy["kind"] == "session" and policy["calendar_id"] not in catalog["market_calendars"]) or (policy["kind"] == "max_age" and policy["max_age_days"] is None)):
            raise ValueError(f"dataset freshness policy is invalid: {row['id']}")
        if policy and policy["kind"] == "current_quarter" and row["period_basis"] != "quarter":
            raise ValueError(f"dataset freshness policy is invalid: {row['id']}")
    return catalog
