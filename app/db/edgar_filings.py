import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"
UNMAPPED_CIK = -1


def connect(db_path=DEFAULT_DB_PATH):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        pragma journal_mode = wal;
        create table if not exists edgar_cik_map (
            symbol text not null primary key,
            cik integer not null,
            title text,
            fetched_at text not null
        );
        create table if not exists edgar_8k_filings (
            symbol text not null,
            accession text not null primary key,
            filing_date text not null,
            primary_document text not null,
            items_json text,
            is_earnings integer,
            fetched_at text not null
        );
        create index if not exists idx_edgar_8k_symbol_date
            on edgar_8k_filings(symbol, filing_date);
        create table if not exists edgar_statement_facts (
            symbol text not null primary key,
            cik integer,
            facts_json text,
            fetched_at text not null
        );
        create table if not exists edgar_form4_filings (
            symbol text not null,
            accession text not null primary key,
            filing_date text not null,
            primary_document text not null,
            fetched_at text not null
        );
        create table if not exists edgar_form4_transactions (
            symbol text not null,
            accession text not null,
            insider_name text not null,
            insider_title text,
            transaction_date text not null,
            transaction_code text,
            code_label text,
            shares real,
            price real,
            shares_after real,
            acquired_disposed text,
            fetched_at text not null
        );
        create index if not exists idx_edgar_form4_symbol_date
            on edgar_form4_transactions(symbol, transaction_date);
        """
    )
    return con


def normalize_symbol(symbol):
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    return normalized


def save_cik(con, symbol, cik, title):
    normalized = normalize_symbol(symbol)
    con.execute(
        """
        insert or replace into edgar_cik_map(symbol, cik, title, fetched_at)
        values (?, ?, ?, ?)
        """,
        (normalized, int(cik), title, datetime.now(UTC).isoformat()),
    )
    con.commit()


def save_cik_miss(con, symbol):
    normalized = normalize_symbol(symbol)
    con.execute(
        """
        insert or replace into edgar_cik_map(symbol, cik, title, fetched_at)
        values (?, ?, ?, ?)
        """,
        (normalized, UNMAPPED_CIK, None, datetime.now(UTC).isoformat()),
    )
    con.commit()


def load_cik(con, symbol):
    normalized = normalize_symbol(symbol)
    row = con.execute(
        "select symbol, cik, title, fetched_at from edgar_cik_map where symbol = ?",
        (normalized,),
    ).fetchone()
    return dict(row) if row else None


def cik_map_fresh(row, max_age_seconds=72000):
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


def save_statement_facts(con, symbol, cik, facts):
    normalized = normalize_symbol(symbol)
    con.execute(
        """
        insert or replace into edgar_statement_facts(symbol, cik, facts_json, fetched_at)
        values (?, ?, ?, ?)
        """,
        (
            normalized,
            cik,
            json.dumps(facts) if facts is not None else None,
            datetime.now(UTC).isoformat(),
        ),
    )
    con.commit()


def load_statement_facts(con, symbol):
    normalized = normalize_symbol(symbol)
    row = con.execute(
        "select symbol, cik, facts_json, fetched_at from edgar_statement_facts where symbol = ?",
        (normalized,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    facts_json = result.pop("facts_json")
    try:
        result["facts"] = json.loads(facts_json) if facts_json else None
    except (ValueError, TypeError):
        result["facts"] = None
    return result


def save_filing(con, symbol, filing):
    normalized = normalize_symbol(symbol)
    items = filing.get("items")
    con.execute(
        """
        insert into edgar_8k_filings(
            symbol, accession, filing_date, primary_document,
            items_json, is_earnings, fetched_at
        ) values (?, ?, ?, ?, ?, ?, ?)
        on conflict(accession) do update set
            items_json = coalesce(excluded.items_json, edgar_8k_filings.items_json),
            is_earnings = coalesce(excluded.is_earnings, edgar_8k_filings.is_earnings)
        """,
        (
            normalized,
            str(filing["accession"]),
            str(filing["filing_date"]),
            str(filing["primary_document"]),
            json.dumps(items) if items is not None else None,
            filing.get("is_earnings"),
            datetime.now(UTC).isoformat(),
        ),
    )
    con.commit()


def load_filings(con, symbol, since=None):
    normalized = normalize_symbol(symbol)
    if since:
        rows = con.execute(
            """
            select symbol, accession, filing_date, primary_document,
                   items_json, is_earnings, fetched_at
            from edgar_8k_filings
            where symbol = ? and filing_date >= ?
            order by filing_date
            """,
            (normalized, since),
        ).fetchall()
    else:
        rows = con.execute(
            """
            select symbol, accession, filing_date, primary_document,
                   items_json, is_earnings, fetched_at
            from edgar_8k_filings
            where symbol = ?
            order by filing_date
            """,
            (normalized,),
        ).fetchall()
    results = []
    for row in rows:
        result = dict(row)
        items_json = result.pop("items_json")
        try:
            result["items"] = json.loads(items_json) if items_json else None
        except (ValueError, TypeError):
            result["items"] = None
        results.append(result)
    return results


def load_filings_missing_items(con, symbol, limit=None):
    normalized = normalize_symbol(symbol)
    query = """
        select symbol, accession, filing_date, primary_document
        from edgar_8k_filings
        where symbol = ? and items_json is null
        order by filing_date desc
    """
    params = [normalized]
    if limit is not None:
        query += " limit ?"
        params.append(limit)
    rows = con.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def save_form4_filing(con, symbol, filing, transactions):
    normalized = normalize_symbol(symbol)
    accession = str(filing["accession"])
    con.execute(
        """
        insert or replace into edgar_form4_filings(
            symbol, accession, filing_date, primary_document, fetched_at
        ) values (?, ?, ?, ?, ?)
        """,
        (
            normalized,
            accession,
            str(filing["filing_date"]),
            str(filing["primary_document"]),
            datetime.now(UTC).isoformat(),
        ),
    )
    con.execute(
        "delete from edgar_form4_transactions where symbol = ? and accession = ?",
        (normalized, accession),
    )
    fetched_at = datetime.now(UTC).isoformat()
    for transaction in transactions:
        con.execute(
            """
            insert into edgar_form4_transactions(
                symbol, accession, insider_name, insider_title, transaction_date,
                transaction_code, code_label, shares, price, shares_after,
                acquired_disposed, fetched_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized,
                str(accession),
                str(transaction["insider_name"]),
                transaction.get("insider_title"),
                str(transaction["transaction_date"]),
                transaction.get("transaction_code"),
                transaction.get("code_label"),
                transaction.get("shares"),
                transaction.get("price"),
                transaction.get("shares_after"),
                transaction.get("acquired_disposed"),
                fetched_at,
            ),
        )
    con.commit()


def load_form4_accessions(con, symbol):
    normalized = normalize_symbol(symbol)
    rows = con.execute(
        "select accession from edgar_form4_filings where symbol = ?",
        (normalized,),
    ).fetchall()
    return {row["accession"] for row in rows}


def load_form4_transactions(con, symbol, since=None):
    normalized = normalize_symbol(symbol)
    query = """
        select accession, insider_name, insider_title, transaction_date,
               transaction_code, code_label, shares, price, shares_after,
               acquired_disposed
        from edgar_form4_transactions
        where symbol = ?
    """
    params = [normalized]
    if since:
        query += " and transaction_date >= ?"
        params.append(since)
    query += " order by transaction_date desc, accession, insider_name"
    rows = con.execute(query, params).fetchall()
    return [dict(row) for row in rows]
