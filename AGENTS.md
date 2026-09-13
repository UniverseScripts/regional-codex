# AGENTS.md — Regional Codex

Single source of truth for every coding agent (OpenAI Codex, Claude Code) and every human on this
repo. `CLAUDE.md` imports this file. Keep it under 32 KiB (Codex's `project_doc_max_bytes`).

## Mission

> **Filled in on D-Day (31 Oct 2026).** Problem, target users, solution, build direction
> (Autonomous & Adaptive AI · AI-Native Products & Operations · Deep Domain AI) and demo script.

## Hackathon constraints

Sea × OpenAI Regional Codex Hackathon — Vietnam (31 Oct 2026, hacking window 10:00–17:00).

- **All product code is written during the event.** Before that the repo holds tooling only
  (tagged `pre-event-baseline`); `services/` and `apps/` stay empty until D-Day.
- Judges score problem framing, build quality, depth of thinking and **how effectively Codex was
  leveraged**. Log notable Codex contributions in `docs/codex-log.md` and in every PR's
  "How Codex was used" section.
- Ship a demoable vertical slice early, then deepen it. A working thin path beats a broad mock.

## Repository map

| Path | Purpose |
| --- | --- |
| `services/` | Python services / agents (uv workspace members), created with `uv init --package services/<name>` |
| `apps/` | TypeScript / web apps (pnpm workspace), created on D-Day |
| `scripts/gate.py` | The quality gate: the Definition of Done in code |
| `tests/` | Tooling tests + repo policy tests (`test_repo_policy.py`) |
| `docs/` | ADRs, GitHub setup, Codex playbook and log |
| `.claude/` | Claude Code settings + hooks (guards, Stop gate) |
| `.codex/config.toml` | Codex project config (sandbox, approvals, Stop gate hook) |
| `.github/` | CI/CD workflows, templates, ruleset, Codex review prompt |

## Setup

```bash
uv sync                      # Python 3.12 toolchain + dev tools
pnpm install                 # Biome (used by the git hooks) + web tooling
uv run pre-commit install    # git hooks: pre-commit, commit-msg, pre-push
cp .env.example .env         # then fill in local secrets (never commit .env)
```

## Commands

| Command | What it does |
| --- | --- |
| `uv run poe check` | **Full quality gate: the Definition of Done** |
| `uv run poe check-fast` | Gate without test suites (quick iteration) |
| `uv run poe fmt` | Format + safe autofixes |
| `uv run poe lint` / `typecheck` / `test` | Individual steps |
| `uv run pre-commit run --all-files` | Every git hook against every file |

## Definition of Done

A change is done only when **all** of these hold:

1. `uv run poe check` passes (ruff lint + format, mypy strict, pytest; plus Biome, tsc and tests
   once `apps/*` exist).
2. New behaviour has tests; every bug fix has a regression test.
3. No secrets, credentials or personal data in code, logs, fixtures or commits. Document new
   environment variables in `.env.example`.
4. Significant decisions (framework, model/provider, data store, agent architecture) have an ADR
   in `docs/adr/` (copy `0000-template.md`).
5. Commits and PR titles follow Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`,
   `test:`, `perf:`, `build:`, `ci:`, `chore:`, `revert:`, `style:`.

## Engineering standards

### Python

- Python 3.12 via uv. Add dependencies with `uv add <pkg>` (dev: `uv add --dev`); never edit
  `uv.lock` by hand.
- Type everything. Tooling is `mypy --strict`; services keep typed public APIs. Validate data at
  boundaries with dataclasses or pydantic models.
- `pathlib` over `os.path`, `logging` over `print`, no bare `except`, no mutable default args.
- Inside a service pick one async stack (`asyncio`/`anyio`) and never block the event loop.

### TypeScript (`apps/*`)

- `tsconfig` extends `../../tsconfig.base.json` (strict). Biome for lint + format, Vitest for tests.
- Each app exposes `typecheck` and `test` scripts so the gate picks them up automatically.

### AI / LLM code

- Model names, endpoints and keys come from environment/config, never hard-coded
  (`OPENAI_API_KEY` is read from the environment).
- Every model call has a timeout, bounded retries with backoff, a token budget, and validated
  structured output.
- Treat model output and tool results as untrusted input: validate, escape, never `eval`/`exec`.
- Keep deterministic logic in code, not prompts, and unit-test it with the model client mocked.
- Log prompts and responses without secrets or PII; keep eval fixtures small and synthetic.

### Testing

- pytest. Tests live in `tests/` or `services/<name>/tests/`. No network in unit tests.
- Keep the suite fast. Register markers (e.g. `integration`) before using them; strict markers
  are on.

## Git and collaboration

- Branch per task (`feat/…`, `fix/…`) and open a PR into `main`; `ci-ok` must be green;
  squash-merge.
- Never bypass hooks (`--no-verify`, `SKIP=`) and never force-push `main`.
- Humans push. Agents may prepare local commits; Codex cloud tasks open PRs through the Codex
  GitHub integration.
- Never commit generated artifacts, binaries over 1 MB, `.env` files or credentials.

## Security

- Secrets only via environment variables / GitHub Actions secrets. gitleaks scans every commit
  and CI.
- Validate all external input (HTTP, files, LLM output). Parameterise SQL. Keep dependencies
  pinned via lockfiles.
- Report vulnerabilities per `SECURITY.md`, never in public issues.

## Code Review Rules

Used by `@codex review` and the Codex PR-review workflow. CI already enforces formatting, lint,
types and tests, so spend review effort on what tools cannot see.

### Correctness

- Logic errors, unhandled edge cases, race conditions, missing `await`, swallowed errors.

### Security

- Leaked secrets, injection (SQL, shell, prompt), unsafe deserialisation, SSRF, over-broad
  permissions, model output used without validation.

### Tests

- New behaviour without tests, tests without meaningful assertions, network access in unit tests.

### AI integration

- Hard-coded model names or keys, missing timeouts/retries, unbounded token usage, prompt
  injection exposure, non-deterministic logic hidden in prompts.

### Conventions

- Anything that breaks the Definition of Done above (missing ADR, non-conventional title,
  undocumented env vars).

Report only actionable findings, most severe first, each with `file:line` and a concrete fix.
If nothing blocks the merge, say "No blocking issues found."
