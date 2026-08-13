import re
from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.tools.market_assistant_artifacts import authority_allows_purpose
from app.tools.market_assistant_artifacts import resolve_artifact_ref

_SECTION_KINDS = (
    "decision",
    "knowledge",
    "observation",
    "research",
    "illustration",
    "governance",
    "notice",
)

_SECTION_HEADINGS = {
    "en": {
        "decision": "",
        "knowledge": "Method & Knowledge",
        "observation": "Local Observations",
        "research": "External Research",
        "illustration": "",
        "governance": "Governance",
        "notice": "Notes",
    },
    "zh": {
        "decision": "",
        "knowledge": "指标与方法",
        "observation": "本地数据观察",
        "research": "外部资料",
        "illustration": "",
        "governance": "数据与规则说明",
        "notice": "说明",
    },
}

_EXAMPLE_PREFIXES = {"en": "[Example] ", "zh": "[举例] "}

_SECTION_BY_PURPOSE = {
    "decision_explanation": "decision",
    "counterfactual_explanation": "decision",
    "method_explanation": "knowledge",
    "source_explanation": "research",
    "governance_explanation": "governance",
    "observation": "observation",
    "bounded_interpretation": "observation",
    "illustration": "illustration",
}

_AUTHORITIES = (
    "decision_fact",
    "method_knowledge",
    "local_observation",
    "external_research",
    "hypothetical",
)

_PURPOSE_LITERAL = Literal[
    "decision_explanation",
    "counterfactual_explanation",
    "method_explanation",
    "source_explanation",
    "governance_explanation",
    "observation",
    "bounded_interpretation",
    "illustration",
]

_AUTHORITY_LITERAL = Literal[
    "decision_fact",
    "method_knowledge",
    "local_observation",
    "external_research",
    "hypothetical",
]

_ERROR_CODES = frozenset(
    {
        "SCHEMA_INVALID",
        "AUTHORITY_PURPOSE_MISMATCH",
        "SECTION_KIND_MISMATCH",
        "REFERENCE_NOT_FOUND",
        "REFERENCE_AUTHORITY_MISMATCH",
        "FIELD_NOT_FOUND",
        "BINDING_VALUE_MISMATCH",
        "UNBOUND_FACTUAL_LITERAL",
        "PROHIBITED_DECISION_CLAIM",
        "UNSUPPORTED_MATERIALITY",
        "PROHIBITED_INTERNAL_CODE",
        "HYPOTHETICAL_REFERENCE_FORBIDDEN",
        "RESEARCH_CITATION_REQUIRED",
        "LIMIT_EXCEEDED",
        "ANSWER_TEXT_MISMATCH",
    }
)

_HYPOTHETICAL_OPERATIONS = frozenset({"add", "subtract", "multiply", "divide"})

_MAX_SECTIONS = 8
_MAX_CLAIMS = 24
_MAX_BINDINGS_PER_CLAIM = 16
_MAX_REFS_PER_CLAIM = 8
_MAX_TEMPLATE_LENGTH = 2000

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_NUMBER_RE = re.compile(r"\d")
_ENUM_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_CODE_TOKEN_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")
_TOKEN_RE = re.compile(r"[a-z][a-z0-9-]*")

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

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

_RESULT_LAYERS = (
    "macro_regime",
    "market_confirmation",
    "market_setup",
    "portfolio_posture",
)

_RESULT_LAYER_LABELS = {
    "macro_regime": "Macro Regime",
    "market_confirmation": "Market Confirmation",
    "market_setup": "Market Setup",
    "portfolio_posture": "Portfolio Posture",
}


class _ClaimRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    artifact_id: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    object_id: str = Field(min_length=1)


class _FieldRef(_ClaimRef):
    field: str = Field(min_length=1)


class _AnnotatedBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    value: int | float | str
    source: _FieldRef


class _Arithmetic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation: Literal["add", "subtract", "multiply", "divide"]
    operands: list[int | float] = Field(min_length=1)
    result_binding: str = Field(min_length=1)


_BindingValue = int | float | str | _FieldRef | _AnnotatedBinding


class _Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    claim_id: str = Field(min_length=1)
    purpose: _PURPOSE_LITERAL
    authority: _AUTHORITY_LITERAL
    refs: list[_ClaimRef] = Field(default_factory=list)
    template: str = Field(min_length=1)
    bindings: dict[str, _BindingValue] = Field(default_factory=dict)
    arithmetic: _Arithmetic | None = None


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal[
        "decision",
        "knowledge",
        "observation",
        "research",
        "illustration",
        "governance",
        "notice",
    ]
    claims: list[_Claim] = Field(min_length=1)


