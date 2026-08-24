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
    if source_urls:
        requested = {url: index for index, url in enumerate(source_urls)}
        return sorted(
            [row for row in rows if row["source_url"] in requested],
            key=lambda row: requested[row["source_url"]],
        )
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
    return _latest_snapshot_per_month(rows)


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
