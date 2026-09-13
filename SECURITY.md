# Security Policy

## Supported versions

Only the `main` branch is supported.

## Reporting a vulnerability

Please **do not open a public issue**. Report privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability):
open the repository's **Security** tab and choose **Report a vulnerability**.

Please include:

- a description of the issue and its impact,
- steps to reproduce or a proof of concept,
- any suggested remediation.

We aim to acknowledge reports within 3 business days. This is a hackathon project maintained on a
best-effort basis.

## Handling secrets

- Secrets live in environment variables (`.env`, git-ignored) and GitHub Actions secrets, never in
  the repository.
- gitleaks runs on every commit (pre-commit) and in CI. If a secret is committed anyway, rotate it
  immediately: rewriting history is not enough.
