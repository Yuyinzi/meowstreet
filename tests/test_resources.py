from pathlib import Path

import pytest

from app.resources import RESOURCE_FILES, resource_path
from app import api
from app.tools import market_setup_predicates, market_setup_v2


EXPECTED_RESOURCE_FILES = {
    "workflow_method": "workflow_method.v1.json",
    "market_setup_confirmation": "market_setup_confirmation.v1.json",
    "market_setup_inputs": "market_setup_inputs.v1.json",
    "assistant_surface": "assistant_surface.v1.json",
    "assistant_knowledge": "assistant_knowledge.v1.json",
    "portfolio_method": "portfolio_method.v1.json",
    "commodity_attribution_catalog": "commodity_attribution_catalog.v1.json",
    "attribution_source_audit": "attribution_source_audit.v1.json",
    "cot_extreme_allowlist": "cot_extreme_allowlist.v1.json",
    "gics_reference": "reference/gics_industries.v1.csv",
}


def test_resource_mapping_uses_neutral_tracked_names():
    assert RESOURCE_FILES == EXPECTED_RESOURCE_FILES
    assert all("method_" not in filename for filename in RESOURCE_FILES.values())


def test_required_json_resources_exist():
    for resource_id in EXPECTED_RESOURCE_FILES:
        if resource_id == "gics_reference":
            continue
        path = resource_path(resource_id)
        assert path.is_file()
        assert path.suffix == ".json"


def test_required_reference_resources_exist():
    path = resource_path("gics_reference")

    assert path.is_file()
    assert path.suffix == ".csv"


def test_resource_path_rejects_unknown_id():
    with pytest.raises(ValueError, match="resource unknown is unknown"):
        resource_path("unknown")


def test_runtime_constants_use_application_resources():
    paths = [
        api.METHOD_PATH,
        api.ATTRIBUTION_CATALOG_PATH,
        api.NON_OIL_ATTRIBUTION_SOURCE_AUDIT_PATH,
        api.COT_HISTORICAL_EXTREME_ALLOWLIST_PATH,
        market_setup_predicates.METHOD_CONTRACTS_PATH,
        market_setup_v2.REGISTRY_PATH,
    ]
    assert all("app/resources" in path.as_posix() for path in paths)
    assert all("data/local_system" not in path.as_posix() for path in paths)


def test_workflow_resource_loads_through_api():
    payload = api.load_workflow_method()
    assert payload["version"] == "v1"
    assert payload["workflow_nodes"]
