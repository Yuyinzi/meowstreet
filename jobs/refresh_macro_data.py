import argparse
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from threading import Event

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import fetch_fomc_documents
from scripts import fetch_ism_reports
from scripts import generate_fomc_minutes_structure
from scripts import generate_fomc_policy_tone
from scripts import import_consumer_sentiment
from scripts import import_economic_confirmation
from scripts import import_fomc_calendar
from scripts import import_gdp_market_relationships
from scripts import import_m2_money_supply
from scripts import import_nfib_sbet
from scripts import import_nfib_sbet_regional
from scripts import import_tracked_commodities
from scripts import import_cyclical_commodities
from scripts import import_dce_iron_ore_sina
from scripts import import_lumber
from scripts import import_oil
from scripts import import_shfe_copper
from scripts import import_us_building_permits
from scripts import import_us_corporate_credit
from scripts import import_us_macro_indicators
from scripts import import_us_rates_liquidity
from scripts import refresh_benchmark_market_data
from scripts import refresh_us_rates_liquidity

from app import llm
from app.services.macro_refresh_registry import build_refresh_tasks
from app.services.macro_refresh_executor import execute_tasks
from app.services.macro_refresh_output import install_output_routers
from app.services.macro_refresh_resources import ArtifactStore
from app.services.macro_refresh_resources import FredRateLimiter
from app.services.macro_refresh_resources import RequestCoordinator
from app.services.macro_refresh_resources import SQLiteWriterGate


def _timestamp():
    return datetime.now().replace(microsecond=0).isoformat()


def _task(name, func, argv, skip_reason=None):
    return {
        "name": name,
        "func": func,
        "argv": list(argv),
        "skip_reason": skip_reason,
    }


def _openai_enrichment_skip_reason(config):
    if config.get("api_key"):
        return None
    return "OPENAI_API_KEY is not configured"


def _run_task(task):
    if task["skip_reason"]:
        return {
            "name": task["name"],
            "status": "skipped",
            "exit_code": 0,
            "error": task["skip_reason"],
            "stdout": "",
            "stderr": "",
        }
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = task["func"](task["argv"])
    except Exception as exc:
        exit_code = 1
        error = str(exc)
    else:
        error = "" if not exit_code else f"exit code {exit_code}"
    return {
        "name": task["name"],
        "status": "ok" if not exit_code else "failed",
        "exit_code": int(exit_code or 0),
        "error": error,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
    }


def _result_counts(results):
    return {
        "ok": sum(result["status"] == "ok" for result in results),
        "skipped": sum(result["status"] == "skipped" for result in results),
        "failed": sum(result["status"] == "failed" for result in results),
    }


def _result_counts_with_blocked(results):
    counts = _result_counts(results)
    counts["blocked"] = sum(result["status"] == "blocked" for result in results)
    return counts


def _fomc_calendar_path(args):
    configured_path = (
        args.fomc_calendar_path or import_fomc_calendar.DEFAULT_CALENDAR_PATH
    )
    path = Path(configured_path)
    return path if path.exists() else None


def _consumer_cache_dir():
    return ROOT / "data" / "local_system" / "consumer_cache"


def _combined_consumer_refresh(consumer_main, cache_dir, db_path):
    fetch_exit = consumer_main(["--fetch-michigan-csv", str(cache_dir)])
    if fetch_exit:
        return fetch_exit
    table_1 = cache_dir / "table_1.csv"
    table_5 = cache_dir / "table_5.csv"
    import_exit = consumer_main(
        ["--michigan-csv-import", str(table_1), str(table_5), "--db-path", str(db_path)]
    )
    if import_exit:
        return import_exit
    front_page_exit = consumer_main(
        ["--fetch-front-page-import", "--db-path", str(db_path)]
    )
    if front_page_exit:
        return front_page_exit
    fred_fetch_exit = consumer_main(["--fetch-fred-csv", str(cache_dir)])
    if fred_fetch_exit:
        return fred_fetch_exit
    return consumer_main(
        ["--fred-csv-import", str(cache_dir), "--db-path", str(db_path)]
    )


