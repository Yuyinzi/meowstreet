import json
from math import isfinite
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from pydantic import field_validator, model_validator

ROOT = Path(__file__).resolve().parents[2]
METHOD_CONTRACTS_PATH = (
    ROOT / "data" / "local_system" / "market_setup_confirmation_methods.v1.json"
)

_STRING_OPERATORS = {"eq", "in"}
_NUMERIC_OPERATORS = {"lt", "gte"}

_OPERATORS = {
    "eq": lambda actual, operand: actual == operand,
    "in": lambda actual, operand: actual in operand,
    "lt": lambda actual, operand: actual < operand,
    "gte": lambda actual, operand: actual >= operand,
}


class EqPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    predicate_id: str = Field(min_length=1)
    field_id: str = Field(min_length=1)
    operator: Literal["eq"]
    operand: str


class InPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    predicate_id: str = Field(min_length=1)
    field_id: str = Field(min_length=1)
    operator: Literal["in"]
    operand: tuple[str, ...]

    @field_validator("operand", mode="before")
    @classmethod
    def _normalize_operand(cls, value):
        if isinstance(value, str) or not isinstance(value, (list, tuple, set)):
            raise ValueError("in predicate operand must be a non-empty list of strings")
        if not value:
            raise ValueError("in predicate operand must not be empty")
        items = []
        for item in value:
            if not isinstance(item, str) or not item:
                raise ValueError(
                    "in predicate operand must contain only non-empty strings"
                )
            items.append(item)
        return tuple(sorted(set(items)))


class LtPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    predicate_id: str = Field(min_length=1)
    field_id: str = Field(min_length=1)
    operator: Literal["lt"]
    operand: float

    @field_validator("operand")
    @classmethod
    def _finite_operand(cls, value):
        if not isfinite(value):
            raise ValueError("predicate operand must be a finite number")
        return value


class GtePredicate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    predicate_id: str = Field(min_length=1)
    field_id: str = Field(min_length=1)
    operator: Literal["gte"]
    operand: float

    @field_validator("operand")
    @classmethod
    def _finite_operand(cls, value):
        if not isfinite(value):
            raise ValueError("predicate operand must be a finite number")
        return value


Predicate = Annotated[
    EqPredicate | InPredicate | LtPredicate | GtePredicate,
    Field(discriminator="operator"),
]


class InputContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    fact_id: str = Field(min_length=1)
    field_id: str = Field(min_length=1)
    type: Literal["string", "number"]
    unit: str | None = None


class ConfirmationMethod(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    method_version: str = Field(min_length=1)
    input_contract: InputContract
    predicates: dict[str, Predicate]


class MethodContracts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: str = Field(min_length=1)
    methods: dict[str, ConfirmationMethod]

    @model_validator(mode="after")
    def _validate_cross_model(self):
        for method_id, method in self.methods.items():
            if method.method_version != method_id:
                raise ValueError("predicate contract is invalid")
            for predicate in method.predicates.values():
                if predicate.field_id != method.input_contract.field_id:
                    raise ValueError("predicate contract is invalid")
                operator_type = (
                    "number" if predicate.operator in _NUMERIC_OPERATORS else "string"
                )
                if method.input_contract.type != operator_type:
                    raise ValueError("predicate contract is invalid")
        return self


def load_method_contracts(path=METHOD_CONTRACTS_PATH):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_method_contracts(payload)


def validate_method_contracts(payload):
    try:
        MethodContracts(**payload)
    except ValidationError as exc:
        raise ValueError("predicate contract is invalid") from exc
    return payload


def _method(contracts, method_id):
    methods = contracts.get("methods") if isinstance(contracts, dict) else None
    if not isinstance(methods, dict):
        raise ValueError("predicate contract is invalid")
    method = methods.get(method_id)
    if method is None:
        raise ValueError(f"confirmation method is unknown: {method_id}")
    return method


def confirmation_predicate(method_id, direction, contracts):
    method = _method(contracts, method_id)
    predicate = method["predicates"].get(direction)
    if predicate is None:
        raise ValueError(f"confirmation predicate is unknown: {method_id}.{direction}")
    return TypeAdapter(Predicate).validate_python(predicate).model_dump()


def predicate_ref(method_id, predicate_id, contracts):
    method = _method(contracts, method_id)
    if predicate_id not in method["predicates"]:
        raise ValueError(
            f"confirmation predicate is unknown: {method_id}.{predicate_id}"
        )
    return {
        "method_id": method_id,
        "method_version": method["method_version"],
        "predicate_id": predicate_id,
    }


def evaluate_predicate(input_payload, predicate):
    validated = TypeAdapter(Predicate).validate_python(predicate)
    actual = input_payload.get(validated.field_id)
    if actual is None:
        actual = input_payload.get("value")
    if actual is None:
        return {
            "state": "not_evaluated",
            "actual_value": None,
            "reason_code": "data_missing",
        }
    result = _evaluate(validated, actual)
    return {"state": "evaluated", "actual_value": actual, "result": result}


def _evaluate(validated, actual):
    if validated.operator in _NUMERIC_OPERATORS:
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            raise ValueError("predicate input type mismatch")
        if not isfinite(actual):
            raise ValueError("predicate input must be a finite number")
    elif not isinstance(actual, str):
        raise ValueError("predicate input type mismatch")
    return _OPERATORS[validated.operator](actual, validated.operand)
