import pytest

from signal_to_issue.analyzer import analyze_mock, load_examples
from signal_to_issue.config import Settings
from signal_to_issue.models import ReviewedReport


@pytest.fixture
def example():
    return load_examples()[0]


@pytest.fixture
def reviewed(example):
    return ReviewedReport.from_draft(analyze_mock(example["feedback"]))


@pytest.fixture
def jira_settings(tmp_path):
    return Settings(
        jira_url="https://example.atlassian.net",
        jira_email="demo@example.test",
        jira_api_token="not-a-real-token",
        jira_project_key="DEMO",
        submission_db=tmp_path / "submissions.sqlite3",
    )
