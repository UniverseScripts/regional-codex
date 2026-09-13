"""PreToolUse guard for file edits. Fails closed.

Denies edits to secrets, git internals and generated lockfiles; asks before touching the
guardrail files themselves so standards can't be weakened silently.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from _common import (
    Decision,
    HookIO,
    JsonDict,
    emit,
    git_toplevel,
    pretool_decision,
    project_root,
    read_payload,
)

EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
_ENV_TEMPLATES = frozenset({".env.example", ".env.sample", ".env.template"})
_LOCKFILES = frozenset(
    {"uv.lock", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "poetry.lock"}
)
_GUARDRAIL_FILES = frozenset(
    {".claude/settings.json", ".pre-commit-config.yaml", ".codex/config.toml", "scripts/gate.py"}
)
_GUARDRAIL_DIRS = (".claude/hooks/", ".github/workflows/")


def classify(path: Path, root: Path) -> Decision | None:
    name = path.name.lower()
    if (name == ".env" or name.startswith(".env.")) and name not in _ENV_TEMPLATES:
        return Decision("deny", "Secrets files (.env*) are off-limits; edit .env.example instead.")
    if ".git" in path.parts:
        return Decision("deny", "Never edit git internals (.git/).")
    if name in _LOCKFILES:
        return Decision("deny", "Lockfiles are generated; use `uv add`/`uv lock` or `pnpm add`.")
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    if rel in _GUARDRAIL_FILES or rel.startswith(_GUARDRAIL_DIRS):
        return Decision("ask", f"`{rel}` is a guardrail file; confirm this change with the user.")
    return None


def target_from(payload: JsonDict) -> Path | None:
    """Absolute path an edit tool is about to touch, or None for other tools."""
    if payload.get("tool_name") not in EDIT_TOOLS:
        return None
    tool_input = payload.get("tool_input") or {}
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw_path, str) or not raw_path:
        raise TypeError("tool_input.file_path must be a non-empty string")
    path = Path(raw_path)
    return path if path.is_absolute() else Path(str(payload.get("cwd") or Path.cwd())) / path


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    del argv
    hook_io = HookIO.resolve(stdin, stdout, stderr, env)
    try:
        payload = read_payload(hook_io.stdin)
        path = target_from(payload)
        decision = None
        if path is not None:
            root = git_toplevel(path.parent) or project_root(hook_io.env, payload)
            decision = classify(path, root)
    except Exception as exc:  # fail closed
        hook_io.stderr.write(f"guard_files: blocked; could not inspect the edit ({exc!r}).\n")
        return 2
    if decision is not None:
        emit(hook_io.stdout, pretool_decision(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
