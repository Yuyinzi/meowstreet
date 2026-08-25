from argparse import Namespace
from threading import Event
import sys
from io import StringIO

from jobs import refresh_macro_data


class FakeProgress:
    def __init__(self, *, total, disable, file):
        self.total = total
        self.disable = disable
        self.file = file
        self.updated = 0
        self.descriptions = []
        self.postfixes = []
        self.writes = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def set_description_str(self, value):
        self.descriptions.append(value)

    def set_postfix(self, value, refresh=False):
        self.postfixes.append(dict(value))

    def update(self, amount):
        self.updated += amount

    def write(self, message, file):
        self.writes.append((message, file))
        print(message, file=file)


def test_run_task_captures_success_output():
    def noisy(argv):
        print("provider stdout")
        print("provider stderr", file=refresh_macro_data.sys.stderr)
        return 0

    result = refresh_macro_data._run_task(
        refresh_macro_data._task("provider", noisy, [])
    )

    assert result == {
        "name": "provider",
        "status": "ok",
        "exit_code": 0,
        "error": "",
        "stdout": "provider stdout\n",
        "stderr": "provider stderr\n",
    }


def test_run_task_returns_skip_without_calling_function():
    task = refresh_macro_data._task(
        "optional",
        lambda argv: (_ for _ in ()).throw(AssertionError("must not run")),
        [],
        skip_reason="OPENAI_API_KEY is not configured",
    )

    result = refresh_macro_data._run_task(task)

    assert result["status"] == "skipped"
    assert result["error"] == "OPENAI_API_KEY is not configured"
    assert result["exit_code"] == 0
    assert result["stdout"] == ""
    assert result["stderr"] == ""


def test_run_task_captures_output_before_exception():
    def raising(argv):
        print("before failure")
        print("diagnostic", file=refresh_macro_data.sys.stderr)
        raise ValueError("provider unavailable")

    result = refresh_macro_data._run_task(
        refresh_macro_data._task("provider", raising, [])
    )

    assert result["status"] == "failed"
    assert result["exit_code"] == 1
    assert result["error"] == "provider unavailable"
    assert result["stdout"] == "before failure\n"
    assert result["stderr"] == "diagnostic\n"


def test_result_counts_separate_success_skips_and_failures():
    results = [
        {"status": "ok"},
        {"status": "skipped"},
        {"status": "failed"},
        {"status": "ok"},
    ]

    assert refresh_macro_data._result_counts(results) == {
        "ok": 2,
        "skipped": 1,
        "failed": 1,
    }


def test_progress_advances_for_registry_results(monkeypatch, capsys):
    progress_instances = []

    def progress_factory(**kwargs):
        instance = FakeProgress(**kwargs)
        progress_instances.append(instance)
        return instance

    monkeypatch.setattr(refresh_macro_data.sys.stderr, "isatty", lambda: True)

    exit_code = refresh_macro_data.run(
        _task9_skip_args(),
        task_providers={
            "rates_fetch": lambda argv: 0,
            "rates_import": lambda argv: 1,
        },
        openai_config={"api_key": None},
        progress_factory=progress_factory,
    )

    captured = capsys.readouterr()
    progress = progress_instances[0]
    assert exit_code == 1
    assert progress.total == 2
    assert progress.updated == 2
    assert progress.postfixes[-1] == {"ok": 1, "skipped": 0, "failed": 1, "blocked": 0}
    assert "macro data refresh completed: ok=1 skipped=0 failed=1 blocked=0" in captured.out


def test_report_hides_success_output_by_default_but_replays_failure_output(capsys):
    result = {
        "name": "provider",
        "status": "failed",
        "exit_code": 1,
        "error": "exit code 1",
        "stdout": "provider stdout\n",
        "stderr": "provider stderr\n",
    }

    refresh_macro_data._report_result(result, verbose=False, progress=FakeProgress(total=1, disable=True, file=sys.stderr))

    captured = capsys.readouterr()
    assert "provider stdout" in captured.out
    assert "provider stderr" in captured.err
    assert "provider: failed - exit code 1" in captured.err


