import re


LANE_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z")
VALID_STAGES = {"fetch", "parse", "persist", "enrich"}
VALID_DEPENDENCY_STATUSES = {"ok", "skipped"}
VALID_RESOURCES = {"fred", "sqlite_writer"}


def make_task(
    name,
    lane,
    stage,
    func,
    argv=(),
    dependencies=(),
    resources=(),
    accepted_dependency_statuses=("ok",),
    skip_reason=None,
    plan_index=0,
):
    return {
        "name": str(name),
        "lane": str(lane),
        "stage": str(stage),
        "func": func,
        "argv": list(argv),
        "dependencies": list(dependencies),
        "accepted_dependency_statuses": list(accepted_dependency_statuses),
        "resources": list(resources),
        "skip_reason": skip_reason,
        "plan_index": int(plan_index),
    }


def validate_tasks(tasks):
    copied_tasks = [_copy_task(task) for task in tasks]
    tasks_by_name = {}

    for task in copied_tasks:
        name = task["name"]
        if name in tasks_by_name:
            raise ValueError(f"macro refresh task {name} is duplicated")
        tasks_by_name[name] = task

    for task in copied_tasks:
        _validate_task(task, tasks_by_name)

    ordered_tasks = sorted(copied_tasks, key=lambda task: task["plan_index"])
    edges = {task["name"]: set() for task in ordered_tasks}
    indegrees = {task["name"]: 0 for task in ordered_tasks}

    for task in ordered_tasks:
        for dependency in task["dependencies"]:
            _add_edge(edges, indegrees, dependency, task["name"])

    tasks_by_lane = group_tasks_by_lane(ordered_tasks)
    for lane_tasks in tasks_by_lane.values():
        for predecessor, task in zip(lane_tasks, lane_tasks[1:]):
            _add_edge(edges, indegrees, predecessor["name"], task["name"])

    ready = sorted(
        (task for task in ordered_tasks if indegrees[task["name"]] == 0),
        key=lambda task: (task["plan_index"], task["name"]),
    )
    visited = []
    while ready:
        task = ready.pop(0)
        task_name = task["name"]
        visited.append(task_name)
        for dependent in sorted(edges[task_name]):
            indegrees[dependent] -= 1
            if indegrees[dependent] == 0:
                ready.append(tasks_by_name[dependent])
                ready.sort(key=lambda item: (item["plan_index"], item["name"]))

    if len(visited) != len(ordered_tasks):
        raise ValueError("macro refresh task graph has a cycle")

    return ordered_tasks


def group_tasks_by_lane(tasks):
    grouped = {}
    ordered_tasks = sorted(tasks, key=lambda task: task["plan_index"])
    for task in ordered_tasks:
        grouped.setdefault(task["lane"], []).append(_copy_task(task))
    return grouped


def make_blocked_result(task, dependency_names, reason):
    dependencies = ", ".join(str(name) for name in dependency_names)
    error = f"{reason}: {dependencies}" if dependencies else str(reason)
    return {
        "name": task["name"],
        "lane": task["lane"],
        "status": "blocked",
        "exit_code": 1,
        "error": error,
        "stdout": "",
        "stderr": "",
    }


def _copy_task(task):
    return {
        **task,
        "argv": list(task["argv"]),
        "dependencies": list(task["dependencies"]),
        "accepted_dependency_statuses": list(task["accepted_dependency_statuses"]),
        "resources": list(task["resources"]),
    }


def _validate_task(task, tasks_by_name):
    name = task["name"]
    lane = task["lane"]
    if not isinstance(lane, str) or LANE_RE.fullmatch(lane) is None:
        raise ValueError(f"macro refresh task {name} has invalid lane {lane}")
    if task["stage"] not in VALID_STAGES:
        raise ValueError(f"macro refresh task {name} has invalid stage {task['stage']}")

    for dependency in task["dependencies"]:
        if dependency not in tasks_by_name:
            raise ValueError(
                f"macro refresh task {name} has unknown dependency {dependency}"
            )

    for status in task["accepted_dependency_statuses"]:
        if status not in VALID_DEPENDENCY_STATUSES:
            raise ValueError(
                f"macro refresh task {name} has invalid dependency status {status}"
            )

    resources = task["resources"]
    if len(resources) != len(set(resources)):
        duplicate = next(resource for resource in resources if resources.count(resource) > 1)
        raise ValueError(f"macro refresh task {name} has duplicate resource {duplicate}")

    for resource in resources:
        if resource not in VALID_RESOURCES:
            raise ValueError(f"macro refresh task {name} has invalid resource {resource}")
        if resource == "sqlite_writer" and task["stage"] != "persist":
            raise ValueError(
                "macro refresh resource sqlite_writer is only allowed on persist tasks"
            )
        if resource == "fred" and task["stage"] != "fetch":
            raise ValueError("macro refresh resource fred is only allowed on fetch tasks")


def _add_edge(edges, indegrees, source, target):
    if target not in edges[source]:
        edges[source].add(target)
        indegrees[target] += 1
