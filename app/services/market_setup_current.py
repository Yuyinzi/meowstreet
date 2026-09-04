import hashlib
from datetime import date

from app.db import benchmark_market_data
from app.db import gdp_market_relationships
from app.db import growth_cycle
from app.db import macro_indicators as macro_indicators_db
from app.db import market_assistant as market_assistant_db
from app.db import us_rates_liquidity as us_rates_liquidity_db
from app.services import consumer_sentiment_dashboard
from app.services import economic_confirmation as economic_confirmation_dashboard
from app.services import survey_synthesis_current
from app.runtime_logging import get_runtime_logger
from app.tools import (
    housing_permits,
    ism_macro_signal,
    macro_growth_cycle,
    market_phase,
    market_setup,
    market_setup_evidence_facts,
    market_setup_evidence_layers,
    market_setup_explanation_snapshot,
    market_setup_v2,
    market_setup_v2_relationships,
    nfib_sbo,
    cyclical_commodities as tool,
)
from app.tools import us_rates_liquidity as us_rates_liquidity_tool

DEFAULT_DB_PATH = market_assistant_db.DEFAULT_DB_PATH
LOGGER = get_runtime_logger(__name__)

_RATES_LIQUIDITY_SCHEMA_DDL = """
create table if not exists us_rate_series (
    series_id text primary key,
    title text not null,
    instrument_type text not null,
    maturity_months integer,
    units text not null,
    source_workbook text not null,
    source_sheet text not null
);
create table if not exists us_rate_points (
    series_id text not null,
    date text not null,
    value real not null,
    source_workbook text not null,
    source_sheet text not null,
    primary key(series_id, date),
    foreign key(series_id) references us_rate_series(series_id)
);
create index if not exists idx_us_rate_points_series_date
on us_rate_points(series_id, date);
create table if not exists macro_ai_interpretations (
    scope text not null,
    snapshot_hash text not null,
    as_of text,
    prompt_version text not null,
    model text not null,
    tone text not null,
    status text not null,
    text_en text not null,
    text_zh text not null,
    metrics_json text not null,
    generated_at text not null,
    primary key(scope, snapshot_hash)
);
create index if not exists idx_macro_ai_interpretations_scope_generated
on macro_ai_interpretations(scope, generated_at);
create table if not exists macro_events (
    event_id text primary key,
    event_type text not null,
    start_date text not null,
    end_date text,
    display_month text not null,
    title text not null,
    source text not null,
    policy_tone text not null default 'unknown',
    has_sep integer not null default 0,
    url text
);
create index if not exists idx_macro_events_type_start
on macro_events(event_type, start_date);
create index if not exists idx_macro_events_type_month
on macro_events(event_type, display_month);
create table if not exists macro_event_documents (
    event_id text not null,
    document_type text not null,
    url text not null,
    text text not null,
    source_hash text not null,
    fetched_at text not null,
    primary key(event_id, document_type),
    foreign key(event_id) references macro_events(event_id)
);
create index if not exists idx_macro_event_documents_type_hash
on macro_event_documents(document_type, source_hash);
create table if not exists macro_event_tone_extractions (
    event_id text not null,
    source_document_type text not null,
    source_hash text not null,
    previous_event_id text,
    policy_action text not null default 'unknown',
    guidance_bias text not null default 'unknown',
    language_tone text not null default 'unknown',
    overall_bias text not null default 'unknown',
    statement_tone text not null,
    minutes_tone text not null,
    marker_tone text not null,
    tone_score integer not null,
    tone_change text not null,
    confidence text not null,
    extraction_status text not null,
    review_rounds integer not null,
    extractor_model text not null,
    reviewer_model text not null,
    facts_json text not null,
    comparison_json text not null,
    reviewer_feedback_json text not null,
    final_reviewer_feedback_json text not null default '[]',
    reason text not null,
    generated_at text not null,
    primary key(event_id, source_document_type, source_hash),
    foreign key(event_id) references macro_events(event_id)
);
create index if not exists idx_macro_event_tone_event_type_generated
on macro_event_tone_extractions(event_id, source_document_type, generated_at);
"""

