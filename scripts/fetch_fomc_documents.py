import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import us_rates_liquidity


class DocumentUnavailableError(ValueError):
    pass


TAG_RE = re.compile(r"<[^>]+>")
BLOCK_RE = re.compile(r"</(?:p|div|h1|h2|h3|li)>", re.IGNORECASE)
STATEMENT_PATH_RE = re.compile(r"/newsevents/pressreleases/monetary\d{8}a\.htm$")
MINUTES_PATH_RE = re.compile(r"/monetarypolicy/fomcminutes\d{8}\.htm$")
FED_BASE_URL = "https://www.federalreserve.gov"
FOMC_CALENDAR_URL = f"{FED_BASE_URL}/monetarypolicy/fomccalendars.htm"
MINUTES_SECTION_HEADINGS = {
    "Developments in Financial Markets and Open Market Operations",
    "Staff Review of the Economic Situation",
    "Staff Review of the Financial Situation",
    "Staff Economic Outlook",
    "Participants' Views on Current Conditions and the Economic Outlook",
    "Committee Policy Actions",
    "Committee Policy Action",
}


def fetched_at_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def statement_url_from_event(event):
    for key in ("statement_url", "url"):
        url = str(event.get(key) or "").strip()
        if _is_statement_url(url):
            return _absolute_fed_url(url)
    return ""


def _absolute_fed_url(url):
    return urljoin(FED_BASE_URL, url)


def _is_statement_url(url):
    if not url:
        return False
    absolute_url = _absolute_fed_url(url)
    return bool(STATEMENT_PATH_RE.search(absolute_url))


def _is_minutes_url(url):
    if not url:
        return False
    absolute_url = _absolute_fed_url(url)
    return bool(MINUTES_PATH_RE.search(absolute_url))


def _statement_date(event):
    date_value = str(event.get("end_date") or event.get("start_date") or "").strip()
    return date_value.replace("-", "")


def _statement_url_from_calendar_html(event, html):
    statement_date = _statement_date(event)
    if not statement_date:
        return ""
    pattern = re.compile(
        rf'href=["\']([^"\']*/newsevents/pressreleases/monetary{statement_date}a\.htm)["\']',
        re.IGNORECASE,
    )
    match = pattern.search(html)
    return _absolute_fed_url(match.group(1)) if match else ""


def _minutes_url_from_calendar_html(event, html):
    minutes_date = _statement_date(event)
    if not minutes_date:
        return ""
    pattern = re.compile(
        rf'href=["\']([^"\']*/monetarypolicy/fomcminutes{minutes_date}\.htm)["\']',
        re.IGNORECASE,
    )
    match = pattern.search(html)
    return _absolute_fed_url(match.group(1)) if match else ""


def resolve_statement_url(event, fetch=None):
    fetch_document = fetch or fetch_text
    direct_url = statement_url_from_event(event)
    if direct_url:
        return direct_url
    event_url = str(event.get("url") or "").strip()
    if not event_url:
        raise ValueError(f"statement url is missing for {event['event_id']}")
    calendar_html = fetch_document(event_url)
    statement_url = _statement_url_from_calendar_html(event, calendar_html)
    if not statement_url:
        raise DocumentUnavailableError(
            f"statement url is missing for {event['event_id']}"
        )
    return statement_url


def resolve_minutes_url(event, fetch=None):
    fetch_document = fetch or fetch_text
    for key in ("minutes_url", "url"):
        url = str(event.get(key) or "").strip()
        if _is_minutes_url(url):
            return _absolute_fed_url(url)
    event_url = str(event.get("url") or "").strip()
    if not event_url:
        raise ValueError(f"minutes url is missing for {event['event_id']}")
    calendar_html = fetch_document(event_url)
    minutes_url = _minutes_url_from_calendar_html(event, calendar_html)
    if not minutes_url:
        raise DocumentUnavailableError(
            f"minutes url is missing for {event['event_id']}"
        )
    return minutes_url


STATEMENT_BODY_STOP_PATTERNS = (
    "Implementation Note",
    "For media inquiries",
    "Last Update:",
    "Back to Top",
)


def extract_statement_body_from_html(html):
    text = extract_text_from_html(html)
    lines = text.splitlines()
    start_index = -1
    for index, line in enumerate(lines):
        if "Federal Reserve issues FOMC statement" in line:
            start_index = index
    if start_index < 0:
        return text
    body_lines = []
    for line in lines[start_index:]:
        if body_lines and any(
            pattern in line for pattern in STATEMENT_BODY_STOP_PATTERNS
        ):
            break
        body_lines.append(line)
    return "\n".join(body_lines).strip()


