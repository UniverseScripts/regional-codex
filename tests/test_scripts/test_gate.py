from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

import gate


def _names(steps: list[gate.Step]) -> list[str]:
    return [s.name for s in steps]


def test_local_plan_autofixes_then_checks(tmp_path: Path) -> None:
    steps = gate.build_plan(tmp_path, fast=False, ci=False)
    assert _names(steps) == [
        "ruff format (fix)",
        "ruff check (fix)",
        "ruff lint",
        "ruff format",
        "mypy",
        "pytest",
    ]
    assert [s.advisory for s in steps[:2]] == [True, True]
    assert not any(s.advisory for s in steps[2:])
    assert "F401,F841" in steps[1].cmd


def test_fast_plan_skips_tests(tmp_path: Path) -> None:
    assert "pytest" not in _names(gate.build_plan(tmp_path, fast=True, ci=False))


def test_ci_plan_has_no_autofix_and_enforces_coverage(tmp_path: Path) -> None:
    steps = gate.build_plan(tmp_path, fast=False, ci=True)
    assert not any("(fix)" in name for name in _names(steps))
    pytest_step = next(s for s in steps if s.name == "pytest")
    assert "--cov" in pytest_step.cmd
    assert "--junitxml=junit.xml" in pytest_step.cmd
    assert "--output-format=github" in next(s for s in steps if s.name == "ruff lint").cmd


def test_web_steps_activate_when_an_app_exists(tmp_path: Path) -> None:
    assert not gate.has_web(tmp_path)
    app = tmp_path / "apps" / "web"
    app.mkdir(parents=True)
    (app / "package.json").write_text("{}", encoding="utf-8")
    assert gate.has_web(tmp_path)
    assert {"biome", "web typecheck", "web test"} <= set(
        _names(gate.build_plan(tmp_path, fast=False, ci=False))
    )
    assert "web test" not in _names(gate.build_plan(tmp_path, fast=True, ci=False))


def _fake_runner(failing: set[str]) -> gate.Runner:
    def run(step: gate.Step, root: Path) -> gate.StepResult:
        ok = step.name not in failing
        return gate.StepResult(
            step.name, ok, 0 if ok else 1, 0.01, "" if ok else f"{step.name} broke", step.advisory
        )

    return run


def test_json_summary_on_failure(tmp_path: Path) -> None:
    out = io.StringIO()
    code = gate.main(
        ["--json"], root=tmp_path, runner=_fake_runner({"mypy", "ruff format (fix)"}), stdout=out
    )
    summary = json.loads(out.getvalue().strip().splitlines()[-1])
    assert code == 1
    assert summary["ok"] is False
    by_name = {s["name"]: s for s in summary["steps"]}
    assert by_name["mypy"]["output"] == "mypy broke"
    assert by_name["ruff format (fix)"]["output"] == ""  # advisory failures never fail the gate


def test_advisory_failures_alone_pass(tmp_path: Path) -> None:
    out = io.StringIO()
    assert gate.main([], root=tmp_path, runner=_fake_runner({"ruff check (fix)"}), stdout=out) == 0
    text = out.getvalue()
    assert "WARN  ruff check (fix)" in text
    assert "Quality gate: PASSED" in text


def test_human_report_shows_failure_output(tmp_path: Path) -> None:
    out = io.StringIO()
    assert gate.main(["--fast"], root=tmp_path, runner=_fake_runner({"ruff lint"}), stdout=out) == 1
    text = out.getvalue()
    assert "FAIL  ruff lint" in text
    assert "ruff lint broke" in text
    assert "Quality gate: FAILED" in text


def test_tail_truncates_long_output() -> None:
    text = gate.tail("x" * 10_000, limit=100)
    assert text.startswith("...(truncated)...")
    assert len(text) < 200


def test_run_step_executes_commands(tmp_path: Path) -> None:
    result = gate.run_step(gate.Step("hello", (sys.executable, "-c", "print('hi')")), tmp_path)
    assert result.ok
    assert result.output.strip() == "hi"


def test_run_step_reports_nonzero_exit(tmp_path: Path) -> None:
    result = gate.run_step(
        gate.Step("boom", (sys.executable, "-c", "raise SystemExit(3)")), tmp_path
    )
    assert (result.ok, result.returncode) == (False, 3)


def test_run_step_reports_missing_executables(tmp_path: Path) -> None:
    result = gate.run_step(gate.Step("ghost", ("definitely-not-a-real-binary-xyz",)), tmp_path)
    assert (result.ok, result.returncode) == (False, 127)
    assert "could not start" in result.output


def test_cli_help_exits_cleanly() -> None:
    with pytest.raises(SystemExit) as exc:
        gate.main(["--help"], stdout=io.StringIO())
    assert exc.value.code == 0
