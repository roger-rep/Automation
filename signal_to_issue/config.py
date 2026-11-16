"""Environment-only secrets; importing this module never starts network requests."""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(default="", repr=False)
    openai_model: str = "gpt-4o-mini"
    jira_url: str = ""
    jira_email: str = field(default="", repr=False)
    jira_api_token: str = field(default="", repr=False)
    jira_project_key: str = "DEMO"
    jira_issue_type: str = "Bug"
    jira_extra_fields: dict = field(default_factory=dict, repr=False)
    submission_db: Path = Path(".local/submissions.sqlite3")

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            extra = json.loads(os.getenv("JIRA_EXTRA_FIELDS", "{}"))
        except json.JSONDecodeError as exc:
            raise ValueError("JIRA_EXTRA_FIELDS must be a JSON object.") from exc
        if not isinstance(extra, dict):
            raise ValueError("JIRA_EXTRA_FIELDS must be a JSON object.")
        if {"summary", "description", "project", "issuetype"} & extra.keys():
            raise ValueError(
                "JIRA_EXTRA_FIELDS cannot override the reviewed report or destination."
            )
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
            jira_url=os.getenv("JIRA_URL", "").strip().rstrip("/"),
            jira_email=os.getenv("JIRA_EMAIL", "").strip(),
            jira_api_token=os.getenv("JIRA_API_TOKEN", "").strip(),
            jira_project_key=os.getenv("JIRA_PROJECT_KEY", "DEMO").strip(),
            jira_issue_type=os.getenv("JIRA_ISSUE_TYPE", "Bug").strip(),
            jira_extra_fields=extra,
            submission_db=Path(os.getenv("SUBMISSION_DB", ".local/submissions.sqlite3")),
        )

    def validate_jira(self) -> None:
        if not re.fullmatch(r"https://[A-Za-z0-9-]+\.atlassian\.net", self.jira_url):
            raise ValueError("JIRA_URL must be your HTTPS Jira Cloud tenant URL.")
        if not self.jira_email or not self.jira_api_token:
            raise ValueError("Set JIRA_EMAIL and JIRA_API_TOKEN in your local .env.")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", self.jira_project_key):
            raise ValueError("Set a valid JIRA_PROJECT_KEY.")
        if not self.jira_issue_type:
            raise ValueError("Set JIRA_ISSUE_TYPE to an issue type in your project.")