def _planned_tasks(
    args,
    benchmark_main=None,
    rates_main=None,
    consumer_main=None,
    m2_main=None,
    building_permits_main=None,
    ism_reports_main=None,
    gdp_main=None,
    macro_indicators_main=None,
    fomc_main=None,
    fomc_document_main=None,
    fomc_policy_tone_main=None,
    fomc_minutes_main=None,
    nfib_main=None,
    nfib_regional_main=None,
    main=None,
    oil_main=None,
    tracked_commodities_main=None,
    lumber_main=None,
    shfe_copper_main=None,
    dce_iron_ore_sina_main=None,
    economic_confirmation_main=None,
    openai_config=None,
    credit_main=None,
    artifact_store=None,
):
    tasks = []
    if credit_main is not None:
        fred_tasks = build_refresh_tasks(
            args,
            {
                "rates": rates_main,
                "credit": credit_main,
                "m2": m2_main,
                "macro_indicators": macro_indicators_main,
                "gdp": gdp_main,
            },
            openai_config=openai_config,
            artifact_store=artifact_store or ArtifactStore(),
        )
        tasks.extend(fred_tasks)
        rates_main = None
        m2_main = None
        macro_indicators_main = None
        gdp_main = None
    if benchmark_main is not None and not args.skip_yahoo:
        tasks.append(_task(
            "benchmark_yahoo",
            benchmark_main,
            [
                "--benchmark-id",
                "us_sp500",
                "--benchmark-id",
                "us_nasdaq_100",
                "--benchmark-id",
                "us_nasdaq_composite",
                "--benchmark-id",
                "us_djia",
            ],
        ))
    if rates_main is not None and not args.skip_rates:
        tasks.append(_task("rates_fred", rates_main, []))
    if consumer_main is not None and not args.skip_consumer_sentiment:
        cache_dir = _consumer_cache_dir()
        consumer_db_path = ROOT / "data" / "local_system" / "market_data.sqlite"
        tasks.append(_task(
            "consumer_sentiment",
            lambda argv: _combined_consumer_refresh(
                consumer_main, cache_dir, consumer_db_path
            ),
            [],
        ))
    if m2_main is not None and not args.skip_m2:
        tasks.append(_task("m2_fred_fetch", m2_main, ["--fetch-fred-csv"]))
        tasks.append(_task("m2_fred_merge", m2_main, ["--fred-csv-merge"]))
    if macro_indicators_main is not None and not args.skip_macro_indicators:
        tasks.append(_task("macro_indicators_fred_fetch", macro_indicators_main, ["--fetch-fred-csv"]))
        tasks.append(_task("macro_indicators_fred_merge", macro_indicators_main, ["--fred-csv-merge"]))
    if building_permits_main is not None and not args.skip_building_permits:
        tasks.append(_task("building_permits_census", building_permits_main, []))
    if ism_reports_main is not None and not args.skip_ism:
        enrichment_skip_reason = _openai_enrichment_skip_reason(openai_config or {})
        tasks.extend(
            [
                _task(
                    "ism_manufacturing_official",
                    ism_reports_main,
                    [
                        "--survey",
                        "manufacturing",
                        "--latest-only",
                        "--core-only",
                    ],
                ),
                _task(
                    "ism_manufacturing_ai_enrichment",
                    ism_reports_main,
                    [
                        "--survey",
                        "manufacturing",
                        "--latest-only",
                        "--enrichment-only",
                    ],
                    enrichment_skip_reason,
                ),
                _task(
                    "ism_services_official",
                    ism_reports_main,
                    ["--survey", "services", "--latest-only", "--core-only"],
                ),
                _task(
                    "ism_services_ai_enrichment",
                    ism_reports_main,
                    [
                        "--survey",
                        "services",
                        "--latest-only",
                        "--enrichment-only",
                    ],
                    enrichment_skip_reason,
                ),
            ]
        )
    if gdp_main is not None and not args.skip_gdp:
        tasks.append(_task("gdp_fred_fetch", gdp_main, ["--fetch-fred-csv"]))
        tasks.append(_task("gdp_fred_merge", gdp_main, ["--us-csv-merge"]))
    if fomc_main is not None and not args.skip_fomc:
        calendar_path = _fomc_calendar_path(args)
        if calendar_path:
            tasks.extend(
                [
                    _task(
                        "fomc_calendar",
                        fomc_main,
                        ["--calendar-path", str(calendar_path)],
                    ),
                    _task("fomc_documents", fomc_document_main, ["--document-type", "all"]),
                    _task(
                        "fomc_policy_tone",
                        fomc_policy_tone_main,
                        ["--all"]
                        + (["--verbose"] if getattr(args, "verbose", False) else []),
                    ),
                    _task(
                        "fomc_minutes_structure",
                        fomc_minutes_main,
                        ["--all"]
                        + (["--verbose"] if getattr(args, "verbose", False) else []),
                    ),
                ]
            )
    if nfib_main is not None and not args.skip_nfib_sbo:
        tasks.append(_task("nfib_sbo_official", nfib_main, []))
    if nfib_regional_main is not None and not args.skip_nfib_sbo_regional:
        tasks.append(_task("nfib_sbo_regional_official", nfib_regional_main, []))
    if main is not None and not args.skip_cyclical_commodities:
        tasks.append(_task("cyclical_commodities_official", main, []))
    if oil_main is not None and not args.skip_oil:
        tasks.append(_task("oil_official", oil_main, []))
    if lumber_main is not None and not args.skip_lumber:
        tasks.append(_task("lumber_yahoo", lumber_main, []))
    if shfe_copper_main is not None and not getattr(args, "skip_shfe_copper", False):
        tasks.append(_task("shfe_copper", shfe_copper_main, ["--incremental"]))
    if dce_iron_ore_sina_main is not None and not args.skip_dce_iron_ore_sina:
        tasks.append(_task("dce_iron_ore_sina", dce_iron_ore_sina_main, []))
    if economic_confirmation_main is not None and not args.skip_economic_confirmation:
        tasks.append(_task("economic_confirmation_official", economic_confirmation_main, []))
    return tasks


