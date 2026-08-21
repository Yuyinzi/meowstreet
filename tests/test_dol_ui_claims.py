import hashlib
from datetime import datetime

import httpx
import pytest
from pypdf import PdfReader

from app.data_sources import dol_ui_claims
from app.http_client import HttpClient

INITIAL_PAGE_URL = "https://oui.doleta.gov/unemploy/Chartbook/a2.asp"
CONTINUING_PAGE_URL = "https://oui.doleta.gov/unemploy/Chartbook/a3.asp"
RELEASE_URL = "https://www.dol.gov/ui/data.pdf"
REPORT_URL = "https://oui.doleta.gov/unemploy/wkclaims/report.asp"
CLAIMS_PAGE_URL = "https://oui.doleta.gov/unemploy/claims.asp"

_RELEASE_TEXT = (
    "TRANSMISSION OF MATERIALS IN THIS RELEASE IS EMBARGOED UNTIL\n"
    "8:30 A.M. (Eastern) Thursday, July 30, 2026\n"
    "\n"
    "UNEMPLOYMENT INSURANCE WEEKLY CLAIMS\n"
    "SEASONALLY ADJUSTED DATA\n"
    "\n"
    "In the week ending July 25, the advance figure for seasonally adjusted "
    "initial claims was 197,000, an increase of 9,000 from the previous "
    "week's revised level. The previous week's level was revised up by "
    "1,000 from 187,000 to 188,000.\n"
    "\n"
    "The advance seasonally adjusted insured unemployment rate was 1.2 "
    "percent for the week ending July 18, unchanged from the previous "
    "week's unrevised rate. The advance number for seasonally adjusted "
    "insured unemployment during the week ending July 18 was 1,782,000, "
    "a decrease of 7,000 from the previous week's revised level. The "
    "previous week's level was revised down by 7,000 from 1,796,000 to "
    "1,789,000.\n"
    "\n"
    "UNADJUSTED DATA\n"
    "\n"
    "The advance number of actual initial claims under state programs, "
    "unadjusted, totaled 175,573 in the week ending July 25.\n"
)


def initial_csv():
    return (
        "Report Date,Initial Claims,4 Week Claims\n"
        "2026-07-05,231000,208\n"
        "2026-07-12,234000,209\n"
        "2026-07-19,189000,208\n"
    )


def continuing_csv():
    return (
        "Report Date,Monthly Continued Claims\n"
        "2026-1,9.264\n"
        "2026-2,7.41\n"
        "2026-3,7.286\n"
    )


def _page_html(chartnum):
    return (
        "<html><body>"
        '<form action="createdf.php" method="post">'
        '<input type="hidden" name="begyr" value="1967" />'
        '<input type="hidden" name="endyr" value="1980" />'
        f'<input type="hidden" name="chartnum" value="{chartnum}" />'
        '<input type="submit" value="Get the Raw Data!" />'
        "</form></body></html>"
    ).encode("utf-8")


def _select_page_html(chartnum):
    return (
        "<html><body>"
        '<form action="createdf.php" method="post">'
        '<select name="begyr">'
        '<option value="1990">1990</option>'
        '<option value="1967" selected>1967</option>'
        "</select>"
        '<select name="endyr">'
        '<option value="2000">2000</option>'
        '<option value="1980" selected>1980</option>'
        "</select>"
        f'<input type="hidden" name="chartnum" value="{chartnum}" />'
        '<input type="submit" value="Get the Raw Data!" />'
        "</form></body></html>"
    ).encode("utf-8")


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


