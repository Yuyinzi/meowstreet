from ast import Call, FunctionDef, Name, parse
from pathlib import Path

from app.services.task_notification_catalog import ACTION_TASKS, CLI_TASKS, NON_TASK_ACTIONS, TASKS


ROOT = Path(__file__).resolve().parents[1]


def test_all_action_endpoints_have_an_explicit_task_or_read_contract():
    from app.api import app

    paths = app.openapi()["paths"]
    actions = {path for path, methods in paths.items() if any(method in methods for method in ("post", "put", "patch", "delete"))}
    assert actions == set(ACTION_TASKS) | NON_TASK_ACTIONS
    assert all(task_id in TASKS for task_id in ACTION_TASKS.values())


def test_every_script_entry_point_has_an_execution_adapter():
    missing = []
    for path in (ROOT / "scripts").glob("*.py"):
        tree = parse(path.read_text())
        main = next((node for node in tree.body if isinstance(node, FunctionDef) and node.name == "main"), None)
        if main is None or path.stem == "refresh_investing_rendered":
            continue
        task_id = CLI_TASKS.get(f"scripts.{path.stem}")
        registered = any(isinstance(decorator, Call) and isinstance(decorator.func, Name) and decorator.func.id == "record_cli_task"
                         and decorator.args[0].value == task_id for decorator in main.decorator_list)
        if not registered or task_id not in TASKS:
            missing.append(path.name)
    assert missing == []


def test_real_benchmark_cli_records_one_execution_without_source_calls():
    from app.db import job_notifications
    from scripts.refresh_benchmark_market_data import main

    assert main(["--benchmark-id", "us_sp500"], refresh_benchmarks=lambda ids, **kwargs: [{"benchmark_id": ids[0], "symbol": "^GSPC", "rows_upserted": 0, "latest_date": "2026-11-13"}]) == 0
    con = job_notifications.connect()
    runs = job_notifications.list_runs(con)["runs"]
    assert len(runs) == 1
    assert runs[0]["job_id"] == "cli_refresh_benchmark_market_data"
    assert runs[0]["exit_code"] == 0
    con.close()
