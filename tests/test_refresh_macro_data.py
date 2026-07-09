from jobs import refresh_macro_data


def test_main_runs_market_and_fred_refreshes_in_order(capsys):
    calls = []

    def benchmark_main(argv):
        calls.append(("benchmark", argv))
        return 0

    def rates_main(argv):
        calls.append(("rates", argv))
        return 0

    def m2_main(argv):
        calls.append(("m2", argv))
        return 0

    def gdp_main(argv):
        calls.append(("gdp", argv))
        return 0

    exit_code = refresh_macro_data.main(
        [],
        benchmark_main=benchmark_main,
        rates_main=rates_main,
        m2_main=m2_main,
        gdp_main=gdp_main,
    )

    assert exit_code == 0
    assert calls == [
        ("benchmark", ["--all"]),
        ("rates", []),
        ("m2", ["--fetch-fred-csv"]),
        ("m2", ["--fred-csv-merge"]),
        ("gdp", ["--fetch-fred-csv"]),
        ("gdp", ["--us-csv-merge"]),
    ]
    out = capsys.readouterr().out
    assert "macro data refresh started" in out
    assert "benchmark_yahoo: ok" in out
    assert "m2_fred_merge: ok" in out
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
        m2_main=recorder("m2"),
        gdp_main=recorder("gdp"),
    )

    assert exit_code == 0
    flattened_args = [arg for _, argv in calls for arg in argv]
    assert "--generate-credit-interpretation" not in flattened_args
    assert "--generate-interpretation" not in flattened_args
