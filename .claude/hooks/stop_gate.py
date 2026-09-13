"""Stop hook: block the end of a turn until the quality gate passes. Shared by Claude Code and Codex.

* Runs only when the work tree changed since the session started (and since the last pass),
  so Q&A sessions and a teammate's pre-existing breakage never block.
* On failure: report on stderr + exit 2 (both agents treat that as "keep working").
* Loop guard: after MAX_BLOCKS consecutive failures it lets the agent stop, loudly.
* Fails open (with a visible warning) if the gate itself can't run, e.g. uv is missing.
* Mode: ``--mode`` flag, else ``CLAUDE_GATE`` (full | fast | off), default full.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from _common import (
    HookIO,
    JsonDict,
    emit,
    load_state,
    normalize_gate_mode,
    project_root,
    read_payload,
    save_state,
    tree_fingerprint,
)

MAX_BLOCKS = 3
GATE_TIMEOUT_SECONDS = 540
_REPORT_CHARS = 6000


@dataclass(frozen=True)
class GateOutcome:
    ok: bool
    report: str


GateRunner = Callable[[Path, str], GateOutcome]


def run_gate(root: Path, mode: str) -> GateOutcome:
    cmd = ["uv", "run", "--frozen", "python", "scripts/gate.py", "--json"]
    if mode == "fast":
        cmd.append("--fast")
    proc = subprocess.run(
        cmd, cwd=root, capture_output=True, timeout=GATE_TIMEOUT_SECONDS, check=False
    )
    lines = proc.stdout.decode("utf-8", "replace").strip().splitlines()
    if not lines:
        raise RuntimeError(
            proc.stderr.decode("utf-8", "replace").strip()[-500:] or "gate printed nothing"
        )
    summary = json.loads(lines[-1])
    if not isinstance(summary, dict) or "ok" not in summary:
        raise TypeError("unexpected gate summary")
    failed = [s for s in summary.get("steps", []) if not s.get("ok") and not s.get("advisory")]
    report = "\n\n".join(f"[{s.get('name')}] FAILED\n{s.get('output', '').strip()}" for s in failed)
    return GateOutcome(bool(summary["ok"]), report)


def _satisfied(last_pass: JsonDict, fingerprint: str, mode: str) -> bool:
    return last_pass.get("fingerprint") == fingerprint and (
        last_pass.get("mode") == "full" or mode == "fast"
    )


def _truncate(text: str) -> str:
    return text if len(text) <= _REPORT_CHARS else text[:_REPORT_CHARS] + "\n... (truncated)"


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    env: Mapping[str, str] | None = None,
    gate: GateRunner | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="stop_gate")
    parser.add_argument("--mode", choices=["full", "fast", "off"])
    args = parser.parse_args(list(argv or []))
    hook_io = HookIO.resolve(stdin, stdout, stderr, env)
    try:
        payload = read_payload(hook_io.stdin)
        mode = normalize_gate_mode(args.mode or hook_io.env.get("CLAUDE_GATE"))
        if mode == "off":
            emit(hook_io.stdout, {})
            return 0
        root = project_root(hook_io.env, payload)
        key = f"session-{payload.get('session_id') or 'unknown'}"
        state = load_state(root, key)
        fingerprint = tree_fingerprint(root)
        if fingerprint in {state.get("baseline"), state.get("gave_up")} or _satisfied(
            load_state(root, "last-pass"), fingerprint, mode
        ):
            emit(hook_io.stdout, {})
            return 0
        if int(state.get("blocks", 0)) >= MAX_BLOCKS:
            state.update(blocks=0, gave_up=fingerprint)
            save_state(root, key, state)
            emit(
                hook_io.stdout,
                {
                    "systemMessage": (
                        f"Quality gate still failing after {MAX_BLOCKS} attempts; stopping anyway. "
                        "Run `uv run poe check` and fix before committing."
                    )
                },
            )
            return 0
        outcome = (gate or run_gate)(root, mode)
    except Exception as exc:  # fail open, visibly
        emit(
            hook_io.stdout,
            {
                "systemMessage": (
                    f"stop_gate: quality gate could not run ({exc!r}); run `uv run poe check` manually."
                )
            },
        )
        return 0
    if outcome.ok:
        save_state(root, "last-pass", {"fingerprint": tree_fingerprint(root), "mode": mode})
        state.update(blocks=0, gave_up=None)
        save_state(root, key, state)
        emit(hook_io.stdout, {})
        return 0
    attempt = int(state.get("blocks", 0)) + 1
    state["blocks"] = attempt
    save_state(root, key, state)
    reproduce = "uv run poe check" + ("-fast" if mode == "fast" else "")
    hook_io.stderr.write(
        f"Quality gate FAILED (attempt {attempt}/{MAX_BLOCKS}, mode={mode}). Fix every issue below "
        f"before finishing; reproduce with `{reproduce}`.\n\n{_truncate(outcome.report)}\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
