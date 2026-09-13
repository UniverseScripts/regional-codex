from __future__ import annotations

import io
from pathlib import Path

import pytest

import check_commit_msg

BAD = [
    "feat: x\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n",
    "feat: x\n\nco-authored-by: claude <someone@example.com>\n",
    "fix: y\n\nCo-authored-by: Anthropic Bot <bot@example.com>\n",
    "docs: z\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n",
    "chore: w\n\nClaude-Session: https://claude.ai/code/session_123\n",
    "feat: v\n\nSigned-off-by: someone <noreply@anthropic.com>\n",
]

GOOD = [
    "feat: add agent loop\n",
    "fix: handle empty payloads\n\nCo-Authored-By: Teammate <mate@example.com>\n",
    "docs: explain why claude hooks exist\n",  # mentioning the tool is fine; attribution is not
    "feat: x\n# Co-Authored-By: Claude <noreply@anthropic.com> (git comment line)\n",
    "feat: x\n# ------------------------ >8 ------------------------\n+ Co-Authored-By: Claude\n",
]


@pytest.mark.parametrize("message", BAD)
def test_rejects_ai_attribution(tmp_path: Path, message: str) -> None:
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(message, encoding="utf-8")
    err = io.StringIO()
    assert check_commit_msg.main([str(path)], stderr=err) == 1
    assert "offending line" in err.getvalue()


@pytest.mark.parametrize("message", GOOD)
def test_accepts_clean_messages(tmp_path: Path, message: str) -> None:
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(message, encoding="utf-8")
    assert check_commit_msg.main([str(path)], stderr=io.StringIO()) == 0


def test_requires_a_path() -> None:
    err = io.StringIO()
    assert check_commit_msg.main([], stderr=err) == 2
    assert "expected" in err.getvalue()