def test_fetch_claims_history_discovers_raw_data_forms_and_parses():
    def handler(request):
        assert request.headers["User-Agent"] == "Meowstreet/1.0"
        if str(request.url) == INITIAL_PAGE_URL:
            return httpx.Response(200, content=_page_html("a2"))
        if str(request.url) == CONTINUING_PAGE_URL:
            return httpx.Response(200, content=_page_html("a3"))
        if str(request.url) == "https://oui.doleta.gov/unemploy/Chartbook/createdf.php":
            assert request.method == "POST"
            body = request.read().decode()
            assert "chartnum=a2" in body or "chartnum=a3" in body
            assert f"endyr={datetime.now().year}" in body
            if "chartnum=a2" in body:
                return httpx.Response(200, content=initial_csv().encode("utf-8"))
            return httpx.Response(200, content=continuing_csv().encode("utf-8"))
        raise AssertionError(f"unexpected request {request.url}")

    client = HttpClient(transport=httpx.MockTransport(handler))
    observations = dol_ui_claims.fetch_claims_history(
        client, INITIAL_PAGE_URL, CONTINUING_PAGE_URL
    )

    initial = [o for o in observations if o["series_id"] == "initial_claims_sa"]
    continuing = [o for o in observations if o["series_id"] == "continuing_claims_sa"]
    assert len(initial) == 3
    assert len(continuing) == 3
    assert initial[0]["reference_period"] == "2026-07-05"
    assert initial[0]["value_at_release"] == 231000.0
    assert initial[2]["reference_period"] == "2026-07-19"
    assert initial[2]["value_at_release"] == 189000.0
    assert initial[0]["seasonal_adjustment"] == "seasonally_adjusted"
    assert initial[0]["latest_revised_value"] is None
    assert initial[0]["revision_number"] == 0
    assert initial[0]["vintage_id"].startswith("history:initial_claims_sa:2026-07-05:")
    assert continuing[0]["reference_period"] == "2026-01"
    assert continuing[0]["value_at_release"] == 9.264
    assert continuing[0]["series_id"] == "continuing_claims_sa"
    assert observations[0]["source_url"] == (
        "https://oui.doleta.gov/unemploy/Chartbook/createdf.php"
    )
    assert (
        observations[0]["source_hash"]
        == hashlib.sha256(initial_csv().encode("utf-8")).hexdigest()
    )


def test_fetch_claims_history_discovers_year_select_fields():
    def handler(request):
        if str(request.url) == INITIAL_PAGE_URL:
            return httpx.Response(200, content=_select_page_html("a2"))
        if str(request.url) == CONTINUING_PAGE_URL:
            return httpx.Response(200, content=_select_page_html("a3"))
        if str(request.url) == "https://oui.doleta.gov/unemploy/Chartbook/createdf.php":
            assert request.method == "POST"
            body = request.read().decode()
            assert "begyr=1967" in body
            assert f"endyr={datetime.now().year}" in body
            if "chartnum=a2" in body:
                return httpx.Response(200, content=initial_csv().encode("utf-8"))
            return httpx.Response(200, content=continuing_csv().encode("utf-8"))
        raise AssertionError(f"unexpected request {request.url}")

    client = HttpClient(transport=httpx.MockTransport(handler))
    observations = dol_ui_claims.fetch_claims_history(
        client, INITIAL_PAGE_URL, CONTINUING_PAGE_URL
    )
    assert len(observations) == 6


def test_fetch_claims_history_defaults_missing_years_explicitly():
    def page_html(chartnum):
        return (
            "<html><body>"
            '<form action="createdf.php" method="post">'
            f'<input type="hidden" name="chartnum" value="{chartnum}" />'
            "</form></body></html>"
        ).encode("utf-8")

    def handler(request):
        if str(request.url) == INITIAL_PAGE_URL:
            return httpx.Response(200, content=page_html("a2"))
        if str(request.url) == CONTINUING_PAGE_URL:
            return httpx.Response(200, content=page_html("a3"))
        if str(request.url) == "https://oui.doleta.gov/unemploy/Chartbook/createdf.php":
            body = request.read().decode()
            assert "begyr=1967" in body
            assert f"endyr={datetime.now().year}" in body
            if "chartnum=a2" in body:
                return httpx.Response(200, content=initial_csv().encode("utf-8"))
            return httpx.Response(200, content=continuing_csv().encode("utf-8"))
        raise AssertionError(f"unexpected request {request.url}")

    client = HttpClient(transport=httpx.MockTransport(handler))
    observations = dol_ui_claims.fetch_claims_history(
        client, INITIAL_PAGE_URL, CONTINUING_PAGE_URL
    )
    assert len(observations) == 6


def test_fetch_claims_history_raises_on_page_404():
    def handler(request):
        if str(request.url) == INITIAL_PAGE_URL:
            return httpx.Response(404, content=b"not found")
        raise AssertionError(f"unexpected request {request.url}")

    client = HttpClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="failed to fetch"):
        dol_ui_claims.fetch_claims_history(
            client, INITIAL_PAGE_URL, CONTINUING_PAGE_URL
        )


