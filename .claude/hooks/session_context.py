"""SessionStart hook: inject the repo's standing rules and record a work-tree baseline. Fails open."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import TextIO

from _common import (
    HookIO,
    additional_context,
    emit,
    normalize_gate_mode,
    project_root,
    prune_state,
    read_payload,
    run,
    save_state,
    tree_fingerprint,
)

D_DAY = date(2026, 10, 31)
GIT_HOOKS = ("pre-commit", "commit-msg", "pre-push")


def _git_text(root: Path, *args: str) -> str:
    proc = run(["git", *args], root)
    return proc.stdout.decode("utf-8", "replace").strip() if proc.returncode == 0 else ""


def missing_git_hooks(root: Path) -> list[str]:
    hooks_dir = _git_text(root, "rev-parse", "--git-path", "hooks")
    if not hooks_dir:
        return list(GIT_HOOKS)
    base = Path(hooks_dir) if Path(hooks_dir).is_absolute() else root / hooks_dir
    missing = []
    for name in GIT_HOOKS:
        hook = base / name
        try:
            installed = "pre-commit" in hook.read_text(encoding="utf-8", errors="replace")
        except OSError:
            installed = False
        if not installed:
            missing.append(name)
    return missing


def build_context(root: Path, mode: str, today: date) -> str:
    lines = ["Regional Codex: standing rules (enforced by hooks in .claude/):"]
    if today < D_DAY:
        lines.append(
            f"- Hackathon rule: product code is built on D-Day ({D_DAY.isoformat()}); "
            "until then only tooling changes."
        )
    lines += [
        "- Never push, open/merge PRs, create releases or otherwise write to GitHub; "
        "the user performs every remote operation.",
        "- No AI attribution in commits or PR text (no `Co-Authored-By: Claude`, no "
        "'Generated with Claude Code').",
        "- Local commits are fine: Conventional Commits, never `--no-verify`, never `SKIP=`.",
        f"- Definition of Done: `uv run poe check` is green. The Stop hook runs the gate (mode: {mode}).",
        "- AGENTS.md is the single source of truth shared with Codex; follow it.",
    ]
    branch = _git_text(root, "branch", "--show-current") or "detached/unknown"
    dirty = len([line for line in _git_text(root, "status", "--porcelain").splitlines() if line])
    lines.append(f"- Git: branch `{branch}`, {dirty} uncommitted path(s).")
    missing = missing_git_hooks(root)
    if missing:
        lines.append(
            f"- WARNING: git hooks not installed ({', '.join(missing)}): run `uv run pre-commit install`."
        )
    if not (root / ".venv").is_dir():
        lines.append("- WARNING: no .venv found: run `uv sync`.")
    if (root / "package.json").is_file() and not (root / "node_modules").is_dir():
        lines.append(
            "- WARNING: no node_modules (Biome is needed by git hooks): run `pnpm install`."
        )
    return "\n".join(lines)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    env: Mapping[str, str] | None = None,
    today: date | None = None,
) -> int:
    del argv
    hook_io = HookIO.resolve(stdin, stdout, stderr, env)
    try:
        payload = read_payload(hook_io.stdin)
        root = project_root(hook_io.env, payload)
        mode = normalize_gate_mode(hook_io.env.get("CLAUDE_GATE"))
        session = str(payload.get("session_id") or "unknown")
        prune_state(root)
        save_state(root, f"session-{session}", {"baseline": tree_fingerprint(root), "blocks": 0})
        text = build_context(root, mode, today or date.today())
    except Exception as exc:  # fail open: context is a convenience
        hook_io.stderr.write(f"session_context: skipped ({exc!r}).\n")
        return 0
    emit(hook_io.stdout, additional_context("SessionStart", text))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
