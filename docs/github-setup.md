# GitHub setup (done by a human)

By design Claude Code never writes to GitHub (hooks and permission rules block it), so a
maintainer runs each step below from their own terminal. Repository:
<https://github.com/UniverseScripts/regional-codex>.

## 1. First push

```bash
git push -u origin main --tags     # includes the pre-event-baseline tag
```

## 2. Secrets

```bash
gh secret set OPENAI_API_KEY       # enables the Codex PR-review workflow
```

The review workflow skips itself (with a notice) until this secret exists.

## 3. Branch ruleset for `main`

```bash
gh api -X POST repos/UniverseScripts/regional-codex/rulesets --input .github/rulesets/main.json
```

This requires a PR to merge, the single `ci-ok` check green, linear history and resolved
conversations, and blocks force-pushes and deletion. It needs zero approvals so four people can
move fast on the day. Repository admins can bypass it in an emergency.

## 4. Security features (Settings → Code security)

- Enable **Dependabot alerts** and **Dependabot security updates** (version updates come from
  `.github/dependabot.yml`).
- Enable **Secret scanning** and **Push protection**.
- Enable **Private vulnerability reporting** (used by `SECURITY.md`):
  `gh api -X PUT repos/UniverseScripts/regional-codex/private-vulnerability-reporting`
- **Settings → Actions → General**: set workflow permissions to "Read repository contents".
  Every workflow requests its own least-privilege scopes.

## 5. Labels

```bash
gh label create codex-review --color 5319e7 --description "Run the Codex PR review workflow"
```

## 6. Codex integration

1. Connect the repository in Codex cloud (<https://chatgpt.com/codex>) and create an environment
   with this setup script:

   ```bash
   uv sync --frozen
   pnpm install --frozen-lockfile
   ```

2. Turn on **Code review** for the repository in Codex settings. `@codex review` in a PR comment
   then works without an API key. Automatic reviews are optional; the `codex-review` workflow is
   the API-key-based alternative.
3. Locally, run `codex` from the repo root and trust the project so `.codex/config.toml` (sandbox
   defaults and the Stop quality-gate hook) loads.

## 7. On D-Day

- Add teammates as collaborators and create `.github/CODEOWNERS`.
- Pick a license (add `LICENSE`) and fill in the Mission section of `AGENTS.md`.
- Open a throwaway PR to confirm `ci-ok` is required and green.
