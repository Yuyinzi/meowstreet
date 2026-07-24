import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import ism_surveys
from app.db import macro_indicators
from app.db import us_rates_liquidity
from app.tools import ism_workbook

DEFAULT_WORKBOOK_PATH = (
    ROOT / "data" / "materials" / "Video 08" / "ISM_NonManufacturing_Index.xlsx"
)

SERIES_CONFIG = {
    "ism_services_pmi": {
        "sheet": "NMI",
        "title": "ISM Services PMI",
        "units": "index",
    },
    "ism_services_business_activity": {
        "sheet": "Business Activity",
        "title": "ISM Services Business Activity",
        "units": "index",
    },
    "ism_services_new_orders": {
        "sheet": "New Orders",
        "title": "ISM Services New Orders",
        "units": "index",
    },
    "ism_services_order_backlog": {
        "sheet": "Order Backlog",
        "title": "ISM Services Order Backlog",
        "units": "index",
    },
}

RANKING_LAYOUT = ism_workbook.RankingLayout(
    sheet="Sectors",
    header_row=3,
    data_row=6,
    industry_column=1,
    first_status_column=2,
)


def parse_workbook(workbook_path=DEFAULT_WORKBOOK_PATH):
    return ism_workbook.parse_series_workbook(
        workbook_path, "ism services", SERIES_CONFIG
    )


def parse_sector_rankings(workbook_path=DEFAULT_WORKBOOK_PATH):
    return ism_workbook.parse_ranking_workbook(
        workbook_path,
        "services",
        "ism services",
        RANKING_LAYOUT,
    )


def parse_industry_comments(workbook_path=DEFAULT_WORKBOOK_PATH):
    path = Path(workbook_path)
    if not path.exists():
        raise ValueError(f"services workbook is missing: {path}")
    workbook = ism_workbook.load_workbook(path, read_only=True, data_only=True)
    sheet_name = "Industry Comments"
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"services sheet is missing: {sheet_name}")
    sheet = workbook[sheet_name]
    rows = []
    last_industry = None
    index_by_key = {}
    for row in sheet.iter_rows(min_row=2, values_only=True):
        industry_raw = row[0]
        date_val = row[1]
        comment_raw = row[2]
        if industry_raw is not None:
            last_industry = str(industry_raw).strip()
        if not last_industry:
            continue
        if not ism_workbook.is_date(date_val):
            continue
        report_month = ism_workbook.iso_date(date_val)
        key = (last_industry, report_month)
        index_by_key[key] = index_by_key.get(key, -1) + 1
        comment_text = str(comment_raw).strip() if comment_raw is not None else ""
        rows.append(
            {
                "survey_type": "services",
                "report_month": report_month,
                "industry": last_industry,
                "comment_index": index_by_key[key],
                "comment_text": comment_text,
                "source": path.name,
            }
        )
    return rows


def import_workbook(con, workbook_path=DEFAULT_WORKBOOK_PATH):
    ism_surveys.init_db(con)
    parsed_list = parse_workbook(workbook_path)
    results = {}
    for parsed in parsed_list:
        sid = parsed["series"]["series_id"]
        saved = macro_indicators.insert_macro_indicator_points(
            con,
            parsed["series"],
            parsed["points"],
        )
        results[sid] = saved["points"]
    rankings = parse_sector_rankings(workbook_path)
    results["ism_services_industry_rankings"] = ism_surveys.insert_industry_rankings(
        con, "services", rankings
    )
    comments = parse_industry_comments(workbook_path)
    results["ism_services_industry_comments"] = ism_surveys.insert_industry_comments(
        con, "services", comments
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
    try:
        inserted = import_workbook(con, args.workbook_path)
    finally:
        con.close()
    for series_id, count in inserted.items():
        print(f"{series_id}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
