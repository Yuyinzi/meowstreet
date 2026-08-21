from pathlib import Path

import pytest

from app.data_sources import commodity_attribution_catalog as catalog


def attribution_text():
    return """Oil
Energy Information Administration – Petroleum - https://www.eia.gov/petroleum/
US Data - https://www.eia.gov/petroleum/data.php
 Including:
o Prices
o Crude Reserves and Production
o Refining and Processing
o Imports/Exports
o Movements
o Stocks
o Consumption/Sales
International Data - https://www.eia.gov/international/data/world
 Including:
o Petroleum and other liquid production
o Refined petroleum products production
Projection Data - https://www.eia.gov/analysis/projection-data.php
 Including:
o Monthly short-term forecasts through the next calendar year
 https://www.eia.gov/outlooks/steo/data/browser/
o Annual projections to 2050
 https://www.eia.gov/outlooks/aeo/data/browser/?src=-f1
o International projections to 2050
 https://www.eia.gov/outlooks/aeo/data/browser/?src=-f1#/?id=3-IEO2017
Analysis Reports - https://www.eia.gov/analysis/reports.php#/T186
OPEC - https://www.opec.org/opec_web/en/
OPEC Data - https://www.opec.org/opec_web/en/data_graphs/40.htm
o Oil Reserves
o Upstream Investment
o Downstream Capacity
o Market Indicators
o Historical Production Data
OPEC Reports - https://www.opec.org/opec_web/en/21.htm
o Monthly Oil Market Report
International Energy Agency - https://www.iea.org/
International Energy Agency - Oil - https://www.iea.org/fuels-and-technologies/oil
o Data Browser:
o Global crude oil imports vs exports
BP World Energy - https://www.bp.com/en/global/corporate/energy-economics/statistical-
review-of-world-energy.html
 Statistical Review of World Energy
o Oil:
o Reserves
o Production
o Consumption
o Prices
o Refining
o Trade Movements
World Bank Commodity Markets - https://www.worldbank.org/en/research/commodity-
markets
Top Suppliers (Exports) 2019
Country Export Value USD
Saudi Arabia 145,157,149,552.00
China 203,942,326,989.00
Top Consumers (Imports) 2019
Country Import Value USD
United States 122,541,986,993.00

Copper
US Geological Survey – Copper Statistics and Information -
https://www.usgs.gov/centers/nmic/copper-statistics-and-information
o Monthly and Annual Copper Industry Surveys, with Data Download
o Ad Hoc Special Copper Publications
International Copper Study Group – https://www.icsg.org/
o World Copper Fact Book
o Monthly Press Release
o Statistics
o Production, Usage, Stocks
o Forecasts
Chilean Copper Commission – https://www.cochilco.cl/
o Weekly and Quarterly World Copper Market Review
Database – https://www.cochilco.cl/Paginas/English/Statistics/Data-Base.aspx#
o Global Copper Mining Production
o Global Refined Copper Inventories
Electronic Monthly Bulletin –
https://www.cochilco.cl/Paginas/Estadisticas/Publicaciones/BoletinMensualElectronico.aspx
o Price, inventories, and other copper market variables
o Copper and copper by product production and sales
o World copper production
Trading Pit – https://www.cochilco.cl/Paginas/English/Statistics/Publications/Trading-
Pit.aspx
o Daily inventories and prices across SHFE, COMEX, LME
o Monthly inventories and prices across SHFE, COMEX, LME
International Wrought Copper Council – http://www.coppercouncil.org/iwcc-statistics-and-
data
o Global Semis Production and Demand
o Global Copper Semis End Use Summary
World Bank Commodity Markets – https://www.worldbank.org/en/research/commodity-
markets
Kitco Metals – http://www.kitcometals.com/charts/copper_historical.html
o Historical LME Copper Inventory Charts
Top Consumers (Imports) 2019
Country Import Value USD
China 31,348,218,948.00
Top Suppliers (Exports) 2019
Country Export Value USD
Chile 18,426,934,323.00

Lumber
Food and Agriculture Organization of the United Nations –
https://www.fao.org/faostat/en/#data/FO
o Production Quantity by Country
o Import Quantity by Country
o Import Value by Country
o Export Quantity by Country
o Export Value by Country
International Tropical Timber Organization – https://www.itto.int/
o Biennial Statistics and Report on production and trade of primary wood products
 https://www.itto.int/biennal_review/
o Uses data from the Joint Forest Sector Questionnaire
Joint Forest Sector Questionnaire - https://www.forestresearch.gov.uk/tools-and-
resources/statistics/statistics-by-topic/international-returns/joint-forest-sector-
questionnaire/
World Bank Commodity Markets - https://www.worldbank.org/en/research/commodity-
markets

Iron Ore
US Geological Survey – Iron Ore Statistics and Information -
https://www.usgs.gov/centers/nmic/iron-ore-statistics-and-information
o Monthly and Annual Copper Industry Surveys, with Data Download
Government of Western Australia – Department of Mines, Industry Regulations and Safety -
https://www.dmp.wa.gov.au/
o Statistics Digest - https://www.dmp.wa.gov.au/About-Us-Careers/Statistics-Digest-3962.aspx
o Latest Statistics Release - https://www.dmp.wa.gov.au/About-Us-Careers/Latest-Statistics-Release-4081.aspx
o Industry Activity Indicators - https://www.dmp.wa.gov.au/About-Us-Careers/Latest-Resources-Investment-4083.aspx
World Bank Commodity Markets - https://www.worldbank.org/en/research/commodity-
markets
Top Suppliers (Exports) 2019
Country Export Value USD
Australia 67,505,286,994.00
Top Consumers (Imports) 2019
Country Import Value USD
China 83,051,198,717.00
"""


