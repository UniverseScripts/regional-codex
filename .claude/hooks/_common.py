"""Shared helpers for the repo's agent hooks (Claude Code and Codex). Stdlib only.

Hooks are invoked as plain scripts (``python .claude/hooks/<name>.py``), so this module
is imported by sibling scripts via ``sys.path[0]`` and by tests via pytest's pythonpath.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

JsonDict = dict[str, Any]

STATE_DIR = Path(".claude") / "state"
GATE_MODES = ("full", "fast", "off")
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]")
_MAX_UNTRACKED_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class Decision:
    """A PreToolUse permission decision: ``deny`` or ``ask``."""

    kind: str
    reason: str


@dataclass(frozen=True)
class HookIO:
    """Streams and environment a hook runs with (injectable for tests)."""

    stdin: TextIO
    stdout: TextIO
    stderr: TextIO
    env: Mapping[str, str]

    @classmethod
    def resolve(
        cls,
        stdin: TextIO | None,
        stdout: TextIO | None,
        stderr: TextIO | None,
        env: Mapping[str, str] | None,
    ) -> HookIO:
        out = stdout or _utf8(sys.stdout)
        err = stderr or _utf8(sys.stderr)
        return cls(stdin or sys.stdin, out, err, os.environ if env is None else env)


def _utf8(stream: TextIO) -> TextIO:
    """Make real console streams tolerant of non-ASCII tool output on Windows."""
    if isinstance(stream, io.TextIOWrapper):
        stream.reconfigure(encoding="utf-8", errors="replace")
    return stream


def read_payload(stdin: TextIO) -> JsonDict:
    """Parse the hook's JSON payload. Reads raw bytes when available (UTF-8 safe on Windows)."""
    buffer = getattr(stdin, "buffer", None)
    raw = buffer.read().decode("utf-8") if buffer is not None else stdin.read()
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise TypeError("hook payload must be a JSON object")
    return data


def emit(stdout: TextIO, obj: JsonDict) -> None:
    stdout.write(json.dumps(obj) + "\n")


def pretool_decision(decision: Decision) -> JsonDict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision.kind,
            "permissionDecisionReason": decision.reason,
        }
    }


def additional_context(event: str, text: str) -> JsonDict:
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def normalize_gate_mode(value: str | None) -> str:
    mode = (value or "full").strip().lower()
    return mode if mode in GATE_MODES else "full"


def run(
    cmd: Sequence[str], cwd: Path, *, timeout: float = 30
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(list(cmd), cwd=cwd, capture_output=True, timeout=timeout, check=False)


def git_toplevel(path: Path) -> Path | None:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.is_file():
        probe = probe.parent
    try:
        proc = run(["git", "rev-parse", "--show-toplevel"], probe)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return Path(proc.stdout.decode("utf-8", "replace").strip())


def project_root(env: Mapping[str, str], payload: JsonDict) -> Path:
    """Repo root: CLAUDE_PROJECT_DIR, else the payload cwd, else the process cwd (git toplevel wins)."""
    for candidate in (env.get("CLAUDE_PROJECT_DIR"), payload.get("cwd")):
        if isinstance(candidate, str) and candidate:
            base = Path(candidate)
            return git_toplevel(base) or base
    cwd = Path.cwd()
    return git_toplevel(cwd) or cwd


def tree_fingerprint(root: Path) -> str:
    """Hash of HEAD + staged + unstaged + untracked content. Changes whenever the work tree does."""
    inside = run(["git", "rev-parse", "--is-inside-work-tree"], root)
    if inside.returncode != 0:
        return "nogit"
    digest = hashlib.sha256()
    for args in (
        ["rev-parse", "--verify", "-q", "HEAD"],
        ["diff", "--binary", "--no-ext-diff"],
        ["diff", "--cached", "--binary", "--no-ext-diff"],
    ):
        digest.update(run(["git", *args], root).stdout)
        digest.update(b"\0")
    listing = run(
        [
            "git",
            "ls-files",
            "-o",
            "--exclude-standard",
            "-z",
            "--",
            ".",
            f":(exclude){STATE_DIR.as_posix()}",
        ],
        root,
    ).stdout
    for rel in sorted(entry for entry in listing.split(b"\0") if entry):
        digest.update(rel + b"\0")
        path = root / os.fsdecode(rel)
        try:
            if path.is_file() and path.stat().st_size <= _MAX_UNTRACKED_BYTES:
                digest.update(path.read_bytes())
        except OSError:
            digest.update(b"?")
    return digest.hexdigest()


def state_path(root: Path, name: str) -> Path:
    safe = _UNSAFE_NAME.sub("_", name).strip(".") or "default"
    return root / STATE_DIR / f"{safe}.json"


def load_state(root: Path, name: str) -> JsonDict:
    try:
        data = json.loads(state_path(root, name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(root: Path, name: str, data: JsonDict) -> None:
    path = state_path(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def prune_state(root: Path, *, max_age_days: float = 7) -> None:
    cutoff = time.time() - max_age_days * 86400
    for path in (root / STATE_DIR).glob("session-*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue
