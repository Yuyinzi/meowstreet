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
        """
    )
    return con


def normalize_symbol(symbol):
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    return normalized


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


def save_industry_tags(con, rows):
    for row in rows:
        industry = str(row.get("industry") or "").strip()
        if not industry:
            raise ValueError("industry is required for every tag row")
        cycle_tag = str(row.get("cycle_tag") or "").strip().lower()
        if cycle_tag not in _VALID_CYCLE_TAGS:
            raise ValueError(f"cycle tag {cycle_tag or 'missing'} is invalid for {industry}")
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


def save_industry_aliases(con, aliases):
    for alias in aliases:
        source = str(alias.get("source") or "").strip()
        source_industry = str(alias.get("source_industry") or "").strip()
        gics_industry = str(alias.get("gics_industry") or "").strip()
        if not source or not source_industry or not gics_industry:
            raise ValueError("alias source, source_industry and gics_industry are required")
        con.execute(
            """
            insert or replace into industry_aliases(source, source_industry, gics_industry)
            values (?, ?, ?)
            """,
            (source, source_industry, gics_industry),
        )
    con.commit()
    return len(aliases)


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
