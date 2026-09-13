# Regional Codex

Team repository for the **Sea × OpenAI Regional Codex Hackathon, Vietnam** (31 Oct 2026, Shopee
Vietnam office, Ho Chi Minh City). Event details: <https://codexhackathon.sea.com/>.

> **Status: pre-event tooling baseline, no product code.** The hackathon rules require all building
> to happen on the day, so this repository currently contains only engineering tooling: CI/CD,
> quality gates, git hooks, agent configuration and templates. The baseline commit is tagged
> `pre-event-baseline`; everything after it is built on D-Day.

## What we're building

_Defined on D-Day. See the Mission section of [AGENTS.md](AGENTS.md)._

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/), Node.js 24 with pnpm, and git.

```bash
uv sync                      # installs Python 3.12 + the dev toolchain
pnpm install                 # Biome, used by the git hooks
uv run pre-commit install    # pre-commit, commit-msg and pre-push hooks
uv run poe check             # the full quality gate (Definition of Done)
```

## Everyday commands

| Command | Purpose |
| --- | --- |
| `uv run poe check` | Full gate: ruff, format, mypy strict, pytest (plus web checks once `apps/*` exists) |
| `uv run poe check-fast` | Gate without tests |
| `uv run poe fmt` | Format + safe autofixes |
| `uv run pre-commit run --all-files` | Run every git hook on the whole repo |

## Repository layout

```text
services/   Python services and agents (created on D-Day)
apps/       Web apps (created on D-Day)
scripts/    Quality gate and git-hook scripts
tests/      Tooling tests and repo policy tests
docs/       ADRs, GitHub setup, Codex playbook and log
.claude/    Claude Code settings and hooks
.codex/     Codex project config
.github/    Workflows, templates, ruleset, Codex review prompt
```

## Quality and CI/CD

| Layer | What runs |
| --- | --- |
| Editor/agent | Claude Code hooks (guards, per-edit diagnostics, blocking Stop gate); Codex Stop gate hook |
| `pre-commit` | ruff, format, mypy, uv lock sync, gitleaks, actionlint, zizmor, schema checks, codespell, Biome |
| `commit-msg` | Conventional Commits and a ban on AI attribution trailers |
| `pre-push` | Full quality gate |
| CI (`ci.yml`) | pre-commit, Python gate with coverage on Ubuntu (and Windows for tooling changes), web gate, single required check `ci-ok` |
| Security (`security.yml`) | CodeQL, `pip-audit`, `pnpm audit` |
| PR hygiene (`pr.yml`) | Conventional PR title, dependency review |
| Docs (`links.yml`) | Link check with lychee |
| Review (`codex-review.yml`) | Codex reviews PRs against the rules in `AGENTS.md` |

Every GitHub Action is pinned to a commit SHA and kept current by Dependabot. Setting up the
remote (secrets, ruleset, Codex integration) is covered in
[docs/github-setup.md](docs/github-setup.md).

## Working with AI agents

[AGENTS.md](AGENTS.md) is the single source of truth for Codex, Claude Code and humans. The Codex
workflow for the day is in [docs/codex-playbook.md](docs/codex-playbook.md).

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

To be decided by the team on D-Day.
