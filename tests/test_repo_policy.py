"""Policy-as-code: structural invariants of the repo's tooling, so no future change can quietly
weaken the standards (unpinned actions, missing timeouts, broken hooks, attribution...)."""

from __future__ import annotations

import json
import re
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

import check_commit_msg
import guard_bash
from helpers import REPO_ROOT

WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
WORKFLOWS = sorted(WORKFLOW_DIR.glob("*.yml"))
SHA_PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
D_DAY = date(2026, 10, 31)


def _yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    on = workflow.get("on", workflow.get(True))  # PyYAML parses bare `on:` as True
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return dict.fromkeys(on)
    assert isinstance(on, dict)
    return on


def _steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for job in workflow["jobs"].values() for step in job.get("steps", [])]


def test_expected_workflows_exist() -> None:
    names = {p.name for p in WORKFLOWS}
    assert {"ci.yml", "security.yml", "pr.yml", "links.yml", "codex-review.yml"} <= names


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_hardening(path: Path) -> None:
    workflow = _yaml(path)
    assert "permissions" in workflow, "set least-privilege top-level permissions"
    assert "concurrency" in workflow, "cancel superseded runs"
    assert "pull_request_target" not in _triggers(workflow), "pull_request_target is forbidden"
    for name, job in workflow["jobs"].items():
        assert "timeout-minutes" in job, f"job {name} needs timeout-minutes"
        assert "permissions" in job, f"job {name} needs explicit permissions"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_actions_are_pinned_to_full_shas(path: Path) -> None:
    for step in _steps(_yaml(path)):
        uses = step.get("uses")
        if uses is None or uses.startswith(("./", "docker://")):
            continue
        assert SHA_PINNED.match(uses), f"{path.name}: pin `{uses}` to a full commit SHA"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_checkout_never_persists_credentials(path: Path) -> None:
    for step in _steps(_yaml(path)):
        if str(step.get("uses", "")).startswith("actions/checkout@"):
            assert step.get("with", {}).get("persist-credentials") is False, path.name


def test_ci_ok_aggregates_every_ci_job() -> None:
    jobs = _yaml(WORKFLOW_DIR / "ci.yml")["jobs"]
    assert set(jobs["ci-ok"]["needs"]) == set(jobs) - {"ci-ok"}
    assert jobs["ci-ok"]["if"] == "always()"


def _claude_settings() -> dict[str, Any]:
    data = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_claude_attribution_disabled() -> None:
    assert _claude_settings()["attribution"] == {"commit": "", "pr": ""}


def test_claude_remote_writes_denied() -> None:
    deny = set(_claude_settings()["permissions"]["deny"])
    assert {"Bash(git push:*)", "PowerShell(git push:*)", "Bash(gh pr create:*)"} <= deny


def test_claude_hooks_registered_and_scripts_exist() -> None:
    hooks = _claude_settings()["hooks"]
    assert {"SessionStart", "PreToolUse", "PostToolUse", "Stop"} <= set(hooks)
    matchers = {group.get("matcher") for group in hooks["PreToolUse"]}
    assert "Bash|PowerShell" in matchers
    for groups in hooks.values():
        for group in groups:
            for hook in group["hooks"]:
                script = re.search(r"\.claude/hooks/(\w+\.py)", hook["command"])
                assert script, hook["command"]
                assert (REPO_ROOT / ".claude" / "hooks" / script.group(1)).is_file()
                assert "timeout" in hook


def test_codex_stop_hook_uses_the_shared_gate() -> None:
    config = tomllib.loads((REPO_ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
    commands = [h["command"] for group in config["hooks"]["Stop"] for h in group["hooks"]]
    assert any("stop_gate.py" in c for c in commands)


def test_precommit_installs_all_stages_and_required_hooks() -> None:
    config = _yaml(REPO_ROOT / ".pre-commit-config.yaml")
    assert set(config["default_install_hook_types"]) == {"pre-commit", "commit-msg", "pre-push"}
    ids = {hook["id"] for repo in config["repos"] for hook in repo["hooks"]}
    required = {
        "ruff-check",
        "ruff-format",
        "mypy",
        "uv-lock",
        "gitleaks",
        "actionlint",
        "zizmor",
        "codespell",
        "detect-private-key",
        "conventional-pre-commit",
        "check-commit-msg",
        "deny-agent-push",
        "poe-check",
    }
    assert required <= ids
    for repo in config["repos"]:
        if repo["repo"] != "local":
            assert repo["rev"] not in {"main", "master", "HEAD"}, repo["repo"]


def test_claude_md_imports_agents_md() -> None:
    assert (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8").startswith("@AGENTS.md")


def test_agents_md_defines_done_and_review_rules() -> None:
    agents = REPO_ROOT / "AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    assert "## Definition of Done" in text
    assert "## Code Review Rules" in text
    assert "uv run poe check" in text
    assert agents.stat().st_size < 32 * 1024, "Codex truncates AGENTS.md beyond 32 KiB"


def test_gitattributes_enforce_lf() -> None:
    assert "* text=auto eol=lf" in (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")


def test_attribution_patterns_stay_in_sync() -> None:
    assert guard_bash.AI_MARKER_PATTERNS == check_commit_msg.AI_MARKER_PATTERNS


def test_no_product_code_before_d_day() -> None:
    if date.today() >= D_DAY:
        pytest.skip("D-Day reached: product code is expected")
    for folder in ("services", "apps"):
        entries = {p.name for p in (REPO_ROOT / folder).iterdir()}
        assert entries <= {"README.md"}, f"{folder}/ must stay empty until {D_DAY} (hackathon rule)"
