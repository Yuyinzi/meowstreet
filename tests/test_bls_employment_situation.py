import hashlib

import pytest

from app.data_sources import bls_employment_situation

SOURCE_URL = "https://www.bls.gov/news.release/pdf/empsit.pdf"


def bls_text():
    return (
        "THE EMPLOYMENT SITUATION -- JUNE 2026\n"
        "\n"
        "FOR RELEASE: 8:30 A.M. (ET) THURSDAY, JULY 2, 2026\n"
        "\n"
        "Nonfarm payroll employment increased by 200,000 in June, and the\n"
        "unemployment rate was 4.0 percent.\n"
        "\n"
        "SEASONALLY ADJUSTED DATA\n"
        "\n"
        "                        May 2026       June 2026\n"
        "Nonfarm payrolls         158,000        158,200\n"
        "Payrolls 3-month avg     157,400        157,700\n"
        "Unemployment rate            4.1           4.0\n"
        "Average weekly hours        34.3          34.4\n"
        "Average hourly earnings    36.50         36.70\n"
        "\n"
        "Revisions: Total nonfarm payroll employment for April 2026 was revised\n"
        "from 157,100 to 157,200. Total nonfarm payroll employment for May 2026\n"
        "was revised from 157,900 to 158,000.\n"
        "\n"
        "The next Employment Situation news release is scheduled for release on\n"
        "Friday, August 7, 2026 at 8:30 a.m. (ET).\n"
    )


