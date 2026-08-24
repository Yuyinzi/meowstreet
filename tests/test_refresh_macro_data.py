from argparse import Namespace
import sys

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


def test_progress_advances_for_ok_skipped_and_failed(monkeypatch, capsys):
    progress_instances = []

    def progress_factory(**kwargs):
        instance = FakeProgress(**kwargs)
        progress_instances.append(instance)
        return instance

    tasks = [
        refresh_macro_data._task("ok", lambda argv: 0, []),
        refresh_macro_data._task("skip", lambda argv: 0, [], "not configured"),
        refresh_macro_data._task("fail", lambda argv: 1, []),
    ]
    monkeypatch.setattr(refresh_macro_data, "_planned_tasks", lambda *args: tasks)
    monkeypatch.setattr(refresh_macro_data.sys.stderr, "isatty", lambda: True)

    exit_code = refresh_macro_data.run([], progress_factory=progress_factory)

    captured = capsys.readouterr()
    progress = progress_instances[0]
    assert exit_code == 1
    assert progress.total == 3
    assert progress.updated == 3
    assert progress.postfixes[-1] == {"ok": 1, "skipped": 1, "failed": 1}
    assert "macro data refresh completed: ok=1 skipped=1 failed=1" in captured.out


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
    tasks = [refresh_macro_data._task("provider", lambda argv: print("details") or 0, [])]
    monkeypatch.setattr(refresh_macro_data, "_planned_tasks", lambda *args: tasks)
    monkeypatch.setattr(refresh_macro_data.sys.stderr, "isatty", lambda: False)

    exit_code = refresh_macro_data.run(["--verbose"], progress_factory=FakeProgress)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "details" in captured.out
    assert "provider: ok" in captured.out


def test_success_output_is_hidden_without_verbose(monkeypatch, capsys):
    tasks = [refresh_macro_data._task("provider", lambda argv: print("details") or 0, [])]
    monkeypatch.setattr(refresh_macro_data, "_planned_tasks", lambda *args: tasks)
    monkeypatch.setattr(refresh_macro_data.sys.stderr, "isatty", lambda: False)

    exit_code = refresh_macro_data.run([], progress_factory=FakeProgress)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "details" not in captured.out
    assert "provider: ok" in captured.out


def test_skip_does_not_trigger_stop_on_error_but_failure_does(monkeypatch):
    calls = []
    tasks = [
        refresh_macro_data._task("skip", lambda argv: calls.append("skip"), [], "optional"),
        refresh_macro_data._task("fail", lambda argv: calls.append("fail") or 1, []),
        refresh_macro_data._task("after", lambda argv: calls.append("after") or 0, []),
    ]
    monkeypatch.setattr(refresh_macro_data, "_planned_tasks", lambda *args: tasks)
    monkeypatch.setattr(refresh_macro_data.sys.stderr, "isatty", lambda: False)

    exit_code = refresh_macro_data.run(["--stop-on-error"], progress_factory=FakeProgress)

    assert exit_code == 1
    assert calls == ["fail"]


def test_progress_is_disabled_when_stderr_is_not_a_tty(monkeypatch):
    progress_instances = []

    def progress_factory(**kwargs):
        instance = FakeProgress(**kwargs)
        progress_instances.append(instance)
        return instance

    monkeypatch.setattr(refresh_macro_data, "_planned_tasks", lambda *args: [])
    monkeypatch.setattr(refresh_macro_data.sys.stderr, "isatty", lambda: False)

    assert refresh_macro_data.run([], progress_factory=progress_factory) == 0
    assert progress_instances[0].disable is True


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
    assert calls == [[]]


def test_main_runs_market_and_fred_refreshes_in_order(capsys):
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
    assert calls[:2] == [
        (
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
        ),
        ("rates", []),
    ]
    assert calls[2][0] == "consumer"
    out = capsys.readouterr().out
    assert "macro data refresh started" in out
    assert "benchmark_yahoo: ok" in out
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
    )

    assert exit_code == 1
    assert [label for label, _ in calls] == [
        "benchmark",
        "rates",
        "m2",
        "m2",
        "gdp",
        "gdp",
    ]
    captured = capsys.readouterr()
    assert "benchmark_yahoo: failed - exit code 1" in captured.err
    assert "macro data refresh completed: ok=19 skipped=0 failed=1" in captured.out


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
    assert calls == [
        (
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
        )
    ]


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
    assert "benchmark_yahoo: failed - yahoo rate limited" in captured.err


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
        ("rates", []),
        ("m2", ["--fetch-fred-csv"]),
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
    )

    assert result == 0
    assert calls == [
        ("ism_reports", ["--survey", "manufacturing", "--latest-only"]),
        ("ism_reports", ["--survey", "services", "--latest-only"]),
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
    )

    assert exit_code == 0
    assert calls == [
        ["--survey", "manufacturing", "--latest-only"],
        ["--survey", "services", "--latest-only"],
    ]


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