class _AnswerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    answer_text: str | None = None
    sections: list[_Section] = Field(min_length=1)


class DraftValidationError(ValueError):
    def __init__(self, message, errors):
        super().__init__(message)
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


def _errors_message(errors):
    return "; ".join(error["message"] for error in errors)


def validate_answer_draft_schema(payload):
    normalized, errors = _validate_draft_schema(payload)
    if errors:
        raise DraftValidationError(_errors_message(errors), errors)
    return normalized


def validate_answer_draft(payload, artifacts, *, language="en"):
    if not isinstance(artifacts, dict):
        raise ValueError("artifact references are required")
    errors = _collect_errors(payload, artifacts, language=language)
    if errors:
        raise DraftValidationError(_errors_message(errors), errors)
    normalized, _ = _validate_draft_schema(payload)
    return normalized


def _collect_errors(payload, artifacts, *, language="en"):
    normalized, schema_errors = _validate_draft_schema(payload)
    if normalized is None:
        return schema_errors
    errors = []
    errors.extend(_duplicate_claim_errors(normalized))
    errors.extend(_section_purpose_errors(normalized))
    errors.extend(_limit_errors(normalized))
    for section in normalized["sections"]:
        for claim in section["claims"]:
            errors.extend(_validate_claim(claim, artifacts))
    errors.extend(
        _answer_text_mismatch_errors(normalized, artifacts, language=language)
    )
    return errors


def _answer_text_mismatch_errors(normalized, artifacts, *, language):
    answer_text = normalized.get("answer_text")
    if answer_text is None:
        return []
    try:
        rendered = render_answer(normalized, artifacts, [], language=language)
    except ValueError:
        return []
    if _normalize_answer_text(answer_text) != _normalize_answer_text(rendered):
        return [
            _error(
                "ANSWER_TEXT_MISMATCH",
                "answer_text does not match the rendered answer",
                expected=_format_value(rendered),
                actual=_format_value(answer_text),
            )
        ]
    return []


def _normalize_answer_text(text):
    return text.replace("\r\n", "\n").rstrip()


def _validate_draft_schema(payload):
    if not isinstance(payload, dict):
        return None, [_error("SCHEMA_INVALID", "answer draft is required")]
    try:
        validated = _AnswerDraft.model_validate(payload)
    except ValidationError as exc:
        return None, _translate_schema_errors(payload, exc)
    return validated.model_dump(), []


def _translate_schema_errors(payload, exc):
    errors = []
    for error in exc.errors():
        loc = error.get("loc", ())
        errors.append(
            _error(
                "SCHEMA_INVALID",
                _schema_error_message(error),
                claim_id=_claim_id_from_loc(payload, loc),
                field_id=str(loc[-1]) if loc else None,
                expected=_sanitize_value(error.get("ctx", {}).get("expected")),
                actual=_sanitize_value(error.get("input")),
            )
        )
    return errors


def _schema_error_message(error):
    error_type = error.get("type")
    loc = error.get("loc", ())
    if error_type == "extra_forbidden":
        return "extra inputs are not permitted"
    if error_type == "missing":
        return f"answer draft is missing required field: {loc[-1] if loc else ''}"
    if error_type == "too_short" and loc == ("sections",):
        return "answer sections are required"
    if error_type == "too_short" and loc and loc[-1] == "claims":
        return "answer section claims are required"
    if error_type == "literal_error" or error_type == "enum":
        return f"answer draft field is invalid: {loc[-1] if loc else ''}"
    return f"answer draft is invalid: {loc[-1] if loc else ''}"


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


def _duplicate_claim_errors(normalized):
    errors = []
    seen = set()
    for section in normalized["sections"]:
        for claim in section["claims"]:
            claim_id = claim["claim_id"]
            if claim_id in seen:
                errors.append(
                    _error(
                        "SCHEMA_INVALID",
                        f"claim id is duplicated: {claim_id}",
                        claim_id=claim_id,
                    )
                )
            seen.add(claim_id)
    return errors