_BENCHMARK_SCHEMA_DDL = """
create table if not exists benchmark_prices (
    benchmark_id text not null,
    date text not null,
    open real,
    high real,
    low real,
    close real not null,
    source text not null,
    source_updated_at text not null default current_timestamp,
    primary key(benchmark_id, date)
);
create index if not exists idx_benchmark_prices_benchmark_date
on benchmark_prices(benchmark_id, date);
"""

_GDP_SCHEMA_DDL = """
create table if not exists gdp_relationships (
    relationship_id text primary key,
    title text not null,
    region text,
    economy text,
    index_name text,
    primary_lag_months integer,
    correlation_window_years integer,
    source_workbook text,
    source_sheet text
);
create table if not exists gdp_lag_rows (
    relationship_id text not null,
    date text not null,
    lag_months integer not null,
    index_yoy real,
    gdp_yoy real,
    rolling_correlation real,
    source_workbook text,
    source_sheet text,
    primary key(relationship_id, date, lag_months),
    foreign key(relationship_id) references gdp_relationships(relationship_id)
);
create index if not exists idx_gdp_lag_rows_relationship_date
on gdp_lag_rows(relationship_id, date, lag_months);
create table if not exists gdp_quad_rows (
    relationship_id text not null,
    date text not null,
    period_label text,
    primary_lag_months integer,
    index_level real,
    gdp_level real,
    index_direction integer,
    gdp_direction integer,
    quad_case text,
    source_workbook text,
    source_sheet text,
    primary key(relationship_id, date),
    foreign key(relationship_id) references gdp_relationships(relationship_id)
);
create index if not exists idx_gdp_quad_rows_relationship_date
on gdp_quad_rows(relationship_id, date);
create table if not exists gdp_raw_source_rows (
    relationship_id text not null,
    date text not null,
    gdp_level real,
    index_level real,
    gdp_source text,
    index_source text,
    primary key(relationship_id, date)
);
create index if not exists idx_gdp_raw_source_rows_relationship_date
on gdp_raw_source_rows(relationship_id, date);
"""

_EC_SCHEMA_DDL = """
create table if not exists economic_confirmation_vintages (
    series_id text not null,
    reference_period text not null,
    vintage_id text not null,
    release_date text,
    as_of_timestamp text not null,
    value_at_release real not null,
    latest_revised_value real,
    revision_number integer not null default 0,
    seasonal_adjustment text not null,
    source_url text not null,
    source_hash text not null,
    primary key(series_id, reference_period, vintage_id)
);
create index if not exists idx_ec_vintages_series_period
on economic_confirmation_vintages(series_id, reference_period);
create table if not exists economic_confirmation_current_observations (
    series_id text not null,
    reference_period text not null,
    vintage_id text not null,
    value real not null,
    value_at_release real not null,
    latest_revised_value real,
    revision_number integer not null,
    seasonal_adjustment text not null,
    release_date text,
    as_of_timestamp text not null,
    source_url text not null,
    source_hash text not null,
    primary key(series_id, reference_period)
);
create table if not exists economic_confirmation_source_contracts (
    series_id text primary key,
    contract_json text not null
);
create table if not exists economic_confirmation_scheduled_events (
    event_id text primary key,
    scheduled_at text not null,
    status text not null,
    timezone text,
    source_url text,
    retrieved_at text
);
"""


def read_current_setup_state(db_path, *, as_of_date):
    con = market_assistant_db.connect(db_path)
    try:
        con.execute("begin")
        return build_current_setup_state(con, as_of_date=as_of_date)
    finally:
        con.rollback()
        con.close()


def build_current_setup_state(con, *, as_of_date):
    _record_read_connection(con)
    return _build_current_state(con, as_of_date)[0]


def _record_read_connection(con):
    pass


def resolve_current_explanation(db_path, *, previous_context_id, resolved_at):
    as_of_date = date.today().isoformat()
    read_con = market_assistant_db.connect(db_path)
    try:
        read_con.execute("begin")
        setup_result, inputs, evidence_layers = _build_current_state(
            read_con, as_of_date
        )
    finally:
        read_con.rollback()
        read_con.close()
    surface = market_setup_evidence_facts.load_explanation_surface()
    evidence = market_setup_evidence_facts.build_evidence_facts(
        setup_result=setup_result,
        inputs=inputs,
        evidence_layers=evidence_layers,
        surface=surface,
    )
    method_contracts = market_setup_v2.build_explanation_method_contracts()
    input_registry_version = market_setup_v2.load_input_registry()["version"]
    snapshot_state = market_setup_explanation_snapshot.build_snapshot_state(
        setup_result=setup_result,
        evidence=evidence,
        method_contracts=method_contracts,
        as_of=as_of_date,
        evidence_through=setup_result.get("evidence_through"),
        input_registry_version=input_registry_version,
        explanation_surface_version=surface["version"],
    )
    explanation_fingerprint = (
        market_setup_explanation_snapshot.compute_explanation_fingerprint(
            snapshot_state
        )
    )
    context_id = _context_id_for(explanation_fingerprint, resolved_at)
    write_con = market_assistant_db.connect(db_path)
    try:
        snapshot = market_assistant_db.get_or_create_snapshot(
            write_con, snapshot_state, context_id=context_id, created_at=resolved_at
        )
        previous = None
        if previous_context_id:
            previous = market_assistant_db.load_snapshot(write_con, previous_context_id)
        delta = market_setup_explanation_snapshot.build_semantic_delta(
            previous, snapshot
        )
    finally:
        write_con.close()
    return {
        "resolution": {
            "mode": "current",
            "resolved_at": resolved_at,
            "previous_context_id": previous_context_id,
            "current_context_id": snapshot["context_id"],
            "context_changed": previous_context_id != snapshot["context_id"],
            "evidence_through": snapshot.get("evidence_through"),
        },
        "delta": delta,
        "snapshot": snapshot,
    }


def _context_id_for(explanation_fingerprint, created_at):
    digest = hashlib.sha1(f"{explanation_fingerprint}{created_at}".encode()).hexdigest()
    return f"ctx_{digest[:12]}"


_REQUIRED_SCHEMA_TABLES = frozenset(
    {
        "benchmark_prices",
        "economic_confirmation_current_observations",
        "economic_confirmation_scheduled_events",
        "economic_confirmation_source_contracts",
        "economic_confirmation_vintages",
        "gdp_lag_rows",
        "gdp_quad_rows",
        "gdp_raw_source_rows",
        "gdp_relationships",
        "ism_ai_extractions",
        "ism_ai_section_extractions",
        "ism_ai_summary_runs",
        "ism_at_a_glance_rows",
        "ism_industry_comments",
        "ism_industry_rankings",
        "ism_report_ai_summaries",
        "ism_report_comments",
        "ism_report_commodities",
        "ism_report_industry_signal_coverage",
        "ism_report_industry_signals",
        "ism_report_narrative_facts",
        "ism_report_snapshots",
        "ism_report_source_snapshots",
        "macro_ai_interpretations",
        "macro_event_documents",
        "macro_event_tone_extractions",
        "macro_events",
        "macro_indicator_observation_metadata",
        "macro_indicator_points",
        "macro_indicator_regional_observation_metadata",
        "macro_indicator_regional_observations",
        "macro_indicator_regional_series",
        "macro_indicator_series",
        "macro_indicator_series_contracts",
        "cot_observations",
        "lumber_overlap_audits",
        "non_oil_attribution_facts",
        "non_oil_attribution_refresh_status",
        "shfe_cu_contract_daily",
        "shfe_cu_main_daily",
        "vendor_series_overlap_audits",
        "us_rate_points",
        "us_rate_series",
    }
)


def _schema_tables_present(con):
    placeholders = ", ".join("?" for _ in _REQUIRED_SCHEMA_TABLES)
    rows = con.execute(
        f"select count(*) as total from sqlite_master "
        f"where type = 'table' and name in ({placeholders})",
        tuple(_REQUIRED_SCHEMA_TABLES),
    ).fetchone()
    return rows["total"] == len(_REQUIRED_SCHEMA_TABLES)


def _init_schema(con):
    if _schema_tables_present(con):
        return
    macro_indicators_db.init_macro_tables(con)
    growth_cycle.init_db(con)
    con.executescript(_RATES_LIQUIDITY_SCHEMA_DDL)
    con.executescript(_BENCHMARK_SCHEMA_DDL)
    con.executescript(_GDP_SCHEMA_DDL)
    con.executescript(_EC_SCHEMA_DDL)


def _build_current_state(con, as_of_date):
    from app import api

    _init_schema(con)
    rows = macro_indicators_db.load_macro_indicator_points(con, "m2_money_stock")
    core_pce_rows = macro_indicators_db.load_macro_indicator_points(
        con, "core_pce_price_index"
    )
    fed_total_assets_rows = macro_indicators_db.load_macro_indicator_points(
        con, "fed_total_assets"
    )
    fed_treasury_rows = macro_indicators_db.load_macro_indicator_points(
        con, "fed_treasury_holdings"
    )
    fed_mbs_rows = macro_indicators_db.load_macro_indicator_points(
        con, "fed_mbs_holdings"
    )
    m2_money_stock = (
        {"series": [{"date": row["date"], "value": row["value"]} for row in rows]}
        if rows
        else None
    )
    core_pce_price_index = {
        "series": [
            {"date": row["date"], "value": row["value"]} for row in core_pce_rows
        ]
    }
    fed_total_assets = {
        "series": [
            {"date": row["date"], "value": row["value"]}
            for row in fed_total_assets_rows
        ]
    }
    fed_treasury_holdings = {
        "series": [
            {"date": row["date"], "value": row["value"]} for row in fed_treasury_rows
        ]
    }
    fed_mbs_holdings = {
        "series": [{"date": row["date"], "value": row["value"]} for row in fed_mbs_rows]
    }
    ism_points = macro_indicators_db.load_macro_indicator_points_for_series(
        con, api.ISM_MANUFACTURING_SERIES_IDS
    )
    ism_manufacturing = (
        macro_growth_cycle.build_ism_manufacturing_payload_from_latest_points(
            ism_points
        )
        if any(ism_points.values())
        else None
    )
    dashboard = macro_growth_cycle.build_growth_cycle_dashboard(
        ism_manufacturing=ism_manufacturing,
        m2_money_stock=m2_money_stock,
        core_pce_price_index=core_pce_price_index if core_pce_rows else None,
        fed_total_assets=fed_total_assets if fed_total_assets_rows else None,
        fed_treasury_holdings=fed_treasury_holdings if fed_treasury_rows else None,
        fed_mbs_holdings=fed_mbs_holdings if fed_mbs_rows else None,
    )
    fomc_latest_tone = us_rates_liquidity_db.load_latest_combined_fomc_policy_read(
        con, as_of_date
    )
    if not fomc_latest_tone:
        fomc_latest_tone = us_rates_liquidity_db.load_latest_approved_macro_event_tone(
            con, "fomc_meeting", as_of_date
        )
    ism_at_a_glance = growth_cycle.load_latest_ism_at_a_glance_rows(con)
    survey_inputs = survey_synthesis_current.load_survey_synthesis_inputs(con)
    ism_reports = survey_inputs["ism_reports"]
    ism_macro_signal_result = survey_inputs["ism_macro_signal_result"]
    survey_synthesis_result = survey_inputs["survey_synthesis_result"]
    growth_cycle_data = dashboard.get("macro", {}).get("growth_cycle", {})
    fomc_tone_headline = macro_growth_cycle.build_fomc_tone_headline(fomc_latest_tone)
    m2_headline = macro_growth_cycle.build_m2_money_supply_headline(growth_cycle_data)
    inflation_context = macro_growth_cycle.build_inflation_context_headline(
        growth_cycle_data
    )
    fed_balance_sheet = macro_growth_cycle.build_fed_balance_sheet_headline(
        growth_cycle_data
    )
    market_phase_payload = _load_market_phase_payload(con)
    rates_liquidity_payload = _load_rates_liquidity_payload(con)
    if ism_reports and ism_macro_signal_result is None:
        ism_macro_signal_result = {
            "version": ism_macro_signal.ISM_MACRO_SIGNAL_VERSION,
            "status": "invalid_data",
        }
    consumer_sentiment_summary = None
    try:
        consumer_sentiment_summary = consumer_sentiment_dashboard.load_overview(con)
    except (ValueError, TypeError, RuntimeError):
        LOGGER.warning(
            "consumer sentiment load failed for market setup", exc_info=True
        )
    housing_permits_signal = None
    try:
        observations = macro_indicators_db.load_macro_indicator_observations(
            con, "building_permits_saar"
        )
        housing_permits_signal = housing_permits.build_housing_permits_signal(
            observations,
            survey_synthesis_result,
            as_of_date,
        )
    except (ValueError, TypeError, RuntimeError):
        LOGGER.warning("housing permits load failed for market setup", exc_info=True)
    nfib_sbo_observations = (
        macro_indicators_db.load_macro_indicator_observations_for_series(
            con,
            api.NFIB_SERIES_IDS,
        )
    )
    nfib_sbo_signal_result = nfib_sbo.build_nfib_sbo_signal(
        nfib_sbo_observations,
        survey_synthesis_result,
        as_of_date,
    )
    expected_growth = _normalize_expected_growth(survey_synthesis_result)
    survey_direction = _survey_direction_of(expected_growth)
    market_environment = _normalize_market_environment(market_phase_payload)
    financial_conditions = _normalize_financial_conditions(
        rates_liquidity_payload, survey_direction
    )
    policy_response = _normalize_policy_response(
        fomc_tone_headline,
        m2_headline,
        inflation_context,
        fed_balance_sheet,
        survey_direction,
    )
    consumer_demand = _normalize_consumer_demand(
        consumer_sentiment_summary, survey_direction
    )
    economic_confirmation_overview = None
    try:
        economic_confirmation_overview = economic_confirmation_dashboard.load_overview(
            con,
            {"expected_gdp_direction": survey_direction},
            as_of_date,
        )
    except Exception:
        LOGGER.warning(
            "economic confirmation overview load failed for market setup",
            exc_info=True,
        )
    observation = None
    try:
        cot_rows = macro_indicators_db.load_cot_observations(con)
        usd_observations = (
            macro_indicators_db.load_macro_indicator_observations_for_series(
                con, api.OBSERVATION_SERIES_IDS
            )
        )
        payload = tool.build_cyclical_commodities_payload(
            cot_rows,
            usd_observations,
            as_of_date=as_of_date,
        )
        if payload:
            observation = {"cyclical_commodities": payload}
    except Exception:
        LOGGER.warning(
            "commodities load failed for market setup",
            exc_info=True,
        )
    observation_only = {"equity_breadth": {"state": "unavailable"}}
    if observation:
        observation_only.update(observation)
    if economic_confirmation_overview:
        claims_confirmation = (economic_confirmation_overview or {}).get(
            "claims_confirmation"
        )
        if isinstance(claims_confirmation, dict) and claims_confirmation:
            observation_only["jobless_claims"] = {
                "claims_direction": claims_confirmation.get("claims_direction"),
                "confirmation_status": claims_confirmation.get("confirmation_status"),
                "observation_period": (
                    claims_confirmation.get("initial_claims") or {}
                ).get("observation_period"),
            }
    context_only = ["economic_confirmation"] if economic_confirmation_overview else None
    manual_review = ["nfib_regional_evidence"] if nfib_sbo_signal_result else None
    setup_result = market_setup_v2.build_market_setup_v2(
        expected_growth=expected_growth,
        market_environment=market_environment,
        financial_conditions=financial_conditions,
        policy_response=policy_response,
        consumer_demand=consumer_demand,
        observation_only=observation_only,
        context_only=context_only,
        manual_review=manual_review,
    )
    gdp_rows = _load_gdp_rows(con)
    evidence_layers = market_setup_evidence_layers.build_evidence_layers(
        market_setup_result=setup_result,
        survey_synthesis=survey_synthesis_result,
        expected_growth=expected_growth,
        financial_conditions=financial_conditions,
        policy_response=policy_response,
        consumer_demand=consumer_demand,
        economic_confirmation_overview=economic_confirmation_overview,
        gdp_rows=gdp_rows,
    )
    setup_result["evidence_layers"] = evidence_layers
    inputs = {
        "expected_growth": expected_growth,
        "market_environment": market_environment,
        "financial_conditions": financial_conditions,
        "policy_response": policy_response,
        "consumer_demand": consumer_demand,
        "observation_only": observation_only,
        "context_only": context_only,
        "manual_review": manual_review,
    }
    return setup_result, inputs, evidence_layers


def _load_market_phase_payload(con):
    from app import api

    try:
        return market_phase.build_dashboard_payload(
            lambda benchmark_id: benchmark_market_data.load_price_rows(
                con, benchmark_id
            ),
            benchmark_ids=api.US_BENCHMARK_IDS,
        )
    except (ValueError, TypeError, RuntimeError):
        LOGGER.warning("market phase load failed for market setup", exc_info=True)
        return None


def _load_rates_liquidity_payload(con):
    try:
        latest_points = us_rates_liquidity_db.load_latest_points(con)
        if not latest_points:
            return None
        latest_macro = macro_indicators_db.load_latest_macro_indicator_points(con)
        credit_rate_points = us_rates_liquidity_db.load_rate_points_for_series(
            con, ["treasury_10y"]
        )
        credit_macro_points = (
            macro_indicators_db.load_macro_indicator_points_for_series(
                con,
                ["aaa_corporate_yield", "bbb_corporate_yield", "ccc_corporate_yield"],
            )
        )
        return us_rates_liquidity_tool.build_dashboard_payload(
            us_rates_liquidity_db.load_rate_series(con),
            latest_points,
            latest_macro,
            credit_rate_points=credit_rate_points,
            credit_macro_points=credit_macro_points,
            credit_macro_series_points=credit_macro_points,
        )
    except (ValueError, TypeError, RuntimeError):
        LOGGER.warning("rates liquidity load failed for market setup", exc_info=True)
        return None


