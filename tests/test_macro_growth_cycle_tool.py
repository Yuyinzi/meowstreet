from app.tools import macro_growth_cycle


def test_growth_cycle_source_fields_are_grouped_by_source():
    source_ids = [source["id"] for source in macro_growth_cycle.GROWTH_CYCLE_SOURCES]

    assert source_ids == [
        "ism_manufacturing",
        "ism_services",
        "m2_money_stock",
        "jobless_claims",
    ]

    fields = [
        field["field"]
        for source in macro_growth_cycle.GROWTH_CYCLE_SOURCES
        for field in source["fields"]
    ]

    assert "macro.growth_cycle.ism_pmi" in fields
    assert "macro.growth_cycle.services_business_activity" in fields
    assert "macro.growth_cycle.m2_money_stock" in fields
    assert "macro.growth_cycle.initial_jobless_claims" in fields
