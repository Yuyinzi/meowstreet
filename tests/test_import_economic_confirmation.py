import httpx

from app.services.macro_refresh_resources import ArtifactStore
from scripts import import_economic_confirmation

OVERVIEW_URL = "https://www.bls.gov/news.release/empsit.htm"
HOUSEHOLD_URL = "https://www.bls.gov/news.release/empsit.a.htm"
ESTABLISHMENT_URL = "https://www.bls.gov/news.release/empsit.b.htm"


def _overview_html():
    return b"""<pre>Transmission of material in this news release is embargoed until USDL-26-1125
8:30 a.m. (ET) Thursday, July 2, 2026
THE EMPLOYMENT SITUATION - JUNE 2026
The next Employment Situation for July 2026 is scheduled to be published on
Friday, August 7, 2026, at 8:30 a.m. (ET).</pre>"""


def _household_html():
    return b"""<table>
<tr><th>Category</th><th>June2025</th><th>Apr.2026</th><th>May2026</th><th>June2026</th><th>Change from: May2026-June2026</th></tr>
<tr><td>Employment status</td></tr>
<tr><td>Unemployment rate</td><td>4.1</td><td>4.3</td><td>4.3</td><td>4.2</td><td>-0.1</td></tr>
</table>"""


def _establishment_html():
    return b"""<table>
<tr><th>Category</th><th>June2025</th><th>Apr.2026</th><th>May2026(p)</th><th>June2026(p)</th></tr>
<tr><td>EMPLOYMENT BY SELECTED INDUSTRY(Over-the-month change, in thousands)</td></tr>
<tr><td>Total nonfarm</td><td>-20</td><td>148</td><td>129</td><td>57</td></tr>
<tr><td>Total private</td><td>-45</td><td>150</td><td>97</td><td>49</td></tr>
<tr><td>(3-month average change, in thousands)</td></tr>
<tr><td>Total nonfarm</td><td>34</td><td>69</td><td>164</td><td>111</td></tr>
<tr><td>Total private</td><td>25</td><td>68</td><td>150</td><td>99</td></tr>
<tr><td>HOURS AND EARNINGS ALL EMPLOYEES</td></tr>
<tr><td>Total private</td></tr>
<tr><td>Average weekly hours</td><td>34.2</td><td>34.3</td><td>34.3</td><td>34.3</td></tr>
<tr><td>Average hourly earnings</td><td>$36.36</td><td>$37.41</td><td>$37.51</td><td>$37.64</td></tr>
</table>"""


def _household_html_missing_unemployment():
    return _household_html().replace(
        b"<tr><td>Unemployment rate</td><td>4.1</td><td>4.3</td><td>4.3</td>"
        b"<td>4.2</td><td>-0.1</td></tr>",
        b"",
    )


def _bls_html_by_url():
    return {
        OVERVIEW_URL: _overview_html(),
        HOUSEHOLD_URL: _household_html(),
        ESTABLISHMENT_URL: _establishment_html(),
    }


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeHttpClient:
    def __init__(self, html_by_url):
        self._html_by_url = html_by_url

    def request(self, method, url, **kwargs):
        if url not in self._html_by_url:
            raise httpx.ConnectError(f"no fixture for {url}")
        return _FakeResponse(self._html_by_url[url])


def g17_observation():
    return {
        "series_id": "manufacturing_production",
        "reference_period": "2026-06-01",
        "vintage_id": "g17:manufacturing_production:2026-06-01:2026-08-03",
        "as_of_timestamp": "2026-08-03T00:00:00+00:00",
        "value_at_release": 100.0,
        "seasonal_adjustment": "seasonally_adjusted",
        "source_url": "https://www.federalreserve.gov/releases/g17/",
        "source_hash": "g17-source-hash",
    }


def initial_claim():
    return {
        "series_id": "initial_claims_sa",
        "reference_period": "2026-07-25",
        "vintage_id": "initial_claims_sa:2026-07-25:2026-08-03",
        "as_of_timestamp": "2026-08-03T00:00:00+00:00",
        "value_at_release": 230.0,
        "seasonal_adjustment": "seasonally_adjusted",
        "source_url": "https://oui.doleta.gov/unemploy/claims.asp",
        "source_hash": "initial-claims-source-hash",
    }


def continuing_claim():
    return {
        "series_id": "continuing_claims_sa",
        "reference_period": "2026-07-25",
        "vintage_id": "continuing_claims_sa:2026-07-25:2026-08-03",
        "as_of_timestamp": "2026-08-03T00:00:00+00:00",
        "value_at_release": 1860.0,
        "seasonal_adjustment": "seasonally_adjusted",
        "source_url": "https://oui.doleta.gov/unemploy/claims.asp",
        "source_hash": "continuing-claims-source-hash",
    }


