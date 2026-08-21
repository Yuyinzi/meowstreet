import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def copy_tracked_runtime(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    deleted_result = subprocess.run(
        ["git", "ls-files", "-z", "--deleted"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    deleted_paths = {
        raw_path.decode("utf-8")
        for raw_path in deleted_result.stdout.split(b"\0")
        if raw_path
    }
    excluded_prefixes = ("docs/", "method_notes/", "static/dist/")
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative = Path(raw_path.decode("utf-8"))
        if relative.as_posix() in deleted_paths:
            continue
        if relative.as_posix().startswith(excluded_prefixes):
            continue
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    return repository


def test_api_import_and_bootstrap_do_not_require_ignored_local_files(tmp_path):
    repository = copy_tracked_runtime(tmp_path)
    environment = dict(os.environ, PYTHONPATH=str(repository))
    imported = subprocess.run(
        [sys.executable, "-c", "import app.api; print('import ok')"],
        cwd=repository,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert imported.returncode == 0, imported.stderr
    assert imported.stdout.strip() == "import ok"
    bootstrapped = subprocess.run(
        [
            sys.executable,
            "scripts/bootstrap_local_data.py",
            "--db-path",
            str(tmp_path / "market_data.sqlite"),
        ],
        cwd=repository,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert bootstrapped.returncode == 0, bootstrapped.stderr
