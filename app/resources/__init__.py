from pathlib import Path


RESOURCE_DIR = Path(__file__).resolve().parent
RESOURCE_FILES = {
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


def resource_path(resource_id):
    filename = RESOURCE_FILES.get(resource_id)
    if filename is None:
        raise ValueError(f"resource {resource_id} is unknown")
    return RESOURCE_DIR / filename
