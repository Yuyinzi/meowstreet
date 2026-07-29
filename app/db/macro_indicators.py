import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"

_MACRO_TABLES_DDL = """
create table if not exists macro_indicator_series (
    series_id text primary key,
    title text not null,
    units text not null,
    source text not null
);
create table if not exists macro_indicator_points (
    series_id text not null,
    date text not null,
    value real not null,
    source text not null,
    primary key(series_id, date),
    foreign key(series_id) references macro_indicator_series(series_id)
);
create index if not exists idx_macro_indicator_points_series_date
on macro_indicator_points(series_id, date);
create table if not exists macro_indicator_observation_metadata (
    series_id text not null,
    date text not null,
    release_date text,
    revision_status text,
    source_url text,
    source_identifier text,
    source_hash text,
    primary key(series_id, date),
    foreign key(series_id) references macro_indicator_series(series_id)
);
"""

_REGIONAL_TABLES_DDL = """
create table if not exists macro_indicator_regional_series (
    region_id text not null,
    indicator_id text not null,
    title text not null,
    units text not null,
    api_label text not null,
    display_label text not null,
    states text not null,
    frequency text not null default 'quarterly_3_month_aggregate',
    primary key(region_id, indicator_id)
);
create table if not exists macro_indicator_regional_observations (
    region_id text not null,
    indicator_id text not null,
    date text not null,
    value real,
    availability text not null default 'available',
    primary key(region_id, indicator_id, date),
    foreign key(region_id, indicator_id) references macro_indicator_regional_series(region_id, indicator_id)
);
create table if not exists macro_indicator_regional_observation_metadata (
    region_id text not null,
    indicator_id text not null,
    date text not null,
    procedure_name text not null,
    request_params text,
    retrieval_time text,
    source_url text,
    response_hash text,
    primary key(region_id, indicator_id, date),
    foreign key(region_id, indicator_id, date) references macro_indicator_regional_observations(region_id, indicator_id, date)
);
"""


__COT_DDL = """
create table if not exists cot_observations (
    commodity_id text not null,
    report_date text not null,
    manager_longs real not null,
    manager_shorts real not null,
    open_interest real not null,
    publication_date text,
    report_type text,
    source_url text,
    source_hash text,
    primary key(commodity_id, report_date)
);
create index if not exists idx_cot_report_date
on cot_observations(report_date);
"""


def init_macro_tables(con):
    con.executescript(_MACRO_TABLES_DDL)
    con.executescript(_REGIONAL_TABLES_DDL)
    con.executescript(__COT_DDL)
    for col in ["source_hash", "publication_date_basis"]:
        try:
            con.execute(
                f"alter table macro_indicator_observation_metadata add column {col} text"
            )
        except sqlite3.OperationalError:
            pass
    try:
        con.execute(
            "alter table cot_observations add column publication_date_basis text"
        )
    except sqlite3.OperationalError:
        pass


def connect(db_path=DEFAULT_DB_PATH):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    init_macro_tables(con)
    return con


def _normalize_series_id(series_id):
    normalized = str(series_id or "").strip().lower()
    if not normalized:
        raise ValueError("series id is required")
    return normalized


def _replace_single(con, series, points):
    sid = _normalize_series_id(series["series_id"])
    con.execute("delete from macro_indicator_points where series_id = ?", (sid,))
    con.execute("delete from macro_indicator_series where series_id = ?", (sid,))
    con.execute(
        """
        insert into macro_indicator_series(series_id, title, units, source)
        values (?, ?, ?, ?)
        """,
        (sid, series["title"], series["units"], series["source"]),
    )
    for point in points:
        con.execute(
            """
            insert into macro_indicator_points(series_id, date, value, source)
            values (?, ?, ?, ?)
            """,
            (sid, point["date"], point["value"], point["source"]),
        )


def replace_macro_indicator_points(con, series, points):
    _replace_single(con, series, points)
    con.commit()
    return {"series": 1, "points": len(points)}