def _write_report_text(text, *, file, progress):
    if not text:
        return
    if getattr(progress, "disable", False):
        print(text, end="", file=file)
        return
    for line in text.splitlines():
        progress.write(line, file=file)


def _write_report_line(message, *, file, progress):
    if getattr(progress, "disable", False):
        print(message, file=file)
    else:
        progress.write(message, file=file)


def _report_result(result, *, verbose, progress):
    replay_output = verbose or result["status"] == "failed"
    if replay_output:
        _write_report_text(result["stdout"], file=sys.stdout, progress=progress)
        _write_report_text(result["stderr"], file=sys.stderr, progress=progress)
    if result["status"] == "ok":
        message = f"{result['name']}: ok"
        file = sys.stdout
    elif result["status"] == "skipped":
        message = f"{result['name']}: skipped - {result['error']}"
        file = sys.stdout
    else:
        message = f"{result['name']}: failed - {result['error']}"
        file = sys.stderr
    _write_report_line(message, file=file, progress=progress)


class _ProgressReporter:
    def __init__(self, tasks, *, progress, verbose, stdout, stderr):
        self._tasks = {task["name"]: task for task in tasks}
        self._lane_order = []
        for task in tasks:
            if task["lane"] not in self._lane_order:
                self._lane_order.append(task["lane"])
        self._progress = progress
        self._verbose = verbose
        self._stdout = stdout
        self._stderr = stderr
        self._active = set()
        self._results = {}

    @property
    def results(self):
        return list(self._results.values())

    def handle_event(self, event):
        event_type = event["type"]
        task = event["task"]
        name = task["name"]
        if event_type == "task_started":
            self._active.add(name)
            self._refresh_description()
            return
        if event_type != "task_finished":
            return
        self._active.discard(name)
        result = event["result"]
        self._results[name] = result
        self._replay_output(result)
        self._progress.update(1)
        self._progress.set_postfix(
            _result_counts_with_blocked(self.results), refresh=False
        )
        self._refresh_description()
        result["stdout"] = ""
        result["stderr"] = ""

    def report_final(self, results):
        for result in sorted(results, key=self._plan_key):
            if result["name"] not in self._results:
                self._replay_output(result)
                self._progress.update(1)
                self._results[result["name"]] = result
            self._write_summary(result)
            result["stdout"] = ""
            result["stderr"] = ""

    def _plan_key(self, result):
        task = self._tasks.get(result["name"], {})
        return (task.get("plan_index", 0), result["name"])

    def _refresh_description(self):
        active_lanes = [
            lane
            for lane in self._lane_order
            if any(self._tasks[name]["lane"] == lane for name in self._active)
        ]
        description = "active lanes: " + ", ".join(active_lanes)
        self._progress.set_description_str(description)

    def _replay_output(self, result):
        if not (self._verbose or result["status"] in {"failed", "blocked"}):
            return
        prefix = _task_label(result)
        _write_prefixed_text(result.get("stdout", ""), prefix, self._stdout, self._progress)
        _write_prefixed_text(result.get("stderr", ""), prefix, self._stderr, self._progress)

    def _write_summary(self, result):
        prefix = _task_label(result)
        status = result["status"]
        if status == "ok":
            message = f"{prefix}: ok"
            target = self._stdout
        elif status == "skipped":
            message = f"{prefix}: skipped - {result['error']}"
            target = self._stdout
        else:
            message = f"{prefix}: {status} - {result['error']}"
            target = self._stderr
        _write_report_line(message, file=target, progress=self._progress)


