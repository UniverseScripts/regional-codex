"""PostToolUse diagnostics for edited files. Report-only (never rewrites files); fails open.

Feeds ruff/biome findings back to the agent right after an edit so problems are fixed
while context is fresh. Formatting itself is applied once, at the end, by the Stop gate.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TextIO

from _common import HookIO, additional_context, emit, git_toplevel, project_root, read_payload

Runner = Callable[[Sequence[str], Path], tuple[int, str]]

PY_SUFFIXES = frozenset({".py", ".pyi"})
WEB_SUFFIXES = frozenset(
    {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".json", ".jsonc", ".css"}
)
_TAIL_CHARS = 2000


def default_runner(cmd: Sequence[str], cwd: Path) -> tuple[int, str]:
    exe = shutil.which(cmd[0]) or cmd[0]
    proc = subprocess.run([exe, *cmd[1:]], cwd=cwd, capture_output=True, timeout=60, check=False)
    return proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", "replace")


def _tail(text: str) -> str:
    text = text.strip()
    return text if len(text) <= _TAIL_CHARS else "...\n" + text[-_TAIL_CHARS:]


def diagnostics(path: Path, root: Path, runner: Runner) -> list[str]:
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return []
    suffix = path.suffix.lower()
    notes: list[str] = []
    if suffix in PY_SUFFIXES:
        uv_ruff = ["uv", "run", "--frozen", "--quiet", "ruff"]
        code, out = runner([*uv_ruff, "check", "--output-format=concise", "--no-fix", rel], root)
        if code != 0:
            notes.append(f"ruff check:\n{_tail(out)}")
        code, _ = runner([*uv_ruff, "format", "--check", rel], root)
        if code != 0:
            notes.append(
                f"ruff format: `{rel}` is not formatted (the Stop gate formats it; or `uv run poe fmt`)."
            )
    elif suffix in WEB_SUFFIXES and (root / "node_modules" / "@biomejs" / "biome").is_dir():
        code, out = runner(
            ["pnpm", "exec", "biome", "check", "--no-errors-on-unmatched", rel], root
        )
        if code != 0:
            notes.append(f"biome check:\n{_tail(out)}")
    return notes


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    env: Mapping[str, str] | None = None,
    runner: Runner | None = None,
) -> int:
    del argv
    hook_io = HookIO.resolve(stdin, stdout, stderr, env)
    try:
        payload = read_payload(hook_io.stdin)
        raw_path = (payload.get("tool_input") or {}).get("file_path")
        if not isinstance(raw_path, str) or not raw_path:
            return 0
        path = Path(raw_path)
        if not path.is_file():
            return 0
        root = git_toplevel(path.parent) or project_root(hook_io.env, payload)
        notes = diagnostics(path, root, runner or default_runner)
    except Exception as exc:  # fail open: diagnostics are advisory
        hook_io.stderr.write(f"post_edit: skipped diagnostics ({exc!r}).\n")
        return 0
    if notes:
        header = f"Diagnostics for {path.name} — fix these now (the Stop gate blocks on them):"
        emit(hook_io.stdout, additional_context("PostToolUse", "\n\n".join([header, *notes])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
