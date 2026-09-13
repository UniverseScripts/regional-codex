# Codex playbook for D-Day

Judges score *how effectively Codex was leveraged*. This is how we make that effective and
visible.

## Before the clock starts (08:30–10:00)

- Codex CLI is installed and signed in on every laptop, the repo is cloned, `uv sync` has run, and
  the project is trusted in Codex so `.codex/config.toml` loads.
- The Codex cloud environment is ready (see [github-setup.md](github-setup.md), step 6).

## Kick-off (first 30 minutes)

1. Frame the problem with the whole team. Have Codex draft the **Mission** section of `AGENTS.md`
   and ADR-0001 (architecture) from our notes; humans edit and decide.
2. Split the build into 3–5 vertical slices, each with a one-line acceptance test.

## Build loop

- **Parallelise with Codex cloud tasks.** Give each slice its own task. The prompt names the
  acceptance test and points to `AGENTS.md`. Every task ends with `uv run poe check` green and
  opens a PR.
- **Pair locally with Codex CLI** for integration work. The Stop hook runs the fast gate before
  Codex finishes a turn.
- **Plan, then test, then code.** Ask Codex for a short plan first, then failing tests, then the
  implementation.
- **Keep PRs small.** Merge often; `ci-ok` must be green.
- **Review with Codex.** Comment `@codex review` (or add the `codex-review` label). A human decides
  on every finding.

## Make Codex's contribution visible

- Fill in "How Codex was used" in every PR.
- Add a row to [codex-log.md](codex-log.md) for anything notable: a slice Codex built end to end,
  a bug it caught in review, a refactor it drove.
- In the final pitch, show the log and one PR where Codex's work is clear.

## Prompt patterns that work

- "Read AGENTS.md. Implement <slice> so that <acceptance test> passes. Write the tests first. Stop
  when `uv run poe check` is green."
- "Review this diff against the Code Review Rules in AGENTS.md. List only blocking issues."
- "Propose 3 designs for <component> with trade-offs; recommend one and draft the ADR."
