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


TAG_RE = re.compile(r"<[^>]+>")
BLOCK_RE = re.compile(r"</(?:p|div|h1|h2|h3|li)>", re.IGNORECASE)
STATEMENT_PATH_RE = re.compile(r"/newsevents/pressreleases/monetary\d{8}a\.htm$")
FED_BASE_URL = "https://www.federalreserve.gov"
FOMC_CALENDAR_URL = f"{FED_BASE_URL}/monetarypolicy/fomccalendars.htm"


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
        raise ValueError(f"statement url is missing for {event['event_id']}")
    return statement_url


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
        "Last Update:",
        "Federal Reserve Board",
        "For media inquiries",
    }
    body_lines = []
    for line in lines[start_index:]:
        if any(line.startswith(phrase) for phrase in stop_phrases):
            break
        body_lines.append(line)
    return "\n".join(body_lines).strip()


def validate_statement_text(event, text):
    if not text:
        raise ValueError(f"statement text is empty for {event['event_id']}")
    if "Federal Reserve issues FOMC statement" not in text:
        raise ValueError(f"statement text is invalid for {event['event_id']}")


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
    url = event.get("minutes_url") or event.get("url")
    if not url:
        raise ValueError(f"fomc event {event['event_id']} has no minutes url")
    html = fetch(url)
    text = extract_minutes_body_from_html(html)
    return document_row(event, "minutes", url, text, now())


def import_statement_documents(con, fetch=fetch_text, skip_empty=True):
    events = us_rates_liquidity.load_macro_events(con, "fomc_meeting")
    count = 0
    errors = 0
    for event in events:
        if not str(event.get("statement_url") or event.get("url") or "").strip():
            print(f"  SKIP {event['event_id']}: no url")
            continue
        try:
            row = fetch_statement_document(event, fetch=fetch)
        except ValueError as exc:
            print(f"  SKIP {event['event_id']}: {exc}")
            errors += 1
            continue
        except Exception as exc:
            print(f"  SKIP {event['event_id']}: {exc}")
            errors += 1
            continue
        us_rates_liquidity.replace_macro_event_document(con, row)
        print(f"  OK   {event['event_id']}: {len(row['text'])} chars")
        count += 1
    print(f"  Result: {count} fetched, {errors} skipped")
    return {"statement_documents": count}


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
    con = us_rates_liquidity.connect(args.db_path)
    try:
        events = us_rates_liquidity.load_macro_events(con, "fomc_meeting")
        for event in events:
            if args.document_type in {"statement", "all"}:
                try:
                    row = fetch_statement_document(event)
                    us_rates_liquidity.replace_macro_event_document(con, row)
                    print(
                        f"  OK   {event['event_id']} statement: {len(row['text'])} chars"
                    )
                except ValueError as exc:
                    print(f"  SKIP {event['event_id']} statement: {exc}")
            if args.document_type in {"minutes", "all"}:
                if not (event.get("minutes_url") or event.get("url")):
                    print(f"  SKIP {event['event_id']} minutes: no url")
                    continue
                try:
                    row = fetch_minutes_document(event)
                    us_rates_liquidity.replace_macro_event_document(con, row)
                    print(
                        f"  OK   {event['event_id']} minutes: {len(row['text'])} chars"
                    )
                except ValueError as exc:
                    print(f"  SKIP {event['event_id']} minutes: {exc}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