def _load_gdp_rows(con):
    try:
        return gdp_market_relationships.load_quad_rows(con, "us_sp500_gdp")
    except Exception:
        LOGGER.warning("gdp quad rows load failed for market setup", exc_info=True)
        return None


def _survey_direction_of(expected_growth):
    if expected_growth is None:
        return None
    fact = expected_growth.get("facts", {}).get("survey_growth_direction")
    if not isinstance(fact, dict):
        return None
    direction = fact.get("direction")
    if (
        direction
        in market_setup_v2_relationships.UPSIDE_DIRECTIONS
        | market_setup_v2_relationships.DOWNSIDE_DIRECTIONS
    ):
        return direction
    return None


def _relationship(fact_id, state, survey_direction):
    return market_setup_v2_relationships.relationship_to_growth_direction(
        fact_id, state, survey_direction
    )


def _monthly_source_period(period):
    if not period:
        return {}
    reference = str(period)[:7]
    return {
        "effective_date": str(period),
        "reference_period": reference,
        "release_date": None,
    }


def _daily_source_period(period):
    if not period:
        return {}
    return {
        "effective_date": str(period),
        "observation_date": str(period),
    }


_SURVEY_EXPLANATION_KEYS = (
    "economic_direction",
    "growth_momentum",
    "survey_alignment",
    "demand_alignment",
    "leading_side",
    "cross_sector_comparison",
    "bias_confirmation",
    "backlog_confirmation",
    "agreements",
    "conflicts",
    "missing_inputs",
    "reasons",
)

_POLICY_READ_KEYS = (
    "policy_action",
    "guidance_bias",
    "language_tone",
    "overall_bias",
    "tone_change",
    "confidence",
    "reason",
)

_FINANCIAL_DETAIL_KEYS = (
    "curve_status",
    "credit_conditions_status",
    "vix",
    "ten_year_real_rate",
)

_POLICY_DETAIL_KEYS = (
    "fomc_tone",
    "fomc_action",
    "m2_status",
    "inflation_above_target",
    "fed_balance_sheet_available",
)

_CONSUMER_EXPLANATION_KEYS = (
    "state",
    "direction",
    "reason",
    "percentile_zone",
    "momentum",
    "percentile_label",
    "confirmation_state",
)


def _project_keys(payload, keys):
    if not isinstance(payload, dict):
        return {}
    return {key: payload.get(key) for key in keys}


def _policy_read_projection(latest_tone):
    if not isinstance(latest_tone, dict):
        return {}
    return {key: latest_tone[key] for key in _POLICY_READ_KEYS if key in latest_tone}


def _normalize_expected_growth(survey_synthesis_result):
    if survey_synthesis_result is None:
        return None
    fact = {
        "direction": survey_synthesis_result.get("expected_gdp_direction"),
        "status": survey_synthesis_result.get("status"),
        "source_period": _monthly_source_period(survey_synthesis_result.get("period")),
        "explanation": _project_keys(survey_synthesis_result, _SURVEY_EXPLANATION_KEYS),
    }
    return {
        "source_module": "ism_survey_synthesis",
        "method_version": "ism_survey_synthesis_v1",
        "facts": {"survey_growth_direction": fact},
    }


