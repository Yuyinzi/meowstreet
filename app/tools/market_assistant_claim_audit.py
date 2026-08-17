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

_DETAIL_OBJECT_TYPES = frozenset(
    {"evidence_detail", "evidence_detail_source", "evidence_detail_method"}
)

_LATIN_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_CJK_CHAR_RE = re.compile(r"[\u3400-\u9fff]")

_NEGATION_WORDS = frozenset({"not", "no", "never", "without", "nor", "neither", "non"})
_NEGATION_CHARS = frozenset("不没未非无别毋勿")

_QUOTED_OR_ATTRIBUTED_RE = re.compile(
    r'["“”‘’「」『』]'
    r"|\b(?:said|says|stated|states|announced|declared|reported|reportedly|"
    r"according to|quoted|quote|verbatim|wording)\b"
    r"|(?:原话|原文|措辞|引述|报告称|声明称|宣布)",
    re.IGNORECASE,
)

_DETAIL_VALUE_LABELS = {
    "hold": ("hold", "维持", "维持利率不变"),
    "hike": ("hike", "加息"),
    "cut": ("cut", "降息"),
    "mild_hawkish": ("mild_hawkish", "mildly hawkish", "偏鹰"),
    "hawkish": ("hawkish", "鹰派"),
    "mild_dovish": ("mild_dovish", "mildly dovish", "偏鸽"),
    "dovish": ("dovish", "鸽派"),
    "more_hawkish": ("more_hawkish", "更偏鹰"),
    "more_dovish": ("more_dovish", "更偏鸽"),
    "unchanged": ("unchanged", "不变"),
    "neutral": ("neutral", "中性"),
    "conflicts": (
        "conflicts",
        "与当前增长方向不一致",
        "与增长方向不一致",
        "冲突",
        "不一致",
    ),
    "supports": ("supports", "与当前增长方向一致", "与增长方向一致", "一致", "支持"),
    "restrictive_confirmed": ("restrictive_confirmed", "紧缩"),
    "restrictive": ("restrictive", "紧缩"),
    "accommodative": ("accommodative", "宽松"),
    "expanding": ("expanding", "扩张"),
    "contracting": ("contracting", "收缩"),
    "rising": ("rising", "上升"),
    "falling": ("falling", "下降"),
    "stable": ("stable", "稳定"),
    "improving": ("improving", "改善"),
    "slowing": ("slowing", "放缓"),
    "bull_market": ("bull_market", "上涨趋势", "牛市"),
    "bear_market": ("bear_market", "下跌趋势", "熊市"),
    "aligned_expansion": ("aligned_expansion", "扩张"),
    "aligned_contraction": ("aligned_contraction", "收缩"),
    "aligned_neutral": ("aligned_neutral", "中性"),
    "divergent": ("divergent", "分化"),
    "confirms_expansion": ("confirms_expansion", "扩张"),
    "confirms_contraction_risk": ("confirms_contraction_risk", "收缩"),
    "mixed": ("mixed", "分化"),
    "elevated": ("elevated", "偏高"),
    "supportive": ("supportive", "支持"),
    "long": ("long", "偏多", "做多"),
    "short": ("short", "偏空", "做空"),
}

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
        "EXACT_WORDING_UNAVAILABLE",
        "UNGROUNDED_CLAIM",
        "UNCOVERED_TEXT",
        "OVERLAPPING_TEXT",
        "TEXT_FRAGMENT_MISMATCH",
        "BINDING_TEXT_MISMATCH",
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
    text: str | None = None


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
        errors.extend(_validate_grounding(claim, artifacts))
        errors.extend(_validate_atomic_facts(claim, artifacts))
    if purpose == "exact_wording" or _claim_quotes_or_attributes_speech(claim):
        errors.extend(_validate_exact_wording(claim, artifacts))
    errors.extend(_validate_span_language(claim))
    return errors


def _claim_quotes_or_attributes_speech(claim):
    return bool(claim["refs"]) and (
        _QUOTED_OR_ATTRIBUTED_RE.search(claim["exact_text"]) is not None
    )


def _validate_grounding(claim, artifacts):
    errors = []
    claim_id = claim["claim_id"]
    refs = claim["refs"]
    values = claim["values"]
    detail_sources = []
    for ref in refs:
        resolved = _resolve_ref(claim_id, ref, artifacts)
        if "code" in resolved:
            continue
        if resolved.get("object_type") in _DETAIL_OBJECT_TYPES:
            detail_sources.append(ref)
    for value in values:
        source = value["source"]
        resolved = _resolve_ref(claim_id, source, artifacts)
        if "code" in resolved:
            continue
        if resolved.get("object_type") in _DETAIL_OBJECT_TYPES:
            detail_sources.append(source)
    if not detail_sources:
        return errors
    if not values:
        for ref in detail_sources:
            errors.append(
                _error(
                    "UNGROUNDED_CLAIM",
                    "detail claim must bind a value",
                    claim_id=claim_id,
                    field_id=_ref_id(ref),
                )
            )
    return errors


