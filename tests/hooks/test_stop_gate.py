from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import _common
import stop_gate
from helpers import HookResult, RunHook


class FakeGate:
    def __init__(self, *outcomes: stop_gate.GateOutcome | Exception) -> None:
        self.outcomes = list(outcomes)
        self.modes: list[str] = []

    def __call__(self, root: Path, mode: str) -> stop_gate.GateOutcome:
        self.modes.append(mode)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


PASS = stop_gate.GateOutcome(ok=True, report="")
FAIL = stop_gate.GateOutcome(ok=False, report="[mypy] FAILED\nerror: bad types")


def _stop(
    run_hook: RunHook,
    repo: Path,
    gate: FakeGate,
    *,
    mode: str = "full",
    argv: list[str] | None = None,
) -> HookResult:
    return run_hook(
        stop_gate.main,
        {"session_id": "s1", "hook_event_name": "Stop", "stop_hook_active": False},
        env={"CLAUDE_PROJECT_DIR": str(repo), "CLAUDE_GATE": mode},
        argv=argv,
        gate=gate,
    )


def _baseline(repo: Path) -> None:
    _common.save_state(
        repo, "session-s1", {"baseline": _common.tree_fingerprint(repo), "blocks": 0}
    )


def _touch(repo: Path, text: str = "x = 1\n") -> None:
    (repo / "mod.py").write_text(text, encoding="utf-8")


def test_off_mode_never_runs_the_gate(run_hook: RunHook, git_repo: Path) -> None:
    _touch(git_repo)
    gate = FakeGate()
    res = _stop(run_hook, git_repo, gate, mode="off")
    assert (res.code, res.json(), gate.modes) == (0, {}, [])


def test_unchanged_tree_since_session_start_skips(run_hook: RunHook, git_repo: Path) -> None:
    _touch(git_repo)  # pre-existing dirt (e.g. a teammate's WIP) is not this session's problem
    _baseline(git_repo)
    gate = FakeGate()
    assert _stop(run_hook, git_repo, gate).code == 0
    assert gate.modes == []


def test_changed_tree_runs_gate_and_records_pass(run_hook: RunHook, git_repo: Path) -> None:
    _baseline(git_repo)
    _touch(git_repo)
    gate = FakeGate(PASS)
    res = _stop(run_hook, git_repo, gate)
    assert (res.code, res.json(), gate.modes) == (0, {}, ["full"])
    assert _common.load_state(git_repo, "last-pass")["fingerprint"] == _common.tree_fingerprint(
        git_repo
    )
    assert _stop(run_hook, git_repo, FakeGate()).code == 0  # nothing new: no rerun


def test_failure_blocks_with_report(run_hook: RunHook, git_repo: Path) -> None:
    _baseline(git_repo)
    _touch(git_repo)
    res = _stop(run_hook, git_repo, FakeGate(FAIL))
    assert res.code == 2
    assert "error: bad types" in res.stderr
    assert "attempt 1/3" in res.stderr
    assert "uv run poe check" in res.stderr


def test_loop_guard_gives_up_after_max_blocks(run_hook: RunHook, git_repo: Path) -> None:
    _baseline(git_repo)
    for attempt in range(stop_gate.MAX_BLOCKS):
        _touch(git_repo, f"x = {attempt}\n")
        assert _stop(run_hook, git_repo, FakeGate(FAIL)).code == 2
    gate = FakeGate()
    res = _stop(run_hook, git_repo, gate)
    assert res.code == 0
    assert "still failing" in res.json()["systemMessage"]
    assert gate.modes == []
    assert _stop(run_hook, git_repo, FakeGate()).code == 0  # same tree: stays quiet
    _touch(git_repo, "x = 'new'\n")
    assert _stop(run_hook, git_repo, FakeGate(FAIL)).code == 2  # new edits: gate is back


def test_pass_resets_the_block_counter(run_hook: RunHook, git_repo: Path) -> None:
    _baseline(git_repo)
    _touch(git_repo, "x = 1\n")
    assert _stop(run_hook, git_repo, FakeGate(FAIL)).code == 2
    _touch(git_repo, "x = 2\n")
    assert _stop(run_hook, git_repo, FakeGate(PASS)).code == 0
    assert _common.load_state(git_repo, "session-s1")["blocks"] == 0


def test_fast_mode_and_flag_override(run_hook: RunHook, git_repo: Path) -> None:
    _touch(git_repo)
    gate = FakeGate(PASS)
    _stop(run_hook, git_repo, gate, mode="full", argv=["--mode", "fast"])
    assert gate.modes == ["fast"]


def test_fast_pass_does_not_satisfy_full(run_hook: RunHook, git_repo: Path) -> None:
    _touch(git_repo)
    _stop(run_hook, git_repo, FakeGate(PASS), mode="fast")
    full = FakeGate(PASS)
    _stop(run_hook, git_repo, full, mode="full")
    assert full.modes == ["full"]
    again = FakeGate()
    _stop(run_hook, git_repo, again, mode="fast")  # a full pass satisfies fast
    assert again.modes == []


def test_gate_crash_fails_open_visibly(run_hook: RunHook, git_repo: Path) -> None:
    _touch(git_repo)
    res = _stop(run_hook, git_repo, FakeGate(FileNotFoundError("uv")))
    assert res.code == 0
    assert "could not run" in res.json()["systemMessage"]


def test_bad_payload_fails_open(run_hook: RunHook) -> None:
    res = run_hook(stop_gate.main, "{bad", env={}, gate=FakeGate())
    assert res.code == 0
    assert "systemMessage" in res.json()


def _fake_proc(stdout: str, stderr: str = "") -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess([], 0, stdout.encode(), stderr.encode())


def test_run_gate_parses_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    summary = {
        "ok": False,
        "steps": [
            {"name": "ruff (fix)", "ok": False, "advisory": True, "output": ""},
            {"name": "mypy", "ok": False, "advisory": False, "output": "error: nope"},
            {"name": "pytest", "ok": True, "advisory": False, "output": ""},
        ],
    }
    seen: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        seen.append(cmd)
        return _fake_proc("noise\n" + json.dumps(summary) + "\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    outcome = stop_gate.run_gate(tmp_path, "fast")
    assert not outcome.ok
    assert "[mypy] FAILED" in outcome.report
    assert "ruff (fix)" not in outcome.report
    assert seen[0][-1] == "--fast"


@pytest.mark.parametrize(("stdout", "error"), [("", RuntimeError), ('"just a string"', TypeError)])
def test_run_gate_rejects_garbage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stdout: str, error: type[Exception]
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda cmd, **_: _fake_proc(stdout, "boom"))
    with pytest.raises(error):
        stop_gate.run_gate(tmp_path, "full")


def test_report_is_truncated(run_hook: RunHook, git_repo: Path) -> None:
    _touch(git_repo)
    res = _stop(run_hook, git_repo, FakeGate(stop_gate.GateOutcome(ok=False, report="E" * 50_000)))
    assert "(truncated)" in res.stderr
    assert len(res.stderr) < 10_000