def _normalize_market_environment(market_phase_payload):
    market_env = market_setup.build_market_environment(market_phase_payload)
    if market_env.get("data_status") == "missing":
        return None
    period = market_env.get("observation_period")
    return {
        "source_module": "market_phase",
        "method_version": "market_phase_v1",
        "facts": {
            "sp500_market_phase": {
                "phase": market_env.get("state"),
                "source_period": _daily_source_period(period),
                "explanation": {
                    "state": market_env.get("state"),
                    "starting_posture": market_env.get("starting_posture"),
                    "reason": market_env.get("reason"),
                },
            }
        },
    }


def _normalize_financial_conditions(rates_liquidity_payload, survey_direction):
    if rates_liquidity_payload is None:
        return None
    derived = rates_liquidity_payload.get("derived", {})
    financial = market_setup.build_financial_conditions(rates_liquidity_payload)
    financial_state = financial.get("state")
    as_of = rates_liquidity_payload.get("as_of")
    period = _daily_source_period(as_of)
    credit_status = derived.get("credit_conditions_status")
    vix = derived.get("vix")
    return {
        "source_module": "us_rates_liquidity",
        "method_version": "us_rates_liquidity_v1",
        "facts": {
            "macro_financial_conditions": {
                "relationship_to_growth_direction": _relationship(
                    "macro_financial_conditions", financial_state, survey_direction
                ),
                "source_period": dict(period),
                "explanation": {
                    "state": financial_state,
                    "growth_confirmation": financial.get("growth_confirmation"),
                    "reasons": list(financial.get("reasons", [])),
                    "details": _project_keys(
                        financial.get("details", {}), _FINANCIAL_DETAIL_KEYS
                    ),
                },
            },
            "credit_conditions": {
                "status": credit_status,
                "source_period": dict(period),
                "explanation": {"status": credit_status},
            },
            "vix_level": {
                "level": vix,
                "source_period": dict(period),
                "explanation": {"level": vix},
            },
        },
    }


def _normalize_policy_response(
    fomc_tone_headline,
    m2_headline,
    inflation_context,
    fed_balance_sheet,
    survey_direction,
):
    policy = market_setup.build_policy_response(
        fomc_tone_headline,
        m2_headline,
        inflation_context,
        fed_balance_sheet,
    )
    policy_state = policy.get("state")
    m2_period = (m2_headline or {}).get("period")
    m2_status = (m2_headline or {}).get("status")
    return {
        "source_module": "fomc_policy_tone",
        "method_version": "fomc_policy_tone_v1",
        "facts": {
            "macro_policy_response": {
                "relationship_to_growth_direction": _relationship(
                    "macro_policy_response", policy_state, survey_direction
                ),
                "source_period": _monthly_source_period(
                    (fomc_tone_headline or {}).get("period") or m2_period
                ),
                "explanation": {
                    "state": policy_state,
                    "reasons": list(policy.get("reasons", [])),
                    "details": _project_keys(
                        policy.get("details", {}), _POLICY_DETAIL_KEYS
                    ),
                    "policy_read": _policy_read_projection(
                        (fomc_tone_headline or {}).get("latest_tone")
                    ),
                },
            },
            "m2_liquidity": {
                "status": m2_status,
                "source_period": _monthly_source_period(m2_period),
                "explanation": {
                    "status": m2_status,
                    "status_label": (m2_headline or {}).get("status_label"),
                },
            },
        },
    }


def _normalize_consumer_demand(consumer_sentiment_summary, survey_direction):
    if consumer_sentiment_summary is None:
        return None
    consumer = market_setup.build_consumer_demand_outlook(consumer_sentiment_summary)
    consumer_state = consumer.get("state")
    return {
        "source_module": "consumer_sentiment",
        "method_version": "market_setup_v2_consumer_demand_v1",
        "facts": {
            "consumer_demand_outlook": {
                "relationship_to_growth_direction": _relationship(
                    "consumer_demand_outlook", consumer_state, survey_direction
                ),
                "source_period": _monthly_source_period(
                    consumer_sentiment_summary.get("aligned_month")
                ),
                "explanation": _project_keys(consumer, _CONSUMER_EXPLANATION_KEYS),
            }
        },
    }
