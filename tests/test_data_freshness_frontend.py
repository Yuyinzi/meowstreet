from pathlib import Path
from re import search
from subprocess import run

from fastapi.testclient import TestClient

from app.api import app


ROOT = Path(__file__).resolve().parents[1]


def test_english_page_assets_and_navigation_are_available():
    client = TestClient(app)
    response = client.get("/data-freshness.html")
    assert response.status_code == 200
    assert '<html lang="en">' in response.text
    assert '<h1>Data Freshness</h1>' in response.text
    assert not search(r"[\u4e00-\u9fff]", response.text)
    assert 'class="subtitle"' not in response.text
    assert '/static/notifications.js' in response.text
    for asset in ("data-freshness.js", "data-freshness.css"):
        assert client.get(f"/static/{asset}").status_code == 200
    for name in ("macro-dashboard", "ticker-context", "portfolio", "quant-screen", "ticker-workflow", "notifications"):
        assert 'href="/data-freshness.html"' in (ROOT / "static" / f"{name}.html").read_text()


def test_freshness_ui_filters_details_focus_safe_text_and_recovery():
    result = run(["node", "tests/data_freshness_dom_harness.mjs"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
