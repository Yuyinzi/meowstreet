import json

import pytest

from app.services.investing_rendered_refresh import DEFAULT_CDP_PORT
from scripts import refresh_investing_rendered
from scripts.refresh_investing_rendered import main


def _result(**overrides):
    result = {
        "series": 3,
        "observations": 6,
        "ranges": {
            "copper_comex": {
                "start_date": "2026-07-30",
                "end_date": "2026-07-31",
            },
            "copper_lme": {
                "start_date": "2026-07-30",
                "end_date": "2026-07-31",
            },
            "iron_ore_62_cfr_china": {
                "start_date": "2026-07-30",
                "end_date": "2026-07-31",
            },
        },
        "no_new_data": [],
        "status": "ok",
        "cdp_endpoint": "http://127.0.0.1:9222",
    }
    result.update(overrides)
    return result


def _mock_refresh(result):
    def refresh(con, **kwargs):
        return result

    return refresh


def test_main_success_exits_zero_with_json_output(tmp_path, capsys):
    exit_code = main(
        ["--db-path", str(tmp_path / "macro.db")],
        refresh=_mock_refresh(_result()),
    )
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["observations"] == 6


def test_main_noop_exits_zero_with_json_output(tmp_path, capsys):
    exit_code = main(
        ["--db-path", str(tmp_path / "macro.db")],
        refresh=_mock_refresh(_result(series=0, observations=0, ranges={})),
    )
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["observations"] == 0
    assert out["no_new_data"] == []


def test_main_passes_cli_configuration_to_service(tmp_path, capsys):
    calls = []

    def capture_refresh(con, **kwargs):
        calls.append(kwargs)
        return _result()

    exit_code = main(
        [
            "--db-path",
            str(tmp_path / "macro.db"),
            "--cdp-port",
            "9333",
            "--lock-file",
            str(tmp_path / "refresh.lock"),
            "--readiness-timeout",
            "9",
        ],
        refresh=capture_refresh,
    )
    assert exit_code == 0
    assert calls == [
        {
            "cdp_port": 9333,
            "lock_path": tmp_path / "refresh.lock",
            "readiness_timeout": 9,
        }
    ]


def test_main_defaults_to_interactive_chrome_port(tmp_path, capsys):
    calls = []

    def capture_refresh(con, **kwargs):
        calls.append(kwargs)
        return _result()

    exit_code = main(["--db-path", str(tmp_path / "macro.db")], refresh=capture_refresh)
    assert exit_code == 0
    assert calls[0]["cdp_port"] == DEFAULT_CDP_PORT
    assert DEFAULT_CDP_PORT == 9222


@pytest.mark.parametrize(
    "message",
    [
        "commodities investing rendered refresh already running (lock held)",
        "Chrome CDP endpoint at http://127.0.0.1:9222 did not become ready",
        "page did not render the Iron Ore 62% Fe CFR China index market title",
        "the Investing historical data table contained no rows",
        "rendered history fetch failed",
    ],
)
def test_main_failures_exit_nonzero_with_remediation(tmp_path, capsys, message):
    def failing_refresh(con, **kwargs):
        raise ValueError(message)

    exit_code = main(
        ["--db-path", str(tmp_path / "macro.db")],
        refresh=failing_refresh,
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert message in captured.err
    assert "retry the job" in captured.err
