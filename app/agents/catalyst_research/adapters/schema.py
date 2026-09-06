from collections.abc import Mapping
import re
from typing import Literal

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator
from soupsieve.util import SelectorSyntaxError

from app.agents.catalyst_research.domain import canonicalize_public_url, url_host


AdapterSourceType = Literal["press_releases", "events_presentations"]
ValueSource = Literal["text", "attribute"]
PaginationType = Literal["none", "next_link", "page_parameter"]
ALLOWED_ATTRIBUTES = frozenset({"href", "datetime", "data-date", "aria-label", "title"})
ALLOWED_DATE_FORMATS = frozenset(
    {
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%m/%d/%Y",
        "%m/%d/%y",
    }
)
_IDENTITY_FIELDS = {"schema_version", "ticker", "source_type", "source_url", "allowed_hosts"}
_FORBIDDEN_SELECTOR_MARKERS = ("javascript:", "xpath", "lambda", "__", "=>", "{{", "}}", "<script")


def _validate_selector(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("selector is required")
    lowered = cleaned.casefold()
    if any(marker in lowered for marker in _FORBIDDEN_SELECTOR_MARKERS) or any(character in cleaned for character in "{};"):
        raise ValueError("selector contains unsupported content")
    try:
        BeautifulSoup("<html><body><a href='x'></a><a href='y'></a></body></html>", "html.parser").select(cleaned)
    except SelectorSyntaxError as exc:
        raise ValueError("selector is invalid") from exc
    return cleaned


def _item_selector_is_broad(selector: str) -> bool:
    if re.search(r"(?<![\w-])\*(?![=])", selector):
        return True
    probe = BeautifulSoup(
        "<html><body><main><article class='item'><a href='x'></a><span></span></article>"
        "<article class='other'><a href='y'></a></article><a href='z'></a></main></body></html>",
        "html.parser",
    )
    matched = probe.select(selector)
    anchors = probe.find_all("a")
    return bool(anchors) and all(any(node is item for item in matched) for node in anchors)


def _validate_public_host(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("allowed host is invalid")
    candidate = value.strip().casefold().rstrip(".")
    if "://" in candidate or "/" in candidate or "@" in candidate:
        raise ValueError("allowed host is invalid")
    try:
        host = url_host(f"https://{candidate}")
    except ValueError as exc:
        raise ValueError("allowed host is invalid") from exc
    return host


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selector: str = Field(min_length=1, max_length=300)
    value_source: ValueSource
    attribute: str | None = None
    formats: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("selector")
    @classmethod
    def _selector_is_safe(cls, value):
        return _validate_selector(value)

    @field_validator("attribute")
    @classmethod
    def _attribute_is_allowlisted(cls, value):
        if value is not None and value not in ALLOWED_ATTRIBUTES:
            raise ValueError("attribute is not allowed")
        return value

    @field_validator("formats")
    @classmethod
    def _formats_are_allowlisted(cls, value):
        if any(item not in ALLOWED_DATE_FORMATS for item in value):
            raise ValueError("date format is not allowed")
        if len(value) != len(set(value)):
            raise ValueError("date formats must be unique")
        return value

    @model_validator(mode="after")
    def _value_source_matches_attribute(self):
        if self.value_source == "attribute" and self.attribute is None:
            raise ValueError("attribute is required for attribute value source")
        if self.value_source == "text" and self.attribute is not None:
            raise ValueError("attribute is only valid for attribute value source")
        return self


class ExtractionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_selector: str = Field(min_length=1, max_length=300)
    date: FieldSpec
    title: FieldSpec
    url: FieldSpec | None = None

    @field_validator("item_selector")
    @classmethod
    def _item_selector_is_safe(cls, value):
        cleaned = _validate_selector(value)
        if cleaned.casefold() in {"html", "body"} or _item_selector_is_broad(cleaned):
            raise ValueError("item selector is too broad")
        return cleaned

    @model_validator(mode="after")
    def _fields_are_operational(self):
        if not self.date.formats:
            raise ValueError("date formats are required")
        if self.url is not None and (self.url.value_source != "attribute" or self.url.attribute != "href"):
            raise ValueError("url field must extract href attribute")
        return self


class PaginationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: PaginationType
    selector: str | None = None
    parameter: str | None = None
    start: int | None = Field(default=None, ge=1)

    @field_validator("selector")
    @classmethod
    def _selector_is_safe(cls, value):
        return _validate_selector(value) if value is not None else value

    @field_validator("parameter")
    @classmethod
    def _parameter_is_safe(cls, value):
        if value is not None and (not value.isidentifier() or len(value) > 32):
            raise ValueError("pagination parameter is invalid")
        return value

    @model_validator(mode="after")
    def _pagination_shape_is_valid(self):
        if self.type == "none" and any(value is not None for value in (self.selector, self.parameter, self.start)):
            raise ValueError("none pagination cannot define controls")
        if self.type == "next_link" and self.selector is None:
            raise ValueError("next link selector is required")
        if self.type == "next_link" and any(value is not None for value in (self.parameter, self.start)):
            raise ValueError("next link pagination cannot define page controls")
        if self.type == "page_parameter" and self.parameter is None:
            raise ValueError("page parameter is required")
        if self.type == "page_parameter" and self.selector is not None:
            raise ValueError("page parameter pagination cannot define next selector")
        return self


class IRSourceAdapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ir_source_adapter_v1"]
    ticker: str = Field(min_length=1, max_length=16)
    source_type: AdapterSourceType
    source_url: HttpUrl
    allowed_hosts: list[str] = Field(min_length=1, max_length=4)
    access_mode: Literal["html"]
    extraction: ExtractionSpec
    pagination: PaginationSpec

    @field_validator("ticker")
    @classmethod
    def _ticker_is_safe(cls, value):
        cleaned = value.strip().upper()
        if not cleaned or any(character in cleaned for character in "{}[]();<>$"):
            raise ValueError("ticker is invalid")
        return cleaned

    @field_validator("source_url")
    @classmethod
    def _source_url_is_public(cls, value):
        try:
            canonicalize_public_url(str(value))
        except ValueError as exc:
            raise ValueError("source url is invalid") from exc
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def _allowed_hosts_are_public(cls, value):
        normalized = [_validate_public_host(item) for item in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("allowed hosts must be unique")
        return normalized

    @model_validator(mode="after")
    def _source_host_is_allowed(self):
        if self.source_type == "press_releases" and self.extraction.url is None:
            raise ValueError("press release url field is required")
        if url_host(str(self.source_url)) not in self.allowed_hosts:
            raise ValueError("source url host is not allowed")
        return self


def validate_adapter_payload(payload, trusted_fields) -> dict:
    if not isinstance(payload, Mapping):
        raise ValueError("adapter payload is required")
    if not isinstance(trusted_fields, Mapping):
        raise ValueError("trusted adapter fields are required")
    missing = sorted(_IDENTITY_FIELDS - set(trusted_fields))
    if missing:
        raise ValueError(f"trusted adapter field is missing: {missing[0]}")
    candidate = dict(payload)
    candidate.update({key: trusted_fields[key] for key in _IDENTITY_FIELDS})
    try:
        adapter = IRSourceAdapter.model_validate(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError(str(exc).lower()) from exc
    return adapter.model_dump(mode="json")
