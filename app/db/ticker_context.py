import sqlite3
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"

_VALID_CYCLE_TAGS = {"cyclical", "defensive", "both"}


def connect(db_path=DEFAULT_DB_PATH):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        pragma journal_mode = wal;
        create table if not exists gics_industry_tags (
            industry text not null primary key,
            sector text not null,
            industry_group text not null,
            official_industry text not null,
            cycle_tag text not null,
            tag_source text not null,
            source_vintage text not null
        );
        create table if not exists industry_aliases (
            source text not null,
            source_industry text not null,
            gics_industry text not null,
            primary key(source, source_industry)
        );
        create table if not exists ticker_profiles (
            symbol text not null primary key,
            company_name text not null,
            provider text not null,
            provider_sector text,
            provider_industry text,
            fetched_at text not null
        );
        create table if not exists ticker_fundamentals (
            symbol text not null primary key,
            forward_pe real,
            forward_eps real,
            trailing_eps real,
            market_cap real,
            shares_short real,
            short_ratio real,
            short_percent_of_float real,
            dividend_yield real,
            debt_to_equity real,
            current_ratio real,
            quick_ratio real,
            return_on_equity real,
            return_on_assets real,
            book_value real,
            total_debt real,
            total_cash real,
            free_cashflow real,
            enterprise_value real,
            ebitda real,
            provider text not null,
            fetched_at text not null
        );
        create table if not exists estimate_consensus_snapshots (
            symbol text not null,
            fiscal_year_end text not null,
            avg real,
            low real,
            high real,
            analyst_count integer,
            captured_at text not null
        );
        """
    )
    return con


def normalize_symbol(symbol):
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    return normalized


def fundamentals_fresh(row, max_age_seconds=72000):
    if row is None:
        return False
    fetched_at = row.get("fetched_at")
    if not fetched_at:
        return False
    try:
        fetched = datetime.fromisoformat(fetched_at)
    except (ValueError, TypeError):
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    return (datetime.now(UTC) - fetched).total_seconds() <= max_age_seconds


def estimate_consensus_fresh(row, max_age_seconds=72000):
    if row is None:
        return False
    captured_at = row.get("captured_at")
    if not captured_at:
        return False
    try:
        captured = datetime.fromisoformat(captured_at)
    except (ValueError, TypeError):
        return False
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=UTC)
    return (datetime.now(UTC) - captured).total_seconds() <= max_age_seconds


def save_estimate_consensus_snapshot(con, symbol, consensus):
    normalized = normalize_symbol(symbol)
    fiscal_year_end = str(consensus.get("fiscal_year_end") or "").strip()
    if not fiscal_year_end:
        raise ValueError(f"fiscal year end is required for {normalized}")
    avg = consensus.get("avg")
    low = consensus.get("low")
    high = consensus.get("high")
    analyst_count = consensus.get("analyst_count")
    latest = con.execute(
        """
        select avg, low, high, analyst_count
        from estimate_consensus_snapshots
        where symbol = ? and fiscal_year_end = ?
        order by captured_at desc
        limit 1
        """,
        (normalized, fiscal_year_end),
    ).fetchone()
    if latest is not None:
        latest_values = (latest["avg"], latest["low"], latest["high"], latest["analyst_count"])
        if latest_values == (avg, low, high, analyst_count):
            return
    captured_at = consensus.get("captured_at") or datetime.now(UTC).isoformat()
    con.execute(
        """
        insert into estimate_consensus_snapshots(
            symbol, fiscal_year_end, avg, low, high, analyst_count, captured_at
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        (normalized, fiscal_year_end, avg, low, high, analyst_count, captured_at),
    )
    con.commit()


def load_latest_estimate_consensus(con, symbol):
    normalized = normalize_symbol(symbol)
    row = con.execute(
        """
        select symbol, fiscal_year_end, avg, low, high, analyst_count, captured_at
        from estimate_consensus_snapshots
        where symbol = ?
        order by captured_at desc
        limit 1
        """,
        (normalized,),
    ).fetchone()
    return dict(row) if row else None


def load_estimate_consensus_history(con, symbol, since_iso):
    normalized = normalize_symbol(symbol)
    rows = con.execute(
        """
        select symbol, fiscal_year_end, avg, low, high, analyst_count, captured_at
        from estimate_consensus_snapshots
        where symbol = ? and captured_at >= ?
        order by captured_at
        """,
        (normalized, since_iso),
    ).fetchall()
    return [dict(row) for row in rows]


def save_ticker_profile(con, profile):
    symbol = normalize_symbol(profile.get("symbol"))
    company_name = str(profile.get("company_name") or "").strip()
    if not company_name:
        raise ValueError(f"company name is required for {symbol}")
    provider = str(profile.get("provider") or "").strip()
    if not provider:
        raise ValueError(f"provider is required for {symbol}")
    fetched_at = profile.get("fetched_at") or datetime.now(UTC).isoformat()
    con.execute(
        """
        insert or replace into ticker_profiles(
            symbol, company_name, provider, provider_sector, provider_industry, fetched_at
        ) values (?, ?, ?, ?, ?, ?)
        """,
        (
            symbol,
            company_name,
            provider,
            profile.get("provider_sector"),
            profile.get("provider_industry"),
            fetched_at,
        ),
    )
    con.commit()


