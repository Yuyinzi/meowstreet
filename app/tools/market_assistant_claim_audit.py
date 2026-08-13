import re
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.tools.market_assistant_artifacts import Authority
from app.tools.market_assistant_artifacts import Purpose
from app.tools.market_assistant_artifacts import SemanticRef
from app.tools.market_assistant_artifacts import authority_allows_purpose
from app.tools.market_assistant_artifacts import resolve_artifact_ref

_MIN_COVERAGE_RATIO = 0.8
_MAX_SPANS = 24

_AUTHORITIES = (
    "decision_fact",
    "method_knowledge",
    "local_observation",
    "external_research",
    "hypothetical",
)

_ERROR_CODES = frozenset(
    {
        "SCHEMA_INVALID",
        "AUTHORITY_PURPOSE_MISMATCH",
        "REFERENCE_NOT_FOUND",
        "REFERENCE_AUTHORITY_MISMATCH",
        "FIELD_NOT_FOUND",
        "BINDING_VALUE_MISMATCH",
        "HYPOTHETICAL_REFERENCE_FORBIDDEN",
        "LIMIT_EXCEEDED",
        "OVERLAPPING_SPANS",
        "COVERAGE_TOO_LOW",
        "PROHIBITED_INTERNAL_CODE",
        "UNSUPPORTED_MATERIALITY",
        "PROHIBITED_DECISION_CLAIM",
        "ANSWER_TEXT_MISMATCH",
    }
)

_CODE_TOKEN_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")

_DECISION_RE = re.compile(
    r"\b(?:buy|sell|should buy|should sell|enter a position|take a position|"
    r"exit the position|add to position|trim the position)\b"
    r"|(?:买入|卖出|应该买入|应该卖出|建立头寸|平仓|加仓|减仓|开仓)",
    re.IGNORECASE,
)

_MATERIALITY_RE = re.compile(
    r"\b(?:significant|significantly|material|materially|strong|weak|extreme|"
    r"unusual|rare|elevated|dangerous|confirms|risk-off|predicts|causes|"
    r"high-stress|implies a regime)\b"
    r"|(?:显著|重大|明显|强劲|疲弱|极端|异常|罕见|高企|危险|高压|避险|"
    r"预示|预测|导致|暗示)",
    re.IGNORECASE,
)


class FieldSemanticRef(SemanticRef):
    field: str = Field(min_length=1)


class AuditValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str = Field(min_length=1)
    value: int | float | str
    source: FieldSemanticRef


class ClaimSpan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    claim_id: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    exact_text: str = Field(min_length=1)
    purpose: Purpose
    authority: Authority
    refs: list[SemanticRef] = Field(default_factory=list)
    values: list[AuditValue] = Field(default_factory=list)


class ClaimAuditSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    claims: list[ClaimSpan] = Field(min_length=1, max_length=_MAX_SPANS)


class AuditValidationError(ValueError):
    def __init__(self, errors):
        super().__init__("claim audit validation failed")
        self.errors = errors


def _error(code, message, *, claim_id=None, field_id=None, expected=None, actual=None):
    return {
        "code": code,
        "message": message,
        "claim_id": claim_id,
        "field_id": field_id,
        "expected": expected,
        "actual": actual,
    }


