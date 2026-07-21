import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import growth_cycle
from app.db import us_rates_liquidity
from app.tools import ism_workbook

DEFAULT_WORKBOOK_PATH = (
    ROOT / "data" / "materials" / "Video 07" / "ISM_Manufacturing_Index.xlsx"
)

SERIES_CONFIG = {
    "ism_manufacturing_pmi": {
        "sheet": "PMI",
        "title": "ISM Manufacturing PMI",
        "units": "index",
    },
    "ism_manufacturing_new_orders": {
        "sheet": "New Orders",
        "title": "ISM New Orders",
        "units": "index",
    },
    "ism_manufacturing_production": {
        "sheet": "Production",
        "title": "ISM Production",
        "units": "index",
    },
    "ism_manufacturing_employment": {
        "sheet": "Employment",
        "title": "ISM Employment",
        "units": "index",
    },
    "ism_manufacturing_supplier_deliveries": {
        "sheet": "Deliveries",
        "title": "ISM Supplier Deliveries",
        "units": "index",
    },
    "ism_manufacturing_inventories": {
        "sheet": "Inventories",
        "title": "ISM Inventories",
        "units": "index",
    },
    "ism_manufacturing_customer_inventories": {
        "sheet": "Customer Inventories",
        "title": "ISM Customer Inventories",
        "units": "index",
    },
    "ism_manufacturing_prices": {
        "sheet": "Prices",
        "title": "ISM Prices",
        "units": "index",
    },
    "ism_manufacturing_order_backlog": {
        "sheet": "Order Backlog",
        "title": "ISM Order Backlog",
        "units": "index",
    },
    "ism_manufacturing_exports": {
        "sheet": "Exports",
        "title": "ISM Exports",
        "units": "index",
    },
    "ism_manufacturing_imports": {
        "sheet": "Imports",
        "title": "ISM Imports",
        "units": "index",
    },
}

MANUFACTURING_RANKING_LAYOUT = ism_workbook.RankingLayout(
    sheet="Sectors",
    header_row=3,
    data_row=6,
    industry_column=2,
    first_status_column=3,
)


def parse_workbook(workbook_path=DEFAULT_WORKBOOK_PATH):
    return ism_workbook.parse_series_workbook(
        workbook_path, "ism manufacturing", SERIES_CONFIG
    )


def parse_sector_rankings(workbook_path=DEFAULT_WORKBOOK_PATH):
    rows = ism_workbook.parse_ranking_workbook(
        workbook_path,
        "manufacturing",
        "ism manufacturing",
        MANUFACTURING_RANKING_LAYOUT,
    )
    return [
        {key: value for key, value in row.items() if key != "survey_type"}
        for row in rows
    ]


def import_workbook(con, workbook_path=DEFAULT_WORKBOOK_PATH):
    parsed_list = parse_workbook(workbook_path)
    results = {}
    for parsed in parsed_list:
        sid = parsed["series"]["series_id"]
        saved = us_rates_liquidity.replace_macro_indicator_points(
            con,
            parsed["series"],
            parsed["points"],
        )
        results[sid] = saved["points"]
    rankings = parse_sector_rankings(workbook_path)
    results["ism_industry_rankings"] = growth_cycle.replace_ism_industry_rankings(
        con, rankings
    )
    return results


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument("--workbook-path", type=Path, default=DEFAULT_WORKBOOK_PATH)
    args = parser.parse_args(argv)
    con = us_rates_liquidity.connect(args.db_path)
    growth_cycle.init_db(con)
    try:
        inserted = import_workbook(con, args.workbook_path)
    finally:
        con.close()
    for series_id, count in inserted.items():
        print(f"{series_id}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