def _section_purpose_errors(normalized):
    errors = []
    for section in normalized["sections"]:
        section_kind = section["kind"]
        for claim in section["claims"]:
            expected_kind = _SECTION_BY_PURPOSE.get(claim["purpose"])
            if expected_kind is not None and expected_kind != section_kind:
                errors.append(
                    _error(
                        "SECTION_KIND_MISMATCH",
                        "claim purpose does not match section kind",
                        claim_id=claim["claim_id"],
                        expected=expected_kind,
                        actual=section_kind,
                    )
                )
    return errors


def _limit_errors(normalized):
    errors = []
    sections = normalized["sections"]
    if len(sections) > _MAX_SECTIONS:
        errors.append(
            _error(
                "LIMIT_EXCEEDED",
                f"answer exceeds the section limit: {_MAX_SECTIONS}",
            )
        )
    claims = [claim for section in sections for claim in section["claims"]]
    if len(claims) > _MAX_CLAIMS:
        errors.append(
            _error(
                "LIMIT_EXCEEDED",
                f"answer exceeds the claim limit: {_MAX_CLAIMS}",
            )
        )
    for claim in claims:
        claim_id = claim["claim_id"]
        if len(claim.get("bindings") or {}) > _MAX_BINDINGS_PER_CLAIM:
            errors.append(
                _error(
                    "LIMIT_EXCEEDED",
                    f"claim exceeds the binding limit: {_MAX_BINDINGS_PER_CLAIM}",
                    claim_id=claim_id,
                )
            )
        if len(claim.get("refs") or []) > _MAX_REFS_PER_CLAIM:
            errors.append(
                _error(
                    "LIMIT_EXCEEDED",
                    f"claim exceeds the reference limit: {_MAX_REFS_PER_CLAIM}",
                    claim_id=claim_id,
                )
            )
        if len(claim["template"]) > _MAX_TEMPLATE_LENGTH:
            errors.append(
                _error(
                    "LIMIT_EXCEEDED",
                    "claim template exceeds the length limit",
                    claim_id=claim_id,
                )
            )
    return errors


def _validate_claim(claim, artifacts):
    errors = []
    claim_id = claim["claim_id"]
    purpose = claim["purpose"]
    authority = claim["authority"]
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
    refs = claim.get("refs") or []
    if authority == "hypothetical":
        if refs:
            errors.append(
                _error(
                    "HYPOTHETICAL_REFERENCE_FORBIDDEN",
                    "hypothetical claim cannot reference artifacts",
                    claim_id=claim_id,
                )
            )
    else:
        if not refs:
            errors.append(
                _error(
                    "REFERENCE_NOT_FOUND",
                    "claim has no semantic references",
                    claim_id=claim_id,
                )
            )
        errors.extend(_validate_claim_refs(claim, artifacts))
    errors.extend(_validate_claim_arithmetic(claim))
    errors.extend(_validate_claim_bindings(claim, artifacts))
    errors.extend(_validate_claim_template(claim))
    errors.extend(_validate_unbound_literals(claim))
    errors.extend(_validate_claim_language(claim, artifacts))
    if authority == "external_research":
        errors.extend(_validate_research_citations(claim, artifacts))
    return errors


def _validate_claim_refs(claim, artifacts):
    errors = []
    claim_id = claim["claim_id"]
    for ref in claim.get("refs") or []:
        resolved = _resolve_ref(claim_id, ref, artifacts)
        if "code" in resolved:
            errors.append(resolved)
            continue
        errors.extend(
            _authority_errors(claim_id, claim["authority"], ref, resolved, artifacts)
        )
    return errors


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
            field_id=(
                f"{ref.get('artifact_id')}.{ref.get('object_type')}."
                f"{ref.get('object_id')}"
            ),
        )


def _authority_errors(claim_id, authority, ref, object_entry, artifacts):
    errors = []
    artifact_id = ref["artifact_id"]
    artifact = artifacts.get(artifact_id) or {}
    object_authority = object_entry.get("authority")
    if object_authority != authority:
        errors.append(
            _error(
                "REFERENCE_AUTHORITY_MISMATCH",
                "claim crosses authority boundary",
                claim_id=claim_id,
                field_id=(
                    f"{artifact_id}.{object_entry.get('object_type')}."
                    f"{object_entry.get('object_id')}"
                ),
                expected=authority,
                actual=object_authority,
            )
        )
    if (
        authority != "decision_fact"
        and artifact.get("market_setup_relation") == "authoritative_snapshot"
    ):
        errors.append(
            _error(
                "REFERENCE_AUTHORITY_MISMATCH",
                "claim cannot reference authoritative snapshot evidence",
                claim_id=claim_id,
                field_id=artifact_id,
                expected="non-decision artifact",
                actual="authoritative_snapshot",
            )
        )
    return errors