def parsed_records(text):
    return catalog.parse_commodity_attribution_text(
        text, Path("cyclical_commodities_demand_supply.pdf")
    )


def by_source(records):
    return {record["source_name"]: record for record in records}


def test_parse_commodity_attribution_text_extracts_method_sources():
    by = by_source(parsed_records(attribution_text()))

    assert by["International Copper Study Group"]["commodity_id"] == "copper"
    assert by["International Copper Study Group"]["coverage"] == [
        "production",
        "usage",
        "stocks",
        "forecasts",
    ]
    assert by["Food and Agriculture Organization of the United Nations"][
        "coverage"
    ] == [
        "production",
        "imports",
        "exports",
    ]
    assert by["Government of Western Australia"]["commodity_id"] == "iron_ore"


def test_parse_commodity_attribution_text_lists_all_method_organizations():
    records = parsed_records(attribution_text())

    assert {record["source_name"] for record in records} == {
        "Energy Information Administration",
        "OPEC",
        "International Energy Agency",
        "BP World Energy",
        "World Bank Commodity Markets",
        "US Geological Survey",
        "International Copper Study Group",
        "Chilean Copper Commission",
        "International Wrought Copper Council",
        "Kitco Metals",
        "Food and Agriculture Organization of the United Nations",
        "International Tropical Timber Organization",
        "Joint Forest Sector Questionnaire",
        "Government of Western Australia",
    }


def test_parse_commodity_attribution_text_catalogs_one_record_per_url():
    records = parsed_records(attribution_text())

    assert len(records) == 35
    assert len({(r["commodity_id"], r["source_url"]) for r in records}) == 35


def test_parse_commodity_attribution_text_joins_wrapped_urls():
    records = parsed_records(attribution_text())
    by = by_source(records)

    assert any(
        record["source_url"]
        == "https://www.bp.com/en/global/corporate/energy-economics/statistical-review-of-world-energy.html"
        for record in records
    )
    assert any(
        record["source_url"]
        == "https://www.cochilco.cl/Paginas/English/Statistics/Publications/Trading-Pit.aspx"
        for record in records
    )
    assert by["World Bank Commodity Markets"]["source_url"] == (
        "https://www.worldbank.org/en/research/commodity-markets"
    )


