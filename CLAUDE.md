@AGENTS.md

# Claude Code: additional rules

These apply to Claude Code only (Codex follows AGENTS.md alone). They are enforced by
`.claude/settings.json` and `.claude/hooks/`; never work around them.

- **Never interact with the remote.** No `git push`, no PR / issue / release / workflow / secret /
  ruleset operations, no GitHub API writes. The user performs every remote operation. Local
  branches and commits are fine.
- **No AI attribution.** Never add `Co-Authored-By: Claude`, "Generated with Claude Code" or
  session links to commits or PR text. Attribution is disabled in settings and the commit-msg
  hook rejects it.
- **The Definition of Done is enforced at Stop.** When a turn changed files, the Stop hook runs
  `scripts/gate.py` and blocks until it is green (up to 3 attempts). Mode comes from
  `CLAUDE_GATE`: `full` (default), `fast` (no tests) or `off`. Override it per person in
  `.claude/settings.local.json`; CI and the pre-push hook always run the full gate.
- **Guardrail files** (`.claude/settings.json`, `.claude/hooks/**`, `.github/workflows/**`,
  `.pre-commit-config.yaml`, `.codex/config.toml`, `scripts/gate.py`) need the user's
  confirmation to edit. Secrets (`.env*`), `.git/` and lockfiles cannot be edited directly.
- Launch Claude Code from this directory (`code/`) so these settings apply.

## Hooks

| Event | Script | Behaviour |
| --- | --- | --- |
| SessionStart | `session_context.py` | Injects these rules and git status; records a work-tree baseline |
| PreToolUse (Bash, PowerShell) | `guard_bash.py` | Denies GitHub writes, hook bypasses and AI trailers (fail-closed) |
| PreToolUse (Edit, Write) | `guard_files.py` | Denies secrets, lockfiles and `.git/`; asks before guardrail edits (fail-closed) |
| PostToolUse (Edit, Write) | `post_edit.py` | Reports ruff/Biome findings for the edited file (report-only) |
| Stop | `stop_gate.py` | Runs the quality gate and blocks until it passes |