def test_fetch_claims_history_raises_on_csv_503():
    def handler(request):
        if str(request.url) == INITIAL_PAGE_URL:
            return httpx.Response(200, content=_page_html("a2"))
        return httpx.Response(503, content=b"unavailable")

    client = HttpClient(
        transport=httpx.MockTransport(handler), sleep=lambda _seconds: None
    )
    with pytest.raises(ValueError, match="failed to fetch"):
        dol_ui_claims.fetch_claims_history(
            client, INITIAL_PAGE_URL, CONTINUING_PAGE_URL
        )


def test_fetch_claims_history_rejects_page_without_raw_data_form():
    def handler(request):
        return httpx.Response(200, content=b"<html><body>no form here</body></html>")

    client = HttpClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="no raw data form"):
        dol_ui_claims.fetch_claims_history(
            client, INITIAL_PAGE_URL, CONTINUING_PAGE_URL
        )


def test_parse_claims_history_csv_skips_empty_future_values():
    csv_text = (
        "Report Date,Initial Claims,4 Week Claims\n"
        "2026-07-19,189000,208\n"
        "2026-07-26,,150\n"
    )
    rows = dol_ui_claims.parse_claims_history_csv(
        csv_text,
        "initial_claims_sa",
        "https://oui.doleta.gov/unemploy/Chartbook/createdf.php",
    )
    assert len(rows) == 1
    assert rows[0]["reference_period"] == "2026-07-19"


def test_parse_claims_history_csv_rejects_missing_value_column():
    csv_text = "Report Date,4 Week Claims\n2026-07-19,208\n"
    with pytest.raises(ValueError, match="missing initial_claims_sa value column"):
        dol_ui_claims.parse_claims_history_csv(
            csv_text, "initial_claims_sa", "https://example.test/a2.csv"
        )


def test_parse_claims_history_csv_rejects_missing_date():
    csv_text = "Report Date,Initial Claims,4 Week Claims\n,189000,208\n"
    with pytest.raises(ValueError, match="missing date"):
        dol_ui_claims.parse_claims_history_csv(
            csv_text, "initial_claims_sa", "https://example.test/a2.csv"
        )


def test_parse_claims_history_csv_rejects_invalid_reference_period():
    csv_text = "Report Date,Initial Claims,4 Week Claims\n2026/07/19,189000,208\n"
    with pytest.raises(ValueError, match="invalid reference period"):
        dol_ui_claims.parse_claims_history_csv(
            csv_text, "initial_claims_sa", "https://example.test/a2.csv"
        )


def test_parse_claims_history_csv_rejects_non_numeric_value():
    csv_text = "Report Date,Initial Claims,4 Week Claims\n2026-07-19,abc,208\n"
    with pytest.raises(ValueError, match="non-numeric value"):
        dol_ui_claims.parse_claims_history_csv(
            csv_text, "initial_claims_sa", "https://example.test/a2.csv"
        )


def test_parse_claims_history_csv_rejects_duplicate_period():
    csv_text = (
        "Report Date,Initial Claims,4 Week Claims\n"
        "2026-07-19,189000,208\n"
        "2026-07-19,190000,210\n"
    )
    with pytest.raises(ValueError, match="duplicate"):
        dol_ui_claims.parse_claims_history_csv(
            csv_text, "initial_claims_sa", "https://example.test/a2.csv"
        )


def test_parse_claims_history_csv_rejects_negative_value():
    csv_text = "Report Date,Initial Claims,4 Week Claims\n2026-07-19,-100,208\n"
    with pytest.raises(ValueError, match="negative"):
        dol_ui_claims.parse_claims_history_csv(
            csv_text, "initial_claims_sa", "https://example.test/a2.csv"
        )


