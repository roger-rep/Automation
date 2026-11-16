# Security

This is a local portfolio application, not a hardened multi-user service. The current `0.1.x` line is the maintained version.

## Reporting an issue

Use the repository's **Security → Advisories → Report a vulnerability** option if private reporting is enabled. Otherwise, open a minimal issue asking the maintainer for a private reporting channel. Do not include credentials, customer data, exploit payloads with secrets, or private logs in a public issue.

## Boundaries

- Treat feedback and model outputs as untrusted.
- The model has no external-action tools. Jira submission is separate, explicit, and uses the saved reviewer report.
- Source-quote validation is a text-presence check, not proof of truth or prompt-injection immunity.
- Credentials come from environment variables or a local `.env`, never from customer feedback.
- Jira authentication is limited to an HTTPS `*.atlassian.net` tenant URL. Redirects are disabled.
- Jira creation has no automatic retry; uncertain outcomes remain reserved locally until manually resolved.
- API error bodies are not shown in user-facing errors.
- Provider data-retention policies still apply. `store=False` is not a universal zero-retention guarantee.

If a token is exposed, revoke it at the provider and replace it locally. Deleting it from the latest commit alone does not remove it from Git history.
