"""Shared fixtures for the repo's tooling tests."""

from __future__ import annotations

from pathlib import Path

import pytest

import helpers

# Set by git when tests run inside a git hook (e.g. pre-push); they would hijack tmp repos.
_GIT_ENV_LEAKS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_PREFIX",
)


@pytest.fixture(autouse=True)
def _isolate_git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _GIT_ENV_LEAKS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def run_hook() -> helpers.RunHook:
    return helpers.run_hook


@pytest.fixture
def git() -> helpers.Git:
    return helpers.git


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A committed repo with hooks disabled, isolated from the developer's git config."""
    repo = tmp_path / "repo"
    repo.mkdir()
    hooks = tmp_path / "no-hooks"
    hooks.mkdir()
    helpers.git(repo, "init", "-q", "-b", "main")
    for key, value in (
        ("user.email", "dev@example.com"),
        ("user.name", "Dev"),
        ("commit.gpgsign", "false"),
        ("core.autocrlf", "false"),
        ("core.hooksPath", hooks.as_posix()),
    ):
        helpers.git(repo, "config", key, value)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    helpers.git(repo, "add", "README.md")
    helpers.git(repo, "commit", "-q", "-m", "chore: init")
    return repo
