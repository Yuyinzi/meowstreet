from concurrent.futures import ThreadPoolExecutor, as_completed


def _latest_snapshot_per_month(rows):
    latest = {}
    for row in rows:
        key = (row["survey_type"], row["report_month"])
        current = latest.get(key)
        if current is None or (row["fetched_at"], row["source_url"]) >= (
            current["fetched_at"],
            current["source_url"],
        ):
            latest[key] = row
    return sorted(
        latest.values(),
        key=lambda row: (row["report_month"], row["fetched_at"], row["source_url"]),
    )


def select_snapshots(
    snapshots,
    *,
    latest_month=None,
    report_month=None,
    current_year=None,
    backfill_since=None,
    source_urls=None,
):
    rows = list(snapshots)
    requested_rows = []
    requested_urls = set(source_urls or [])
    if source_urls:
        rows_by_url = {row["source_url"]: row for row in rows}
        selected_urls = set()
        for source_url in source_urls:
            row = rows_by_url.get(source_url)
            if row is not None and source_url not in selected_urls:
                requested_rows.append(row)
                selected_urls.add(source_url)
    if report_month:
        rows = [row for row in rows if row["report_month"] == report_month]
    elif latest_month:
        rows = [row for row in rows if row["report_month"] == latest_month]
    elif current_year:
        rows = [
            row
            for row in rows
            if row["report_month"].startswith(f"{current_year}-")
        ]
    elif backfill_since:
        rows = [
            row
            for row in rows
            if row["report_month"] >= f"{backfill_since}-01-01"
        ]
    period_rows = _latest_snapshot_per_month(rows)
    if not source_urls:
        return period_rows
    if not (report_month or latest_month or current_year or backfill_since):
        return requested_rows
    return requested_rows + [
        row for row in period_rows if row["source_url"] not in requested_urls
    ]


def enrich_snapshots(snapshots, enrich_one, report_concurrency=1):
    rows = list(snapshots)
    if report_concurrency <= 1:
        results = []
        failed = 0
        for row in rows:
            try:
                results.append(enrich_one(row))
            except Exception:
                results.append(None)
                failed += 1
        return results, failed

    results = [None] * len(rows)
    failed = 0
    with ThreadPoolExecutor(max_workers=report_concurrency) as executor:
        futures = {
            executor.submit(enrich_one, row): index
            for index, row in enumerate(rows)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                results[index] = future.result()
            except Exception:
                failed += 1
    return results, failed
