"""Explicitly approved Jira Cloud writes with metadata preflight and no POST retries."""

import hashlib
import json
import re

import requests

from .config import Settings
from .journal import SubmissionJournal
from .models import ReviewedReport
from .render import render_markdown, to_adf


class JiraError(ValueError):
    pass


class SubmissionUnknown(JiraError):
    pass


class JiraClient:
    def __init__(self, settings: Settings, journal: SubmissionJournal, *, session=None):
        settings.validate_jira()
        self.settings = settings
        self.journal = journal
        self.session = session or requests.Session()
        self.session.auth = (settings.jira_email, settings.jira_api_token)
        self.session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )

    def _get(self, path: str, **params) -> dict:
        try:
            response = self.session.get(
                self.settings.jira_url + path, params=params, timeout=20, allow_redirects=False
            )
        except requests.RequestException as exc:
            raise JiraError(
                "Could not read Jira metadata. Check your connection and tenant URL."
            ) from exc
        if response.status_code != 200:
            raise JiraError(
                f"Jira metadata returned HTTP {response.status_code}. "
                "Check authentication, project access, and Create issues permission."
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise JiraError("Jira returned invalid metadata JSON.") from exc
        if not isinstance(data, dict):
            raise JiraError("Jira returned an unexpected metadata format.")
        return data

    def _pages(self, path: str, key: str) -> list[dict]:
        result, start = [], 0
        for _ in range(100):
            page = self._get(path, startAt=start, maxResults=50)
            items = page.get(key)
            if not isinstance(items, list) or any(not isinstance(x, dict) for x in items):
                raise JiraError("Jira metadata was missing the expected fields.")
            result.extend(items)
            start += len(items)
            if not items or page.get("isLast") or start >= page.get("total", start):
                return result
        raise JiraError("Jira metadata exceeded the supported page limit.")

    def prepare_payload(self, report: ReviewedReport, *, mode: str) -> dict:
        project = self.settings.jira_project_key
        base = f"/rest/api/3/issue/createmeta/{project}/issuetypes"
        issue_types = self._pages(base, "issueTypes")
        found = next(
            (
                x
                for x in issue_types
                if x.get("name", "").casefold() == self.settings.jira_issue_type.casefold()
                and not x.get("subtask")
            ),
            None,
        )
        if not found or not re.fullmatch(r"\d+", str(found.get("id", ""))):
            raise JiraError(
                "Configured issue type is unavailable. Check JIRA_ISSUE_TYPE in your project."
            )
        metadata = self._pages(f"{base}/{found['id']}", "fields")
        fields = {
            **self.settings.jira_extra_fields,
            "project": {"key": project},
            "issuetype": {"id": found["id"]},
            "summary": report.title,
            "description": to_adf(render_markdown(report, mode=mode)),
        }
        missing = [
            str(x.get("fieldId", x.get("key", x.get("name", "unknown"))))
            for x in metadata
            if x.get("required")
            and not x.get("hasDefaultValue")
            and x.get("fieldId", x.get("key")) not in fields
        ]
        if missing:
            raise JiraError(
                "Jira requires additional fields: "
                + ", ".join(missing)
                + ". Configure their values in JIRA_EXTRA_FIELDS."
            )
        allowed = {x.get("fieldId", x.get("key")) for x in metadata}
        invalid = set(self.settings.jira_extra_fields) - allowed
        if invalid:
            raise JiraError(
                "Extra fields are not on this Jira create screen: " + ", ".join(sorted(invalid))
            )
        return {"fields": fields}

    def create_issue(self, report: ReviewedReport, *, mode: str, approved: bool = False) -> dict:
        if not approved:
            raise JiraError("Review and approve the report before creating a Jira issue.")
        payload = self.prepare_payload(report, mode=mode)
        fingerprint = hashlib.sha256(
            json.dumps(
                {"tenant": self.settings.jira_url, "payload": payload}, sort_keys=True
            ).encode()
        ).hexdigest()
        self.journal.reserve(fingerprint)
        try:
            response = self.session.post(
                self.settings.jira_url + "/rest/api/3/issue",
                json=payload,
                timeout=25,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            self.journal.record(fingerprint, "unknown")
            raise SubmissionUnknown(
                "Jira submission outcome is unknown. Check Jira before retrying. "
                f"Submission ID: {fingerprint}"
            ) from exc
        if response.status_code != 201:
            if response.status_code >= 500 or 200 <= response.status_code < 300:
                self.journal.record(fingerprint, "unknown")
                raise SubmissionUnknown(
                    "Unexpected Jira response; the issue may exist. Check Jira. "
                    f"Submission ID: {fingerprint}"
                )
            self.journal.release(fingerprint)
            # Never echo provider response bodies; they may contain feedback or secrets.
            raise JiraError(
                f"Jira rejected the request (HTTP {response.status_code}). "
                "Check required fields, field values, permissions, and token."
            )
        try:
            data = response.json()
            key = data.get("key", "")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*-\d+", key):
                raise ValueError("Invalid key")
        except (ValueError, AttributeError, TypeError) as exc:
            self.journal.record(fingerprint, "unknown")
            raise SubmissionUnknown(
                "Jira accepted the request but returned no valid issue key. "
                f"Check Jira. Submission ID: {fingerprint}"
            ) from exc
        self.journal.record(fingerprint, "created", key)
        return {
            "key": key,
            "url": f"{self.settings.jira_url}/browse/{key}",
            "submission_id": fingerprint,
        }