def _validate_claim_arithmetic(claim):
    errors = []
    arithmetic = claim.get("arithmetic")
    if arithmetic is None:
        return errors
    claim_id = claim["claim_id"]
    if claim["authority"] != "hypothetical":
        errors.append(
            _error(
                "SCHEMA_INVALID",
                "arithmetic is only permitted for hypothetical claims",
                claim_id=claim_id,
                field_id="arithmetic",
            )
        )
        return errors
    for index, operand in enumerate(arithmetic["operands"]):
        if not isfinite(operand):
            errors.append(
                _error(
                    "BINDING_VALUE_MISMATCH",
                    "hypothetical arithmetic operand must be finite",
                    claim_id=claim_id,
                    field_id=f"arithmetic.operands.{index}",
                )
            )
    if arithmetic["result_binding"] in (claim.get("bindings") or {}):
        errors.append(
            _error(
                "BINDING_VALUE_MISMATCH",
                "hypothetical arithmetic result must come from the calculator",
                claim_id=claim_id,
                field_id=arithmetic["result_binding"],
            )
        )
    return errors


def _validate_claim_bindings(claim, artifacts):
    errors = []
    claim_id = claim["claim_id"]
    for key, binding in (claim.get("bindings") or {}).items():
        if isinstance(binding, dict):
            if claim["authority"] == "hypothetical":
                errors.append(
                    _error(
                        "HYPOTHETICAL_REFERENCE_FORBIDDEN",
                        "hypothetical claim cannot reference artifacts",
                        claim_id=claim_id,
                        field_id=key,
                    )
                )
                continue
            if "value" in binding and "source" in binding:
                errors.extend(
                    _validate_annotated_binding(claim, key, binding, artifacts)
                )
            elif "artifact_id" in binding:
                errors.extend(
                    _validate_field_ref_binding(claim, key, binding, artifacts)
                )
            continue
        if claim["authority"] != "hypothetical":
            errors.append(
                _error(
                    "UNBOUND_FACTUAL_LITERAL",
                    "unbound factual literal",
                    claim_id=claim_id,
                    field_id=key,
                )
            )
    return errors


def _validate_annotated_binding(claim, key, binding, artifacts):
    errors = []
    claim_id = claim["claim_id"]
    source = binding["source"]
    resolved = _resolve_ref(claim_id, source, artifacts)
    if "code" in resolved:
        resolved["field_id"] = key
        errors.append(resolved)
        return errors
    errors.extend(
        _authority_errors(claim_id, claim["authority"], source, resolved, artifacts)
    )
    payload = resolved.get("payload")
    actual = _get_path(payload, source["field"]) if isinstance(payload, dict) else None
    if actual is None:
        errors.append(
            _error(
                "FIELD_NOT_FOUND",
                "binding field is not found",
                claim_id=claim_id,
                field_id=key,
                expected=source["field"],
            )
        )
    elif actual != binding["value"]:
        errors.append(
            _error(
                "BINDING_VALUE_MISMATCH",
                "binding value does not match",
                claim_id=claim_id,
                field_id=key,
                expected=_format_value(actual),
                actual=_format_value(binding["value"]),
            )
        )
    else:
        errors.extend(_validate_typed_value(claim, key, actual))
        errors.extend(
            _internal_code_binding_errors(claim, key, source["field"], binding["value"])
        )
    return errors


def _validate_field_ref_binding(claim, key, binding, artifacts):
    errors = []
    claim_id = claim["claim_id"]
    resolved = _resolve_ref(claim_id, binding, artifacts)
    if "code" in resolved:
        resolved["field_id"] = key
        errors.append(resolved)
        return errors
    errors.extend(
        _authority_errors(claim_id, claim["authority"], binding, resolved, artifacts)
    )
    payload = resolved.get("payload")
    value = _get_path(payload, binding["field"]) if isinstance(payload, dict) else None
    if value is None:
        errors.append(
            _error(
                "FIELD_NOT_FOUND",
                "binding field is not found",
                claim_id=claim_id,
                field_id=key,
                expected=binding["field"],
            )
        )
    else:
        errors.extend(_validate_typed_value(claim, key, value))
    errors.extend(_internal_code_binding_errors(claim, key, binding["field"], value))
    return errors