def test_parse_claims_release_text_extracts_release_and_revision():
    observations = dol_ui_claims.parse_claims_release_text(_RELEASE_TEXT, RELEASE_URL)
    initial = [o for o in observations if o["series_id"] == "initial_claims_sa"]
    continuing = [o for o in observations if o["series_id"] == "continuing_claims_sa"]

    assert len(initial) == 2
    assert len(continuing) == 2

    initial_current, initial_prior = initial
    assert initial_current["reference_period"] == "2026-07-25"
    assert initial_current["value_at_release"] == 197000.0
    assert initial_current["latest_revised_value"] is None
    assert initial_current["revision_number"] == 0
    assert initial_current["release_date"] == "2026-07-30"
    assert initial_current["seasonal_adjustment"] == "seasonally_adjusted"
    assert initial_current["source_url"] == RELEASE_URL
    assert (
        initial_current["vintage_id"]
        == "release:initial_claims_sa:2026-07-25:2026-07-30"
    )

    assert initial_prior["reference_period"] == "2026-07-18"
    assert initial_prior["value_at_release"] == 187000.0
    assert initial_prior["latest_revised_value"] == 188000.0
    assert initial_prior["revision_number"] == 1
    assert initial_prior["release_date"] == "2026-07-30"
    assert (
        initial_prior["vintage_id"] == "release:initial_claims_sa:2026-07-18:2026-07-30"
    )

    continuing_current, continuing_prior = continuing
    assert continuing_current["reference_period"] == "2026-07-18"
    assert continuing_current["value_at_release"] == 1782000.0
    assert continuing_current["latest_revised_value"] is None
    assert continuing_current["revision_number"] == 0
    assert (
        continuing_current["vintage_id"]
        == "release:continuing_claims_sa:2026-07-18:2026-07-30"
    )

    assert continuing_prior["reference_period"] == "2026-07-11"
    assert continuing_prior["value_at_release"] == 1796000.0
    assert continuing_prior["latest_revised_value"] == 1789000.0
    assert continuing_prior["revision_number"] == 1
    assert continuing_prior["release_date"] == "2026-07-30"
    assert (
        continuing_prior["vintage_id"]
        == "release:continuing_claims_sa:2026-07-11:2026-07-30"
    )


def test_parse_claims_release_text_accepts_revision_without_by():
    text = _RELEASE_TEXT.replace("revised down by 7,000", "revised down 7,000")

    observations = dol_ui_claims.parse_claims_release_text(text, RELEASE_URL)
    continuing = [
        row for row in observations if row["series_id"] == "continuing_claims_sa"
    ]

    assert len(continuing) == 2
    assert continuing[1]["reference_period"] == "2026-07-11"
    assert continuing[1]["value_at_release"] == 1796000.0
    assert continuing[1]["latest_revised_value"] == 1789000.0
    assert continuing[1]["revision_number"] == 1


def test_parse_claims_release_text_without_revision_yields_current_week_only():
    text = _RELEASE_TEXT.replace(
        " The previous week's level was revised up by 1,000 from 187,000 to 188,000.",
        "",
    ).replace(
        " The previous week's level was revised down by "
        "7,000 from 1,796,000 to 1,789,000.",
        "",
    )
    observations = dol_ui_claims.parse_claims_release_text(text, RELEASE_URL)
    initial = [o for o in observations if o["series_id"] == "initial_claims_sa"]
    continuing = [o for o in observations if o["series_id"] == "continuing_claims_sa"]

    assert len(initial) == 1
    assert initial[0]["reference_period"] == "2026-07-25"
    assert initial[0]["value_at_release"] == 197000.0
    assert initial[0]["latest_revised_value"] is None
    assert initial[0]["revision_number"] == 0

    assert len(continuing) == 1
    assert continuing[0]["reference_period"] == "2026-07-18"
    assert continuing[0]["value_at_release"] == 1782000.0
    assert continuing[0]["latest_revised_value"] is None
    assert continuing[0]["revision_number"] == 0


def test_parse_claims_release_text_rejects_missing_release_date():
    text = _RELEASE_TEXT.replace("Thursday, July 30, 2026", "Thursday")
    with pytest.raises(ValueError, match="missing release date"):
        dol_ui_claims.parse_claims_release_text(text, RELEASE_URL)


def test_parse_claims_release_text_rejects_missing_seasonally_adjusted_initial():
    text = (
        "TRANSMISSION OF MATERIALS IN THIS RELEASE IS EMBARGOED UNTIL\n"
        "8:30 A.M. (Eastern) Thursday, July 30, 2026\n"
        "\n"
        "UNADJUSTED DATA\n"
        "\n"
        "The advance number of actual initial claims under state programs, "
        "unadjusted, totaled 175,573 in the week ending July 25.\n"
    )
    with pytest.raises(ValueError, match="initial claims"):
        dol_ui_claims.parse_claims_release_text(text, RELEASE_URL)


