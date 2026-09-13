from __future__ import annotations

from pathlib import Path

import pytest

import guard_files
from helpers import RunHook


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        (".env", "deny"),
        ("services/api/.env.local", "deny"),
        (".env.production", "deny"),
        (".env.example", None),
        (".git/config", "deny"),
        ("uv.lock", "deny"),
        ("pnpm-lock.yaml", "deny"),
        ("apps/web/pnpm-lock.yaml", "deny"),
        (".claude/settings.json", "ask"),
        (".claude/hooks/guard_bash.py", "ask"),
        (".github/workflows/ci.yml", "ask"),
        (".pre-commit-config.yaml", "ask"),
        (".codex/config.toml", "ask"),
        ("scripts/gate.py", "ask"),
        (".claude/settings.local.json", None),
        ("services/api/src/api/main.py", None),
        ("scripts/other.py", None),
        ("README.md", None),
        (".github/PULL_REQUEST_TEMPLATE.md", None),
    ],
)
def test_classify(tmp_path: Path, rel: str, expected: str | None) -> None:
    decision = guard_files.classify(tmp_path / rel, tmp_path)
    assert (decision.kind if decision else None) == expected


def test_guardrail_paths_outside_repo_are_not_asked(tmp_path: Path) -> None:
    other = tmp_path / "elsewhere" / ".claude" / "settings.json"
    assert guard_files.classify(other, tmp_path / "repo") is None


def test_main_denies_env_write(run_hook: RunHook, git_repo: Path) -> None:
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(git_repo / ".env")}}
    res = run_hook(guard_files.main, payload, env={"CLAUDE_PROJECT_DIR": str(git_repo)})
    assert res.code == 0
    assert res.json()["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_asks_for_guardrails_via_git_root(run_hook: RunHook, git_repo: Path) -> None:
    target = git_repo / ".claude" / "hooks" / "new_hook.py"
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(target)}}
    res = run_hook(guard_files.main, payload, env={})
    assert res.json()["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_main_resolves_relative_paths_against_cwd(run_hook: RunHook, git_repo: Path) -> None:
    payload = {"tool_name": "Write", "cwd": str(git_repo), "tool_input": {"file_path": "uv.lock"}}
    res = run_hook(guard_files.main, payload, env={})
    assert res.json()["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_handles_notebooks(run_hook: RunHook, git_repo: Path) -> None:
    payload = {
        "tool_name": "NotebookEdit",
        "tool_input": {"notebook_path": str(git_repo / "a.ipynb")},
    }
    res = run_hook(guard_files.main, payload, env={})
    assert (res.code, res.stdout) == (0, "")


def test_main_ignores_other_tools(run_hook: RunHook) -> None:
    res = run_hook(guard_files.main, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert (res.code, res.stdout) == (0, "")


@pytest.mark.parametrize("payload", ["{bad", {"tool_name": "Write", "tool_input": {}}])
def test_main_fails_closed(run_hook: RunHook, payload: object) -> None:
    res = run_hook(guard_files.main, payload)
    assert res.code == 2
    assert "guard_files" in res.stderr