def test_verbose_replays_success_output_and_captured_strings_are_cleared(monkeypatch, capsys):
    monkeypatch.setattr(refresh_macro_data.sys.stderr, "isatty", lambda: False)

    exit_code = refresh_macro_data.run(
        ["--verbose", *_task9_skip_args()],
        task_providers={
            "rates_fetch": lambda argv: print("details") or 0,
            "rates_import": lambda argv: 0,
        },
        openai_config={"api_key": None},
        progress_factory=FakeProgress,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "details" in captured.out
    assert "fred_macro.rates_fred_fetch: ok" in captured.out


def test_success_output_is_hidden_without_verbose(monkeypatch, capsys):
    monkeypatch.setattr(refresh_macro_data.sys.stderr, "isatty", lambda: False)

    exit_code = refresh_macro_data.run(
        _task9_skip_args(),
        task_providers={
            "rates_fetch": lambda argv: print("details") or 0,
            "rates_import": lambda argv: 0,
        },
        openai_config={"api_key": None},
        progress_factory=FakeProgress,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "details" not in captured.out
    assert "fred_macro.rates_fred_fetch: ok" in captured.out


def test_stop_on_error_blocks_only_the_failed_registry_lane(monkeypatch):
    calls = []
    monkeypatch.setattr(refresh_macro_data.sys.stderr, "isatty", lambda: False)

    exit_code = refresh_macro_data.run(
        ["--stop-on-error", *_task9_skip_args()],
        task_providers={
            "rates_fetch": lambda argv: calls.append("fetch") or 1,
            "rates_import": lambda argv: calls.append("persist") or 0,
        },
        openai_config={"api_key": None},
        progress_factory=FakeProgress,
    )

    assert exit_code == 1
    assert calls == ["fetch"]


def test_progress_is_disabled_when_stderr_is_not_a_tty(monkeypatch):
    progress_instances = []

    def progress_factory(**kwargs):
        instance = FakeProgress(**kwargs)
        progress_instances.append(instance)
        return instance

    monkeypatch.setattr(refresh_macro_data.sys.stderr, "isatty", lambda: False)

    assert refresh_macro_data.run(
        _task9_skip_args(),
        openai_config={"api_key": None},
        progress_factory=progress_factory,
    ) == 0
    assert progress_instances[0].disable is True


def test_non_tty_verbose_output_replays_in_plan_order_regardless_of_completion_order():
    tasks = [
        {"name": "first", "lane": "a", "plan_index": 0},
        {"name": "second", "lane": "b", "plan_index": 1},
    ]
    results = {
        "first": {
            "name": "first",
            "lane": "a",
            "status": "ok",
            "error": "",
            "stdout": "first details\n",
            "stderr": "",
        },
        "second": {
            "name": "second",
            "lane": "b",
            "status": "failed",
            "error": "second failed",
            "stdout": "second details\n",
            "stderr": "second diagnostic\n",
        },
    }

    def replay(order):
        stdout = StringIO()
        stderr = StringIO()
        reporter = refresh_macro_data._ProgressReporter(
            tasks,
            progress=FakeProgress(total=2, disable=True, file=stderr),
            verbose=True,
            stdout=stdout,
            stderr=stderr,
        )
        for name in order:
            task = tasks[0 if name == "first" else 1]
            reporter.handle_event(
                {"type": "task_finished", "task": task, "result": dict(results[name])}
            )
        reporter.report_final([dict(results["first"]), dict(results["second"])])
        return stdout.getvalue(), stderr.getvalue()

    assert replay(["first", "second"]) == replay(["second", "first"])


def args_without_skips():
    return Namespace(
        skip_yahoo=False,
        skip_rates=False,
        skip_consumer_sentiment=False,
        skip_m2=False,
        skip_macro_indicators=False,
        skip_building_permits=False,
        skip_ism=False,
        skip_gdp=False,
        skip_fomc=False,
        skip_nfib_sbo=False,
        skip_nfib_sbo_regional=False,
        skip_cyclical_commodities=False,
        skip_oil=False,
        skip_tracked_commodities=False,
        skip_lumber=False,
        skip_dce_iron_ore_sina=False,
        skip_economic_confirmation=False,
        fomc_calendar_path=None,
        stop_on_error=False,
        verbose=False,
    )


def fake_benchmark_main(argv):
    return 0


def fake_rates_main(argv):
    return 0


def fake_consumer_main(argv):
    return 0


def fake_m2_main(argv):
    return 0


def fake_building_permits_main(argv):
    return 0


def fake_ism_reports_main(argv):
    return 0


def fake_gdp_main(argv):
    return 0


def fake_lumber_main(argv):
    return 0


def test_ism_plans_core_and_skipped_enrichment_without_key():
    tasks = refresh_macro_data._planned_tasks(
        args_without_skips(),
        ism_reports_main=fake_ism_reports_main,
        openai_config={"api_key": None},
    )
    ism_tasks = [task for task in tasks if task["name"].startswith("ism_")]

    assert [
        (task["name"], task["argv"], task["skip_reason"])
        for task in ism_tasks
    ] == [
        (
            "ism_manufacturing_official",
            ["--survey", "manufacturing", "--latest-only", "--core-only"],
            None,
        ),
        (
            "ism_manufacturing_ai_enrichment",
            ["--survey", "manufacturing", "--latest-only", "--enrichment-only"],
            "OPENAI_API_KEY is not configured",
        ),
        (
            "ism_services_official",
            ["--survey", "services", "--latest-only", "--core-only"],
            None,
        ),
        (
            "ism_services_ai_enrichment",
            ["--survey", "services", "--latest-only", "--enrichment-only"],
            "OPENAI_API_KEY is not configured",
        ),
    ]


def test_ism_enrichment_is_runnable_when_key_exists():
    tasks = refresh_macro_data._planned_tasks(
        args_without_skips(),
        ism_reports_main=fake_ism_reports_main,
        openai_config={"api_key": "configured"},
    )

    enrichment = [task for task in tasks if task["name"].endswith("ai_enrichment")]
    assert len(enrichment) == 2
    assert all(task["skip_reason"] is None for task in enrichment)


def test_skip_ism_removes_all_four_ism_tasks():
    args = args_without_skips()
    args.skip_ism = True

    tasks = refresh_macro_data._planned_tasks(
        args,
        ism_reports_main=fake_ism_reports_main,
        openai_config={"api_key": "configured"},
    )

    assert not [task for task in tasks if task["name"].startswith("ism_")]


def test_main_refreshes_official_building_permits_when_enabled():
    calls = []

    def permits_main(argv):
        calls.append(argv)
        return 0

    exit_code = refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-fomc",
        ],
        building_permits_main=permits_main,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )

    assert exit_code == 0
    assert calls == [["--fetch-census-workbook"], ["--import-census-workbook"]]


