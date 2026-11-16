# Contributing

Small, focused improvements are welcome. Keep the default walkthrough credential-free and every Jira write behind explicit human review.

## Development

Follow the README's virtual-environment instructions, then install the development extra:

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check .
ruff format --check .
```

Use Python 3.11 or newer. Direct dependencies are pinned in `pyproject.toml`; full environment snapshots are not treated as cross-platform lockfiles.

## Changes

- Describe the user-visible problem, the resulting behavior, and how you verified it.
- Add behavior tests for meaningful logic changes; use mocks at external API boundaries.
- Keep fictional fixtures clearly labeled. Do not commit customer conversations, production logs, credentials, or generated private reports.
- Preserve the distinction between schema validity, quote presence, factual correctness, and reviewer judgment.
- Do not introduce automatic retries for Jira issue creation or remove the approval boundary.
- Run live evaluation only deliberately, with authorized inputs and your own API credentials.

Open an issue for substantial design changes before implementing them. See `SECURITY.md` for vulnerability reports.
