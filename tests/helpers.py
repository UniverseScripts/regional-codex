"""Test helpers shared across test modules (importable; conftest.py is not under importlib mode)."""

from __future__ import annotations

import io
import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class HookResult:
    code: int
    stdout: str
    stderr: str

    def json(self) -> dict[str, Any]:
        data = json.loads(self.stdout)
        assert isinstance(data, dict)
        return data


RunHook = Callable[..., HookResult]
Git = Callable[..., str]


def run_hook(
    main: Callable[..., int],
    payload: object,
    *,
    env: Mapping[str, str] | None = None,
    argv: list[str] | None = None,
    **kwargs: Any,
) -> HookResult:
    """Call a hook's ``main`` in-process with a JSON payload (so coverage counts)."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    out, err = io.StringIO(), io.StringIO()
    code = main(
        argv or [], stdin=io.StringIO(text), stdout=out, stderr=err, env=dict(env or {}), **kwargs
    )
    return HookResult(code, out.getvalue(), err.getvalue())


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return proc.stdout
