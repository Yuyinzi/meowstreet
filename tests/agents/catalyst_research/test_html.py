import hashlib

from app.agents.catalyst_research.extraction.html import build_structural_snapshot


HTML = """
<!doctype html>
<html><head><title>Investor Events</title>
<style>.hidden { display: none }</style><script>alert('ignore')</script>
</head><body onload="steal()">
<!-- ignore this comment -->
<nav class="navigation"><a href="/home?utm_source=menu">Home</a></nav>
<div id="cookie-banner"><button onclick="acceptCookies()">Accept cookies</button></div>
<form action="/search"><input name="q"><button>Search</button></form>
<main id="events">
  <h1 aria-label="Events heading">Investor Events</h1>
  <article class="event-card" data-date="2026-01-02" onclick="track()">
    <h2 title="Event title">Fourth quarter update</h2>
    <time datetime="2026-01-02">January 2, 2026</time>
    <a class="event-link" href="https://example.com/events/q4?gclid=tracking" title="Details">Details</a>
  </article>
  <article class="event-card" data-date="2026-02-03">
    <h2>Investor day</h2><time datetime="2026-02-03">February 3, 2026</time>
    <a href="/events/day?utm_medium=email&id=2">Details</a>
  </article>
</main>
</body></html>
"""


def page(html=HTML):
    return {
        "requested_url": "https://example.com/events?utm_source=search",
        "final_url": "https://example.com/events?utm_medium=browser",
        "content_type": "text/html",
        "html": html,
        "response_bytes": len(html.encode()),
        "fetched_at": "2026-09-06T12:00:00+00:00",
        "truncated": False,
    }


def test_build_structural_snapshot_removes_unsafe_content_and_preserves_event_structure():
    snapshot = build_structural_snapshot(page())

    assert snapshot["requested_url"] == "https://example.com/events"
    assert snapshot["final_url"] == "https://example.com/events"
    assert "<script" not in snapshot["structural_html"].lower()
    assert "<style" not in snapshot["structural_html"].lower()
    assert "<form" not in snapshot["structural_html"].lower()
    assert "alert(" not in snapshot["structural_html"]
    assert "onclick" not in snapshot["structural_html"].lower()
    assert "steal()" not in snapshot["structural_html"]
    assert "Investor Events" in snapshot["normalized"]["text"]
    assert len(snapshot["normalized"]["headings"]) == 3
    assert len(snapshot["normalized"]["links"]) == 2
    assert snapshot["normalized"]["links"][0]["href"] == "https://example.com/events/q4"
    assert snapshot["normalized"]["links"][1]["href"] == "https://example.com/events/day?id=2"
    assert snapshot["normalized"]["links"][0]["title"] == "Details"
    assert "event-card" in snapshot["structural_html"]
    assert "data-date=\"2026-01-02\"" in snapshot["structural_html"]
    assert "datetime=\"2026-01-02\"" in snapshot["structural_html"]


def test_build_structural_snapshot_bounds_html_text_and_links_before_hashing():
    large = page("<main>" + "word " * 1000 + "</main>" + "<a href='https://example.com/one'>one</a>" * 20)

    snapshot = build_structural_snapshot(large, max_html_chars=120, max_text_chars=80, max_links=3)

    assert len(snapshot["structural_html"]) <= 120
    assert len(snapshot["normalized"]["text"]) <= 80
    assert len(snapshot["normalized"]["links"]) <= 3
    assert snapshot["content_hash"] == hashlib.sha256(snapshot["structural_html"].encode()).hexdigest()


def test_build_structural_snapshot_prunes_navigation_context_and_bounds_headings_without_raw_slicing():
    source = page("<main><nav>Menu</nav><h1>" + "heading " * 20 + "</h1><article><h2>Event</h2><p>Details</p></article><aside>Ads</aside><footer>Footer</footer></main>")

    snapshot = build_structural_snapshot(source, max_html_chars=80, max_text_chars=40)

    assert "<nav" not in snapshot["structural_html"]
    assert "<aside" not in snapshot["structural_html"]
    assert "<footer" not in snapshot["structural_html"]
    assert all(len(row["text"]) <= 40 for row in snapshot["normalized"]["headings"])
    assert snapshot["truncated"] is True
    assert snapshot["structural_html"].count("<") == snapshot["structural_html"].count(">")


def test_build_structural_snapshot_is_content_addressed_for_equivalent_normalized_content():
    first = page("<main>  <h1>Investor   Events</h1> <a href='/x?utm_source=a&id=1'> Link </a> </main>")
    second = page("<main><h1>Investor Events</h1><a href='https://example.com/x?id=1&utm_campaign=b'>Link</a></main>")

    first_snapshot = build_structural_snapshot(first)
    second_snapshot = build_structural_snapshot(second)

    assert first_snapshot["structural_html"] == second_snapshot["structural_html"]
    assert first_snapshot["normalized"] == second_snapshot["normalized"]
    assert first_snapshot["content_hash"] == second_snapshot["content_hash"]


def test_build_structural_snapshot_preserves_only_stable_attributes_and_plain_fields():
    snapshot = build_structural_snapshot(page('<article class="card" id="one" data-date="2026-01-02" aria-label="A" title="T" style="color:red" data-track="x" onmouseover="bad()">Text</article>'))

    assert set(snapshot["normalized"]) >= {"title", "text", "headings", "links"}
    assert snapshot["structural_html"] == '<article aria-label="A" class="card" data-date="2026-01-02" id="one" title="T">Text</article>'
    assert isinstance(snapshot["content_hash"], str)
    assert set(snapshot) >= {"requested_url", "final_url", "structural_html", "normalized", "content_hash", "snapshot_schema_version"}


def test_build_structural_snapshot_applies_link_limit_after_invalid_links_are_filtered():
    html = "<main><a href='mailto:test@example.com'>bad</a><a href='javascript:alert(1)'>bad</a><a href='/first'>first</a><a href='/second'>second</a></main>"

    snapshot = build_structural_snapshot(page(html), max_links=2)

    assert [row["href"] for row in snapshot["normalized"]["links"]] == [
        "https://example.com/first",
        "https://example.com/second",
    ]