def test_main_runs_market_and_fred_refreshes_through_staged_registry(capsys):
    calls = []

    def benchmark_main(argv):
        calls.append(("benchmark", argv))
        return 0

    def rates_main(argv):
        calls.append(("rates", argv))
        return 0

    def consumer_main(argv):
        calls.append(("consumer", argv))
        return 0

    def m2_main(argv):
        calls.append(("m2", argv))
        return 0

    def gdp_main(argv):
        calls.append(("gdp", argv))
        return 0

    def ism_reports_main(argv):
        calls.append(("ism_reports", argv))
        return 0

    exit_code = refresh_macro_data.run(
        ["--skip-fomc"],
        benchmark_main=benchmark_main,
        rates_main=rates_main,
        consumer_main=consumer_main,
        m2_main=m2_main,
        building_permits_main=lambda argv: 0,
        ism_reports_main=ism_reports_main,
        gdp_main=gdp_main,
        fomc_main=lambda argv: 0,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )

    assert exit_code == 0
    assert (
        "benchmark",
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
    ) in calls
    assert ("rates", ["--fetch-fred-csv"]) in calls
    assert ("rates", ["--fred-csv-merge"]) in calls
    assert ("consumer", ["--fetch-michigan-csv", "data/local_system/consumer_cache"]) in calls
    out = capsys.readouterr().out
    assert "macro data refresh started" in out
    assert "yahoo.benchmarks_import: ok" in out
    assert "macro data refresh completed: ok=" in out


def test_main_does_not_generate_ai_interpretations():
    calls = []

    def recorder(label):
        def _record(argv):
            calls.append((label, argv))
            return 0

        return _record

    exit_code = refresh_macro_data.run(
        ["--skip-fomc"],
        benchmark_main=recorder("benchmark"),
        rates_main=recorder("rates"),
        consumer_main=recorder("consumer"),
        m2_main=recorder("m2"),
        building_permits_main=lambda argv: 0,
        ism_reports_main=recorder("ism_reports"),
        gdp_main=recorder("gdp"),
        fomc_main=recorder("fomc"),
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )

    assert exit_code == 0
    flattened_args = [arg for _, argv in calls for arg in argv]
    assert "--generate-credit-interpretation" not in flattened_args
    assert "--generate-interpretation" not in flattened_args


def test_main_continues_after_provider_failure(capsys):
    calls = []

    def failing_benchmark(argv):
        calls.append(("benchmark", argv))
        return 1

    def ok_task(label):
        def _ok(argv):
            calls.append((label, argv))
            return 0

        return _ok

    exit_code = refresh_macro_data.run(
        ["--skip-fomc"],
        benchmark_main=failing_benchmark,
        rates_main=ok_task("rates"),
        consumer_main=lambda argv: 0,
        m2_main=ok_task("m2"),
        building_permits_main=lambda argv: 0,
        ism_reports_main=lambda argv: 0,
        gdp_main=ok_task("gdp"),
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
        openai_config={"api_key": None},
    )

    assert exit_code == 1
    assert ("benchmark", [
        "--benchmark-id", "us_sp500", "--benchmark-id", "us_nasdaq_100",
        "--benchmark-id", "us_nasdaq_composite", "--benchmark-id", "us_djia",
    ]) in calls
    assert ("rates", ["--fetch-fred-csv"]) in calls
    assert ("m2", ["--fetch-fred-csv"]) in calls
    assert ("gdp", ["--fetch-fred-csv"]) in calls
    captured = capsys.readouterr()
    assert "yahoo.benchmarks_import: failed - exit code 1" in captured.err
    assert "failed=1 blocked=0" in captured.out


def test_main_can_stop_after_first_failure():
    calls = []

    def failing_benchmark(argv):
        calls.append(("benchmark", argv))
        return 1

    def ok_task(label):
        def _ok(argv):
            calls.append((label, argv))
            return 0

        return _ok

    exit_code = refresh_macro_data.run(
        ["--stop-on-error", "--skip-fomc"],
        benchmark_main=failing_benchmark,
        rates_main=ok_task("rates"),
        consumer_main=lambda argv: 0,
        m2_main=ok_task("m2"),
        building_permits_main=lambda argv: 0,
        ism_reports_main=lambda argv: 0,
        gdp_main=ok_task("gdp"),
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )

    assert exit_code == 1
    assert (
        "benchmark",
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
    ) in calls
    assert ("rates", ["--fetch-fred-csv"]) in calls


def test_main_records_exceptions_as_failures(capsys):
    def raising_benchmark(argv):
        raise ValueError("yahoo rate limited")

    exit_code = refresh_macro_data.run(
        [
            "--skip-rates",
            "--skip-m2",
            "--skip-gdp",
            "--skip-consumer-sentiment",
            "--skip-fomc",
        ],
        benchmark_main=raising_benchmark,
        rates_main=lambda argv: 0,
        consumer_main=lambda argv: 0,
        m2_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        gdp_main=lambda argv: 0,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "yahoo.benchmarks_import: failed - yahoo rate limited" in captured.err


def test_refresh_macro_data_skips_fomc_when_calendar_csv_is_missing(tmp_path):
    calls = []

    def fake_task(argv):
        calls.append(argv)
        return 0

    exit_code = refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-consumer-sentiment",
            "--fomc-calendar-path",
            str(tmp_path / "missing_fomc_calendar.csv"),
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        fomc_main=fake_task,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )

    assert exit_code == 0
    assert calls == []


