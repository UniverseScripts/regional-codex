# Contributing

Thanks for building with us. The rules below keep a four-person, one-day build shippable.
[AGENTS.md](AGENTS.md) has the full engineering standards and the Definition of Done.

## One-time setup

```bash
uv sync
pnpm install                 # Biome (used by the git hooks) + web tooling
uv run pre-commit install    # installs pre-commit, commit-msg and pre-push hooks
```

## Workflow

1. **Branch** from `main`: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`.
2. **Build with tests.** Run `uv run poe check-fast` while iterating and `uv run poe check`
   before pushing (the pre-push hook runs it anyway).
3. **Commit** with [Conventional Commits](https://www.conventionalcommits.org/) (`feat: …`,
   `fix: …`). The commit-msg hook enforces the format and rejects AI attribution trailers.
4. **Open a PR** using the template. Fill in "How Codex was used" and add a line to
   [docs/codex-log.md](docs/codex-log.md) for notable Codex work.
5. **Review.** `ci-ok` must be green. Add the `codex-review` label (or comment `@codex review`)
   for an AI review, and address findings or explain why not.
6. **Squash-merge** with a conventional title.

## Decisions

Record significant decisions (framework, model/provider, storage, agent architecture) as an ADR:
copy [docs/adr/0000-template.md](docs/adr/0000-template.md) to the next number.

## Never

- Bypass hooks (`git commit --no-verify`, `SKIP=…`) or force-push `main`.
- Commit secrets, `.env` files, large binaries or generated artifacts.
- Hand-edit lockfiles; use `uv add` or `pnpm add`.