def test_parse_commodity_attribution_text_keeps_http_urls_as_stated():
    records = parsed_records(attribution_text())

    assert any(
        record["source_url"] == "http://www.coppercouncil.org/iwcc-statistics-and-data"
        for record in records
    )
    assert any(
        record["source_url"]
        == "http://www.kitcometals.com/charts/copper_historical.html"
        for record in records
    )


def test_parse_commodity_attribution_text_catalogs_world_bank_for_four_commodities():
    records = parsed_records(attribution_text())

    world_bank = [
        record
        for record in records
        if record["source_name"] == "World Bank Commodity Markets"
    ]
    assert sorted(record["commodity_id"] for record in world_bank) == [
        "copper",
        "iron_ore",
        "lumber",
        "oil",
    ]


def test_parse_commodity_attribution_text_excludes_trade_tables():
    records = parsed_records(attribution_text())

    for record in records:
        assert not record["source_name"].startswith("Top Suppliers")
        assert not record["source_name"].startswith("Top Consumers")
    assert all(" " not in record["source_url"] for record in records)
    assert "145,157,149,552.00" not in " ".join(r["source_url"] for r in records)


def test_parse_commodity_attribution_text_assigns_subpage_urls_to_parent_org():
    records = parsed_records(attribution_text())

    eia_urls = {
        record["source_url"]
        for record in records
        if record["source_name"] == "Energy Information Administration"
    }
    assert "https://www.eia.gov/petroleum/data.php" in eia_urls
    assert "https://www.eia.gov/international/data/world" in eia_urls
    assert "https://www.eia.gov/outlooks/steo/data/browser/" in eia_urls

    cochilco_urls = {
        record["source_url"]
        for record in records
        if record["source_name"] == "Chilean Copper Commission"
    }
    assert "https://www.cochilco.cl/" in cochilco_urls
    assert (
        "https://www.cochilco.cl/Paginas/English/Statistics/Data-Base.aspx#"
        in cochilco_urls
    )

    wa_urls = {
        record["source_url"]
        for record in records
        if record["source_name"] == "Government of Western Australia"
    }
    assert "https://www.dmp.wa.gov.au/" in wa_urls
    assert (
        "https://www.dmp.wa.gov.au/About-Us-Careers/Statistics-Digest-3962.aspx"
        in wa_urls
    )


def test_parse_commodity_attribution_text_assigns_same_org_name_across_commodities():
    records = parsed_records(attribution_text())

    usgs = {
        record["commodity_id"]
        for record in records
        if record["source_name"] == "US Geological Survey"
    }
    assert usgs == {"copper", "iron_ore"}


def test_parse_commodity_attribution_text_populates_all_evidence_fields():
    records = parsed_records(attribution_text())

    for record in records:
        assert set(record) == {
            "commodity_id",
            "source_name",
            "source_url",
            "source_type",
            "coverage",
            "source_ref",
            "status",
        }
        assert record["commodity_id"] in catalog.VALID_COMMODITY_IDS
        assert record["source_type"] in catalog.VALID_SOURCE_TYPES
        assert record["status"] == "cataloged"
        assert record["source_ref"] == "cyclical_commodities_demand_supply"
        assert record["coverage"]
        assert set(record["coverage"]) <= catalog.COVERAGE_VOCABULARY


def test_parse_commodity_attribution_text_rejects_duplicate_url():
    text = attribution_text().replace(
        "https://www.opec.org/opec_web/en/", "https://www.eia.gov/petroleum/", 1
    )

    with pytest.raises(
        ValueError, match="duplicate commodities attribution url https://www.eia.gov/petroleum/"
    ):
        parsed_records(text)


def test_parse_commodity_attribution_text_raises_when_no_urls():
    with pytest.raises(ValueError, match="no commodities attribution resources"):
        parsed_records("Oil\n\nsome organization without any link\n")


def test_parse_commodity_attribution_text_raises_when_empty():
    with pytest.raises(ValueError, match="empty"):
        parsed_records("   \n  \n")


def test_parse_commodity_attribution_pdf_requires_existing_file(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        catalog.parse_commodity_attribution_pdf(tmp_path / "missing.pdf")