def _write_prefixed_text(text, prefix, file, progress):
    if not text:
        return
    for line in text.splitlines():
        _write_report_line(f"{prefix}: {line}", file=file, progress=progress)


def _task_label(result):
    lane = result["lane"]
    name = result["name"]
    return name if name.startswith(f"{lane}.") else f"{lane}.{name}"


def _build_task_providers(values):
    mapping = {
        "benchmarks_fetch": values.get("benchmark_main"),
        "benchmarks_import": values.get("benchmark_main"),
        "rates": values.get("rates_main"),
        "credit": values.get("credit_main"),
        "consumer_michigan_fetch": values.get("consumer_main"),
        "consumer_michigan_import": values.get("consumer_main"),
        "consumer_fred_fetch": values.get("consumer_main"),
        "consumer_fred_import": values.get("consumer_main"),
        "m2": values.get("m2_main"),
        "building_permits_fetch": values.get("building_permits_main"),
        "building_permits_import": values.get("building_permits_main"),
        "macro_indicators": values.get("macro_indicators_main"),
        "gdp": values.get("gdp_main"),
        "ism_manufacturing_fetch": values.get("ism_reports_main"),
        "ism_manufacturing_import": values.get("ism_reports_main"),
        "ism_manufacturing_enrichment": values.get("ism_reports_main"),
        "ism_manufacturing_enrichment_import": values.get("ism_reports_main"),
        "ism_services_fetch": values.get("ism_reports_main"),
        "ism_services_import": values.get("ism_reports_main"),
        "ism_services_enrichment": values.get("ism_reports_main"),
        "ism_services_enrichment_import": values.get("ism_reports_main"),
        "fomc_calendar_import": values.get("fomc_main"),
        "fomc_documents_fetch": values.get("fomc_document_main"),
        "fomc_documents_import": values.get("fomc_document_main"),
        "fomc_policy_tone_extract": values.get("fomc_policy_tone_main"),
        "fomc_policy_tone_import": values.get("fomc_policy_tone_main"),
        "fomc_minutes_extract": values.get("fomc_minutes_main"),
        "fomc_minutes_import": values.get("fomc_minutes_main"),
        "nfib_fetch": values.get("nfib_main"),
        "nfib_import": values.get("nfib_main"),
        "nfib_regional_fetch": values.get("nfib_regional_main"),
        "nfib_regional_import": values.get("nfib_regional_main"),
        "tracked_commodities_fetch": values.get("tracked_commodities_main"),
        "tracked_commodities_import": values.get("tracked_commodities_main"),
        "cyclical_cot_fetch": values.get("main"),
        "cyclical_cot_import": values.get("main"),
        "oil_fetch": values.get("oil_main"),
        "oil_import": values.get("oil_main"),
        "lumber_fetch": values.get("lumber_main"),
        "lumber_import": values.get("lumber_main"),
        "shfe_copper_fetch": values.get("shfe_copper_main"),
        "shfe_copper_import": values.get("shfe_copper_main"),
        "dce_iron_ore_sina_fetch": values.get("dce_iron_ore_sina_main"),
        "dce_iron_ore_sina_import": values.get("dce_iron_ore_sina_main"),
        "dol_fetch": values.get("economic_confirmation_main"),
        "dol_import": values.get("economic_confirmation_main"),
        "bls_fetch": values.get("economic_confirmation_main"),
        "bls_import": values.get("economic_confirmation_main"),
        "federal_reserve_fetch": values.get("economic_confirmation_main"),
        "federal_reserve_import": values.get("economic_confirmation_main"),
    }
    return {key: value for key, value in mapping.items() if value is not None}