def _sanitize_value(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not isfinite(value):
            return None
        return value
    if isinstance(value, str) and len(value) <= 200:
        return value
    return None


def _format_value(value):
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def validate_claim_audit(payload, *, answer_text, artifacts):
    if not isinstance(answer_text, str):
        raise ValueError("answer text is required")
    if not isinstance(artifacts, dict):
        raise ValueError("artifact references are required")
    errors = _collect_errors(payload, answer_text, artifacts)
    if errors:
        raise AuditValidationError(errors)
    normalized, _ = _validate_schema(payload)
    coverage = _coverage(normalized["claims"], answer_text)
    return {
        "claims": normalized["claims"],
        "coverage": {
            "covered_chars": coverage["covered_chars"],
            "eligible_chars": coverage["eligible_chars"],
        },
        "coverage_ratio": coverage["coverage_ratio"],
    }


def _collect_errors(payload, answer_text, artifacts):
    normalized, schema_errors = _validate_schema(payload)
    if normalized is None:
        return schema_errors
    errors = []
    for claim in normalized["claims"]:
        errors.extend(_validate_span(claim, answer_text, artifacts))
    errors.extend(_overlap_errors(normalized["claims"]))
    if not _has_code(errors, "OVERLAPPING_SPANS"):
        errors.extend(_coverage_errors(normalized["claims"], answer_text))
    return errors


def _validate_schema(payload):
    if not isinstance(payload, dict):
        return None, [_error("SCHEMA_INVALID", "claim audit is required")]
    try:
        validated = ClaimAuditSchema.model_validate(payload)
    except ValidationError as exc:
        return None, _translate_schema_errors(payload, exc)
    return validated.model_dump(), []


def _translate_schema_errors(payload, exc):
    errors = []
    for error in exc.errors():
        loc = error.get("loc", ())
        errors.append(
            _error(
                _schema_error_code(error, loc),
                _schema_error_message(error, loc),
                claim_id=_claim_id_from_loc(payload, loc),
                field_id=str(loc[-1]) if loc else None,
                expected=_sanitize_value(error.get("ctx", {}).get("expected")),
                actual=_sanitize_value(error.get("input")),
            )
        )
    return errors


def _schema_error_code(error, loc):
    if error.get("type") == "too_long" and loc and loc[-1] == "claims":
        return "LIMIT_EXCEEDED"
    return "SCHEMA_INVALID"


def _schema_error_message(error, loc):
    error_type = error.get("type")
    if error_type == "extra_forbidden":
        return "extra inputs are not permitted"
    if error_type == "missing":
        return f"claim audit is missing required field: {loc[-1] if loc else ''}"
    if error_type == "too_short" and loc and loc[-1] == "claims":
        return "claim audit spans are required"
    if error_type == "too_long" and loc and loc[-1] == "claims":
        return f"claim audit exceeds the span limit: {_MAX_SPANS}"
    if error_type == "literal_error" or error_type == "enum":
        return f"claim audit field is invalid: {loc[-1] if loc else ''}"
    return f"claim audit is invalid: {loc[-1] if loc else ''}"


def _claim_id_from_loc(payload, loc):
    node = payload
    claim_id = None
    for part in loc:
        if isinstance(part, int):
            if not isinstance(node, list) or part >= len(node):
                return claim_id
            node = node[part]
            if isinstance(node, dict) and isinstance(node.get("claim_id"), str):
                claim_id = node["claim_id"]
        else:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return claim_id
    return claim_id


def _validate_span(claim, answer_text, artifacts):
    errors = []
    claim_id = claim["claim_id"]
    span_text = answer_text[claim["start"] : claim["end"]]
    if span_text != claim["exact_text"]:
        errors.append(
            _error(
                "ANSWER_TEXT_MISMATCH",
                "claim span does not match the answer text",
                claim_id=claim_id,
                field_id="exact_text",
                expected=_format_value(span_text),
                actual=_format_value(claim["exact_text"]),
            )
        )
    authority = claim["authority"]
    purpose = claim["purpose"]
    if not authority_allows_purpose(authority, purpose):
        allowed = [
            candidate
            for candidate in _AUTHORITIES
            if authority_allows_purpose(candidate, purpose)
        ]
        errors.append(
            _error(
                "AUTHORITY_PURPOSE_MISMATCH",
                "authority does not permit purpose",
                claim_id=claim_id,
                expected=", ".join(allowed),
                actual=authority,
            )
        )
    refs = claim["refs"]
    values = claim["values"]
    if authority == "hypothetical":
        if refs:
            errors.append(
                _error(
                    "HYPOTHETICAL_REFERENCE_FORBIDDEN",
                    "hypothetical span cannot reference artifacts",
                    claim_id=claim_id,
                )
            )
        for value in values:
            errors.append(
                _error(
                    "HYPOTHETICAL_REFERENCE_FORBIDDEN",
                    "hypothetical span cannot reference artifacts",
                    claim_id=claim_id,
                    field_id=value["name"],
                )
            )
    else:
        if not refs:
            errors.append(
                _error(
                    "REFERENCE_NOT_FOUND",
                    "claim span has no semantic references",
                    claim_id=claim_id,
                )
            )
        errors.extend(_validate_span_refs(claim, artifacts))
        errors.extend(_validate_span_values(claim, artifacts))
    errors.extend(_validate_span_language(claim))
    return errors


def _validate_span_refs(claim, artifacts):
    errors = []
    claim_id = claim["claim_id"]
    for ref in claim["refs"]:
        resolved = _resolve_ref(claim_id, ref, artifacts)
        if "code" in resolved:
            errors.append(resolved)
            continue
        if resolved.get("authority") != claim["authority"]:
            errors.append(
                _error(
                    "REFERENCE_AUTHORITY_MISMATCH",
                    "claim span crosses authority boundary",
                    claim_id=claim_id,
                    field_id=_ref_id(ref),
                    expected=claim["authority"],
                    actual=resolved.get("authority"),
                )
            )
    return errors


def _validate_span_values(claim, artifacts):
    errors = []
    claim_id = claim["claim_id"]
    for value in claim["values"]:
        errors.extend(
            _validate_span_value(claim_id, claim["authority"], value, artifacts)
        )
    return errors


def _validate_span_value(claim_id, span_authority, value, artifacts):
    errors = []
    source = value["source"]
    resolved = _resolve_ref(claim_id, source, artifacts)
    if "code" in resolved:
        resolved["field_id"] = value["name"]
        errors.append(resolved)
        return errors
    if resolved.get("authority") != span_authority:
        errors.append(
            _error(
                "REFERENCE_AUTHORITY_MISMATCH",
                "claim span crosses authority boundary",
                claim_id=claim_id,
                field_id=value["name"],
                expected=span_authority,
                actual=resolved.get("authority"),
            )
        )
    payload = resolved.get("payload")
    actual = _get_path(payload, source["field"]) if isinstance(payload, dict) else None
    if actual is None:
        errors.append(
            _error(
                "FIELD_NOT_FOUND",
                "bound field is not found",
                claim_id=claim_id,
                field_id=value["name"],
                expected=source["field"],
            )
        )
    elif not _values_match(actual, value["value"]):
        errors.append(
            _error(
                "BINDING_VALUE_MISMATCH",
                "bound value does not match",
                claim_id=claim_id,
                field_id=value["name"],
                expected=_format_value(actual),
                actual=_format_value(value["value"]),
            )
        )
    return errors


def _values_match(actual, expected):
    if isinstance(actual, bool) or isinstance(expected, bool):
        return (
            isinstance(actual, bool)
            and isinstance(expected, bool)
            and actual == expected
        )
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return isfinite(actual) and isfinite(expected) and actual == expected
    if isinstance(actual, str) and isinstance(expected, str):
        return actual == expected
    return False


def _resolve_ref(claim_id, ref, artifacts):
    try:
        return resolve_artifact_ref(
            artifacts,
            {
                "artifact_id": ref.get("artifact_id"),
                "object_type": ref.get("object_type"),
                "object_id": ref.get("object_id"),
            },
        )
    except ValueError as exc:
        return _error(
            "REFERENCE_NOT_FOUND",
            str(exc),
            claim_id=claim_id,
            field_id=_ref_id(ref),
        )


def _ref_id(ref):
    return f"{ref['artifact_id']}.{ref['object_type']}.{ref['object_id']}"


def _get_path(payload, field_path):
    if not isinstance(field_path, str) or not field_path:
        return None
    node = payload
    for part in field_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _validate_span_language(claim):
    errors = []
    claim_id = claim["claim_id"]
    text = claim["exact_text"]
    for match in _CODE_TOKEN_RE.findall(text):
        errors.append(
            _error(
                "PROHIBITED_INTERNAL_CODE",
                "internal code is shown in beginner narration",
                claim_id=claim_id,
                field_id="exact_text",
                actual=match,
            )
        )
    for word in _MATERIALITY_RE.findall(text):
        errors.append(
            _error(
                "UNSUPPORTED_MATERIALITY",
                "unsupported materiality language",
                claim_id=claim_id,
                field_id="exact_text",
                actual=word.strip().lower(),
            )
        )
    for match in _DECISION_RE.findall(text):
        errors.append(
            _error(
                "PROHIBITED_DECISION_CLAIM",
                "ticker-level buy/sell instruction",
                claim_id=claim_id,
                field_id="exact_text",
                actual=match,
            )
        )
    return errors


def _overlap_errors(claims):
    errors = []
    ordered = sorted(claims, key=lambda claim: (claim["start"], claim["end"]))
    for previous, current in zip(ordered, ordered[1:]):
        if current["start"] < previous["end"]:
            errors.append(
                _error(
                    "OVERLAPPING_SPANS",
                    "claim spans overlap",
                    claim_id=current["claim_id"],
                    field_id="start",
                    expected=previous["end"],
                    actual=current["start"],
                )
            )
    return errors


def _coverage_errors(claims, answer_text):
    coverage = _coverage(claims, answer_text)
    if coverage["coverage_ratio"] >= _MIN_COVERAGE_RATIO:
        return []
    return [
        _error(
            "COVERAGE_TOO_LOW",
            "claim spans do not cover the required answer share",
            expected=f"{_MIN_COVERAGE_RATIO:.0%}",
            actual=f"{coverage['coverage_ratio']:.0%}",
        )
    ]


def _coverage(claims, answer_text):
    denominator = sum(1 for char in answer_text if _is_eligible(char))
    covered = set()
    for claim in claims:
        for index in range(claim["start"], min(claim["end"], len(answer_text))):
            if _is_eligible(answer_text[index]):
                covered.add(index)
    if denominator == 0:
        return {
            "covered_chars": len(covered),
            "eligible_chars": 0,
            "coverage_ratio": 1.0,
        }
    return {
        "covered_chars": len(covered),
        "eligible_chars": denominator,
        "coverage_ratio": len(covered) / denominator,
    }


def _is_eligible(char):
    return char.isalnum()


def _has_code(errors, code):
    return any(error.get("code") == code for error in errors)


def build_audit_validation_report(errors):
    if not isinstance(errors, list):
        raise ValueError("validation errors are required")
    sanitized = [
        _sanitize_error(error)
        for error in errors
        if isinstance(error, dict) and error.get("code") in _ERROR_CODES
    ]
    return {
        "valid": not sanitized,
        "error_count": len(sanitized),
        "errors": sanitized,
    }


def _sanitize_error(error):
    return {
        "code": error["code"],
        "message": error.get("message"),
        "claim_id": error.get("claim_id"),
        "field_id": error.get("field_id"),
        "expected": _sanitize_value(error.get("expected")),
        "actual": _sanitize_value(error.get("actual")),
    }