def test_production_runtime_omits_fomc_graph_when_default_calendar_is_missing(
    tmp_path, monkeypatch
):
    calls = []
    missing_path = tmp_path / "missing-fomc-calendar.csv"
    monkeypatch.setattr(
        refresh_macro_data.import_fomc_calendar,
        "DEFAULT_CALENDAR_PATH",
        missing_path,
    )

    exit_code = refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-m2",
            "--skip-macro-indicators",
            "--skip-consumer-sentiment",
            "--skip-building-permits",
            "--skip-ism",
            "--skip-gdp",
            "--skip-nfib-sbo",
            "--skip-nfib-sbo-regional",
            "--skip-tracked-commodities",
            "--skip-cyclical-commodities",
            "--skip-oil",
            "--skip-lumber",
            "--skip-shfe-copper",
            "--skip-dce-iron-ore-sina",
            "--skip-economic-confirmation",
        ],
        task_providers={
            "credit_fetch": lambda argv: 0,
            "credit_import": lambda argv: 0,
            "fomc_calendar_import": lambda argv: calls.append("calendar") or 0,
            "fomc_documents_fetch": lambda argv: calls.append("documents") or 0,
            "fomc_documents_import": lambda argv: calls.append("documents_import") or 0,
            "fomc_policy_tone_extract": lambda argv: calls.append("tone") or 0,
            "fomc_policy_tone_import": lambda argv: calls.append("tone_import") or 0,
            "fomc_minutes_extract": lambda argv: calls.append("minutes") or 0,
            "fomc_minutes_import": lambda argv: calls.append("minutes_import") or 0,
        },
        openai_config={"api_key": None},
        progress_factory=FakeProgress,
        use_runtime_defaults=True,
    )

    assert exit_code == 0
    assert calls == []


def test_refresh_macro_data_imports_fomc_when_calendar_csv_exists(tmp_path):
    calls = []
    csv_path = tmp_path / "fomc_calendar.csv"
    csv_path.write_text(
        "start_date,end_date,title,has_sep,url\n"
        "2026-07-28,2026-07-29,FOMC Meeting,0,https://example.test/fomc\n",
        encoding="utf-8",
    )

    def fake_task(argv):
        calls.append(argv)
        return 0

    exit_code = refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-consumer-sentiment",
            "--fomc-calendar-path",
            str(csv_path),
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        fomc_main=fake_task,
        fomc_document_main=lambda argv: 0,
        fomc_policy_tone_main=lambda argv: 0,
        fomc_minutes_main=lambda argv: 0,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )

    assert exit_code == 0
    assert calls == [["--calendar-path", str(csv_path)]]


def test_main_skip_flags_remove_tasks():
    calls = []

    def recorder(label):
        def _record(argv):
            calls.append((label, argv))
            return 0

        return _record

    exit_code = refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-ism",
            "--skip-gdp",
            "--skip-consumer-sentiment",
            "--skip-fomc",
        ],
        benchmark_main=recorder("benchmark"),
        rates_main=recorder("rates"),
        consumer_main=lambda argv: 0,
        m2_main=recorder("m2"),
        building_permits_main=lambda argv: 0,
        gdp_main=recorder("gdp"),
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )

    assert exit_code == 0
    assert calls == [
        ("rates", ["--fetch-fred-csv"]),
        ("m2", ["--fetch-fred-csv"]),
        ("rates", ["--fred-csv-merge"]),
        ("m2", ["--fred-csv-merge"]),
    ]


def test_main_runs_both_ism_surveys_in_order():
    calls = []

    def recorder(label):
        def run(argv):
            calls.append((label, argv))
            return 0

        return run

    result = refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-m2",
            "--skip-gdp",
            "--skip-fomc",
            "--skip-consumer-sentiment",
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        ism_reports_main=recorder("ism_reports"),
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
        openai_config={"api_key": None},
    )

    assert result == 0
    assert calls == [
        (
            "ism_reports",
            ["--survey", "manufacturing", "--latest-only", "--core-only"],
        ),
        (
            "ism_reports",
            ["--survey", "services", "--latest-only", "--core-only"],
        ),
    ]


def test_planned_tasks_includes_nfib_import_by_default():
    calls = []

    def record(label):
        def run(argv):
            calls.append((label, argv))
            return 0

        return run

    refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-fomc",
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        macro_indicators_main=lambda argv: 0,
        nfib_main=record("nfib"),
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )

    assert any(call[0] == "nfib" for call in calls)


def test_skip_nfib_sbo_removes_nfib_task():
    refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-fomc",
            "--skip-nfib-sbo",
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: (_ for _ in ()).throw(
            AssertionError("should not be called")
        ),
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )


def test_planned_tasks_includes_nfib_regional_import_by_default():
    calls = []

    def record(label):
        def run(argv):
            calls.append((label, argv))
            return 0

        return run

    refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-fomc",
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        macro_indicators_main=lambda argv: 0,
        nfib_main=record("nfib"),
        nfib_regional_main=record("nfib_regional"),
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )

    assert any(call[0] == "nfib_regional" for call in calls)


def test_planned_tasks_includes_unless_skipped():
    calls = []

    def record(label):
        def run(argv):
            calls.append((label, argv))
            return 0

        return run

    refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-fomc",
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=record("commodities"),
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )

    assert any(call[0] == "commodities" for call in calls)


def test_skip_cyclical_commodities_removes_task():
    refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-fomc",
            "--skip-cyclical-commodities",
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: (_ for _ in ()).throw(
            AssertionError("should not be called")
        ),
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )


def test_skip_nfib_sbo_regional_removes_nfib_regional_task():
    refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-fomc",
            "--skip-nfib-sbo-regional",
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: (_ for _ in ()).throw(
            AssertionError("should not be called")
        ),
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )


def test_refresh_macro_data_runs_official_ism_fetch_when_enabled():
    calls = []

    exit_code = refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-m2",
            "--skip-gdp",
            "--skip-fomc",
            "--skip-consumer-sentiment",
        ],
        benchmark_main=lambda argv: 0,
        rates_main=lambda argv: 0,
        consumer_main=lambda argv: 0,
        m2_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        ism_reports_main=lambda argv: calls.append(argv) or 0,
        gdp_main=lambda argv: 0,
        fomc_main=lambda argv: 0,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
        openai_config={"api_key": None},
    )

    assert exit_code == 0
    assert calls == [
        ["--survey", "manufacturing", "--latest-only", "--core-only"],
        ["--survey", "services", "--latest-only", "--core-only"],
    ]


def test_verbose_is_forwarded_to_fomc_generators(tmp_path):
    csv_path = tmp_path / "fomc.csv"
    csv_path.write_text(
        "start_date,end_date,title,has_sep,url\n"
        "2026-07-28,2026-07-29,FOMC Meeting,0,https://example.test/fomc\n",
        encoding="utf-8",
    )
    calls = []

    refresh_macro_data.run(
        ["--verbose", "--skip-ism", "--fomc-calendar-path", str(csv_path)],
        fomc_main=lambda argv: 0,
        fomc_document_main=lambda argv: 0,
        fomc_policy_tone_main=lambda argv: calls.append(("tone", argv)) or 0,
        fomc_minutes_main=lambda argv: calls.append(("minutes", argv)) or 0,
        openai_config={"api_key": "configured", "model": "test-model"},
    )

    assert ("tone", ["--all", "--verbose"]) in calls
    assert ("minutes", ["--all"]) in calls


def test_fomc_registry_omits_verbose_from_all_task_argv_when_not_requested(tmp_path):
    csv_path = tmp_path / "fomc.csv"
    csv_path.write_text(
        "start_date,end_date,title,has_sep,url\n"
        "2026-07-28,2026-07-29,FOMC Meeting,0,https://example.test/fomc\n",
        encoding="utf-8",
    )
    args = args_without_skips()
    args.skip_fomc = False
    args.fomc_calendar_path = csv_path

    tasks = refresh_macro_data._planned_tasks(
        args,
        fomc_main=lambda argv: 0,
        fomc_document_main=lambda argv: 0,
        fomc_policy_tone_main=lambda argv: 0,
        fomc_minutes_main=lambda argv: 0,
    )

    fomc_tasks = [task for task in tasks if task["name"].startswith("fomc_")]
    assert fomc_tasks
    assert all("--verbose" not in task["argv"] for task in fomc_tasks)


def test_main_runs_all_fomc_tasks_in_order(tmp_path):
    calls = []
    csv_path = tmp_path / "fomc_calendar.csv"
    csv_path.write_text(
        "start_date,end_date,title,has_sep,url\n"
        "2026-07-28,2026-07-29,FOMC Meeting,0,https://example.test/fomc\n",
        encoding="utf-8",
    )

    def calendar_recorder(argv):
        calls.append(("calendar", argv))
        return 0

    def documents_recorder(argv):
        calls.append(("documents", argv))
        return 0

    def tone_recorder(argv):
        calls.append(("policy_tone", argv))
        return 0

    def minutes_recorder(argv):
        calls.append(("minutes_structure", argv))
        return 0

    exit_code = refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--fomc-calendar-path",
            str(csv_path),
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        fomc_main=calendar_recorder,
        fomc_document_main=documents_recorder,
        fomc_policy_tone_main=tone_recorder,
        fomc_minutes_main=minutes_recorder,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
        openai_config={"api_key": "configured", "model": "test-model"},
    )

    assert exit_code == 0
    assert calls == [
        ("calendar", ["--calendar-path", str(csv_path)]),
        ("documents", ["--document-type", "all"]),
        ("policy_tone", ["--all"]),
        ("minutes_structure", ["--all"]),
    ]


def test_main_skips_all_fomc_tasks_when_skip_fomc_flag():
    exit_code = refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-fomc",
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        fomc_main=lambda argv: (_ for _ in ()).throw(
            AssertionError("should not be called")
        ),
        fomc_document_main=lambda argv: (_ for _ in ()).throw(
            AssertionError("should not be called")
        ),
        fomc_policy_tone_main=lambda argv: (_ for _ in ()).throw(
            AssertionError("should not be called")
        ),
        fomc_minutes_main=lambda argv: (_ for _ in ()).throw(
            AssertionError("should not be called")
        ),
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )

    assert exit_code == 0


