"""The repo's single quality gate: `uv run poe check` (Definition of Done).

Used identically by humans, Claude Code (Stop hook), Codex (Stop hook + AGENTS.md), the
pre-push git hook and CI. Stdlib only.

    python scripts/gate.py          # autofix format/safe lint, then lint, types, tests
    python scripts/gate.py --fast   # same, without test suites
    python scripts/gate.py --ci     # no autofix; coverage + junit enforced
    python scripts/gate.py --json   # machine-readable summary (last stdout line)
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_TAIL_CHARS = 4000


@dataclass(frozen=True)
class Step:
    name: str
    cmd: tuple[str, ...]
    advisory: bool = False  # autofix steps never fail the gate


@dataclass(frozen=True)
class StepResult:
    name: str
    ok: bool
    returncode: int
    seconds: float
    output: str
    advisory: bool = False


Runner = Callable[[Step, Path], StepResult]


def has_web(root: Path) -> bool:
    return any(root.glob("apps/*/package.json")) or any(root.glob("packages/*/package.json"))


def build_plan(root: Path, *, fast: bool, ci: bool) -> list[Step]:
    py = (sys.executable, "-m")
    steps: list[Step] = []
    if not ci:
        steps += [
            Step("ruff format (fix)", (*py, "ruff", "format", "."), advisory=True),
            Step(
                "ruff check (fix)",
                (*py, "ruff", "check", "--fix", "--unfixable", "F401,F841", "--exit-zero", "."),
                advisory=True,
            ),
        ]
    lint_fmt = ("--output-format=github",) if ci else ()
    steps += [
        Step("ruff lint", (*py, "ruff", "check", *lint_fmt, ".")),
        Step("ruff format", (*py, "ruff", "format", "--check", ".")),
        Step("mypy", (*py, "mypy")),
    ]
    if not fast:
        cov = (
            (
                "--cov",
                "--cov-report=term-missing:skip-covered",
                "--cov-report=xml",
                "--junitxml=junit.xml",
            )
            if ci
            else ()
        )
        steps.append(Step("pytest", (*py, "pytest", "-q", *cov)))
    if has_web(root):
        steps += [
            Step("biome", ("pnpm", "exec", "biome", "ci", ".")),
            Step("web typecheck", ("pnpm", "-r", "--if-present", "typecheck")),
        ]
        if not fast:
            steps.append(Step("web test", ("pnpm", "-r", "--if-present", "test")))
    return steps


def run_step(step: Step, root: Path) -> StepResult:
    exe = shutil.which(step.cmd[0]) or step.cmd[0]
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            [exe, *step.cmd[1:]],
            cwd=root,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
    except OSError as exc:
        elapsed = time.perf_counter() - start
        return StepResult(
            step.name, False, 127, elapsed, f"could not start `{step.cmd[0]}`: {exc}", step.advisory
        )
    output = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    elapsed = time.perf_counter() - start
    return StepResult(
        step.name, proc.returncode == 0, proc.returncode, elapsed, output, step.advisory
    )


def tail(text: str, limit: int = OUTPUT_TAIL_CHARS) -> str:
    text = text.strip()
    return text if len(text) <= limit else "...(truncated)...\n" + text[-limit:]


def summarize(results: Sequence[StepResult], ok: bool) -> dict[str, object]:
    return {
        "ok": ok,
        "steps": [
            {
                "name": r.name,
                "ok": r.ok,
                "advisory": r.advisory,
                "returncode": r.returncode,
                "seconds": round(r.seconds, 2),
                "output": "" if r.ok or r.advisory else tail(r.output),
            }
            for r in results
        ],
    }


def report_human(results: Sequence[StepResult], ok: bool, out: TextIO) -> None:
    for r in results:
        status = "PASS" if r.ok else ("WARN" if r.advisory else "FAIL")
        out.write(f"{status}  {r.name}  ({r.seconds:.1f}s)\n")
    for r in results:
        if not r.ok and not r.advisory:
            out.write(f"\n---- {r.name} (exit {r.returncode}) ----\n{tail(r.output)}\n")
    out.write(f"\nQuality gate: {'PASSED' if ok else 'FAILED'}\n")


def main(
    argv: Sequence[str] | None = None,
    *,
    root: Path | None = None,
    runner: Runner | None = None,
    stdout: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="gate", description="Repo quality gate (Definition of Done)."
    )
    parser.add_argument("--fast", action="store_true", help="skip test suites")
    parser.add_argument(
        "--ci", action="store_true", help="no autofix; enforce coverage, write junit"
    )
    parser.add_argument("--json", action="store_true", help="print a JSON summary as the last line")
    args = parser.parse_args(argv)
    base = root or ROOT
    run = runner or run_step
    out = stdout or sys.stdout
    if isinstance(out, io.TextIOWrapper):
        out.reconfigure(errors="replace")
    results = [run(step, base) for step in build_plan(base, fast=args.fast, ci=args.ci)]
    ok = all(r.ok for r in results if not r.advisory)
    if args.json:
        out.write(json.dumps(summarize(results, ok)) + "\n")
    else:
        report_human(results, ok, out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