def test_parse_claims_release_text_rejects_missing_seasonally_adjusted_continuing():
    text = _RELEASE_TEXT.replace(
        "The advance seasonally adjusted insured unemployment rate was 1.2 ",
        "The advance insured unemployment rate was 1.2 ",
    ).replace(
        "for seasonally adjusted insured unemployment during the week ending "
        "July 18 was 1,782,000",
        "for insured unemployment during the week ending July 18 was 1,782,000",
    )
    with pytest.raises(ValueError, match="insured unemployment"):
        dol_ui_claims.parse_claims_release_text(text, RELEASE_URL)


def test_fetch_claims_release_downloads_and_parses_pdf():
    pdf = build_pdf(_RELEASE_TEXT.splitlines())

    def handler(request):
        assert str(request.url) == RELEASE_URL
        assert request.headers["User-Agent"] == "Meowstreet/1.0"
        return httpx.Response(200, content=pdf)

    client = HttpClient(transport=httpx.MockTransport(handler))
    observations = dol_ui_claims.fetch_claims_release(client, RELEASE_URL)

    initial = [o for o in observations if o["series_id"] == "initial_claims_sa"]
    initial_current = initial[0]
    assert initial_current["value_at_release"] == 197000.0
    assert initial_current["latest_revised_value"] is None
    assert isinstance(initial_current["source_hash"], str)
    assert len(initial_current["source_hash"]) == 64
    initial_prior = next(o for o in initial if o["revision_number"] == 1)
    assert initial_prior["latest_revised_value"] == 188000.0


def test_fetch_claims_release_raises_on_404():
    def handler(request):
        return httpx.Response(404, content=b"not found")

    client = HttpClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="failed to fetch"):
        dol_ui_claims.fetch_claims_release(client, RELEASE_URL)


def test_fetch_claims_release_rejects_invalid_pdf():
    def handler(request):
        return httpx.Response(200, content=b"not a pdf")

    client = HttpClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="could not be read"):
        dol_ui_claims.fetch_claims_release(client, RELEASE_URL)


def national_claims_history_html():
    return b"""
    <table summary="r539cy Report Table">
      <tr><th id="report_date"></th><th id="sa_initial_claims">S.A.</th>
          <th id="sa_continued_claims">S.A.</th></tr>
      <tr><th id="01/04/2025">01/04/2025</th>
          <td headers="01/04/2025 sa_initial_claims">206,000</td>
          <td headers="01/04/2025 sa_continued_claims">1,850,000</td></tr>
      <tr><th id="01/11/2025">01/11/2025</th>
          <td headers="01/11/2025 sa_initial_claims">219,000</td>
          <td headers="01/11/2025 sa_continued_claims">1,871,000</td></tr>
    </table>
    """


def national_claims_page_html():
    return (
        "<html><body>"
        '<form action="https://www.doleta.gov/gsearch.cfm" method="post">'
        '<input type="text" name="search" />'
        "</form>"
        '<form name="wkclaim" method="post" action="wkclaims/report.asp">'
        '<input type="radio" name="level" value="us" checked />National'
        '<input type="radio" name="level" value="state" />State'
        '<input type="hidden" name="final_yr" value="2027" />'
        '<select name="strtdate"><option value="">Start</option></select>'
        '<select name="enddate"><option value="">End</option></select>'
        '<input type="radio" name="filetype" id="html" value="html" checked />'
        '<input type="radio" name="filetype" value="xls" />'
        '<input type="radio" name="filetype" value="xml" />'
        '<input type="submit" name="submit" value="Submit" />'
        "</form></body></html>"
    ).encode("utf-8")