def extract_text_from_html(html):
    with_blocks = BLOCK_RE.sub("\n", html)
    text = TAG_RE.sub("", with_blocks)
    lines = [unescape(line).strip() for line in text.splitlines()]
    return "\n".join([line for line in lines if line])


def extract_minutes_body_from_html(html):
    text = extract_text_from_html(html)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    start_index = 0
    for index, line in enumerate(lines):
        if "Minutes of the Federal Open Market Committee" in line:
            start_index = index
    stop_phrases = {
        "Back to Top",
        "Last Update:",
        "Federal Reserve Board",
        "For media inquiries",
        "_______________________",
    }
    body_lines = []
    section_seen = False
    skip_attendance = False
    for line in lines[start_index:]:
        if line in MINUTES_SECTION_HEADINGS:
            section_seen = True
            skip_attendance = False
        if line == "Attendance":
            if section_seen:
                break
            skip_attendance = True
            continue
        if skip_attendance:
            continue
        if any(line.startswith(phrase) for phrase in stop_phrases):
            break
        body_lines.append(line)
    return "\n".join(body_lines).strip()


def validate_statement_text(event, text):
    if not text:
        raise ValueError(f"statement text is empty for {event['event_id']}")
    if "Federal Reserve issues FOMC statement" not in text:
        raise ValueError(f"statement text is invalid for {event['event_id']}")


def validate_minutes_text(event, text):
    if not text:
        raise ValueError(f"minutes text is empty for {event['event_id']}")
    if "Minutes of the Federal Open Market Committee" not in text:
        raise ValueError(f"minutes text is invalid for {event['event_id']}")


def fetch_text(url):
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
    )
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def document_row(event, document_type, url, text, fetched_at):
    return {
        "event_id": event["event_id"],
        "document_type": document_type,
        "url": url,
        "text": text,
        "source_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "fetched_at": fetched_at,
    }


def fetch_statement_document(event, fetch=fetch_text, now=fetched_at_now):
    url = resolve_statement_url(event, fetch=fetch)
    html = fetch(url)
    text = extract_statement_body_from_html(html)
    validate_statement_text(event, text)
    return document_row(event, "statement", url, text, now())


def fetch_minutes_document(event, fetch=fetch_text, now=fetched_at_now):
    url = resolve_minutes_url(event, fetch=fetch)
    html = fetch(url)
    text = extract_minutes_body_from_html(html)
    validate_minutes_text(event, text)
    return document_row(event, "minutes", url, text, now())


def fetch_document_type(con, document_type, fetch=fetch_text, now=fetched_at_now):
    fetch_document = {
        "statement": fetch_statement_document,
        "minutes": fetch_minutes_document,
    }[document_type]
    result = {
        "document_type": document_type,
        "fetched": 0,
        "unavailable": 0,
        "failed": 0,
    }
    for event in us_rates_liquidity.load_macro_events(con, "fomc_meeting"):
        try:
            row = fetch_document(event, fetch=fetch, now=now)
            us_rates_liquidity.replace_macro_event_document(con, row)
            result["fetched"] += 1
        except DocumentUnavailableError as exc:
            result["unavailable"] += 1
            print(f"  SKIP {event['event_id']} {document_type}: {exc}")
            continue
        except Exception as exc:
            result["failed"] += 1
            print(f"  FAIL {event['event_id']} {document_type}: {exc}", file=sys.stderr)
            continue
        print(f"  OK   {event['event_id']} {document_type}: {len(row['text'])} chars")
    return result


def import_statement_documents(con, fetch=fetch_text, skip_empty=True):
    result = fetch_document_type(con, "statement", fetch=fetch)
    return {"statement_documents": result["fetched"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fetch FOMC documents")
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument(
        "--document-type",
        choices=["statement", "minutes", "all"],
        default="statement",
    )
    args = parser.parse_args(argv)

    document_types = (
        ["statement", "minutes"]
        if args.document_type == "all"
        else [args.document_type]
    )

    con = us_rates_liquidity.connect(args.db_path)
    try:
        results = []
        for doc_type in document_types:
            result = fetch_document_type(con, doc_type)
            print(f"  {result}")
            results.append(result)
    finally:
        con.close()

    return 1 if any(r["failed"] > 0 for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