def run(
    argv=None,
    *,
    task_providers=None,
    artifact_store=None,
    executor=execute_tasks,
    progress_factory=tqdm,
    openai_config=None,
    benchmark_main=None,
    rates_main=None,
    consumer_main=None,
    m2_main=None,
    building_permits_main=None,
    ism_reports_main=None,
    gdp_main=None,
    macro_indicators_main=None,
    fomc_main=None,
    fomc_document_main=None,
    fomc_policy_tone_main=None,
    fomc_minutes_main=None,
    nfib_main=None,
    nfib_regional_main=None,
    main=None,
    oil_main=None,
    tracked_commodities_main=None,
    lumber_main=None,
    shfe_copper_main=None,
    dce_iron_ore_sina_main=None,
    economic_confirmation_main=None,
    credit_main=None,
):
    parser = argparse.ArgumentParser(description="Refresh macro dashboard market data")
    parser.add_argument("--skip-yahoo", action="store_true")
    parser.add_argument("--skip-rates", action="store_true")
    parser.add_argument("--skip-consumer-sentiment", action="store_true")
    parser.add_argument("--skip-m2", action="store_true")
    parser.add_argument("--skip-macro-indicators", action="store_true")
    parser.add_argument("--skip-building-permits", action="store_true")
    parser.add_argument("--skip-ism", action="store_true")
    parser.add_argument("--skip-gdp", action="store_true")
    parser.add_argument("--skip-fomc", action="store_true")
    parser.add_argument("--skip-nfib-sbo", action="store_true")
    parser.add_argument("--skip-nfib-sbo-regional", action="store_true")
    parser.add_argument("--skip-tracked-commodities", action="store_true")
    parser.add_argument("--skip-cyclical-commodities", action="store_true")
    parser.add_argument("--skip-oil", action="store_true")
    parser.add_argument("--skip-lumber", action="store_true")
    parser.add_argument("--skip-shfe-copper", action="store_true")
    parser.add_argument("--skip-dce-iron-ore-sina", action="store_true")
    parser.add_argument("--skip-economic-confirmation", action="store_true")
    parser.add_argument("--fomc-calendar-path", type=Path)
    parser.add_argument("--initial", action="store_true")
    parser.add_argument("--serial", action="store_true", help="run refresh lanes serially")
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="stop running remaining refresh tasks after the first failure",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if openai_config is None:
        openai_config = llm.load_openai_config(args, root=ROOT)
    real_stdout = sys.stdout
    real_stderr = sys.stderr
    print(f"macro data refresh started: {_timestamp()}", file=real_stdout)

    if task_providers is None:
        tasks = _planned_tasks(
            args,
            benchmark_main,
            rates_main,
            consumer_main,
            m2_main,
            building_permits_main,
            ism_reports_main,
            gdp_main,
            macro_indicators_main,
            fomc_main,
            fomc_document_main,
            fomc_policy_tone_main,
            fomc_minutes_main,
            nfib_main,
            nfib_regional_main,
            main,
            oil_main,
            tracked_commodities_main,
            lumber_main,
            shfe_copper_main,
            dce_iron_ore_sina_main,
            economic_confirmation_main,
            openai_config,
            credit_main,
            artifact_store,
        )
        results = []
        with progress_factory(
            total=len(tasks),
            disable=not real_stderr.isatty(),
            file=real_stderr,
        ) as progress:
            for task in tasks:
                progress.set_description_str(task["name"])
                result = _run_task(task)
                _report_result(result, verbose=args.verbose, progress=progress)
                result["stdout"] = ""
                result["stderr"] = ""
                results.append(result)
                progress.set_postfix(_result_counts(results), refresh=False)
                progress.update(1)
                if result["status"] == "failed" and args.stop_on_error:
                    break
        counts = _result_counts(results)
        print(
            "macro data refresh completed: "
            f"ok={counts['ok']} skipped={counts['skipped']} failed={counts['failed']}",
            file=real_stdout,
        )
        return 1 if counts["failed"] else 0

    store = artifact_store if artifact_store is not None else ArtifactStore()
    tasks = build_refresh_tasks(
        args,
        task_providers,
        openai_config=openai_config,
        artifact_store=store,
    )
    cancel_event = Event()
    coordinator = RequestCoordinator(FredRateLimiter())
    writer_gate = SQLiteWriterGate()
    with progress_factory(
        total=len(tasks),
        disable=not real_stderr.isatty(),
        file=real_stderr,
    ) as progress:
        reporter = _ProgressReporter(
            tasks,
            progress=progress,
            verbose=args.verbose,
            stdout=real_stdout,
            stderr=real_stderr,
        )
        try:
            with install_output_routers(
                stdout=real_stdout,
                stderr=real_stderr,
            ) as streams:
                results = executor(
                    tasks,
                    serial=args.serial,
                    stop_on_error=args.stop_on_error,
                    request_coordinator=coordinator,
                    writer_gate=writer_gate,
                    on_event=reporter.handle_event,
                    cancel_event=cancel_event,
                    stdout_router=streams["stdout"],
                    stderr_router=streams["stderr"],
                )
        except KeyboardInterrupt:
            cancel_event.set()
            reporter.report_final(reporter.results)
            print("macro data refresh interrupted", file=real_stderr)
            return 130
        reporter.report_final(results)
    counts = _result_counts_with_blocked(results)
    print(
        "macro data refresh completed: "
        f"ok={counts['ok']} skipped={counts['skipped']} "
        f"failed={counts['failed']} blocked={counts['blocked']}",
        file=real_stdout,
    )
    return 1 if counts["failed"] or counts["blocked"] else 0


