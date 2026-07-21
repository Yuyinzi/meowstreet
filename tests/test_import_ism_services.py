from datetime import datetime

import pytest
from openpyxl import Workbook

from app.db import us_rates_liquidity
from scripts import import_ism_services


def write_services_workbook(path):
    workbook = Workbook()
    for index, name in enumerate(
        ["NMI", "Business Activity", "New Orders", "Order Backlog"]
    ):
        sheet = workbook.active if index == 0 else workbook.create_sheet()
        sheet.title = name
        sheet.append(["Date", name])
        sheet.append([datetime(2026, 5, 1), 51.0 + index])
    sectors = workbook.create_sheet("Sectors")
    sectors.append([None] * 6)
    sectors.append([None] * 6)
    sectors.append(["ISM Services", datetime(2026, 5, 1), None])
    sectors.append([None] * 6)
    sectors.append([None] * 6)
    sectors.append(["Construction", "Growth", 1])
    comments = workbook.create_sheet("Industry Comments")
    comments.append(["Sector", "Date", "Comment"])
    comments.append(["Construction", datetime(2026, 5, 1), "Pipeline remains healthy."])
    workbook.save(path)


def test_import_workbook_saves_four_series_and_services_rankings(tmp_path):
    workbook_path = tmp_path / "services.xlsx"
    db_path = tmp_path / "market.sqlite"
    write_services_workbook(workbook_path)
    con = us_rates_liquidity.connect(db_path)

    inserted = import_ism_services.import_workbook(con, workbook_path)

    assert inserted["ism_services_pmi"] == 1
    assert inserted["ism_services_industry_rankings"] == 1
    assert inserted["ism_services_industry_comments"] == 1


def test_import_workbook_rejects_duplicate_after_normalization(tmp_path):
    from openpyxl import Workbook

    workbook_path = tmp_path / "services.xlsx"
    db_path = tmp_path / "market.sqlite"
    workbook = Workbook()
    for index, name in enumerate(
        ["NMI", "Business Activity", "New Orders", "Order Backlog"]
    ):
        sheet = workbook.active if index == 0 else workbook.create_sheet()
        sheet.title = name
        sheet.append(["Date", name])
        sheet.append([datetime(2026, 5, 1), 51.0 + index])
    sectors = workbook.create_sheet("Sectors")
    sectors.append([None] * 6)
    sectors.append([None] * 6)
    sectors.append(["ISM Services", datetime(2026, 5, 1), None])
    sectors.append([None] * 6)
    sectors.append([None] * 6)
    sectors.append(["Construction", "Growth", 1])
    sectors.append(["  Construction  ", "Growth", 2])
    comments = workbook.create_sheet("Industry Comments")
    comments.append(["Sector", "Date", "Comment"])
    comments.append(["Construction", datetime(2026, 5, 1), "Pipeline remains healthy."])
    workbook.save(workbook_path)

    con = import_ism_services.us_rates_liquidity.connect(db_path)
    try:
        import_ism_services.import_workbook(con, workbook_path)
    except ValueError as exc:
        assert "duplicate" in str(exc).lower()
    else:
        pytest.fail("expected ValueError for duplicate after normalization")
    finally:
        con.close()


def test_parse_industry_comments_rejects_orphan_continuation_row(tmp_path):
    from openpyxl import Workbook

    path = tmp_path / "services.xlsx"
    workbook = Workbook()
    for index, name in enumerate(
        ["NMI", "Business Activity", "New Orders", "Order Backlog"]
    ):
        sheet = workbook.active if index == 0 else workbook.create_sheet()
        sheet.title = name
        sheet.append(["Date", name])
        sheet.append([datetime(2026, 5, 1), 51.0 + index])
    sectors = workbook.create_sheet("Sectors")
    sectors.append([None] * 6)
    sectors.append([None] * 6)
    sectors.append(["ISM Services", datetime(2026, 5, 1), None])
    sectors.append([None] * 6)
    sectors.append([None] * 6)
    sectors.append(["Construction", "Growth", 1])
    comments = workbook.create_sheet("Industry Comments")
    comments.append(["Sector", "Date", "Comment"])
    comments.append([None, datetime(2026, 5, 1), "Orphan comment without industry"])
    workbook.save(path)

    with pytest.raises(ValueError, match="no preceding industry"):
        import_ism_services.parse_industry_comments(path)


def test_parse_industry_comments_allows_trailing_empty_rows(tmp_path):
    from openpyxl import Workbook

    path = tmp_path / "services.xlsx"
    workbook = Workbook()
    for index, name in enumerate(
        ["NMI", "Business Activity", "New Orders", "Order Backlog"]
    ):
        sheet = workbook.active if index == 0 else workbook.create_sheet()
        sheet.title = name
        sheet.append(["Date", name])
        sheet.append([datetime(2026, 5, 1), 51.0 + index])
    sectors = workbook.create_sheet("Sectors")
    sectors.append([None] * 6)
    sectors.append([None] * 6)
    sectors.append(["ISM Services", datetime(2026, 5, 1), None])
    sectors.append([None] * 6)
    sectors.append([None] * 6)
    sectors.append(["Construction", "Growth", 1])
    comments = workbook.create_sheet("Industry Comments")
    comments.append(["Sector", "Date", "Comment"])
    comments.append(["Construction", datetime(2026, 5, 1), "Pipeline remains healthy."])
    comments.append([None, None, None])
    comments.append([None, None, None])
    workbook.save(path)

    rows = import_ism_services.parse_industry_comments(path)
    assert len(rows) == 1
