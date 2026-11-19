from app.tools.macro_data_freshness import evaluate_dataset


def build_audit_records(rows, before, after, observations, returned, catalog, at, importing):
    result = []
    for row in rows:
        evidence = observations.get(row['id'], {'availability': 'missing'})
        freshness = evaluate_dataset(row, evidence, catalog['schedules'][row['schedule_id']], at, catalog.get('market_calendars', {}))
        previous = before.get(row['id'])
        current = after.get(row['id'])
        source = returned.get(row['id'])
        returned_period = max(source) if source else None
        stored_period = evidence.get('current_period')
        issue = None
        warning = importing and freshness['status'] in {'due', 'missing', 'processing'}
        if importing and source is not None and current is not None and any(current.get(period) != value for period, value in source.items()):
            warning = True
            issue = 'persistence_mismatch'
        elif warning:
            issue = 'source_behind' if source is not None else 'stored_data_behind'
        if importing and evidence.get('availability') in {'unavailable', 'invalid'}:
            warning = True
            issue = 'audit_unavailable'
        if not importing:
            source_evidence = {'availability': 'available' if source else 'missing', 'current_period': returned_period}
            freshness = evaluate_dataset(row, source_evidence, catalog['schedules'][row['schedule_id']], at, catalog.get('market_calendars', {})) if source is not None else {'status': 'unknown', 'reason': 'Returned observation dates are not captured by this adapter', 'expected_release': freshness.get('expected_release')}
            warning = source is not None and freshness['status'] in {'due', 'missing'}
            issue = 'source_behind' if warning else None
        result.append({
            'dataset_id': row['id'], 'name': row['name'], 'checked_at': at.isoformat(),
            'expected_period': freshness.get('expected_period') or (freshness.get('expected_release') or {}).get('period'),
            'source_period': evidence.get('source_observation_date'),
            'returned_period': returned_period, 'returned_rows': len(source) if source is not None else None,
            'before_period': max(previous) if previous else None, 'stored_period': stored_period,
            'inserted': sum(period not in previous for period in current) if importing and previous is not None and current is not None else None,
            'updated': sum(period in previous and previous[period] != value for period, value in current.items()) if importing and previous is not None and current is not None else None,
            'freshness': freshness['status'], 'reason': freshness['reason'], 'warning': warning, 'issue': issue,
        })
    return result