def _escape(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(lines):
    content = "\n".join(
        f"BT /F1 10 Tf 72 {720 - 14 * i} Td ({_escape(line or ' ')}) Tj ET"
        for i, line in enumerate(lines)
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
    ]
    stream = content.encode("latin-1")
    objects.append(
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % index + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_pos,
    )
    return bytes(out)


def _release_pdf():
    return build_pdf(bls_text().splitlines())


def _parse(text=None):
    pdf = build_pdf((text or bls_text()).splitlines())
    return bls_employment_situation.parse_employment_situation_release(pdf, SOURCE_URL)


def test_parse_employment_situation_release_extracts_context_metrics():
    result = _parse()
    by_id = {obs["series_id"]: obs for obs in result["observations"]}
    payrolls = [
        obs
        for obs in result["observations"]
        if obs["series_id"] == "nonfarm_payrolls"
        and obs["reference_period"] == "2026-06"
    ][0]

    assert result["reference_period"] == "2026-06"
    assert result["release_date"] == "2026-07-02"

    assert payrolls["reference_period"] == "2026-06"
    assert payrolls["value_at_release"] == 158200.0
    assert payrolls["release_date"] == "2026-07-02"
    assert payrolls["seasonal_adjustment"] == "seasonally_adjusted"
    assert payrolls["source_url"] == SOURCE_URL
    assert payrolls["vintage_id"] == "nonfarm_payrolls:2026-06:2026-07-02"

    assert by_id["payrolls_3m_average"]["value_at_release"] == 157700.0
    assert by_id["unemployment_rate"]["value_at_release"] == 4.0
    assert by_id["average_weekly_hours"]["value_at_release"] == 34.4
    assert by_id["average_hourly_earnings"]["value_at_release"] == 36.7


def test_parse_employment_situation_release_extracts_payroll_revisions():
    result = _parse()
    revisions = [
        obs for obs in result["observations"] if obs["latest_revised_value"] is not None
    ]
    assert len(revisions) == 2
    by_period = {obs["reference_period"]: obs for obs in revisions}
    assert by_period["2026-04"]["series_id"] == "nonfarm_payrolls"
    assert by_period["2026-04"]["value_at_release"] == 157100.0
    assert by_period["2026-04"]["latest_revised_value"] == 157200.0
    assert by_period["2026-04"]["revision_number"] == 1
    assert by_period["2026-05"]["value_at_release"] == 157900.0
    assert by_period["2026-05"]["latest_revised_value"] == 158000.0


def test_parse_employment_situation_release_extracts_next_event():
    result = _parse()
    assert len(result["scheduled_events"]) == 1
    event = result["scheduled_events"][0]
    assert event["event_id"] == "bls_employment_situation"
    assert event["scheduled_at"] == "2026-08-07T08:30:00"
    assert event["timezone"] == "ET"
    assert event["status"] == "upcoming"


def test_parse_employment_situation_release_sets_source_hash():
    pdf = _release_pdf()
    result = bls_employment_situation.parse_employment_situation_release(
        pdf, SOURCE_URL
    )
    assert result["observations"][0]["source_hash"] == hashlib.sha256(pdf).hexdigest()


def test_parse_employment_situation_release_rejects_garbage_bytes():
    with pytest.raises(ValueError, match="could not be read"):
        bls_employment_situation.parse_employment_situation_release(
            b"not a pdf", SOURCE_URL
        )


def test_parse_employment_situation_release_rejects_missing_release_date():
    text = bls_text().replace("FOR RELEASE: 8:30 A.M. (ET) THURSDAY, JULY 2, 2026", "")
    with pytest.raises(ValueError, match="missing release date"):
        _parse(text)


def test_parse_employment_situation_release_rejects_missing_reference_month():
    text = bls_text().replace(
        "THE EMPLOYMENT SITUATION -- JUNE 2026", "THE EMPLOYMENT SITUATION"
    )
    with pytest.raises(ValueError, match="missing reference month"):
        _parse(text)


@pytest.mark.parametrize(
    "label,series_id",
    [
        ("nonfarm payroll", "nonfarm_payrolls"),
        ("3-month", "payrolls_3m_average"),
        ("unemployment rate", "unemployment_rate"),
        ("average weekly hours", "average_weekly_hours"),
        ("average hourly earnings", "average_hourly_earnings"),
    ],
)
def test_parse_employment_situation_release_rejects_missing_metric(label, series_id):
    lines = [line for line in bls_text().splitlines() if label not in line.lower()]
    with pytest.raises(ValueError, match=f"missing {series_id}"):
        _parse("\n".join(lines))


def test_parse_employment_situation_release_rejects_value_count_mismatch():
    lines = []
    for line in bls_text().splitlines():
        if line.strip().startswith("Nonfarm payrolls"):
            lines.append("Nonfarm payrolls 158,200")
        else:
            lines.append(line)
    with pytest.raises(ValueError, match="nonfarm_payrolls"):
        _parse("\n".join(lines))


def test_parse_employment_situation_release_rejects_missing_next_event():
    text = (
        bls_text()
        .replace(
            "The next Employment Situation news release is scheduled for release on",
            "The next Employment Situation news release is scheduled for release",
        )
        .replace("Friday, August 7, 2026 at 8:30 a.m. (ET).", "")
    )
    with pytest.raises(ValueError, match="next release event"):
        _parse(text)


OVERVIEW_URL = "https://www.bls.gov/news.release/empsit.htm"
HOUSEHOLD_URL = "https://www.bls.gov/news.release/empsit.a.htm"
ESTABLISHMENT_URL = "https://www.bls.gov/news.release/empsit.b.htm"


def current_overview_html():
    return """
    <pre>Transmission of material in this news release is embargoed until USDL-26-1125
    8:30 a.m. (ET) Thursday, July 2, 2026
    THE EMPLOYMENT SITUATION - JUNE 2026
    The next Employment Situation for July 2026 is scheduled to be published on
    Friday, August 7, 2026, at 8:30 a.m. (ET).</pre>
    """


def household_table_html():
    return """
    <table>
    <tr><th>Category</th><th>June2025</th><th>Apr.2026</th><th>May2026</th><th>June2026</th><th>Change from: May2026-June2026</th></tr>
    <tr><td>Employment status</td></tr>
    <tr><td>Unemployment rate</td><td>4.1</td><td>4.3</td><td>4.3</td><td>4.2</td><td>-0.1</td></tr>
    </table>
    """


_ESTABLISHMENT_HEADER = (
    "<tr><th>Category</th><th>June2025</th><th>Apr.2026</th><th>May2026(p)</th>"
    "<th>June2026(p)</th></tr>"
)
_OVER_THE_MONTH_SECTION = """<tr><td>EMPLOYMENT BY SELECTED INDUSTRY(Over-the-month change, in thousands)</td></tr>
<tr><td>Total nonfarm</td><td>-20</td><td>148</td><td>129</td><td>57</td></tr>
<tr><td>Total private</td><td>-45</td><td>150</td><td>97</td><td>49</td></tr>"""
_THREE_MONTH_SECTION = """<tr><td>(3-month average change, in thousands)</td></tr>
<tr><td>Total nonfarm</td><td>34</td><td>69</td><td>164</td><td>111</td></tr>
<tr><td>Total private</td><td>25</td><td>68</td><td>150</td><td>99</td></tr>"""
_HOURS_EARNINGS_SECTION = """<tr><td>HOURS AND EARNINGS ALL EMPLOYEES</td></tr>
<tr><td>Total private</td></tr>
<tr><td>Average weekly hours</td><td>34.2</td><td>34.3</td><td>34.3</td><td>34.3</td></tr>
<tr><td>Average hourly earnings</td><td>$36.36</td><td>$37.41</td><td>$37.51</td><td>$37.64</td></tr>"""


def establishment_table_html():
    return f"""<table>
    {_ESTABLISHMENT_HEADER}
    {_OVER_THE_MONTH_SECTION}
    {_THREE_MONTH_SECTION}
    {_HOURS_EARNINGS_SECTION}
    </table>
    """


def establishment_table_html_without_three_month_section():
    return f"""<table>
    {_ESTABLISHMENT_HEADER}
    {_OVER_THE_MONTH_SECTION}
    {_HOURS_EARNINGS_SECTION}
    </table>
    """


def test_parse_employment_situation_html_returns_current_context_metrics():
    result = bls_employment_situation.parse_employment_situation_html(
        current_overview_html(),
        household_table_html(),
        establishment_table_html(),
        OVERVIEW_URL,
        HOUSEHOLD_URL,
        ESTABLISHMENT_URL,
    )
    values = {
        row["series_id"]: row["value_at_release"] for row in result["observations"]
    }
    assert result["release_date"] == "2026-07-02"
    assert result["reference_period"] == "2026-06"
    assert values == {
        "nonfarm_payrolls_change": 57.0,
        "payrolls_3m_average_change": 111.0,
        "unemployment_rate": 4.2,
        "average_weekly_hours": 34.3,
        "average_hourly_earnings": 37.64,
    }
    assert result["scheduled_events"][0]["scheduled_at"] == "2026-08-07T08:30:00"


def overview_html_with_revisions():
    return current_overview_html().replace(
        "</pre>",
        "The change in total nonfarm payroll employment for April was revised down by "
        "31,000, from +179,000 to +148,000, and the change for May was revised down by "
        "43,000, from +172,000 to +129,000.</pre>",
    )


def household_table_html_missing_unemployment():
    return household_table_html().replace(
        "<tr><td>Unemployment rate</td><td>4.1</td><td>4.3</td><td>4.3</td>"
        "<td>4.2</td><td>-0.1</td></tr>",
        "",
    )


def establishment_table_html_duplicate_ahe():
    return establishment_table_html().replace(
        "<tr><td>Average hourly earnings</td><td>$36.36</td><td>$37.41</td>"
        "<td>$37.51</td><td>$37.64</td></tr>",
        "<tr><td>Average hourly earnings</td><td>$36.36</td><td>$37.41</td>"
        "<td>$37.51</td><td>$37.64</td></tr>\n"
        "    <tr><td>Average hourly earnings, private</td><td>$36.36</td><td>$37.41</td>"
        "<td>$37.51</td><td>$37.64</td></tr>",
    )


def _parse_html(overview, household, establishment):
    return bls_employment_situation.parse_employment_situation_html(
        overview,
        household,
        establishment,
        OVERVIEW_URL,
        HOUSEHOLD_URL,
        ESTABLISHMENT_URL,
    )


def test_parse_employment_situation_html_omits_unstated_three_month_payroll_average():
    result = _parse_html(
        current_overview_html(),
        household_table_html(),
        establishment_table_html_without_three_month_section(),
    )
    series_ids = {row["series_id"] for row in result["observations"]}
    assert "payrolls_3m_average_change" not in series_ids


def test_parse_employment_situation_html_extracts_table_three_month_payroll_average():
    result = _parse_html(
        current_overview_html(),
        household_table_html(),
        establishment_table_html(),
    )
    values = {
        row["series_id"]: row["value_at_release"] for row in result["observations"]
    }
    assert values["payrolls_3m_average_change"] == 111.0


def test_parse_employment_situation_html_rejects_missing_current_unemployment_rate():
    with pytest.raises(
        ValueError, match="employment situation html is missing unemployment_rate"
    ):
        _parse_html(
            current_overview_html(),
            household_table_html_missing_unemployment(),
            establishment_table_html(),
        )


def test_parse_employment_situation_html_rejects_ambiguous_average_hourly_earnings_row():
    with pytest.raises(
        ValueError,
        match="employment situation html has ambiguous average_hourly_earnings",
    ):
        _parse_html(
            current_overview_html(),
            household_table_html(),
            establishment_table_html_duplicate_ahe(),
        )


def test_parse_employment_situation_html_extracts_payroll_revisions():
    result = _parse_html(
        overview_html_with_revisions(),
        household_table_html(),
        establishment_table_html(),
    )
    revisions = [
        row for row in result["observations"] if row["latest_revised_value"] is not None
    ]
    assert len(revisions) == 2
    by_period = {row["reference_period"]: row for row in revisions}
    assert by_period["2026-04"]["series_id"] == "nonfarm_payrolls_change"
    assert by_period["2026-04"]["value_at_release"] == 179.0
    assert by_period["2026-04"]["latest_revised_value"] == 148.0
    assert by_period["2026-04"]["revision_number"] == 1
    assert by_period["2026-05"]["value_at_release"] == 172.0
    assert by_period["2026-05"]["latest_revised_value"] == 129.0
    assert by_period["2026-05"]["revision_number"] == 1