def test_skip_oil_removes_oil_task():
    refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-fomc",
            "--skip-oil",
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: (_ for _ in ()).throw(
            AssertionError("should not be called")
        ),
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )


def test_planned_tasks_includes_macro_indicators_fred_tasks_by_default():
    calls = []

    def record(label):
        def run(argv):
            calls.append((label, argv))
            return 0

        return run

    refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-ism",
            "--skip-gdp",
            "--skip-fomc",
        ],
        m2_main=lambda argv: 0,
        macro_indicators_main=record("macro_indicators"),
        building_permits_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )

    assert calls == [
        ("macro_indicators", ["--fetch-fred-csv"]),
        ("macro_indicators", ["--fred-csv-merge"]),
    ]


def test_skip_macro_indicators_removes_macro_indicator_tasks():
    refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-fomc",
            "--skip-macro-indicators",
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        macro_indicators_main=lambda argv: (_ for _ in ()).throw(
            AssertionError("should not be called")
        ),
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: 0,
    )


def test_macro_refresh_registers_lumber_yahoo_without_chrome_import(monkeypatch):
    tasks = refresh_macro_data._planned_tasks(
        args_without_skips(),
        fake_benchmark_main,
        fake_rates_main,
        fake_consumer_main,
        fake_m2_main,
        fake_building_permits_main,
        fake_ism_reports_main,
        fake_gdp_main,
        lumber_main=fake_lumber_main,
    )
    assert any(
        task["name"] == "lumber_yahoo"
        and task["func"] is fake_lumber_main
        and task["argv"] == []
        for task in tasks
    )
    assert not any(task["name"] == "tracked_commodities" for task in tasks)


def test_macro_refresh_skip_lumber_omits_only_lumber_task():
    args = args_without_skips()
    args.skip_lumber = True
    tasks = refresh_macro_data._planned_tasks(
        args,
        fake_benchmark_main,
        fake_rates_main,
        fake_consumer_main,
        fake_m2_main,
        fake_building_permits_main,
        fake_ism_reports_main,
        fake_gdp_main,
        lumber_main=fake_lumber_main,
    )
    assert not any(task["name"] == "lumber_yahoo" for task in tasks)


def test_macro_refresh_does_not_schedule_vendor_copper_tasks():
    tasks = refresh_macro_data._planned_tasks(
        args_without_skips(),
        fake_benchmark_main,
        fake_rates_main,
        fake_consumer_main,
        fake_m2_main,
        fake_building_permits_main,
        fake_ism_reports_main,
        fake_gdp_main,
    )
    names = [task["name"] for task in tasks]
    assert "copper_comex_yahoo" not in names
    assert "lme_copper_sina" not in names


def test_refresh_registry_runs_sina_dce_iron_ore_unless_skipped():
    tasks = refresh_macro_data._planned_tasks(
        args_without_skips(),
        fake_benchmark_main,
        fake_rates_main,
        fake_consumer_main,
        fake_m2_main,
        fake_building_permits_main,
        fake_ism_reports_main,
        fake_gdp_main,
        dce_iron_ore_sina_main=fake_lumber_main,
    )

    assert any(task["name"] == "dce_iron_ore_sina" for task in tasks)


def test_macro_refresh_skip_dce_iron_ore_sina_omits_the_task():
    args = args_without_skips()
    args.skip_dce_iron_ore_sina = True
    tasks = refresh_macro_data._planned_tasks(
        args,
        fake_benchmark_main,
        fake_rates_main,
        fake_consumer_main,
        fake_m2_main,
        fake_building_permits_main,
        fake_ism_reports_main,
        fake_gdp_main,
        dce_iron_ore_sina_main=fake_lumber_main,
    )

    assert not any(task["name"] == "dce_iron_ore_sina" for task in tasks)


def test_macro_refresh_does_not_register_vendor_lme_copper_by_default():
    tasks = refresh_macro_data._planned_tasks(
        args_without_skips(),
        fake_benchmark_main,
        fake_rates_main,
        fake_consumer_main,
        fake_m2_main,
        fake_building_permits_main,
        fake_ism_reports_main,
        fake_gdp_main,
    )
    names = [task["name"] for task in tasks]
    assert "lme_copper_sina" not in names


def test_refresh_registry_runs_economic_confirmation_by_default():
    calls = []

    def economic_confirmation_main(argv):
        calls.append(argv)
        return 0

    exit_code = refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-fomc",
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=economic_confirmation_main,
    )

    assert exit_code == 0
    assert calls == [[]]


def test_skip_economic_confirmation_removes_task():
    refresh_macro_data.run(
        [
            "--skip-yahoo",
            "--skip-rates",
            "--skip-consumer-sentiment",
            "--skip-m2",
            "--skip-ism",
            "--skip-gdp",
            "--skip-fomc",
            "--skip-economic-confirmation",
        ],
        consumer_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        macro_indicators_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
        nfib_regional_main=lambda argv: 0,
        main=lambda argv: 0,
        oil_main=lambda argv: 0,
        lumber_main=lambda argv: 0,
        dce_iron_ore_sina_main=lambda argv: 0,
        shfe_copper_main=lambda argv: 0,
        economic_confirmation_main=lambda argv: (_ for _ in ()).throw(
            AssertionError("should not be called")
        ),
    )


