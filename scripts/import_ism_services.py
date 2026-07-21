import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import ism_surveys
from app.db import us_rates_liquidity
from app.tools import ism_workbook
from app.tools import ism_services_industry

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
    for row_index, row in enumerate(
        sheet.iter_rows(min_row=2, values_only=True), start=2
    ):
        industry_raw = row[0]
        date_val = row[1]
        comment_raw = row[2]
        if industry_raw is not None:
            raw_name = str(industry_raw).strip()
            try:
                last_industry = ism_services_industry.normalize_industry(raw_name)
            except ValueError as exc:
                raise ValueError(
                    f"services comment row {row_index} has non-services industry: {raw_name}"
                ) from exc
        if not last_industry:
            has_content = date_val is not None or (
                comment_raw is not None and str(comment_raw).strip()
            )
            if has_content:
                raise ValueError(
                    "services comment row has content but no preceding industry assignment"
                )
            continue
        if not ism_workbook.is_date(date_val):
            if date_val is not None:
                raise ValueError(
                    f"services comment row {row_index} has invalid date: {date_val!r}"
                )
            continue
        report_month = ism_workbook.iso_date(date_val)
        if not comment_raw or not str(comment_raw).strip():
            raise ValueError(f"services comment row {row_index} has empty comment")
        comment_text = str(comment_raw).strip()
        key = (last_industry, report_month)
        index_by_key[key] = index_by_key.get(key, -1) + 1
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
    rankings = parse_sector_rankings(workbook_path)
    comments = parse_industry_comments(workbook_path)
    for ranking in rankings:
        try:
            ranking["industry"] = ism_services_industry.normalize_industry(
                ranking["industry"]
            )
        except ValueError as exc:
            raise ValueError(
                f"services ranking has non-services industry: {ranking['industry']}"
            ) from exc
    seen_ranking = set()
    for ranking in rankings:
        key = (ranking["date"], ranking["industry"])
        if key in seen_ranking:
            raise ValueError(
                f"services ranking has duplicate industry {ranking['industry']} for {ranking['date']} after normalization"
            )
        seen_ranking.add(key)
    con.execute("begin")
    try:
        results = {}
        for parsed in parsed_list:
            sid = parsed["series"]["series_id"]
            saved = us_rates_liquidity.insert_macro_indicator_points(
                con,
                parsed["series"],
                parsed["points"],
                commit=False,
            )
            results[sid] = saved["points"]
        results["ism_services_industry_rankings"] = (
            ism_surveys.insert_industry_rankings(
                con, "services", rankings, commit=False
            )
        )
        results["ism_services_industry_comments"] = (
            ism_surveys.insert_industry_comments(
                con, "services", comments, commit=False
            )
        )
        con.commit()
    except BaseException:
        con.rollback()
        raise
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