def _internal_code_binding_errors(claim, key, source_field, value):
    if claim["purpose"] == "governance_explanation":
        return []
    final_segment = (
        source_field.rsplit(".", 1)[-1] if isinstance(source_field, str) else ""
    )
    is_code_field = final_segment == "code"
    is_code_value = isinstance(value, str) and bool(_ENUM_RE.search(value))
    if not (is_code_field or is_code_value):
        return []
    return [
        _error(
            "PROHIBITED_INTERNAL_CODE",
            "internal code cannot be displayed in an explanation",
            claim_id=claim["claim_id"],
            field_id=key,
            expected=_format_value(source_field),
            actual=_format_value(value),
        )
    ]


def _validate_typed_value(claim, key, value):
    if isinstance(value, bool):
        return [_binding_type_error(claim["claim_id"], key)]
    if isinstance(value, (int, float)):
        if isfinite(value):
            return []
        return [_binding_type_error(claim["claim_id"], key)]
    if isinstance(value, str) and value:
        return []
    return [_binding_type_error(claim["claim_id"], key)]


def _binding_type_error(claim_id, key):
    return _error(
        "BINDING_VALUE_MISMATCH",
        "binding value is not a supported typed value",
        claim_id=claim_id,
        field_id=key,
    )


def _validate_claim_template(claim):
    errors = []
    claim_id = claim["claim_id"]
    placeholders = set(_PLACEHOLDER_RE.findall(claim["template"]))
    bindings = set(claim.get("bindings") or {})
    arithmetic = claim.get("arithmetic")
    result_binding = arithmetic["result_binding"] if arithmetic else None
    if arithmetic is not None and result_binding not in placeholders:
        errors.append(
            _error(
                "FIELD_NOT_FOUND",
                "arithmetic result binding is not used in template",
                claim_id=claim_id,
                field_id=result_binding,
            )
        )
    expected_bindings = (
        bindings | {result_binding} if arithmetic is not None else bindings
    )
    for placeholder in sorted(placeholders - expected_bindings):
        errors.append(
            _error(
                "FIELD_NOT_FOUND",
                f"template placeholder is not bound: {placeholder}",
                claim_id=claim_id,
                field_id=placeholder,
            )
        )
    for binding_key in sorted(bindings - placeholders):
        errors.append(
            _error(
                "FIELD_NOT_FOUND",
                f"binding is not used in template: {binding_key}",
                claim_id=claim_id,
                field_id=binding_key,
            )
        )
    return errors


def _validate_unbound_literals(claim):
    if claim["authority"] == "hypothetical":
        return []
    stripped = _PLACEHOLDER_RE.sub("", claim["template"])
    if _NUMBER_RE.search(stripped) or _ENUM_RE.search(stripped):
        return [
            _error(
                "UNBOUND_FACTUAL_LITERAL",
                "unbound factual literal",
                claim_id=claim["claim_id"],
                field_id="template",
            )
        ]
    return []


def _validate_claim_language(claim, artifacts):
    errors = []
    claim_id = claim["claim_id"]
    stripped = _PLACEHOLDER_RE.sub("", claim["template"])
    decision_matches = _DECISION_RE.findall(stripped)
    if decision_matches:
        errors.append(
            _error(
                "PROHIBITED_DECISION_CLAIM",
                "prohibited decision claim",
                claim_id=claim_id,
                field_id="template",
                actual=decision_matches[0],
            )
        )
    allowed_tokens, allowed_texts = _referenced_payload_words(claim, artifacts)
    for word in _MATERIALITY_RE.findall(stripped):
        normalized = word.strip().lower()
        if _payload_has_word(allowed_tokens, allowed_texts, normalized):
            continue
        errors.append(
            _error(
                "UNSUPPORTED_MATERIALITY",
                "unsupported materiality language",
                claim_id=claim_id,
                field_id="template",
                actual=normalized,
            )
        )
    return errors


def _referenced_payload_words(claim, artifacts):
    tokens = set()
    texts = []
    for ref in claim.get("refs") or []:
        try:
            object_entry = resolve_artifact_ref(artifacts, ref)
        except ValueError:
            continue
        classifications = (object_entry.get("payload") or {}).get("classifications")
        for text in _iter_strings(classifications):
            lowered = text.lower()
            tokens.update(_TOKEN_RE.findall(lowered))
            texts.append(lowered)
    return tokens, texts


