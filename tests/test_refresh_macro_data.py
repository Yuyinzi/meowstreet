from jobs import refresh_macro_data


def test_main_refreshes_official_building_permits_when_enabled():
    calls = []

    def permits_main(argv):
        calls.append(argv)
        return 0

    exit_code = refresh_macro_data.main(
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
        nfib_main=lambda argv: 0,
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

    def ism_main(argv):
        calls.append(("ism", argv))
        return 0

    def ism_reports_main(argv):
        calls.append(("ism_reports", argv))
        return 0

    exit_code = refresh_macro_data.main(
        [],
        benchmark_main=benchmark_main,
        rates_main=rates_main,
        consumer_main=consumer_main,
        m2_main=m2_main,
        building_permits_main=lambda argv: 0,
        ism_main=ism_main,
        ism_services_main=lambda argv: 0,
        ism_reports_main=ism_reports_main,
        gdp_main=gdp_main,
        fomc_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
    )

    assert exit_code == 0
    assert calls[:2] == [
        ("benchmark", ["--all"]),
        ("rates", ["--skip-credit-workbook"]),
    ]
    assert calls[2][0] == "consumer"
    out = capsys.readouterr().out
    assert "macro data refresh started" in out
    assert "benchmark_yahoo: ok" in out
    assert "macro data refresh completed: ok" in out


def test_main_does_not_generate_ai_interpretations():
    calls = []

    def recorder(label):
        def _record(argv):
            calls.append((label, argv))
            return 0

        return _record

    exit_code = refresh_macro_data.main(
        [],
        benchmark_main=recorder("benchmark"),
        rates_main=recorder("rates"),
        consumer_main=recorder("consumer"),
        m2_main=recorder("m2"),
        building_permits_main=lambda argv: 0,
        ism_main=recorder("ism"),
        ism_services_main=recorder("services_workbook"),
        ism_reports_main=recorder("ism_reports"),
        gdp_main=recorder("gdp"),
        fomc_main=recorder("fomc"),
        nfib_main=lambda argv: 0,
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

    exit_code = refresh_macro_data.main(
        [],
        benchmark_main=failing_benchmark,
        rates_main=ok_task("rates"),
        consumer_main=lambda argv: 0,
        m2_main=ok_task("m2"),
        building_permits_main=lambda argv: 0,
        ism_main=ok_task("ism"),
        ism_services_main=lambda argv: 0,
        ism_reports_main=lambda argv: 0,
        gdp_main=ok_task("gdp"),
        nfib_main=lambda argv: 0,
    )

    assert exit_code == 1
    assert [label for label, _ in calls] == [
        "benchmark",
        "rates",
        "m2",
        "m2",
        "ism",
        "gdp",
        "gdp",
    ]
    captured = capsys.readouterr()
    assert "benchmark_yahoo: failed - exit code 1" in captured.err
    assert "macro data refresh completed: failed" in captured.out


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

    exit_code = refresh_macro_data.main(
        ["--stop-on-error"],
        benchmark_main=failing_benchmark,
        rates_main=ok_task("rates"),
        consumer_main=lambda argv: 0,
        m2_main=ok_task("m2"),
        building_permits_main=lambda argv: 0,
        ism_main=ok_task("ism"),
        ism_services_main=lambda argv: 0,
        ism_reports_main=lambda argv: 0,
        gdp_main=ok_task("gdp"),
        nfib_main=lambda argv: 0,
    )

    assert exit_code == 1
    assert calls == [("benchmark", ["--all"])]


def test_main_records_exceptions_as_failures(capsys):
    def raising_benchmark(argv):
        raise ValueError("yahoo rate limited")

    exit_code = refresh_macro_data.main(
        ["--skip-rates", "--skip-m2", "--skip-gdp", "--skip-consumer-sentiment"],
        benchmark_main=raising_benchmark,
        rates_main=lambda argv: 0,
        consumer_main=lambda argv: 0,
        m2_main=lambda argv: 0,
        building_permits_main=lambda argv: 0,
        ism_main=lambda argv: 0,
        gdp_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "benchmark_yahoo: failed - yahoo rate limited" in captured.err


def test_refresh_macro_data_skips_fomc_when_calendar_csv_is_missing(tmp_path):
    calls = []

    def fake_task(argv):
        calls.append(argv)
        return 0

    exit_code = refresh_macro_data.main(
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
        nfib_main=lambda argv: 0,
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

    exit_code = refresh_macro_data.main(
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
        nfib_main=lambda argv: 0,
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

    exit_code = refresh_macro_data.main(
        ["--skip-yahoo", "--skip-ism", "--skip-gdp", "--skip-consumer-sentiment"],
        benchmark_main=recorder("benchmark"),
        rates_main=recorder("rates"),
        consumer_main=lambda argv: 0,
        m2_main=recorder("m2"),
        building_permits_main=lambda argv: 0,
        ism_main=recorder("ism"),
        gdp_main=recorder("gdp"),
        nfib_main=lambda argv: 0,
    )

    assert exit_code == 0
    assert calls == [
        ("rates", ["--skip-credit-workbook"]),
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

    result = refresh_macro_data.main(
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
        ism_main=recorder("manufacturing_workbook"),
        ism_services_main=recorder("services_workbook"),
        ism_reports_main=recorder("ism_reports"),
        nfib_main=lambda argv: 0,
    )

    assert result == 0
    assert calls == [
        ("manufacturing_workbook", []),
        ("ism_reports", ["--survey", "manufacturing", "--latest-only"]),
        ("services_workbook", []),
        ("ism_reports", ["--survey", "services", "--latest-only"]),
    ]


def test_planned_tasks_includes_nfib_import_by_default():
    calls = []

    def record(label):
        def run(argv):
            calls.append((label, argv))
            return 0

        return run

    refresh_macro_data.main(
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
        nfib_main=record("nfib"),
    )

    assert any(call[0] == "nfib" for call in calls)


def test_skip_nfib_sbo_removes_nfib_task():
    refresh_macro_data.main(
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
        nfib_main=lambda argv: (_ for _ in ()).throw(
            AssertionError("should not be called")
        ),
    )


def test_refresh_macro_data_runs_official_ism_fetch_when_enabled():
    calls = []

    exit_code = refresh_macro_data.main(
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
        ism_main=lambda argv: 0,
        ism_services_main=lambda argv: 0,
        ism_reports_main=lambda argv: calls.append(argv) or 0,
        gdp_main=lambda argv: 0,
        fomc_main=lambda argv: 0,
        nfib_main=lambda argv: 0,
    )

    assert exit_code == 0
    assert calls == [
        ["--survey", "manufacturing", "--latest-only"],
        ["--survey", "services", "--latest-only"],
    ]
