from jobs import refresh_macro_data


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

    def ism_official_main(argv):
        calls.append(("ism_official", argv))
        return 0

    exit_code = refresh_macro_data.main(
        [],
        benchmark_main=benchmark_main,
        rates_main=rates_main,
        consumer_main=consumer_main,
        m2_main=m2_main,
        ism_main=ism_main,
        ism_official_main=ism_official_main,
        ism_services_main=lambda argv: 0,
        ism_services_official_main=lambda argv: 0,
        gdp_main=gdp_main,
        fomc_main=lambda argv: 0,
    )

    assert exit_code == 0
    assert calls[:2] == [
        ("benchmark", ["--all"]),
        ("rates", ["--skip-credit-workbook"]),
    ]
    assert len(calls) >= 6
    consumer_calls = [c for c in calls if c[0] == "consumer"]
    assert len(consumer_calls) == 4
    assert consumer_calls[0][1][0] == "--fetch-michigan-csv"
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
        ism_main=recorder("ism"),
        ism_official_main=recorder("ism_official"),
        ism_services_main=recorder("services_workbook"),
        ism_services_official_main=recorder("services_official"),
        gdp_main=recorder("gdp"),
        fomc_main=recorder("fomc"),
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
        ism_main=ok_task("ism"),
        gdp_main=ok_task("gdp"),
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
        ism_main=ok_task("ism"),
        gdp_main=ok_task("gdp"),
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
        ism_main=lambda argv: 0,
        gdp_main=lambda argv: 0,
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
        fomc_main=fake_task,
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
        fomc_main=fake_task,
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
        ism_main=recorder("ism"),
        gdp_main=recorder("gdp"),
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
        ism_main=recorder("manufacturing_workbook"),
        ism_official_main=recorder("manufacturing_official"),
        ism_services_main=recorder("services_workbook"),
        ism_services_official_main=recorder("services_official"),
    )

    assert result == 0
    assert calls == [
        ("manufacturing_workbook", []),
        ("manufacturing_official", []),
        ("services_workbook", []),
        ("services_official", []),
    ]


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
        ism_main=lambda argv: 0,
        ism_official_main=lambda argv: calls.append(argv) or 0,
        ism_services_main=lambda argv: 0,
        ism_services_official_main=lambda argv: 0,
        gdp_main=lambda argv: 0,
        fomc_main=lambda argv: 0,
    )

    assert exit_code == 0
    assert calls == [[]]