def _payload_has_word(tokens, texts, word):
    if " " in word:
        return any(word in text for text in texts)
    return word in tokens


def _iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _validate_research_citations(claim, artifacts):
    for ref in claim.get("refs") or []:
        try:
            object_entry = resolve_artifact_ref(artifacts, ref)
        except ValueError:
            continue
        if object_entry.get("object_type") == "research_source":
            return []
    return [
        _error(
            "RESEARCH_CITATION_REQUIRED",
            "research citation is required",
            claim_id=claim["claim_id"],
        )
    ]


def _get_path(payload, field_path):
    if not isinstance(field_path, str) or not field_path:
        return None
    node = payload
    for part in field_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def build_validation_report(errors):
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


def render_unvalidated_debug_answer(draft, *, language="en"):
    normalized = validate_answer_draft_schema(draft)
    headings = _SECTION_HEADINGS.get(language, _SECTION_HEADINGS["en"])
    parts = []
    for section in normalized.get("sections", []):
        claims = section.get("claims") or []
        if not claims:
            continue
        rendered_claims = []
        for claim in claims:
            rendered = _render_unvalidated_claim(claim, language=language)
            if rendered is not None:
                rendered_claims.append(rendered)
        if not rendered_claims:
            continue
        heading = headings.get(section.get("kind"), "")
        if heading:
            parts.append(heading)
        parts.extend(rendered_claims)
    return "\n".join(parts)


def _render_unvalidated_claim(claim, *, language):
    unavailable = "暂不可用" if language == "zh" else "unavailable"
    values = {
        key: _render_unvalidated_binding(binding, unavailable=unavailable)
        for key, binding in (claim.get("bindings") or {}).items()
    }
    arithmetic = claim.get("arithmetic")
    if arithmetic:
        result = calculate_hypothetical(arithmetic["operation"], arithmetic["operands"])
        values[arithmetic["result_binding"]] = (
            _format_value(result["value"])
            if result["state"] == "calculated"
            else unavailable
        )
    rendered = _PLACEHOLDER_RE.sub(
        lambda match: values.get(match.group(1), unavailable),
        claim["template"],
    )
    if _DECISION_RE.search(rendered):
        return None
    if _CODE_TOKEN_RE.search(rendered):
        return None
    if claim.get("authority") == "hypothetical":
        return _EXAMPLE_PREFIXES.get(language, _EXAMPLE_PREFIXES["en"]) + rendered
    return rendered


def _render_unvalidated_binding(binding, *, unavailable):
    if isinstance(binding, dict):
        if "value" in binding:
            value = binding["value"]
        else:
            return unavailable
    else:
        value = binding
    if isinstance(value, str) and _ENUM_RE.search(value):
        return unavailable
    return _format_value(value)


def detect_answer_language(text) -> Literal["en", "zh"]:
    if isinstance(text, str) and _CJK_RE.search(text):
        return "zh"
    return "en"


def render_answer(draft, artifacts, notices, *, language="en"):
    parts = []
    headings = _SECTION_HEADINGS[language]
    for section in draft.get("sections", []):
        claims = section.get("claims") or []
        if not claims:
            continue
        heading = headings.get(section.get("kind"), "")
        if heading:
            parts.append(heading)
        for claim in claims:
            parts.append(_render_claim(claim, artifacts, language=language))
    for notice in notices or []:
        if isinstance(notice, dict) and isinstance(notice.get("text"), str):
            parts.append(notice["text"])
    return "\n".join(parts)


def _render_claim(claim, artifacts, *, language="en"):
    values = {}
    for key, binding in (claim.get("bindings") or {}).items():
        values[key] = _render_binding(binding, artifacts)
    arithmetic = claim.get("arithmetic")
    if arithmetic:
        result = calculate_hypothetical(arithmetic["operation"], arithmetic["operands"])
        if result["state"] == "calculated":
            values[arithmetic["result_binding"]] = _format_value(result["value"])
        else:
            values[arithmetic["result_binding"]] = "unavailable"
    rendered = _PLACEHOLDER_RE.sub(
        lambda match: values.get(match.group(1), match.group(0)),
        claim["template"],
    )
    if claim.get("authority") == "hypothetical":
        return _EXAMPLE_PREFIXES[language] + rendered
    return rendered