def load_ticker_profile(con, symbol):
    normalized = normalize_symbol(symbol)
    row = con.execute(
        """
        select symbol, company_name, provider, provider_sector, provider_industry, fetched_at
        from ticker_profiles
        where symbol = ?
        """,
        (normalized,),
    ).fetchone()
    return dict(row) if row else None


_FUNDAMENTAL_COLUMNS = [
    "forward_pe",
    "forward_eps",
    "trailing_eps",
    "market_cap",
    "shares_short",
    "short_ratio",
    "short_percent_of_float",
    "dividend_yield",
    "debt_to_equity",
    "current_ratio",
    "quick_ratio",
    "return_on_equity",
    "return_on_assets",
    "book_value",
    "total_debt",
    "total_cash",
    "free_cashflow",
    "enterprise_value",
    "ebitda",
]


def save_ticker_fundamentals(con, fundamentals):
    symbol = normalize_symbol(fundamentals.get("symbol"))
    provider = str(fundamentals.get("provider") or "").strip()
    if not provider:
        raise ValueError(f"provider is required for {symbol}")
    fetched_at = fundamentals.get("fetched_at") or datetime.now(UTC).isoformat()
    column_names = ", ".join(_FUNDAMENTAL_COLUMNS)
    placeholders = ", ".join(["?"] * len(_FUNDAMENTAL_COLUMNS))
    values = [fundamentals.get(column) for column in _FUNDAMENTAL_COLUMNS]
    con.execute(
        f"""
        insert or replace into ticker_fundamentals(
            symbol, {column_names}, provider, fetched_at
        ) values (?, {placeholders}, ?, ?)
        """,
        (symbol, *values, provider, fetched_at),
    )
    con.commit()


def load_ticker_fundamentals(con, symbol):
    normalized = normalize_symbol(symbol)
    column_names = ", ".join(_FUNDAMENTAL_COLUMNS)
    row = con.execute(
        f"""
        select symbol, {column_names}, provider, fetched_at
        from ticker_fundamentals
        where symbol = ?
        """,
        (normalized,),
    ).fetchone()
    return dict(row) if row else None


def _validate_industry_tag(row):
    industry = str(row.get("industry") or "").strip()
    if not industry:
        raise ValueError("industry is required for every tag row")
    cycle_tag = str(row.get("cycle_tag") or "").strip().lower()
    if cycle_tag not in _VALID_CYCLE_TAGS:
        raise ValueError(f"cycle tag {cycle_tag or 'missing'} is invalid for {industry}")
    required_fields = ("sector", "industry_group", "tag_source", "source_vintage")
    if any(not str(row.get(field) or "").strip() for field in required_fields):
        raise ValueError(f"industry tag fields are required for {industry}")
    return industry, cycle_tag


def _validate_industry_alias(alias):
    source = str(alias.get("source") or "").strip()
    source_industry = str(alias.get("source_industry") or "").strip()
    gics_industry = str(alias.get("gics_industry") or "").strip()
    if not source or not source_industry or not gics_industry:
        raise ValueError("alias source, source_industry and gics_industry are required")
    return source, source_industry, gics_industry


def _validate_industry_reference_data(industries, aliases):
    industry_names = {_validate_industry_tag(row)[0] for row in industries}
    for alias in aliases:
        _, _, gics_industry = _validate_industry_alias(alias)
        if gics_industry not in industry_names:
            raise ValueError(f"alias industry {gics_industry} is unknown")


def _insert_industry_tags(con, rows):
    for row in rows:
        industry, cycle_tag = _validate_industry_tag(row)
        con.execute(
            """
            insert or replace into gics_industry_tags(
                industry, sector, industry_group, official_industry,
                cycle_tag, tag_source, source_vintage
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                industry,
                row["sector"],
                row["industry_group"],
                row.get("official_industry") or industry,
                cycle_tag,
                row["tag_source"],
                row["source_vintage"],
            ),
        )


def save_industry_tags(con, rows):
    _insert_industry_tags(con, rows)
    con.commit()
    return len(rows)


def load_industry_tag(con, industry):
    row = con.execute(
        """
        select industry, sector, industry_group, official_industry,
               cycle_tag, tag_source, source_vintage
        from gics_industry_tags
        where industry = ?
        """,
        (industry,),
    ).fetchone()
    return dict(row) if row else None


def load_industry_tags(con):
    rows = con.execute(
        """
        select industry, sector, industry_group, official_industry,
               cycle_tag, tag_source, source_vintage
        from gics_industry_tags
        order by sector, industry_group, industry
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _insert_industry_aliases(con, aliases):
    for alias in aliases:
        source, source_industry, gics_industry = _validate_industry_alias(alias)
        con.execute(
            """
            insert or replace into industry_aliases(source, source_industry, gics_industry)
            values (?, ?, ?)
            """,
            (source, source_industry, gics_industry),
        )


def save_industry_aliases(con, aliases):
    _insert_industry_aliases(con, aliases)
    con.commit()
    return len(aliases)


def replace_industry_reference_data(con, industries, aliases):
    _validate_industry_reference_data(industries, aliases)
    try:
        _insert_industry_tags(con, industries)
        _insert_industry_aliases(con, aliases)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return {"industries": len(industries), "aliases": len(aliases)}


def load_industry_alias(con, source, source_industry):
    row = con.execute(
        """
        select source, source_industry, gics_industry
        from industry_aliases
        where source = ? and source_industry = ?
        """,
        (source, source_industry),
    ).fetchone()
    return dict(row) if row else None
