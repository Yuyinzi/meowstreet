from datetime import date
from math import isclose, isfinite
from sqlite3 import Row, connect as sqlite_connect


_TABLES = {"macro": "macro_indicator_points", "rate": "us_rate_points"}
_BASES = {"captured_at_import", "reconstructed_from_cached_source"}
_SCHEMA = """create table if not exists macro_source_lineage (
    dataset_id text not null,
    observation_date text not null,
    value real not null,
    source_date text not null,
    source_series_id text not null,
    source_hash text not null,
    basis text not null,
    primary key(dataset_id, observation_date)
)"""


def connect(db_path):
    con = sqlite_connect(f"{db_path.resolve().as_uri()}?mode=rw", uri=True)
    con.row_factory = Row
    return con


def _validate(rows, basis):
    if basis not in _BASES:
        raise ValueError("lineage verification basis is invalid")
    for row in rows:
        if date.fromisoformat(row["source_date"]) > date.fromisoformat(row["date"]):
            raise ValueError("lineage source date exceeds the stored date")
        if not isfinite(row["value"]) or not row["source_series_id"] or len(row["source_hash"]) != 64:
            raise ValueError("lineage source evidence is invalid")


def replace_lineage(con, dataset_id, rows, basis):
    _validate(rows, basis)
    con.execute(_SCHEMA)
    with con:
        con.execute("delete from macro_source_lineage where dataset_id=?", (dataset_id,))
        con.executemany("insert into macro_source_lineage values(?,?,?,?,?,?,?)", [(dataset_id, r["date"], r["value"], r["source_date"], r["source_series_id"], r["source_hash"], basis) for r in rows])
    return len(rows)


def merge_reconstructed_lineage(con, dataset_id, rows):
    _validate(rows, "reconstructed_from_cached_source")
    con.execute(_SCHEMA)
    existing = {row[0]: row for row in con.execute("select observation_date,value,source_date,source_series_id,basis from macro_source_lineage where dataset_id=?", (dataset_id,))}
    conflicts = 0
    with con:
        for row in rows:
            previous = existing.get(row["date"])
            if previous and isclose(previous[1], row["value"], rel_tol=1e-12, abs_tol=1e-12):
                if previous[4] == "conflicting" or previous[2:4] != (row["source_date"], row["source_series_id"]):
                    con.execute("update macro_source_lineage set basis='conflicting' where dataset_id=? and observation_date=?", (dataset_id, row["date"]))
                    conflicts += 1
                continue
            con.execute("insert into macro_source_lineage values(?,?,?,?,?,?,?) on conflict(dataset_id,observation_date) do update set value=excluded.value,source_date=excluded.source_date,source_series_id=excluded.source_series_id,source_hash=excluded.source_hash,basis=excluded.basis", (dataset_id, row["date"], row["value"], row["source_date"], row["source_series_id"], row["source_hash"], "reconstructed_from_cached_source"))
    return conflicts


def load_stored_points(con, storage):
    table = _TABLES[storage["kind"]]
    return [dict(row) for row in con.execute(f"select date,value from {table} where series_id=? order by date", (storage["key"],))]


def matching_lineage(stored, reconstructed):
    values = {row["date"]: row["value"] for row in stored}
    return [row for row in reconstructed if row["date"] in values and isinstance(values[row["date"]], (int, float)) and isclose(row["value"], values[row["date"]], rel_tol=1e-12, abs_tol=1e-12)]