def merge_macro_indicator_points(con, series, points, commit=True):
    sid = _normalize_series_id(series["series_id"])
    con.execute(
        """
        insert into macro_indicator_series(series_id, title, units, source)
        values (?, ?, ?, ?)
        on conflict(series_id) do update set
            title = excluded.title,
            units = excluded.units,
            source = excluded.source
        """,
        (sid, series["title"], series["units"], series["source"]),
    )
    for point in points:
        con.execute(
            """
            insert into macro_indicator_points(series_id, date, value, source)
            values (?, ?, ?, ?)
            on conflict(series_id, date) do update set
                value = excluded.value,
                source = excluded.source
            """,
            (sid, point["date"], point["value"], point["source"]),
        )
    if commit:
        con.commit()
    return {"series": 1, "points": len(points)}


def insert_macro_indicator_points(con, series, points, commit=True):
    sid = _normalize_series_id(series["series_id"])
    con.execute(
        "insert or ignore into macro_indicator_series(series_id, title, units, source) values (?, ?, ?, ?)",
        (sid, series["title"], series["units"], series["source"]),
    )
    for point in points:
        con.execute(
            """
            insert or ignore into macro_indicator_points(series_id, date, value, source)
            values (?, ?, ?, ?)
            """,
            (sid, point["date"], point["value"], point["source"]),
        )
    if commit:
        con.commit()
    return {"series": 1, "points": len(points)}


