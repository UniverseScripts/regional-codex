"""pre-push hook: refuse pushes launched from a Claude Code session (CLAUDECODE=1).

Shell-agnostic backstop behind the Claude permission rules and guard_bash.py: however the
push was spawned (python subprocess, alias, script), git runs this hook first.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from typing import TextIO


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    stderr: TextIO | None = None,
) -> int:
    del argv
    environ = os.environ if env is None else env
    if environ.get("CLAUDECODE") == "1":
        (stderr or sys.stderr).write(
            "Push refused: pushes must not originate from a Claude Code session "
            "(repo policy). Push from your own terminal.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