def _patch_sources(monkeypatch, html_by_url, g17_observations=None):
    patch_other_import_sources(monkeypatch, html_by_url, g17_observations)
    monkeypatch.setattr(
        import_economic_confirmation.dol_ui_claims,
        "fetch_national_claims_history",
        lambda *args: [],
    )


def patch_other_import_sources(monkeypatch, html_by_url=None, g17_observations=None):
    if html_by_url is None:
        html_by_url = _bls_html_by_url()
    monkeypatch.setattr(
        import_economic_confirmation,
        "HttpClient",
        lambda: _FakeHttpClient(html_by_url),
    )
    monkeypatch.setattr(
        import_economic_confirmation.dol_ui_claims,
        "fetch_claims_release",
        lambda *args: [],
    )
    monkeypatch.setattr(
        import_economic_confirmation.federal_reserve_g17,
        "fetch_g17_release",
        lambda *args: {"observations": [g17_observation()], "csv": b"g17 csv"},
    )
    monkeypatch.setattr(
        import_economic_confirmation.federal_reserve_g17,
        "fetch_g17_release",
        lambda *args: {
            "observations": g17_observations
            if g17_observations is not None
            else [g17_observation()],
            "csv": b"g17 csv",
        },
    )


def stored_labor_rows(db_path):
    con = import_economic_confirmation.economic_confirmation.connect(db_path)
    try:
        rows = import_economic_confirmation.economic_confirmation.load_current_series(
            con,
            [
                "nonfarm_payrolls_change",
                "unemployment_rate",
                "average_weekly_hours",
                "average_hourly_earnings",
                "payrolls_3m_average_change",
            ],
        )
    finally:
        con.close()
    return {series_id for series_id, observations in rows.items() if observations}


def stored_event(db_path):
    con = import_economic_confirmation.economic_confirmation.connect(db_path)
    try:
        events = (
            import_economic_confirmation.economic_confirmation.load_scheduled_events(
                con
            )
        )
    finally:
        con.close()
    return next(
        event for event in events if event["event_id"] == "bls_employment_situation"
    )


def stored_series_ids(db_path):
    con = import_economic_confirmation.economic_confirmation.connect(db_path)
    try:
        rows = import_economic_confirmation.economic_confirmation.load_current_series(
            con, ["manufacturing_production", "nonfarm_payrolls_change"]
        )
    finally:
        con.close()
    return {series_id for series_id, observations in rows.items() if observations}


def test_main_imports_bls_html_observations_and_event(monkeypatch, tmp_path):
    _patch_sources(monkeypatch, _bls_html_by_url())

    db_path = tmp_path / "market.sqlite"
    exit_code = import_economic_confirmation.main(["--db-path", str(db_path)])

    assert exit_code == 0
    assert stored_labor_rows(db_path) == {
        "nonfarm_payrolls_change",
        "payrolls_3m_average_change",
        "unemployment_rate",
        "average_weekly_hours",
        "average_hourly_earnings",
    }
    assert stored_event(db_path)["event_id"] == "bls_employment_situation"


def test_main_continues_to_g17_when_bls_html_parse_fails(monkeypatch, tmp_path, capsys):
    html_by_url = _bls_html_by_url()
    html_by_url[HOUSEHOLD_URL] = _household_html_missing_unemployment()
    _patch_sources(monkeypatch, html_by_url)

    db_path = tmp_path / "market.sqlite"
    exit_code = import_economic_confirmation.main(["--db-path", str(db_path)])

    assert exit_code == 1
    assert stored_series_ids(db_path) == {"manufacturing_production"}
    assert "esr: failed -" in capsys.readouterr().err


def test_main_saves_raw_bls_html_to_cache_dir(monkeypatch, tmp_path):
    _patch_sources(monkeypatch, _bls_html_by_url())

    db_path = tmp_path / "market.sqlite"
    cache_dir = tmp_path / "cache"
    import_economic_confirmation.main(
        ["--db-path", str(db_path), "--cache-dir", str(cache_dir)]
    )

    assert (cache_dir / "bls_esr_overview.html").read_bytes() == _overview_html()
    assert (cache_dir / "bls_esr_household.html").read_bytes() == _household_html()
    assert (cache_dir / "bls_esr_establishment.html").read_bytes() == (
        _establishment_html()
    )