def main(argv=None):
    return run(
        argv,
        task_providers=_build_task_providers(
            {
                "benchmark_main": refresh_benchmark_market_data.main,
                "rates_main": import_us_rates_liquidity.main,
                "credit_main": import_us_corporate_credit.main,
                "consumer_main": import_consumer_sentiment.main,
                "m2_main": import_m2_money_supply.main,
                "building_permits_main": import_us_building_permits.main,
                "ism_reports_main": fetch_ism_reports.main,
                "gdp_main": import_gdp_market_relationships.main,
                "macro_indicators_main": import_us_macro_indicators.main,
                "fomc_main": import_fomc_calendar.main,
                "fomc_document_main": fetch_fomc_documents.main,
                "fomc_policy_tone_main": generate_fomc_policy_tone.main,
                "fomc_minutes_main": generate_fomc_minutes_structure.main,
                "nfib_main": import_nfib_sbet.main,
                "nfib_regional_main": import_nfib_sbet_regional.main,
                "main": import_cyclical_commodities.main,
                "oil_main": import_oil.main,
                "tracked_commodities_main": import_tracked_commodities.main,
                "lumber_main": import_lumber.main,
                "shfe_copper_main": import_shfe_copper.main,
                "dce_iron_ore_sina_main": import_dce_iron_ore_sina.main,
                "economic_confirmation_main": import_economic_confirmation.main,
            }
        ),
        benchmark_main=refresh_benchmark_market_data.main,
        rates_main=import_us_rates_liquidity.main,
        credit_main=import_us_corporate_credit.main,
        consumer_main=import_consumer_sentiment.main,
        m2_main=import_m2_money_supply.main,
        building_permits_main=import_us_building_permits.main,
        ism_reports_main=fetch_ism_reports.main,
        gdp_main=import_gdp_market_relationships.main,
        macro_indicators_main=import_us_macro_indicators.main,
        fomc_main=import_fomc_calendar.main,
        fomc_document_main=fetch_fomc_documents.main,
        fomc_policy_tone_main=generate_fomc_policy_tone.main,
        fomc_minutes_main=generate_fomc_minutes_structure.main,
        nfib_main=import_nfib_sbet.main,
        nfib_regional_main=import_nfib_sbet_regional.main,
        main=import_cyclical_commodities.main,
        oil_main=import_oil.main,
        tracked_commodities_main=import_tracked_commodities.main,
        lumber_main=import_lumber.main,
        shfe_copper_main=import_shfe_copper.main,
        dce_iron_ore_sina_main=import_dce_iron_ore_sina.main,
        economic_confirmation_main=import_economic_confirmation.main,
    )


if __name__ == "__main__":
    raise SystemExit(main())
