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
