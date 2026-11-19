from pathlib import Path
from sqlite3 import connect


_POINT_STORES = {
    'macro': ('macro_indicator_points', 'series_id', 'date', 'value'),
    'rate': ('us_rate_points', 'series_id', 'date', 'value'),
    'benchmark': ('benchmark_prices', 'benchmark_id', 'date', 'close'),
}


def load_point_snapshots(datasets, db_path):
    supported = [row for row in datasets if row['storage']['kind'] in _POINT_STORES]
    if not Path(db_path).exists():
        return {row['id']: {} for row in supported}
    con = connect(f'{Path(db_path).resolve().as_uri()}?mode=ro', uri=True, timeout=5)
    try:
        con.execute('pragma query_only=on')
        con.execute('begin')
        result = {}
        tables = {row[0] for row in con.execute("select name from sqlite_master where type='table'")}
        for row in supported:
            table, key, period, value = _POINT_STORES[row['storage']['kind']]
            result[row['id']] = dict(con.execute(f'select {period},{value} from {table} where {key}=?', (row['storage']['key'],))) if table in tables else {}
        return result
    finally:
        con.close()
