import json

import pytest

from app.tools import market_setup_predicates


def test_vix_downside_predicate_uses_inclusive_twenty_boundary():
    contracts = market_setup_predicates.load_method_contracts()
    predicate = market_setup_predicates.confirmation_predicate(
        "vix_confirmation_v2", "downside", contracts
    )

    assert market_setup_predicates.evaluate_predicate({"value": 20.0}, predicate) == {
        "state": "evaluated",
        "actual_value": 20.0,
        "result": True,
    }
    assert (
        market_setup_predicates.evaluate_predicate({"value": 19.99}, predicate)[
            "result"
        ]
        is False
    )


def test_numeric_predicate_rejects_string_operand(tmp_path):
    payload = json.loads(
        market_setup_predicates.METHOD_CONTRACTS_PATH.read_text(encoding="utf-8")
    )
    payload["methods"]["vix_confirmation_v2"]["predicates"]["downside"]["operand"] = (
        "20"
    )
    path = tmp_path / "methods.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="predicate contract is invalid"):
        market_setup_predicates.load_method_contracts(path)
