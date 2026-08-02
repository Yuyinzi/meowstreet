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
