from app.db import growth_cycle
from app.services import ism_services_dashboard
from app.runtime_logging import get_runtime_logger
from app.tools import ism_macro_signal, ism_survey_synthesis

LOGGER = get_runtime_logger(__name__)


def load_survey_synthesis_inputs(con):
    from app import api

    ism_industry_breadth = api._load_latest_ism_industry_breadth(con)
    ism_reports = growth_cycle.load_recent_ism_report_snapshots(con, limit=6)
    ism_macro_signal_result = None
    if ism_reports:
        report_ids = [row["report_id"] for row in ism_reports]
        report_at_a_glance = growth_cycle.load_ism_at_a_glance_rows_for_reports(
            con, report_ids
        )
        try:
            ism_macro_signal_result = ism_macro_signal.build_ism_macro_signal(
                ism_reports,
                report_at_a_glance,
                industry_breadth=ism_industry_breadth,
            )
        except ValueError:
            LOGGER.warning("ism macro signal build failed", exc_info=True)
    ism_services_data = ism_services_dashboard.load_overview(con)
    return {
        "ism_reports": ism_reports,
        "ism_macro_signal_result": ism_macro_signal_result,
        "survey_synthesis_result": ism_survey_synthesis.build_survey_synthesis(
            ism_macro_signal_result,
            ism_services_data["signal"],
        ),
    }
