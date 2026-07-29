from app.db import us_rates_liquidity
from scripts import fetch_fomc_documents

CALENDAR_EVENT = {
    "event_id": "fomc_2026_03_17",
    "event_type": "fomc_meeting",
    "start_date": "2026-03-17",
    "end_date": "2026-03-18",
    "display_month": "2026-03-01",
    "title": "FOMC Meeting",
    "source": "Federal Reserve",
    "policy_tone": "unknown",
    "has_sep": 1,
    "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
}

STATEMENT_EVENT = {
    "event_id": "fomc_2026_07_28",
    "event_type": "fomc_meeting",
    "start_date": "2026-07-28",
    "end_date": "2026-07-29",
    "display_month": "2026-07-01",
    "title": "FOMC Meeting",
    "source": "Federal Reserve",
    "policy_tone": "unknown",
    "has_sep": 1,
    "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm",
}


def test_statement_url_from_event_uses_event_url_when_it_is_statement_url():
    event = {
        "event_id": "fomc_2026_07_28",
        "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm",
    }

    assert fetch_fomc_documents.statement_url_from_event(event) == event["url"]


def test_statement_url_from_event_ignores_calendar_url():
    event = {
        "event_id": "fomc_2026_07_28",
        "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    }

    assert fetch_fomc_documents.statement_url_from_event(event) == ""


def test_statement_url_from_event_uses_statement_url_when_present():
    event = {
        "event_id": "fomc_2026_07_28",
        "statement_url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm",
        "url": "https://example.test/generic",
    }

    assert (
        fetch_fomc_documents.statement_url_from_event(event)
        == "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm"
    )


def test_resolve_statement_url_finds_html_link_from_calendar_page():
    event = {
        "event_id": "fomc_2026_03_17",
        "start_date": "2026-03-17",
        "end_date": "2026-03-18",
        "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    }
    html = """
    <strong>Statement:</strong><br>
    <a href="/monetarypolicy/files/monetary20260318a1.pdf">PDF</a> |
    <a href="/newsevents/pressreleases/monetary20260318a.htm">HTML</a><br>
    <a href="/newsevents/pressreleases/monetary20260318a1.htm">Implementation Note</a>
    """

    resolved = fetch_fomc_documents.resolve_statement_url(
        event,
        fetch=lambda url: html,
    )

    assert resolved == (
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260318a.htm"
    )


def test_resolve_statement_url_raises_when_calendar_has_no_statement_link():
    event = {
        "event_id": "fomc_2026_07_28",
        "start_date": "2026-07-28",
        "end_date": "2026-07-29",
        "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    }

    raised = False
    try:
        fetch_fomc_documents.resolve_statement_url(
            event,
            fetch=lambda url: "<html>Meeting calendars and information</html>",
        )
    except fetch_fomc_documents.DocumentUnavailableError as exc:
        assert "statement url is missing" in str(exc)
        raised = True
    assert raised


def test_extract_text_from_html_removes_tags():
    html = "<html><body><h1>Federal Reserve issues FOMC statement</h1><p>Recent indicators expanded.</p></body></html>"

    assert fetch_fomc_documents.extract_text_from_html(html) == (
        "Federal Reserve issues FOMC statement\nRecent indicators expanded."
    )


def test_document_row_hashes_text():
    row = fetch_fomc_documents.document_row(
        {"event_id": "fomc_2026_07_28"},
        "statement",
        "https://example.test/statement",
        "Statement text",
        "2026-07-30T00:00:00Z",
    )

    assert row["event_id"] == "fomc_2026_07_28"
    assert row["document_type"] == "statement"
    assert len(row["source_hash"]) == 64


def test_fetch_statement_document_raises_on_empty_url():
    event = {"event_id": "fomc_2026_07_28"}

    raised = False
    try:
        fetch_fomc_documents.fetch_statement_document(event)
    except ValueError as exc:
        assert "statement url is missing" in str(exc)
        raised = True
    assert raised


def test_fetch_statement_document_raises_on_empty_text():
    event = {
        "event_id": "fomc_2026_07_28",
        "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm",
    }

    raised = False
    try:
        fetch_fomc_documents.fetch_statement_document(
            event,
            fetch=lambda url: "<html></html>",
        )
    except ValueError as exc:
        assert "statement text is empty" in str(exc)
        raised = True
    assert raised


def test_fetch_statement_document_raises_when_text_is_not_statement():
    event = {
        "event_id": "fomc_2026_07_28",
        "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm",
    }

    raised = False
    try:
        fetch_fomc_documents.fetch_statement_document(
            event,
            fetch=lambda url: (
                "<html><title>Meeting calendars and information</title></html>"
            ),
        )
    except ValueError as exc:
        assert "statement text is invalid" in str(exc)
        raised = True
    assert raised


def test_extract_statement_body_targets_body_heading_not_page_title():
    html = """
    <html>
      <head><title>Federal Reserve issues FOMC statement</title></head>
      <body>
        <nav>Meeting calendars and information</nav>
        <div class="gov-banner">.gov banner content</div>
        <a href="#content">Skip to main content</a>
        <h1>Federal Reserve issues FOMC statement</h1>
        <p>Recent indicators suggest that economic activity has continued to expand.</p>
        <p>Voting for the monetary policy action were Jerome H. Powell and other members.</p>
        <footer>Last Update: June 17, 2026</footer>
      </body>
    </html>
    """

    body = fetch_fomc_documents.extract_statement_body_from_html(html)

    assert "Meeting calendars and information" not in body
    assert ".gov banner content" not in body
    assert "Skip to main content" not in body
    assert "Last Update" not in body
    assert body.startswith("Federal Reserve issues FOMC statement")
    assert "Recent indicators suggest" in body


def test_extract_statement_body_removes_navigation_and_implementation_note():
    html = """
    <html>
      <body>
        <nav>Meeting calendars and information</nav>
        <h1>Federal Reserve issues FOMC statement</h1>
        <p>Recent indicators suggest that economic activity has continued to expand.</p>
        <p>Inflation remains elevated relative to the Committee's 2 percent goal.</p>
        <p>Voting for the monetary policy action were Jerome H. Powell and other members.</p>
        <a href="/newsevents/pressreleases/monetary20260617a1.htm">Implementation Note</a>
        <footer>Last Update: June 17, 2026</footer>
      </body>
    </html>
    """

    body = fetch_fomc_documents.extract_statement_body_from_html(html)

    assert "Meeting calendars and information" not in body
    assert "Implementation Note" not in body
    assert "Last Update" not in body
    assert body.startswith("Federal Reserve issues FOMC statement")
    assert "Recent indicators suggest" in body
    assert "Voting for the monetary policy action" in body


def test_fetch_statement_document_stores_statement_body_only():
    event = {
        "event_id": "fomc_2026_06_16",
        "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm",
    }
    html = """
    <html>
      <body>
        <div>Skip to main content</div>
        <h1>Federal Reserve issues FOMC statement</h1>
        <p>Recent indicators suggest that economic activity has continued to expand.</p>
        <p>Inflation remains elevated relative to the Committee's 2 percent goal.</p>
        <p>Voting for the monetary policy action were Jerome H. Powell and other members.</p>
        <div>Back to Top</div>
      </body>
    </html>
    """

    row = fetch_fomc_documents.fetch_statement_document(
        event,
        fetch=lambda url: html,
        now=lambda: "2026-06-17T00:00:00Z",
    )

    assert row["text"] == (
        "Federal Reserve issues FOMC statement\n"
        "Recent indicators suggest that economic activity has continued to expand.\n"
        "Inflation remains elevated relative to the Committee's 2 percent goal.\n"
        "Voting for the monetary policy action were Jerome H. Powell and other members."
    )


def test_extract_minutes_body_removes_navigation_and_footer():
    html = """
    <html>
      <head><title>Minutes of the Federal Open Market Committee</title></head>
      <body>
        <nav>Federal Reserve navigation</nav>
        <main>
          <h1>Minutes of the Federal Open Market Committee</h1>
          <p>June 16-17, 2026</p>
          <p>Participants agreed that inflation remained elevated.</p>
          <p>A few participants noted downside risks to employment.</p>
        </main>
        <footer>Last Update: July 8, 2026</footer>
      </body>
    </html>
    """

    body = fetch_fomc_documents.extract_minutes_body_from_html(html)

    assert "Minutes of the Federal Open Market Committee" in body
    assert "Participants agreed that inflation remained elevated." in body
    assert "A few participants noted downside risks to employment." in body
    assert "Federal Reserve navigation" not in body
    assert "Last Update" not in body


def test_extract_minutes_body_stops_before_attendance_and_end_matter():
    html = """
    <html>
      <body>
        <h1>Minutes of the Federal Open Market Committee</h1>
        <h2>Committee Policy Actions</h2>
        <p>Members agreed to maintain the target range.</p>
        <h2>Attendance</h2>
        <p>Kevin Warsh, Chairman</p>
        <p>_______________________</p>
        <p>Joshua Gallin</p>
        <p>1. The Federal Open Market Committee is referenced as the FOMC.</p>
        <p>Back to Top</p>
      </body>
    </html>
    """

    body = fetch_fomc_documents.extract_minutes_body_from_html(html)

    assert "Committee Policy Actions" in body
    assert "Members agreed to maintain the target range." in body
    assert "Attendance" not in body
    assert "Kevin Warsh" not in body
    assert "_______________________" not in body
    assert "Back to Top" not in body


def test_extract_minutes_body_skips_initial_attendance_block():
    html = """
    <html>
      <body>
        <h1>Minutes of the Federal Open Market Committee</h1>
        <p>January 30-31, 2024</p>
        <p>A joint meeting was held.</p>
        <h2>Attendance</h2>
        <p>Jerome H. Powell, Chair</p>
        <h2>Developments in Financial Markets and Open Market Operations</h2>
        <p>The manager reviewed market developments.</p>
        <h2>Committee Policy Actions</h2>
        <p>Members agreed to maintain the target range.</p>
      </body>
    </html>
    """

    body = fetch_fomc_documents.extract_minutes_body_from_html(html)

    assert "A joint meeting was held." in body
    assert "Jerome H. Powell" not in body
    assert "Developments in Financial Markets and Open Market Operations" in body
    assert "The manager reviewed market developments." in body
    assert "Committee Policy Actions" in body


def test_fetch_minutes_document_stores_minutes_body():
    event = {
        "event_id": "fomc_2026_06_16",
        "start_date": "2026-06-16",
        "end_date": "2026-06-17",
        "url": "https://www.federalreserve.gov/monetarypolicy/fomcminutes20260617.htm",
    }
    html = """
    <html><body>
      <h1>Minutes of the Federal Open Market Committee</h1>
      <p>Participants agreed that inflation remained elevated.</p>
    </body></html>
    """

    row = fetch_fomc_documents.fetch_minutes_document(
        event,
        fetch=lambda url: html,
        now=lambda: "2026-07-11T00:00:00Z",
    )

    assert row["event_id"] == "fomc_2026_06_16"
    assert row["document_type"] == "minutes"
    assert row["url"] == event["url"]
    assert "Participants agreed" in row["text"]
    assert row["source_hash"]
    assert row["fetched_at"] == "2026-07-11T00:00:00Z"


def test_resolve_minutes_url_finds_html_link_from_calendar_page():
    event = {
        "event_id": "fomc_2026_06_16",
        "start_date": "2026-06-16",
        "end_date": "2026-06-17",
        "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    }
    html = """
    <strong>Minutes:</strong>
    <a href="/monetarypolicy/fomcminutes20260617.htm">HTML</a>
    <strong>Statement:</strong>
    <a href="/newsevents/pressreleases/monetary20260617a.htm">HTML</a>
    """

    resolved = fetch_fomc_documents.resolve_minutes_url(
        event,
        fetch=lambda url: html,
    )

    assert resolved == (
        "https://www.federalreserve.gov/monetarypolicy/fomcminutes20260617.htm"
    )


def test_fetch_minutes_document_raises_when_calendar_has_no_minutes_link():
    event = {
        "event_id": "fomc_2026_06_16",
        "start_date": "2026-06-16",
        "end_date": "2026-06-17",
        "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    }

    raised = False
    try:
        fetch_fomc_documents.fetch_minutes_document(
            event,
            fetch=lambda url: "<html>Meeting calendars and information</html>",
        )
    except fetch_fomc_documents.DocumentUnavailableError as exc:
        assert "minutes url is missing" in str(exc)
        raised = True
    assert raised


def test_import_statement_documents_resolves_calendar_url(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_events(
            con,
            "fomc_meeting",
            [CALENDAR_EVENT],
        )

        def fake_fetch(url):
            if url.endswith("/monetarypolicy/fomccalendars.htm"):
                return """
                <strong>Statement:</strong>
                <a href="/newsevents/pressreleases/monetary20260318a.htm">HTML</a>
                """
            return """
            <html><title>Federal Reserve issues FOMC statement</title>
            <p>Recent indicators suggest economic activity expanded.</p></html>
            """

        imported = fetch_fomc_documents.import_statement_documents(
            con,
            fetch=fake_fetch,
        )
        documents = us_rates_liquidity.load_macro_event_documents(
            con,
            "fomc_2026_03_17",
        )
    finally:
        con.close()

    assert imported == {"statement_documents": 1}
    assert documents[0]["url"] == (
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260318a.htm"
    )


def test_fetch_document_type_records_missing_calendar_link_as_unavailable(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_events(con, "fomc_meeting", [CALENDAR_EVENT])
        result = fetch_fomc_documents.fetch_document_type(
            con,
            "statement",
            fetch=lambda url: "<html>Meeting calendars and information</html>",
        )
    finally:
        con.close()

    assert result == {
        "document_type": "statement",
        "fetched": 0,
        "unavailable": 1,
        "failed": 0,
    }


def test_fetch_document_type_records_failure_on_invalid_published_statement(
    tmp_path,
):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_events(con, "fomc_meeting", [STATEMENT_EVENT])
        result = fetch_fomc_documents.fetch_document_type(
            con,
            "statement",
            fetch=lambda url: "<html>not a statement</html>",
        )
        assert result == {
            "document_type": "statement",
            "fetched": 0,
            "unavailable": 0,
            "failed": 1,
        }
        assert (
            us_rates_liquidity.load_macro_event_documents(
                con, STATEMENT_EVENT["event_id"]
            )
            == []
        )
    finally:
        con.close()


NO_URL_EVENT = {
    "event_id": "fomc_2026_09_15",
    "event_type": "fomc_meeting",
    "start_date": "2026-09-15",
    "end_date": "2026-09-16",
    "display_month": "2026-09-01",
    "title": "FOMC Meeting",
    "source": "Federal Reserve",
    "policy_tone": "unknown",
    "has_sep": 1,
}


def test_fetch_document_type_records_missing_event_url_as_failure(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    try:
        us_rates_liquidity.replace_macro_events(con, "fomc_meeting", [NO_URL_EVENT])
        result = fetch_fomc_documents.fetch_document_type(
            con,
            "statement",
            fetch=lambda url: "<html>not reached</html>",
        )
        assert result == {
            "document_type": "statement",
            "fetched": 0,
            "unavailable": 0,
            "failed": 1,
        }
    finally:
        con.close()


def test_main_returns_1_on_fetch_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fetch_fomc_documents,
        "fetch_document_type",
        lambda *args, **kwargs: {"failed": 1},
    )
    result = fetch_fomc_documents.main(
        [
            "--document-type",
            "statement",
            "--db-path",
            str(tmp_path / "market.sqlite"),
        ]
    )
    assert result == 1