def load_macro_indicator_series(con):
    rows = con.execute(
        """
        select series_id, title, units, source
        from macro_indicator_series
        order by series_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def load_macro_indicator_points(con, series_id):
    sid = _normalize_series_id(series_id)
    rows = con.execute(
        """
        select date, value, source
        from macro_indicator_points
        where series_id = ?
        order by date
        """,
        (sid,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_latest_macro_indicator_points(con):
    rows = con.execute(
        """
        select p.series_id, p.date, p.value, p.source
        from macro_indicator_points p
        join (
            select series_id, max(date) as max_date
            from macro_indicator_points
            group by series_id
        ) latest
        on latest.series_id = p.series_id and latest.max_date = p.date
        order by p.series_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def load_macro_indicator_points_for_series(con, series_ids):
    normalized_ids = [_normalize_series_id(sid) for sid in series_ids]
    return {sid: load_macro_indicator_points(con, sid) for sid in normalized_ids}


def replace_macro_indicator_points_batch(con, series_points_list):
    try:
        for item in series_points_list:
            _replace_single(con, item["series"], item["points"])
        con.commit()
    except Exception:
        con.rollback()
        raise


def merge_macro_indicator_observations(con, series, observations):
    merge_macro_indicator_points(con, series, observations, commit=False)
    for observation in observations:
        con.execute(
            """insert into macro_indicator_observation_metadata(
                series_id, date, release_date, revision_status, source_url, source_identifier
            ) values (?, ?, ?, ?, ?, ?)
            on conflict(series_id, date) do update set
                release_date = excluded.release_date,
                revision_status = excluded.revision_status,
                source_url = excluded.source_url,
                source_identifier = excluded.source_identifier""",
            (
                series["series_id"],
                observation["date"],
                observation.get("release_date"),
                observation.get("revision_status"),
                observation.get("source_url"),
                observation.get("source_identifier"),
            ),
        )
    con.commit()


def load_macro_indicator_observations(con, series_id):
    sid = _normalize_series_id(series_id)
    rows = con.execute(
        """select p.date, p.value, p.source,
                  m.release_date, m.revision_status, m.source_url, m.source_identifier, m.source_hash
           from macro_indicator_points p
           left join macro_indicator_observation_metadata m
             on m.series_id = p.series_id and m.date = p.date
           where p.series_id = ?
           order by p.date""",
        (sid,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_macro_indicator_observations_for_series(con, series_ids):
    normalized_ids = [_normalize_series_id(sid) for sid in series_ids]
    return {sid: load_macro_indicator_observations(con, sid) for sid in normalized_ids}


_NFIB_SERIES_METADATA = {
    "nfib_sbo_optimism": {
        "title": "Small Business Optimism Index",
        "units": "index",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_employment_plans": {
        "title": "Plans to Increase Employment",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_expansion_outlook": {
        "title": "Good Time to Expand",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_inventory_plans": {
        "title": "Plans to Increase Inventories",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_economic_expectations": {
        "title": "Expect Economy to Improve",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_real_sales_expectations": {
        "title": "Expect Real Sales Higher",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_capital_outlay_plans": {
        "title": "Plans to Make Capital Expenditures",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_current_inventory_low": {
        "title": "Current Inventory Too Low",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_job_openings": {
        "title": "Current Job Openings",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_credit_conditions_expectations": {
        "title": "Credit Conditions Expectation",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_earnings_trends": {
        "title": "Earnings Trends",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
}


def merge_macro_indicator_observations_batch(con, observations):
    try:
        by_series = {}
        for obs in observations:
            sid = _normalize_series_id(obs["series_id"])
            by_series.setdefault(sid, []).append(obs)

        for sid, series_observations in by_series.items():
            meta = _NFIB_SERIES_METADATA.get(sid, {})
            series = {
                "series_id": sid,
                "title": meta.get("title", sid),
                "units": meta.get("units", "index"),
                "source": meta.get("source", "nfib_sbet_pdf"),
            }
            merge_macro_indicator_points(con, series, series_observations, commit=False)
            for obs in series_observations:
                con.execute(
                    """insert into macro_indicator_observation_metadata(
                        series_id, date, release_date, revision_status, source_url, source_identifier, source_hash
                    ) values (?, ?, ?, ?, ?, ?, ?)
                    on conflict(series_id, date) do update set
                        release_date = excluded.release_date,
                        revision_status = excluded.revision_status,
                        source_url = excluded.source_url,
                        source_identifier = excluded.source_identifier,
                        source_hash = excluded.source_hash""",
                    (
                        sid,
                        obs["date"],
                        obs.get("release_date"),
                        obs.get("revision_status"),
                        obs.get("source_url"),
                        obs.get("source_identifier"),
                        obs.get("source_hash"),
                    ),
                )

        con.commit()
        return {"series": len(by_series), "observations": len(observations)}
    except Exception:
        con.rollback()
        raise


def _region_id(value):
    if not value or not str(value).strip():
        raise ValueError("region id is required")
    return str(value).strip().lower()


def _indicator_id(value):
    if not value or not str(value).strip():
        raise ValueError("indicator id is required")
    return str(value).strip().lower()


def _json_val(val):
    if val is None:
        return None
    if isinstance(val, (dict, list, tuple)):
        return json.dumps(val, default=str)
    return val


def merge_nfib_regional_observations_batch(con, observations):
    try:
        seen = set()
        for obs in observations:
            rid = _region_id(obs["region_id"])
            iid = _indicator_id(obs["indicator_id"])
            key = (rid, iid, obs["date"])
            if key in seen:
                continue
            seen.add(key)

            con.execute(
                """insert or ignore into macro_indicator_regional_series(
                    region_id, indicator_id, title, units, api_label, display_label, states, frequency
                ) values (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rid,
                    iid,
                    obs.get("title", ""),
                    obs.get("units", ""),
                    obs.get("api_label", ""),
                    obs.get("display_label", ""),
                    obs.get("states", ""),
                    obs.get("frequency", "quarterly_3_month_aggregate"),
                ),
            )
            con.execute(
                """insert into macro_indicator_regional_observations(
                    region_id, indicator_id, date, value, availability
                ) values (?, ?, ?, ?, ?)
                on conflict(region_id, indicator_id, date) do update set
                    value = excluded.value,
                    availability = excluded.availability""",
                (
                    rid,
                    iid,
                    obs["date"],
                    obs.get("value"),
                    obs.get("availability", "available"),
                ),
            )
            con.execute(
                """insert into macro_indicator_regional_observation_metadata(
                    region_id, indicator_id, date, procedure_name, request_params, retrieval_time, source_url, response_hash
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(region_id, indicator_id, date) do update set
                    procedure_name = excluded.procedure_name,
                    request_params = excluded.request_params,
                    retrieval_time = excluded.retrieval_time,
                    source_url = excluded.source_url,
                    response_hash = excluded.response_hash""",
                (
                    rid,
                    iid,
                    obs["date"],
                    obs.get("procedure_name", "getTotals2"),
                    _json_val(obs.get("request_params")),
                    obs.get("retrieval_time"),
                    obs.get("source_url", ""),
                    _json_val(obs.get("response_hash")),
                ),
            )
        con.commit()
        return len(seen)
    except Exception:
        con.rollback()
        raise


_REGIONAL_OBS_COLS = """
    o.region_id, o.indicator_id, o.date, o.value, o.availability,
    s.title, s.units, s.api_label, s.display_label, s.states, s.frequency,
    m.procedure_name, m.request_params, m.retrieval_time, m.source_url, m.response_hash
"""


def load_nfib_regional_observations(con, region_id, indicator_id):
    rid = _region_id(region_id)
    iid = _indicator_id(indicator_id)
    rows = con.execute(
        f"""select {_REGIONAL_OBS_COLS}
           from macro_indicator_regional_observations o
           left join macro_indicator_regional_series s
               on o.region_id = s.region_id and o.indicator_id = s.indicator_id
           left join macro_indicator_regional_observation_metadata m
               on o.region_id = m.region_id and o.indicator_id = m.indicator_id and o.date = m.date
           where o.region_id = ? and o.indicator_id = ?
           order by o.date""",
        (rid, iid),
    ).fetchall()
    return [dict(row) for row in rows]


def load_all_nfib_regional_observations(con):
    rows = con.execute(
        f"""select {_REGIONAL_OBS_COLS}
           from macro_indicator_regional_observations o
           left join macro_indicator_regional_series s
               on o.region_id = s.region_id and o.indicator_id = s.indicator_id
           left join macro_indicator_regional_observation_metadata m
               on o.region_id = m.region_id and o.indicator_id = m.indicator_id and o.date = m.date
           order by o.region_id, o.indicator_id, o.date"""
    ).fetchall()
    return [dict(row) for row in rows]


__COT_REQUIRED_FIELDS = [
    "commodity_id",
    "report_date",
    "manager_longs",
    "manager_shorts",
    "open_interest",
]


def merge_cot_observations(con, observations):
    try:
        for obs in observations:
            for field in __COT_REQUIRED_FIELDS:
                if field not in obs:
                    raise ValueError(
                        f" cot observation is missing required field: {field}"
                    )
            commodity_id = str(obs["commodity_id"] or "").strip().lower()
            if not commodity_id:
                raise ValueError(" cot commodity_id is required")
            report_date = str(obs["report_date"] or "").strip()
            if not report_date:
                raise ValueError(" cot report_date is required")
            manager_longs = float(obs["manager_longs"])
            manager_shorts = float(obs["manager_shorts"])
            open_interest = float(obs["open_interest"])
            if manager_longs < 0 or manager_shorts < 0 or open_interest < 0:
                raise ValueError(
                    f" cot {commodity_id} has negative values on {report_date}"
                )
            if manager_longs > open_interest:
                raise ValueError(
                    f" cot {commodity_id} manager longs exceed open interest on {report_date}"
                )
            if manager_shorts > open_interest:
                raise ValueError(
                    f" cot {commodity_id} manager shorts exceed open interest on {report_date}"
                )
            con.execute(
                """insert into cot_observations(
                    commodity_id, report_date, manager_longs, manager_shorts,
                    open_interest, publication_date, publication_date_basis,
                    report_type, source_url, source_hash
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(commodity_id, report_date) do update set
                    manager_longs = excluded.manager_longs,
                    manager_shorts = excluded.manager_shorts,
                    open_interest = excluded.open_interest,
                    publication_date = excluded.publication_date,
                    publication_date_basis = excluded.publication_date_basis,
                    report_type = excluded.report_type,
                    source_url = excluded.source_url,
                    source_hash = excluded.source_hash""",
                (
                    commodity_id,
                    report_date,
                    manager_longs,
                    manager_shorts,
                    open_interest,
                    str(obs.get("publication_date", "") or ""),
                    str(obs.get("publication_date_basis", "") or ""),
                    str(obs.get("report_type", "") or ""),
                    str(obs.get("source_url", "") or ""),
                    str(obs.get("source_hash", "") or ""),
                ),
            )
        con.commit()
        return len(observations)
    except Exception:
        con.rollback()
        raise


__COT_COLS = """
    commodity_id, report_date, manager_longs, manager_shorts, open_interest,
    publication_date, publication_date_basis, report_type, source_url, source_hash
"""


def load_cot_observations(con):
    rows = con.execute(
        f"select {__COT_COLS} from cot_observations order by commodity_id, report_date"
    ).fetchall()
    return [dict(row) for row in rows]