def _render_binding(binding, artifacts):
    if isinstance(binding, dict):
        if "value" in binding:
            return _format_value(binding["value"])
        if "artifact_id" in binding:
            object_entry = resolve_artifact_ref(
                artifacts,
                {
                    "artifact_id": binding.get("artifact_id"),
                    "object_type": binding.get("object_type"),
                    "object_id": binding.get("object_id"),
                },
            )
            payload = object_entry.get("payload")
            value = (
                _get_path(payload, binding["field"])
                if isinstance(payload, dict)
                else None
            )
            return _format_value(value)
    return _format_value(binding)


def _format_value(value):
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def collect_citations(draft, artifacts):
    citations = []
    seen = set()
    for section in draft.get("sections", []):
        for claim in section.get("claims", []):
            if claim.get("authority") != "external_research":
                continue
            for ref in claim.get("refs") or []:
                object_entry = resolve_artifact_ref(artifacts, ref)
                if object_entry.get("object_type") != "research_source":
                    continue
                source = object_entry.get("payload") or {}
                source_id = source.get("source_id")
                if not source_id or source_id in seen:
                    continue
                seen.add(source_id)
                citations.append(
                    {
                        "source_id": source_id,
                        "title": source.get("title"),
                        "url": source.get("canonical_url"),
                        "publisher": source.get("publisher"),
                        "publication_date": source.get("publication_date"),
                        "event_date": source.get("event_date"),
                    }
                )
    return citations


def calculate_hypothetical(operation, operands):
    if operation not in _HYPOTHETICAL_OPERATIONS:
        raise ValueError("operation is not supported")
    if not isinstance(operands, list) or not operands:
        raise ValueError("operands are required")
    if operation in ("subtract", "divide") and len(operands) != 2:
        raise ValueError("hypothetical arithmetic requires two operands")
    for operand in operands:
        if (
            isinstance(operand, bool)
            or not isinstance(operand, (int, float))
            or not isfinite(operand)
        ):
            raise ValueError("hypothetical arithmetic operand must be finite")
    result = _apply_hypothetical(operation, operands)
    if result is None:
        return {
            "state": "unavailable",
            "reason_code": "division_by_zero",
            "operation": operation,
            "operands": operands,
        }
    return {
        "state": "calculated",
        "value": result,
        "operation": operation,
        "operands": operands,
    }


def _apply_hypothetical(operation, operands):
    if operation == "add":
        return sum(operands)
    if operation == "subtract":
        return operands[0] - operands[1]
    if operation == "multiply":
        product = 1
        for operand in operands:
            product *= operand
        return product
    if operands[1] == 0:
        return None
    return operands[0] / operands[1]


def render_fallback(*, plan, artifacts, notices):
    if not isinstance(plan, dict):
        raise ValueError("task plan is required")
    intent = plan.get("intent")
    router = _FALLBACK_ROUTERS.get(intent) if isinstance(intent, str) else None
    if router is None:
        router = _fallback_unsupported
    parts = [router(artifacts)]
    for notice in notices or []:
        if isinstance(notice, dict) and isinstance(notice.get("text"), str):
            parts.append(notice["text"])
    return "\n".join(parts)


def _find_artifacts(artifacts, kind):
    return [
        artifact
        for artifact in artifacts.values()
        if artifact.get("artifact_kind") == kind
    ]


def _fallback_decision(artifacts):
    snapshots = _find_artifacts(artifacts, "explanation_snapshot")
    if not snapshots:
        return "A deterministic decision explanation is currently unavailable."
    payload = snapshots[0].get("payload") or {}
    results = payload.get("results") or {}
    lines = ["Market Setup decision result:"]
    for layer in _RESULT_LAYERS:
        result = results.get(layer) or {}
        code = result.get("code")
        if code is None:
            continue
        label = result.get("label")
        if label:
            lines.append(f"{_RESULT_LAYER_LABELS[layer]}: {code} ({label})")
        else:
            lines.append(f"{_RESULT_LAYER_LABELS[layer]}: {code}")
    path = payload.get("decision_path") or []
    if path:
        lines.append("Decision path:")
        for step in path:
            lines.append(f"- {step.get('label')}: {step.get('code')}")
    return "\n".join(lines)


