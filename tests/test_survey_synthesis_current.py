from app.services import survey_synthesis_current


def test_load_survey_synthesis_inputs_returns_shared_results(monkeypatch):
    monkeypatch.setattr(
        "app.api._load_latest_ism_industry_breadth", lambda con: None
    )
    monkeypatch.setattr(
        survey_synthesis_current.growth_cycle,
        "load_recent_ism_report_snapshots",
        lambda con, limit=6: [],
    )
    monkeypatch.setattr(
        survey_synthesis_current.ism_services_dashboard,
        "load_overview",
        lambda con: {"signal": {"state": "pending_inputs"}},
    )

    inputs = survey_synthesis_current.load_survey_synthesis_inputs(None)

    assert inputs["ism_reports"] == []
    assert inputs["ism_macro_signal_result"] is None
    result = inputs["survey_synthesis_result"]
    assert result["status"] == "partial"
    assert result["expected_gdp_direction"] is None
    assert result["period"] is None


def test_load_survey_synthesis_inputs_builds_macro_signal(monkeypatch):
    reports = [{"report_id": "r1"}, {"report_id": "r2"}]
    glance_calls = []
    monkeypatch.setattr(
        "app.api._load_latest_ism_industry_breadth", lambda con: {"breadth": 1}
    )
    monkeypatch.setattr(
        survey_synthesis_current.growth_cycle,
        "load_recent_ism_report_snapshots",
        lambda con, limit=6: reports,
    )
    monkeypatch.setattr(
        survey_synthesis_current.growth_cycle,
        "load_ism_at_a_glance_rows_for_reports",
        lambda con, report_ids: glance_calls.append(list(report_ids)) or [],
    )
    monkeypatch.setattr(
        survey_synthesis_current.ism_macro_signal,
        "build_ism_macro_signal",
        lambda reports_arg, glance_arg, industry_breadth=None: None,
    )
    monkeypatch.setattr(
        survey_synthesis_current.ism_services_dashboard,
        "load_overview",
        lambda con: {"signal": {"state": "pending_inputs"}},
    )

    inputs = survey_synthesis_current.load_survey_synthesis_inputs(None)

    assert glance_calls == [["r1", "r2"]]
    assert inputs["ism_reports"] == reports
    assert inputs["survey_synthesis_result"]["status"] == "partial"


def test_load_survey_synthesis_inputs_tolerates_invalid_macro_signal(monkeypatch):
    monkeypatch.setattr(
        "app.api._load_latest_ism_industry_breadth", lambda con: None
    )
    monkeypatch.setattr(
        survey_synthesis_current.growth_cycle,
        "load_recent_ism_report_snapshots",
        lambda con, limit=6: [{"report_id": "r1"}],
    )
    monkeypatch.setattr(
        survey_synthesis_current.growth_cycle,
        "load_ism_at_a_glance_rows_for_reports",
        lambda con, report_ids: [],
    )

    def raise_invalid(reports, glance, industry_breadth=None):
        raise ValueError("invalid report data")

    monkeypatch.setattr(
        survey_synthesis_current.ism_macro_signal,
        "build_ism_macro_signal",
        raise_invalid,
    )
    monkeypatch.setattr(
        survey_synthesis_current.ism_services_dashboard,
        "load_overview",
        lambda con: {"signal": {"state": "pending_inputs"}},
    )

    inputs = survey_synthesis_current.load_survey_synthesis_inputs(None)

    assert inputs["ism_macro_signal_result"] is None
    assert inputs["survey_synthesis_result"]["expected_gdp_direction"] is None