def test_fetch_national_claims_history_posts_one_national_spreadsheet_request():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, content=national_claims_page_html())
        assert str(request.url) == REPORT_URL
        body = request.read().decode()
        assert "level=us" in body
        assert "strtdate=1967" in body
        assert f"enddate={datetime.now().year}" in body
        assert "filetype=xls" in body
        return httpx.Response(200, content=national_claims_history_html())

    rows = dol_ui_claims.fetch_national_claims_history(
        HttpClient(transport=httpx.MockTransport(handler)), CLAIMS_PAGE_URL
    )
    assert len(requests) == 2
    assert {row["series_id"] for row in rows} == {
        "initial_claims_sa",
        "continuing_claims_sa",
    }


def test_fetch_national_claims_history_rejects_page_without_national_form():
    def handler(request):
        return httpx.Response(200, content=b"<html><body>no form here</body></html>")

    client = HttpClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="claims page has no national report form"):
        dol_ui_claims.fetch_national_claims_history(client, CLAIMS_PAGE_URL)


def test_fetch_national_claims_history_rejects_report_form_without_national_radio():
    def handler(request):
        return httpx.Response(
            200,
            content=(
                "<html><body>"
                '<form action="wkclaims/report.asp" method="post">'
                '<input type="radio" name="level" value="state" checked />'
                "</form></body></html>"
            ).encode("utf-8"),
        )

    client = HttpClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="claims page has no national report form"):
        dol_ui_claims.fetch_national_claims_history(client, CLAIMS_PAGE_URL)


def test_fetch_national_claims_history_raises_on_page_404():
    def handler(request):
        return httpx.Response(404, content=b"not found")

    client = HttpClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="failed to fetch national claims page from"):
        dol_ui_claims.fetch_national_claims_history(client, CLAIMS_PAGE_URL)


def test_fetch_national_claims_history_raises_on_report_503():
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, content=national_claims_page_html())
        return httpx.Response(503, content=b"unavailable")

    client = HttpClient(
        transport=httpx.MockTransport(handler), sleep=lambda _seconds: None
    )
    with pytest.raises(
        ValueError, match="failed to fetch national claims history report from"
    ):
        dol_ui_claims.fetch_national_claims_history(client, CLAIMS_PAGE_URL)


def test_fetch_national_claims_history_submits_discovered_final_yr():
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, content=national_claims_page_html())
        body = request.read().decode()
        assert "final_yr=2027" in body
        assert "submit=Submit" in body
        return httpx.Response(200, content=national_claims_history_html())

    client = HttpClient(transport=httpx.MockTransport(handler))
    rows = dol_ui_claims.fetch_national_claims_history(client, CLAIMS_PAGE_URL)
    assert len(rows) == 4


def test_parse_national_claims_history_html_returns_both_sa_series():
    rows = dol_ui_claims.parse_national_claims_history_html(
        national_claims_history_html(), REPORT_URL
    )
    assert [
        (row["series_id"], row["reference_period"], row["value_at_release"])
        for row in rows
    ] == [
        ("initial_claims_sa", "2025-01-04", 206000.0),
        ("continuing_claims_sa", "2025-01-04", 1850000.0),
        ("initial_claims_sa", "2025-01-11", 219000.0),
        ("continuing_claims_sa", "2025-01-11", 1871000.0),
    ]


def test_parse_national_claims_history_html_builds_history_observation_schema():
    rows = dol_ui_claims.parse_national_claims_history_html(
        national_claims_history_html(), REPORT_URL
    )
    assert len(rows) == 4
    as_of_timestamps = {row["as_of_timestamp"] for row in rows}
    assert len(as_of_timestamps) == 1
    retrieval_date = rows[0]["as_of_timestamp"][:10]
    for row in rows:
        assert row["release_date"] is None
        assert row["latest_revised_value"] is None
        assert row["revision_number"] == 0
        assert row["seasonal_adjustment"] == "seasonally_adjusted"
        assert row["source_url"] == REPORT_URL
        assert (
            row["source_hash"]
            == hashlib.sha256(national_claims_history_html()).hexdigest()
        )
        assert row["vintage_id"] == (
            f"history:{row['series_id']}:{row['reference_period']}:{retrieval_date}"
        )