def test_planned_tasks_includes_economic_confirmation_by_default():
    tasks = refresh_macro_data._planned_tasks(
        args_without_skips(),
        fake_benchmark_main,
        fake_rates_main,
        fake_consumer_main,
        fake_m2_main,
        fake_building_permits_main,
        fake_ism_reports_main,
        fake_gdp_main,
        economic_confirmation_main=fake_consumer_main,
    )
    assert any(
        task["name"] == "economic_confirmation_official"
        and task["func"] is fake_consumer_main
        and task["argv"] == []
        for task in tasks
    )


def test_planned_tasks_skips_economic_confirmation_when_flag_set():
    args = args_without_skips()
    args.skip_economic_confirmation = True
    tasks = refresh_macro_data._planned_tasks(
        args,
        fake_benchmark_main,
        fake_rates_main,
        fake_consumer_main,
        fake_m2_main,
        fake_building_permits_main,
        fake_ism_reports_main,
        fake_gdp_main,
        economic_confirmation_main=fake_consumer_main,
    )
    assert not any(
        task["name"] == "economic_confirmation_official" for task in tasks
    )


def test_planned_tasks_uses_separate_fred_provider_seam():
    args = args_without_skips()
    args.skip_yahoo = True
    args.skip_consumer_sentiment = True
    args.skip_building_permits = True
    args.skip_ism = True
    args.skip_fomc = True
    args.skip_nfib_sbo = True
    args.skip_nfib_sbo_regional = True
    args.skip_tracked_commodities = True
    args.skip_cyclical_commodities = True
    args.skip_oil = True
    args.skip_lumber = True
    args.skip_shfe_copper = True
    args.skip_dce_iron_ore_sina = True
    args.skip_economic_confirmation = True
    providers = {
        "rates": lambda argv: 0,
        "credit": lambda argv: 0,
        "m2": lambda argv: 0,
        "macro_indicators": lambda argv: 0,
        "gdp": lambda argv: 0,
    }

    tasks = refresh_macro_data._planned_tasks(
        args,
        rates_main=providers["rates"],
        m2_main=providers["m2"],
        macro_indicators_main=providers["macro_indicators"],
        gdp_main=providers["gdp"],
        credit_main=providers["credit"],
        openai_config={"api_key": None},
    )

    assert [task["name"] for task in tasks] == [
        "rates_fred_fetch",
        "m2_fred_fetch",
        "macro_indicators_fred_fetch",
        "gdp_fred_fetch",
        "rates_fred_import",
        "m2_fred_import",
        "macro_indicators_fred_import",
        "gdp_fred_import",
        "credit_fred_fetch",
        "credit_fred_import",
    ]


