from app.db.ticker_context import normalize_symbol
from app.services import job_notifications
from app.services import ticker_quant_context
from app.tools import benchmark_market_data


def _run(job_id, target, operation):
    handle = job_notifications.start_run(job_id, target=target, origin="manual")
    try:
        with job_notifications.bind_run(handle):
            result = operation()
    except KeyboardInterrupt:
        handle.interrupt()
        raise
    except Exception:
        handle.fail()
        raise
    limited = any(child["status"] in {"failed", "blocked", "completed_partial"} for child in handle.results.values())
    handle.complete("completed_partial" if limited else "succeeded", "Refresh completed with limitations" if limited else "Refresh completed")
    return result


def refresh_benchmark(benchmark_id):
    config = benchmark_market_data.benchmark_config(benchmark_id)
    target = config["benchmark_id"]
    return _run("benchmark_refresh", target, lambda: benchmark_market_data.refresh_benchmarks([target]))


def refresh_ticker(symbol, peer=None):
    target = normalize_symbol(symbol)
    normalized_peer = normalize_symbol(peer) if peer is not None else None
    return _run("ticker_refresh", target, lambda: ticker_quant_context.get_ticker_quant_context(
        target, peer=normalized_peer, force_refresh=True, include_catalyst=False,
    ))