def _fallback_method(artifacts):
    snapshots = _find_artifacts(artifacts, "explanation_snapshot")
    if not snapshots:
        return "The approved method contract is currently unavailable."
    contracts = (snapshots[0].get("payload") or {}).get("method_contracts") or {}
    methods = contracts.get("methods") or {}
    if not methods:
        return "The approved method contract is currently unavailable."
    lines = ["Approved method contracts:"]
    for method_id, method in methods.items():
        lines.append(
            f"- {method_id} (version {method.get('method_version', 'unknown')}, "
            f"kind {method.get('kind', 'unknown')})"
        )
        predicates = (method.get("decision_contract") or {}).get("predicates") or {}
        for direction, predicate in predicates.items():
            lines.append(
                f"  {direction}: {predicate.get('field_id')} "
                f"{predicate.get('operator')} {_format_value(predicate.get('operand'))}"
            )
    return "\n".join(lines)


def _fallback_knowledge(artifacts):
    records = _find_artifacts(artifacts, "knowledge_record")
    if not records:
        return "The approved knowledge record is currently unavailable."
    record = records[0].get("payload") or {}
    title = record.get("title")
    prose = record.get("explanation") or record.get("description")
    if not prose:
        return "The approved knowledge record is currently unavailable."
    if title:
        return f"{title}\n{prose}"
    return prose


def _fallback_exploration(artifacts):
    results = _find_artifacts(artifacts, "exploration_result")
    if not results:
        return "Local exploration data is currently unavailable."
    result = results[0].get("payload") or {}
    lines = ["Local exploration result:"]
    query = result.get("query_contract") or {}
    if query.get("indicator_id"):
        lines.append(f"Indicator: {query['indicator_id']}")
    window = result.get("observed_window") or {}
    if window.get("start") and window.get("end"):
        lines.append(f"Window: {window['start']} to {window['end']}")
    rows = result.get("rows") or []
    if rows:
        lines.append("Rows:")
        for row in rows:
            lines.append(f"- {row.get('date')}: {_format_value(row.get('value'))}")
    statistics = result.get("deterministic_statistics") or {}
    if statistics:
        lines.append("Statistics:")
        for statistic_id, value in statistics.items():
            lines.append(f"- {statistic_id}: {_format_value(value)}")
    gaps = result.get("gaps")
    if isinstance(gaps, dict):
        lines.append(f"Gaps: {gaps.get('policy', 'unknown')}")
    return "\n".join(lines)


def _fallback_local_facts(artifacts):
    snapshots = _find_artifacts(artifacts, "explanation_snapshot")
    if not snapshots:
        return "Current market evidence is currently unavailable."
    evidence = (snapshots[0].get("payload") or {}).get("evidence") or []
    if not evidence:
        return "No current market evidence is available."
    lines = ["Current market evidence:"]
    for fact in evidence:
        label = fact.get("label") or fact.get("fact_id")
        accepted = fact.get("accepted_values") or {}
        lines.append(f"- {label}: {_format_value(_single_value(accepted))}")
    return "\n".join(lines)


def _single_value(accepted):
    if len(accepted) == 1:
        return next(iter(accepted.values()))
    return accepted


def _fallback_research(artifacts):
    lines = ["External research is currently unavailable."]
    snapshots = _find_artifacts(artifacts, "explanation_snapshot")
    evidence = (snapshots[0].get("payload") or {}).get("evidence") if snapshots else []
    if evidence:
        lines.append("Independently valid local decision facts:")
        for fact in evidence:
            label = fact.get("label") or fact.get("fact_id")
            accepted = fact.get("accepted_values") or {}
            lines.append(f"- {label}: {_format_value(_single_value(accepted))}")
    return "\n".join(lines)


def _fallback_teaching(artifacts):
    for artifact in artifacts.values():
        payload = artifact.get("payload")
        if not isinstance(payload, dict):
            continue
        example = payload.get("predefined_example")
        if isinstance(example, str) and example:
            return f"Example: {example}"
    return "A teaching example could not be generated."


def _fallback_unsupported(artifacts):
    return "This question cannot be answered deterministically."


_FALLBACK_ROUTERS = {
    "decision_explanation": _fallback_decision,
    "counterfactual": _fallback_decision,
    "historical_snapshot": _fallback_decision,
    "snapshot_comparison": _fallback_decision,
    "current_evidence": _fallback_local_facts,
    "method": _fallback_method,
    "definition": _fallback_knowledge,
    "source": _fallback_knowledge,
    "governance": _fallback_knowledge,
    "local_current": _fallback_exploration,
    "local_history": _fallback_exploration,
    "local_comparison": _fallback_exploration,
    "release_history": _fallback_exploration,
    "illustration": _fallback_teaching,
    "external_research": _fallback_research,
    "unsupported": _fallback_unsupported,
}