def test_main_wires_separate_fred_importers_instead_of_combined_refresh(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(refresh_macro_data, "run", fake_run)

    assert refresh_macro_data.main([]) == 0
    assert captured == {"use_runtime_defaults": True}


def _task9_skip_args(*extra):
    return [
        "--skip-yahoo",
        "--skip-consumer-sentiment",
        "--skip-building-permits",
        "--skip-ism",
        "--skip-fomc",
        "--skip-nfib-sbo",
        "--skip-nfib-sbo-regional",
        "--skip-cyclical-commodities",
        "--skip-oil",
        "--skip-lumber",
        "--skip-shfe-copper",
        "--skip-dce-iron-ore-sina",
        "--skip-economic-confirmation",
        *extra,
    ]


def test_task9_serial_flag_executes_registry_graph_in_stable_order():
    calls = []

    def recorder(name):
        def run(argv):
            calls.append((name, list(argv)))
            return 0

        return run

    result = refresh_macro_data.run(
        _task9_skip_args("--serial"),
        task_providers={
            "rates": recorder("rates"),
            "credit": recorder("credit"),
            "m2": recorder("m2"),
            "macro_indicators": recorder("macro"),
            "gdp": recorder("gdp"),
        },
        openai_config={"api_key": None},
        progress_factory=FakeProgress,
    )

    assert result == 0
    assert calls == [
        ("rates", ["--fetch-fred-csv"]),
        ("m2", ["--fetch-fred-csv"]),
        ("macro", ["--fetch-fred-csv"]),
        ("gdp", ["--fetch-fred-csv"]),
        ("rates", ["--fred-csv-merge"]),
        ("m2", ["--fred-csv-merge"]),
        ("macro", ["--fred-csv-merge"]),
        ("gdp", ["--us-csv-merge"]),
        ("credit", ["--fetch-fred-csv"]),
        ("credit", ["--fred-csv-merge"]),
    ]


def test_task9_default_mode_starts_independent_lanes_before_release():
    started = {"fred": Event(), "yahoo": Event()}
    release = Event()

    def wait_for(label, other):
        def run(argv):
            started[label].set()
            if started["fred"].is_set() and started["yahoo"].is_set():
                release.set()
            assert started[other].wait(1)
            assert release.wait(1)
            return 0

        return run

    def executor(tasks, **kwargs):
        try:
            return refresh_macro_data.execute_tasks(tasks, **kwargs)
        finally:
            release.set()

    result = refresh_macro_data.run(
        [flag for flag in _task9_skip_args() if flag != "--skip-yahoo"],
        task_providers={
            "rates": wait_for("fred", "yahoo"),
            "benchmarks_fetch": wait_for("yahoo", "fred"),
            "benchmarks_import": lambda argv: 0,
        },
        openai_config={"api_key": None},
        executor=executor,
        progress_factory=FakeProgress,
    )

    assert result == 0


def test_task9_summary_includes_blocked_tasks(capsys):
    def failing(argv):
        return 1

    result = refresh_macro_data.run(
        _task9_skip_args("--stop-on-error"),
        task_providers={"rates": failing},
        openai_config={"api_key": None},
        progress_factory=FakeProgress,
    )

    assert result == 1
    assert "ok=0 skipped=0 failed=1 blocked=1" in capsys.readouterr().out


def test_task9_keyboard_interrupt_reports_and_returns_130(capsys):
    cancel_event = Event()

    def interrupting_executor(tasks, **kwargs):
        cancel_event.set()
        raise KeyboardInterrupt

    result = refresh_macro_data.run(
        _task9_skip_args(),
        task_providers={"rates": lambda argv: 0},
        openai_config={"api_key": None},
        executor=interrupting_executor,
        progress_factory=FakeProgress,
    )

    assert result == 130
    assert "macro data refresh interrupted" in capsys.readouterr().err


def test_task9_legacy_provider_seam_is_adapted_to_registry_tasks(monkeypatch):
    planned = []

    def fail_flat_loop(*args, **kwargs):
        raise AssertionError("legacy flat task loop must not run")

    monkeypatch.setattr(refresh_macro_data, "_planned_tasks", fail_flat_loop)

    def recorder(argv):
        planned.append(list(argv))
        return 0

    result = refresh_macro_data.run(
        _task9_skip_args("--serial"),
        rates_main=recorder,
        openai_config={"api_key": None},
        progress_factory=FakeProgress,
    )

    assert result == 0
    assert planned == [["--fetch-fred-csv"], ["--fred-csv-merge"]]


def test_task9_default_provider_pair_requires_fetched_artifact(monkeypatch):
    store = refresh_macro_data.ArtifactStore()
    calls = []

    def fetch(argv):
        calls.append(("fetch", list(argv)))
        store.put("rates", {"fetched": True})
        return 0

    def persist(argv):
        calls.append(("persist", list(argv)))
        store.get("rates")
        return 0

    providers = refresh_macro_data._build_task_providers(
        {"rates_main": fetch},
        artifact_store=store,
        provider_overrides={"rates_fetch": fetch, "rates_import": persist},
    )

    assert providers["rates_fetch"] is fetch
    assert providers["rates_import"] is persist
    assert calls == []


def test_task9_production_registry_executes_staged_override_handoff():
    store = refresh_macro_data.ArtifactStore()
    calls = []

    def fetch(argv):
        assert argv == ["--fetch-fred-csv"]
        store.put("staged.rates", {"payload": "fetched"})
        calls.append("fetch")
        return 0

    def persist(argv):
        assert argv == ["--fred-csv-merge"]
        assert store.get("staged.rates")["payload"] == "fetched"
        calls.append("persist")
        return 0

    result = refresh_macro_data.run(
        _task9_skip_args("--serial"),
        task_providers={"rates_fetch": fetch, "rates_import": persist},
        artifact_store=store,
        openai_config={"api_key": None},
        progress_factory=FakeProgress,
    )

    assert result == 0
    assert calls == ["fetch", "persist"]


def test_task9_lifecycle_and_failure_output_share_ordered_stream(monkeypatch):
    import io

    stream = io.StringIO()
    monkeypatch.setattr(refresh_macro_data.sys, "stdout", stream)
    monkeypatch.setattr(refresh_macro_data.sys, "stderr", stream)

    result = refresh_macro_data.run(
        _task9_skip_args(),
        task_providers={"rates": lambda argv: 1},
        openai_config={"api_key": None},
        progress_factory=FakeProgress,
    )

    output = stream.getvalue()
    assert result == 1
    assert output.index("macro data refresh started") < output.index("failed")
    assert output.index("failed") < output.index("macro data refresh completed")


def test_task9_legacy_combined_seam_runs_once_across_registry_nodes():
    calls = []
    store = refresh_macro_data.ArtifactStore()
    providers = refresh_macro_data._build_task_providers(
        {"economic_confirmation_main": lambda argv: calls.append(list(argv)) or 0},
        artifact_store=store,
    )

    for key in ("dol_fetch", "bls_fetch", "federal_reserve_fetch"):
        assert providers[key]([]) == 0
    assert calls == []
    for key in ("dol_import", "bls_import", "federal_reserve_import"):
        assert providers[key]([]) == 0

    assert calls == [[]]


def test_task9_legacy_ism_seam_adapts_all_registry_stages():
    store = refresh_macro_data.ArtifactStore()
    providers = refresh_macro_data._build_task_providers(
        {"ism_reports_main": lambda argv: 0},
        artifact_store=store,
    )

    for survey in ("manufacturing", "services"):
        assert {
            f"ism_{survey}_{stage}"
            for stage in ("fetch", "import", "enrichment", "enrichment_import")
        } <= providers.keys()