def test_parse_national_claims_history_html_ignores_non_sa_cells():
    html = b"""
    <table summary="r539cy Report Table">
      <tr><th id="report_date"></th><th id="sa_initial_claims">S.A.</th>
          <th id="sa_continued_claims">S.A.</th></tr>
      <tr><th id="01/04/2025">01/04/2025</th>
          <td headers="01/04/2025 sa_initial_claims">206,000</td>
          <td headers="01/04/2025 sa_continued_claims">1,850,000</td>
          <td headers="01/04/2025 sa_four_week_avg">208,000</td>
          <td headers="01/04/2025 nsa_initial_claims">199,000</td></tr>
    </table>
    """
    rows = dol_ui_claims.parse_national_claims_history_html(html, REPORT_URL)
    assert len(rows) == 2
    assert rows[0]["series_id"] == "initial_claims_sa"
    assert rows[0]["value_at_release"] == 206000.0
    assert rows[1]["series_id"] == "continuing_claims_sa"
    assert rows[1]["value_at_release"] == 1850000.0


def duplicate_initial_html():
    return b"""
    <table summary="r539cy Report Table">
      <tr><th id="01/04/2025">01/04/2025</th>
          <td headers="01/04/2025 sa_initial_claims">206,000</td></tr>
      <tr><th id="01/04/2025">01/04/2025</th>
          <td headers="01/04/2025 sa_initial_claims">207,000</td></tr>
    </table>
    """


def single_series_initial_only_html():
    return b"""
    <table summary="r539cy Report Table">
      <tr><th id="report_date"></th><th id="sa_initial_claims">S.A.</th></tr>
      <tr><th id="01/04/2025">01/04/2025</th>
          <td headers="01/04/2025 sa_initial_claims">206,000</td></tr>
      <tr><th id="01/11/2025">01/11/2025</th>
          <td headers="01/11/2025 sa_initial_claims">219,000</td></tr>
    </table>
    """


def test_parse_national_claims_history_html_rejects_report_missing_continuing_series():
    with pytest.raises(
        ValueError,
        match="national claims history report is missing continuing_claims_sa series",
    ):
        dol_ui_claims.parse_national_claims_history_html(
            single_series_initial_only_html(), REPORT_URL
        )


def test_parse_national_claims_history_html_rejects_empty_report():
    with pytest.raises(
        ValueError,
        match="national claims history report has no seasonally adjusted claims rows",
    ):
        dol_ui_claims.parse_national_claims_history_html(b"<table></table>", REPORT_URL)


def test_parse_national_claims_history_html_rejects_duplicate_period_series():
    with pytest.raises(
        ValueError,
        match="national claims history has duplicate initial_claims_sa period 2025-01-04",
    ):
        dol_ui_claims.parse_national_claims_history_html(
            duplicate_initial_html(), REPORT_URL
        )


def test_parse_national_claims_history_html_rejects_invalid_date():
    html = b"""
    <table summary="r539cy Report Table">
      <tr><th id="02/30/2025">02/30/2025</th>
          <td headers="02/30/2025 sa_initial_claims">206,000</td></tr>
    </table>
    """
    with pytest.raises(ValueError, match="invalid report date"):
        dol_ui_claims.parse_national_claims_history_html(html, REPORT_URL)


def test_parse_national_claims_history_html_rejects_non_numeric_value():
    html = b"""
    <table summary="r539cy Report Table">
      <tr><th id="01/04/2025">01/04/2025</th>
          <td headers="01/04/2025 sa_initial_claims">abc</td></tr>
    </table>
    """
    with pytest.raises(ValueError, match="non-numeric value"):
        dol_ui_claims.parse_national_claims_history_html(html, REPORT_URL)


def test_parse_national_claims_history_html_rejects_negative_value():
    html = b"""
    <table summary="r539cy Report Table">
      <tr><th id="01/04/2025">01/04/2025</th>
          <td headers="01/04/2025 sa_initial_claims">-100</td></tr>
    </table>
    """
    with pytest.raises(ValueError, match="negative initial_claims_sa value"):
        dol_ui_claims.parse_national_claims_history_html(html, REPORT_URL)


def test_parse_national_claims_history_html_rejects_value_without_paired_report_date():
    html = b"""
    <table summary="r539cy Report Table">
      <tr><th id="01/04/2025">01/04/2025</th></tr>
      <tr><td headers="01/11/2025 sa_initial_claims">219,000</td></tr>
    </table>
    """
    with pytest.raises(ValueError, match="missing report date"):
        dol_ui_claims.parse_national_claims_history_html(html, REPORT_URL)
