import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = ROOT / ".githooks" / "pre-commit"


def _run_git(repository, *args, check=True):
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        check=check,
        text=True,
        capture_output=True,
    )


def _init_repository(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    _run_git(repository, "init")
    _run_git(repository, "config", "user.email", "test@example.com")
    _run_git(repository, "config", "user.name", "Test User")
    hook_dir = repository / ".githooks"
    hook_dir.mkdir()
    installed_hook = hook_dir / "pre-commit"
    shutil.copy(HOOK_PATH, installed_hook)
    installed_hook.chmod(0o755)
    _run_git(repository, "config", "core.hooksPath", ".githooks")
    return repository


def test_precommit_hook_rejects_force_staged_superpowers_docs(tmp_path):
    repository = _init_repository(tmp_path)
    document = repository / "docs" / "superpowers" / "plan.md"
    document.parent.mkdir(parents=True)
    document.write_text("private plan\n")
    _run_git(repository, "add", "-f", "docs/superpowers/plan.md")

    result = _run_git(
        repository,
        "commit",
        "-m",
        "attempt prohibited commit",
        check=False,
    )

    assert result.returncode != 0
    assert "docs/superpowers/" in result.stderr


def test_precommit_hook_rejects_force_staged_data_file(tmp_path):
    repository = _init_repository(tmp_path)
    document = repository / "data" / "private" / "example.json"
    document.parent.mkdir(parents=True)
    document.write_text("private data\n")
    _run_git(repository, "add", "-f", "data/private/example.json")

    result = _run_git(
        repository,
        "commit",
        "-m",
        "attempt prohibited data commit",
        check=False,
    )

    assert result.returncode != 0
    assert "data/" in result.stderr


def test_precommit_hook_allows_other_staged_files(tmp_path):
    repository = _init_repository(tmp_path)
    document = repository / "readme.txt"
    document.write_text("allowed\n")
    _run_git(repository, "add", "readme.txt")

    result = _run_git(repository, "commit", "-m", "allow ordinary file", check=False)

    assert result.returncode == 0
