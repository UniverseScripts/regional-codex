from __future__ import annotations

import json
import subprocess
import sys

import pytest

import guard_bash
from helpers import REPO_ROOT, RunHook

DENY = [
    # direct and compound pushes
    "git push",
    "git push origin main --force-with-lease",
    "cd services && git push",
    "git status; git push",
    "git status || git push",
    "echo ok | git push",
    "git -C ../code push",
    "git -c user.name=x push origin HEAD",
    "/usr/bin/git push",
    "git.exe push",
    "git lfs push origin main",
    # wrappers, nesting, substitutions
    "bash -c 'git push'",
    'sh -c "git fetch && git push"',
    "bash -lc 'git push'",
    'pwsh -Command "git push"',
    'powershell.exe -NoProfile -Command "git push origin"',
    "powershell -EncodedCommand ZwBpAHQAIABwAHUAcwBoAA==",
    'cmd /c "git push"',
    "env GIT_TRACE=1 git push",
    "command git push",
    "timeout 30 git push",
    "eval 'git push'",
    "xargs -n 1 git push",
    "uv run git push",
    "uv run --with rich git push",
    "echo $(git push)",
    "echo `git push`",
    "& git push",
    "Start-Process git -ArgumentList 'push'",
    "iex 'git push'",
    # remotes / config / hook bypasses
    "git remote add upstream https://github.com/x/y.git",
    "git remote set-url origin https://github.com/x/y.git",
    "git config alias.p push",
    "git config --global user.name Someone",
    "git config core.hooksPath /dev/null",
    "git -c core.hooksPath=/dev/null commit -m 'feat: x'",
    "git commit --no-verify -m 'feat: x'",
    "git commit -n -m 'feat: x'",
    "git commit -anm 'feat: x'",
    "git merge --no-verify feature",
    "SKIP=ruff git commit -m 'feat: x'",
    "PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m 'feat: x'",
    "export SKIP=mypy",
    "$env:SKIP='mypy'; git commit -m 'feat: x'",
    # attribution
    "git commit -m 'feat: x' -m 'Co-Authored-By: Claude <noreply@anthropic.com>'",
    "git commit -F - <<'EOF'\nfeat: x\n\nGenerated with Claude Code\nEOF",
    # gh writes
    "gh pr create --fill",
    "gh pr merge 12 --squash",
    "gh pr comment 12 --body hi",
    "gh pr review 12 --approve",
    "gh -R org/repo pr create",
    "gh issue create --title x",
    "gh repo create org/new --public",
    "gh repo delete org/repo --yes",
    "gh repo edit --visibility private",
    "gh repo sync",
    "gh release create v1.0.0",
    "gh workflow run ci.yml",
    "gh run rerun 123",
    "gh secret set OPENAI_API_KEY",
    "gh variable set FOO",
    "gh label create bug",
    "gh alias set p 'pr create'",
    "gh api -X POST repos/o/r/issues",
    "gh api --method=PATCH repos/o/r",
    "gh api -XDELETE repos/o/r",
    "gh api repos/o/r/issues -f title=x",
    "gh api repos/o/r/rulesets --input ruleset.json",
    "gh api graphql -f query='query { viewer { login } }'",
    # raw HTTP writes
    "curl -X POST https://api.github.com/repos/o/r/issues",
    "curl --data '{}' https://api.github.com/repos/o/r/issues",
    "curl -d @x.json https://api.github.com/repos/o/r/pulls",
    "wget --post-data=x https://api.github.com/repos/o/r/issues",
    "Invoke-RestMethod -Method Post -Uri https://api.github.com/repos/o/r/issues",
    "irm https://api.github.com/repos/o/r/issues -Method PATCH -Body '{}'",
]

ALLOW = [
    "git status",
    "git status; git diff",
    "git diff --stat",
    "git log --oneline -5",
    "git log --grep=push",
    "git add -A",
    "git commit -m 'feat: add agent loop'",
    "git commit -am 'fix: typo'",
    "git switch -c feat/x",
    "git branch -d old",
    "git stash",
    "git fetch origin",
    "git pull --ff-only",
    "git remote -v",
    "git config --get user.name",
    "git config --list",
    "git tag pre-event-baseline",
    "git clean -n",
    "gh pr view 12",
    "gh pr list",
    "gh pr diff 12",
    "gh pr checks 12",
    "gh issue list",
    "gh repo view",
    "gh run list",
    "gh run view 123 --log",
    "gh release list",
    "gh secret list",
    "gh api repos/o/r",
    "gh api repos/o/r/pulls --jq '.[].title'",
    "gh api -X GET search/issues -f q=bug",
    "curl https://api.github.com/repos/o/r",
    "curl -sSL https://example.com -o out.html",
    "uv run pytest -q",
    "uv run poe check",
    "pnpm install",
    "echo pushing is disabled",
    "grep -rn 'git push' docs",
    "python -m pytest",
    "Get-ChildItem",
    "ls -la && cat README.md",
]

ASK = ["git reset --hard HEAD~1", "git clean -fdx", "git clean -fd"]


@pytest.mark.parametrize("command", DENY)
def test_denies(command: str) -> None:
    decision = guard_bash.evaluate(command)
    assert decision is not None, command
    assert decision.kind == "deny", command


@pytest.mark.parametrize("command", ALLOW)
def test_allows(command: str) -> None:
    assert guard_bash.evaluate(command) is None


@pytest.mark.parametrize("command", ASK)
def test_asks(command: str) -> None:
    decision = guard_bash.evaluate(command)
    assert decision is not None
    assert decision.kind == "ask"


def test_deny_wins_over_ask() -> None:
    decision = guard_bash.evaluate("git reset --hard && git push")
    assert decision is not None
    assert decision.kind == "deny"


def test_absurd_nesting_is_denied() -> None:
    command = "git status"
    for _ in range(10):
        command = f"bash -c {json.dumps(command)}"
    decision = guard_bash.evaluate(command)
    assert decision is not None
    assert decision.kind == "deny"


@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
def test_main_emits_deny_json(run_hook: RunHook, tool: str) -> None:
    res = run_hook(guard_bash.main, {"tool_name": tool, "tool_input": {"command": "git push"}})
    assert res.code == 0
    out = res.json()["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "deny"
    assert "GitHub" in out["permissionDecisionReason"]


def test_main_is_silent_when_allowed(run_hook: RunHook) -> None:
    res = run_hook(guard_bash.main, {"tool_name": "Bash", "tool_input": {"command": "git status"}})
    assert (res.code, res.stdout) == (0, "")


def test_main_ignores_other_tools(run_hook: RunHook) -> None:
    res = run_hook(guard_bash.main, {"tool_name": "Read", "tool_input": {"file_path": "x"}})
    assert (res.code, res.stdout) == (0, "")


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[1]",
        {"tool_name": "Bash", "tool_input": {"command": 123}},
        {"tool_name": "Bash"},
    ],
)
def test_main_fails_closed(run_hook: RunHook, payload: object) -> None:
    res = run_hook(guard_bash.main, payload)
    assert res.code == 2
    assert "guard_bash" in res.stderr


def test_script_smoke() -> None:
    script = REPO_ROOT / ".claude" / "hooks" / "guard_bash.py"
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "cd x && git push"}})
    proc = subprocess.run(
        [sys.executable, str(script)], input=payload.encode(), capture_output=True, check=False
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