def test_main_imports_g17_when_claims_history_fails(monkeypatch, tmp_path, capsys):
    def failing_claims_history(*args):
        raise ValueError("claims chartbook is unavailable")

    replacements = []
    monkeypatch.setattr(
        import_economic_confirmation.dol_ui_claims,
        "fetch_national_claims_history",
        failing_claims_history,
    )
    monkeypatch.setattr(
        import_economic_confirmation.economic_confirmation,
        "replace_national_claims_history_batch",
        lambda con, rows: replacements.append(rows) or 2,
    )
    monkeypatch.setattr(
        import_economic_confirmation.dol_ui_claims,
        "fetch_claims_release",
        lambda *args: [],
    )
    monkeypatch.setattr(
        import_economic_confirmation,
        "_fetch_bytes",
        lambda *args: b"employment situation overview",
    )
    monkeypatch.setattr(
        import_economic_confirmation.bls_employment_situation,
        "parse_employment_situation_html",
        lambda *args: {"observations": [], "scheduled_events": []},
    )
    monkeypatch.setattr(
        import_economic_confirmation.federal_reserve_g17,
        "fetch_g17_release",
        lambda *args: {"observations": [g17_observation()], "csv": b"g17 csv"},
    )

    db_path = tmp_path / "market.sqlite"
    exit_code = import_economic_confirmation.main(["--db-path", str(db_path)])

    con = import_economic_confirmation.economic_confirmation.connect(db_path)
    try:
        rows = import_economic_confirmation.economic_confirmation.load_current_series(
            con, ["manufacturing_production"]
        )
    finally:
        con.close()

    assert exit_code == 1
    assert rows["manufacturing_production"][0]["value"] == 100.0
    assert replacements == []
    assert (
        "claims_history: failed - claims chartbook is unavailable"
        in capsys.readouterr().err
    )


def test_main_uses_one_national_claims_history_source(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        import_economic_confirmation.dol_ui_claims,
        "fetch_national_claims_history",
        lambda client, url: calls.append(url) or [initial_claim(), continuing_claim()],
    )
    patch_other_import_sources(monkeypatch)
    assert (
        import_economic_confirmation.main(
            ["--db-path", str(tmp_path / "market.sqlite")]
        )
        == 0
    )
    assert calls == [import_economic_confirmation.DOL_NATIONAL_CLAIMS_URL]


def test_main_replaces_legacy_claims_history_after_national_fetch(
    monkeypatch, tmp_path
):
    replacements = []
    monkeypatch.setattr(
        import_economic_confirmation.dol_ui_claims,
        "fetch_national_claims_history",
        lambda client, url: [initial_claim(), continuing_claim()],
    )
    monkeypatch.setattr(
        import_economic_confirmation.economic_confirmation,
        "replace_national_claims_history_batch",
        lambda con, rows: replacements.append(rows) or 2,
    )
    patch_other_import_sources(monkeypatch)

    assert (
        import_economic_confirmation.main(
            ["--db-path", str(tmp_path / "market.sqlite")]
        )
        == 0
    )
    assert replacements == [[initial_claim(), continuing_claim()]]


def test_staged_economic_sources_persist_independently(monkeypatch, tmp_path):
    artifacts = ArtifactStore()
    monkeypatch.setattr(
        import_economic_confirmation.dol_ui_claims,
        "fetch_national_claims_history",
        lambda *args: [initial_claim(), continuing_claim()],
    )
    monkeypatch.setattr(
        import_economic_confirmation.dol_ui_claims,
        "fetch_claims_release",
        lambda *args: [],
    )
    monkeypatch.setattr(
        import_economic_confirmation.federal_reserve_g17,
        "fetch_g17_release",
        lambda *args: {"observations": [g17_observation()], "csv": b"g17 csv"},
    )
    import_economic_confirmation.fetch_dol(
        artifacts, client=_FakeHttpClient({})
    )
    import_economic_confirmation.fetch_bls(
        artifacts,
        client=_FakeHttpClient(_bls_html_by_url()),
    )
    import_economic_confirmation.fetch_federal_reserve(
        artifacts,
        client=_FakeHttpClient({}),
    )

    db_path = tmp_path / "market.sqlite"
    assert import_economic_confirmation.persist_dol(db_path, artifacts)["status"] == "ok"
    assert import_economic_confirmation.persist_bls(db_path, artifacts)["status"] == "ok"
    assert (
        import_economic_confirmation.persist_federal_reserve(db_path, artifacts)["status"]
        == "ok"
    )
