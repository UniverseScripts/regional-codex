from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

import post_edit
from helpers import RunHook


class FakeRunner:
    def __init__(self, responses: dict[str, tuple[int, str]] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[list[str]] = []

    def __call__(self, cmd: Sequence[str], cwd: Path) -> tuple[int, str]:
        self.calls.append(list(cmd))
        for needle, response in self.responses.items():
            if needle in cmd:
                return response
        return 0, ""


def _payload(path: Path) -> dict[str, object]:
    return {"tool_name": "Write", "tool_input": {"file_path": str(path)}}


def test_reports_ruff_findings(run_hook: RunHook, git_repo: Path) -> None:
    target = git_repo / "mod.py"
    target.write_text("import os\n", encoding="utf-8")
    runner = FakeRunner({"check": (1, "mod.py:1:8: F401 `os` imported but unused")})
    res = run_hook(post_edit.main, _payload(target), runner=runner)
    assert res.code == 0
    context = res.json()["hookSpecificOutput"]["additionalContext"]
    assert "F401" in context
    assert runner.calls[0][-1] == "mod.py"


def test_reports_format_drift(run_hook: RunHook, git_repo: Path) -> None:
    target = git_repo / "mod.py"
    target.write_text("x=1\n", encoding="utf-8")
    res = run_hook(
        post_edit.main, _payload(target), runner=FakeRunner({"format": (1, "Would reformat")})
    )
    assert "ruff format" in res.json()["hookSpecificOutput"]["additionalContext"]


def test_clean_python_file_is_silent(run_hook: RunHook, git_repo: Path) -> None:
    target = git_repo / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    res = run_hook(post_edit.main, _payload(target), runner=FakeRunner())
    assert (res.code, res.stdout) == (0, "")


def test_non_code_files_are_ignored(run_hook: RunHook, git_repo: Path) -> None:
    runner = FakeRunner()
    res = run_hook(post_edit.main, _payload(git_repo / "README.md"), runner=runner)
    assert (res.code, res.stdout, runner.calls) == (0, "", [])


def test_web_files_need_biome_installed(run_hook: RunHook, git_repo: Path) -> None:
    target = git_repo / "app.ts"
    target.write_text("let x = 1\n", encoding="utf-8")
    runner = FakeRunner({"biome": (1, "lint/style/useConst")})
    assert run_hook(post_edit.main, _payload(target), runner=runner).stdout == ""
    (git_repo / "node_modules" / "@biomejs" / "biome").mkdir(parents=True)
    res = run_hook(post_edit.main, _payload(target), runner=runner)
    assert "useConst" in res.json()["hookSpecificOutput"]["additionalContext"]


def test_long_output_is_truncated(run_hook: RunHook, git_repo: Path) -> None:
    target = git_repo / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    res = run_hook(
        post_edit.main, _payload(target), runner=FakeRunner({"check": (1, "E" * 10_000)})
    )
    assert len(res.json()["hookSpecificOutput"]["additionalContext"]) < 3000


def test_files_outside_the_repo_are_ignored(tmp_path: Path) -> None:
    outside = tmp_path / "x.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    assert post_edit.diagnostics(outside, tmp_path / "repo", FakeRunner()) == []


@pytest.mark.parametrize(
    "payload",
    [
        "{bad json",
        {"tool_name": "Write", "tool_input": {}},
        {"tool_input": {"file_path": "/nope/x.py"}},
    ],
)
def test_fails_open(run_hook: RunHook, payload: object) -> None:
    assert run_hook(post_edit.main, payload, runner=FakeRunner()).code == 0


def test_runner_errors_fail_open(run_hook: RunHook, git_repo: Path) -> None:
    target = git_repo / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    def broken(cmd: Sequence[str], cwd: Path) -> tuple[int, str]:
        raise OSError("uv not found")

    res = run_hook(post_edit.main, _payload(target), runner=broken)
    assert res.code == 0
    assert "skipped" in res.stderr


def test_default_runner_runs_commands(tmp_path: Path) -> None:
    import sys

    code, out = post_edit.default_runner([sys.executable, "-c", "print('hi')"], tmp_path)
    assert (code, out.strip()) == (0, "hi")
