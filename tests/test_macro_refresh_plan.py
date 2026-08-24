import pytest

from app.services import macro_refresh_plan


def noop(argv):
    return 0


def test_make_task_normalizes_tuple_fields_and_plan_index():
    task = macro_refresh_plan.make_task(
        "m2_import",
        "fred_macro",
        "persist",
        noop,
        ["--fred-csv-merge"],
        dependencies=["m2_fetch"],
        resources=["sqlite_writer"],
        plan_index=4,
    )

    assert task == {
        "name": "m2_import",
        "lane": "fred_macro",
        "stage": "persist",
        "func": noop,
        "argv": ["--fred-csv-merge"],
        "dependencies": ["m2_fetch"],
        "accepted_dependency_statuses": ["ok"],
        "resources": ["sqlite_writer"],
        "skip_reason": None,
        "plan_index": 4,
    }


def test_validate_tasks_rejects_cycle_created_by_lane_order():
    tasks = [
        macro_refresh_plan.make_task(
            "a1", "a", "fetch", noop, dependencies=["b1"], plan_index=0
        ),
        macro_refresh_plan.make_task("a2", "a", "persist", noop, plan_index=1),
        macro_refresh_plan.make_task(
            "b1", "b", "fetch", noop, dependencies=["a2"], plan_index=2
        ),
    ]

    with pytest.raises(ValueError, match="macro refresh task graph has a cycle"):
        macro_refresh_plan.validate_tasks(tasks)


def test_validate_tasks_sorts_without_mutating_tasks():
    first = macro_refresh_plan.make_task("first", "lane", "fetch", noop, plan_index=3)
    second = macro_refresh_plan.make_task("second", "lane", "persist", noop, plan_index=1)
    tasks = [first, second]

    validated = macro_refresh_plan.validate_tasks(tasks)

    assert [task["name"] for task in validated] == ["second", "first"]
    assert tasks == [first, second]
    assert validated[0] is not second
    assert validated[0]["dependencies"] is not second["dependencies"]


@pytest.mark.parametrize(
    ("tasks", "message"),
    [
        (
            [
                macro_refresh_plan.make_task("same", "a", "fetch", noop),
                macro_refresh_plan.make_task("same", "b", "fetch", noop),
            ],
            "macro refresh task same is duplicated",
        ),
        (
            [
                macro_refresh_plan.make_task(
                    "task", "a", "persist", noop, dependencies=["missing"]
                )
            ],
            "macro refresh task task has unknown dependency missing",
        ),
        (
            [macro_refresh_plan.make_task("task", "a", "unknown", noop)],
            "macro refresh task task has invalid stage unknown",
        ),
        (
            [
                macro_refresh_plan.make_task(
                    "task", "a", "fetch", noop, accepted_dependency_statuses=["failed"]
                )
            ],
            "macro refresh task task has invalid dependency status failed",
        ),
        (
            [
                macro_refresh_plan.make_task(
                    "task", "a", "fetch", noop, resources=["fred", "fred"]
                )
            ],
            "macro refresh task task has duplicate resource fred",
        ),
        (
            [
                macro_refresh_plan.make_task(
                    "task", "a", "fetch", noop, resources=["sqlite_writer"]
                )
            ],
            "macro refresh resource sqlite_writer is only allowed on persist tasks",
        ),
        (
            [
                macro_refresh_plan.make_task(
                    "task", "a", "persist", noop, resources=["fred"]
                )
            ],
            "macro refresh resource fred is only allowed on fetch tasks",
        ),
    ],
)
def test_validate_tasks_rejects_invalid_graph_contract(tasks, message):
    with pytest.raises(ValueError, match=message):
        macro_refresh_plan.validate_tasks(tasks)


def test_group_tasks_by_lane_preserves_plan_order():
    tasks = [
        macro_refresh_plan.make_task("b", "second", "fetch", noop, plan_index=2),
        macro_refresh_plan.make_task("a2", "first", "persist", noop, plan_index=3),
        macro_refresh_plan.make_task("a1", "first", "fetch", noop, plan_index=1),
    ]

    grouped = macro_refresh_plan.group_tasks_by_lane(tasks)

    assert list(grouped) == ["first", "second"]
    assert [task["name"] for task in grouped["first"]] == ["a1", "a2"]
    assert [task["name"] for task in grouped["second"]] == ["b"]


def test_make_blocked_result_has_dependency_diagnostic():
    task = macro_refresh_plan.make_task("import", "fred_macro", "persist", noop)

    assert macro_refresh_plan.make_blocked_result(
        task, ["fetch"], "required dependency failed"
    ) == {
        "name": "import",
        "lane": "fred_macro",
        "status": "blocked",
        "exit_code": 1,
        "error": "required dependency failed: fetch",
        "stdout": "",
        "stderr": "",
    }
