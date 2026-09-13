from __future__ import annotations

import io

import deny_agent_push


def test_refuses_pushes_from_claude_sessions() -> None:
    err = io.StringIO()
    assert deny_agent_push.main([], env={"CLAUDECODE": "1"}, stderr=err) == 1
    assert "Push refused" in err.getvalue()


def test_allows_human_pushes() -> None:
    assert deny_agent_push.main([], env={}, stderr=io.StringIO()) == 0
    assert deny_agent_push.main([], env={"CLAUDECODE": "0"}, stderr=io.StringIO()) == 0
