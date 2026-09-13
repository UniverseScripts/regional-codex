"""commit-msg hook: reject AI attribution trailers/markers (Claude/Anthropic) in commit messages.

Keep AI_MARKER_PATTERNS in sync with .claude/hooks/guard_bash.py (enforced by tests).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

AI_MARKER_PATTERNS: tuple[str, ...] = (
    r"co-authored-by:[^\n]*\b(?:claude|anthropic)\b",
    r"noreply@anthropic\.com",
    r"generated (?:with|by) \[?claude",
    r"claude\.ai/code",
)
_AI_MARKERS = re.compile("|".join(AI_MARKER_PATTERNS), re.IGNORECASE)
_SCISSORS = "# ------------------------ >8 ------------------------"


def find_violations(message: str) -> list[str]:
    violations = []
    for line in message.splitlines():
        if line.startswith(_SCISSORS):
            break
        if line.lstrip().startswith("#"):
            continue
        if _AI_MARKERS.search(line):
            violations.append(line.strip())
    return violations


def main(argv: Sequence[str] | None = None, *, stderr: TextIO | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    err = stderr or sys.stderr
    if not args:
        err.write("check_commit_msg: expected the commit message file path\n")
        return 2
    message = Path(args[0]).read_text(encoding="utf-8", errors="replace")
    violations = find_violations(message)
    if violations:
        err.write("Commit rejected: AI attribution is not allowed in this repo.\n")
        for line in violations:
            err.write(f"  offending line: {line}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
