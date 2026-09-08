from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SourceType = Literal[
    "ir_home",
    "press_releases",
    "events_presentations",
    "earnings_results",
]
EarningsState = Literal["earnings", "non_earnings", "ambiguous"]
RegistryChannel = Literal["press_releases", "events_presentations", "earnings_results"]
RegistryEndpointType = Literal["rss", "atom", "search_domain", "archive"]
RegistryConfidence = Literal["high", "medium", "low"]
_CONCRETE_ENDPOINT_TYPES = frozenset({"rss", "atom", "archive"})


class SourceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    url: str = Field(min_length=1)
    evidence_result_ids: list[int] = Field(min_length=1, max_length=20)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("evidence_result_ids")
    @classmethod
    def _result_ids_are_positive(cls, value):
        if any(item < 1 for item in value):
            raise ValueError("evidence result ids must be positive")
        return value

    @field_validator("reason")
    @classmethod
    def _reason_is_nonempty(cls, value):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("reason is required")
        return cleaned


class SourceSelectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selections: list[SourceSelection] = Field(max_length=4)

    @model_validator(mode="after")
    def _source_types_are_unique(self):
        source_types = [item.source_type for item in self.selections]
        if len(source_types) != len(set(source_types)):
            raise ValueError("source selection source types must be unique")
        return self


class RegistryEndpointSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: RegistryChannel
    endpoint_type: RegistryEndpointType
    url: str | None = None
    domain: str = Field(min_length=1, max_length=253)
    evidence_result_ids: list[int] = Field(min_length=1, max_length=20)
    confidence: RegistryConfidence
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("domain")
    @classmethod
    def _domain_is_valid(cls, value):
        cleaned = value.strip().casefold()
        if not cleaned or "://" in cleaned or "/" in cleaned or any(character.isspace() for character in cleaned):
            raise ValueError("domain is invalid")
        return cleaned

    @field_validator("evidence_result_ids")
    @classmethod
    def _result_ids_are_positive(cls, value):
        if any(item < 1 for item in value):
            raise ValueError("evidence result ids must be positive")
        return value

    @field_validator("reason")
    @classmethod
    def _reason_is_nonempty(cls, value):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("reason is required")
        return cleaned

    @model_validator(mode="after")
    def _url_required_for_concrete_endpoints(self):
        if self.endpoint_type in _CONCRETE_ENDPOINT_TYPES and not (self.url or "").strip():
            raise ValueError("url is required for feed and archive endpoints")
        return self


class RegistrySelectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoints: list[RegistryEndpointSelection] = Field(max_length=12)

    @model_validator(mode="after")
    def _endpoints_are_unique(self):
        identities = [
            (item.channel, item.endpoint_type, (item.url or "").strip().casefold() or item.domain)
            for item in self.endpoints
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("registry endpoints must be unique")
        return self


class EventClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1)
    earnings_state: EarningsState
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason_is_nonempty(cls, value):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("reason is required")
        return cleaned


class EventClassificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classifications: list[EventClassification] = Field(max_length=50)

    @model_validator(mode="after")
    def _ids_are_unique(self):
        ids = [item.id for item in self.classifications]
        if len(ids) != len(set(ids)):
            raise ValueError("classification ids must be unique")
        return self