def _validate_atomic_facts(claim, artifacts):
    errors = []
    claim_id = claim["claim_id"]
    refs = claim["refs"]
    values = claim["values"]
    if not refs or not values:
        return errors
    detail_source = None
    ref_keys = {_ref_key(ref) for ref in refs}
    for ref in refs:
        resolved = _resolve_ref(claim_id, ref, artifacts)
        if "code" in resolved:
            continue
        if resolved.get("object_type") in _DETAIL_OBJECT_TYPES:
            detail_source = resolved
            break
    if detail_source is None:
        for value in values:
            source = value["source"]
            resolved = _resolve_ref(claim_id, source, artifacts)
            if "code" in resolved:
                continue
            if resolved.get("object_type") in _DETAIL_OBJECT_TYPES:
                detail_source = resolved
                break
    if detail_source is None:
        return errors
    for value in values:
        source = value["source"]
        if _ref_key(source) not in ref_keys:
            errors.append(
                _error(
                    "REFERENCE_NOT_FOUND",
                    "value source must be a claim semantic ref",
                    claim_id=claim_id,
                    field_id=value["name"],
                )
            )
    if errors:
        return errors
    exact_text = claim["exact_text"]
    fragments = [value.get("text") for value in values]
    if any(not isinstance(fragment, str) or not fragment for fragment in fragments):
        errors.append(
            _error(
                "TEXT_FRAGMENT_MISMATCH",
                "detail claim value requires a text fragment",
                claim_id=claim_id,
            )
        )
        return errors
    positions = []
    for fragment in fragments:
        start = exact_text.find(fragment)
        if start < 0:
            errors.append(
                _error(
                    "TEXT_FRAGMENT_MISMATCH",
                    "detail claim fragment is not in the claim text",
                    claim_id=claim_id,
                    expected=fragment,
                )
            )
            return errors
        positions.append((start, start + len(fragment)))
    positions.sort()
    covered = 0
    for start, end in positions:
        if start < covered:
            errors.append(
                _error(
                    "OVERLAPPING_TEXT",
                    "detail claim fragments overlap",
                    claim_id=claim_id,
                    expected=covered,
                    actual=start,
                )
            )
            break
        if start > covered:
            errors.append(
                _error(
                    "UNCOVERED_TEXT",
                    "detail claim text is not bound",
                    claim_id=claim_id,
                    expected=covered,
                    actual=start,
                )
            )
            break
        covered = end
    if not errors and covered != len(exact_text):
        errors.append(
            _error(
                "UNCOVERED_TEXT",
                "detail claim text is not bound",
                claim_id=claim_id,
                expected=len(exact_text),
                actual=covered,
            )
        )
    for value, (start, end) in zip(values, positions):
        fragment = value["text"]
        bound_value = value["value"]
        if not _fragment_supports_value(fragment, bound_value):
            errors.append(
                _error(
                    "BINDING_TEXT_MISMATCH",
                    "detail claim fragment does not support the bound value",
                    claim_id=claim_id,
                    field_id=value["name"],
                    expected=_format_value(bound_value),
                    actual=fragment,
                )
            )
    return errors


def _ref_key(ref):
    return (
        ref.get("artifact_id"),
        ref.get("object_type"),
        ref.get("object_id"),
    )


def _fragment_supports_value(fragment, bound_value):
    if isinstance(bound_value, str) and bound_value:
        return _string_value_supported(fragment, bound_value)
    return _numeric_value_supported(fragment, bound_value)


def _string_value_supported(fragment, bound_value):
    labels = _DETAIL_VALUE_LABELS.get(bound_value)
    tokens = (bound_value,)
    if labels is not None:
        tokens = labels
    return any(_token_positively_present(fragment, token) for token in tokens)


def _numeric_value_supported(fragment, bound_value):
    token = _canonical_number_token(bound_value)
    return _token_positively_present(fragment, token)


def _canonical_number_token(bound_value):
    if isinstance(bound_value, float) and bound_value.is_integer():
        return str(int(bound_value))
    return _format_value(bound_value)


def _token_positively_present(fragment, token):
    if not token:
        return False
    if _CJK_CHAR_RE.search(token):
        return _cjk_token_positively_present(fragment, token)
    return _latin_token_positively_present(fragment, token)


def _latin_token_positively_present(fragment, token):
    pattern = rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])"
    for match in re.finditer(pattern, fragment, re.IGNORECASE):
        prefix = fragment[: match.start()]
        words = _LATIN_TOKEN_RE.findall(prefix)
        if words and words[-1].lower() in _NEGATION_WORDS:
            continue
        return True
    return False


def _cjk_token_positively_present(fragment, token):
    start = 0
    while True:
        index = fragment.find(token, start)
        if index < 0:
            return False
        if index == 0 or fragment[index - 1] not in _NEGATION_CHARS:
            return True
        start = index + len(token)


def _validate_exact_wording(claim, artifacts):
    errors = []
    claim_id = claim["claim_id"]
    refs = claim["refs"]
    if not refs:
        errors.append(
            _error(
                "EXACT_WORDING_UNAVAILABLE",
                "exact wording requires an exact-excerpt-capable artifact",
                claim_id=claim_id,
            )
        )
        return errors
    for ref in refs:
        resolved = _resolve_ref(claim_id, ref, artifacts)
        if "code" in resolved:
            continue
        if not resolved.get("exact_excerpt_capable"):
            errors.append(
                _error(
                    "EXACT_WORDING_UNAVAILABLE",
                    "exact wording requires an exact-excerpt-capable artifact",
                    claim_id=claim_id,
                    field_id=_ref_id(ref),
                )
            )
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
