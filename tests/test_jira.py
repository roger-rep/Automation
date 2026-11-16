from dataclasses import replace
from unittest.mock import Mock

import pytest
import requests

from signal_to_issue.jira import JiraClient, JiraError, SubmissionUnknown
from signal_to_issue.journal import SubmissionBlocked, SubmissionJournal


def response(status=200, data=None):
    return Mock(status_code=status, json=Mock(return_value=data))


def session_with_metadata(*, required_extra=False):
    fields = [
        {"fieldId": name, "required": True, "hasDefaultValue": False}
        for name in ["project", "issuetype", "summary"]
    ]
    fields.append({"fieldId": "description", "required": False})
    if required_extra:
        fields.append({"fieldId": "customfield_10001", "required": True, "hasDefaultValue": False})
    session = Mock()
    session.headers = {}
    session.get.side_effect = [
        response(
            data={"issueTypes": [{"id": "10001", "name": "Bug", "subtask": False}], "total": 1}
        ),
        response(data={"fields": fields, "total": len(fields)}),
    ]
    session.post.return_value = response(201, {"key": "DEMO-42"})
    return session


def test_approval_is_required_before_any_api_call(jira_settings, reviewed):
    session = session_with_metadata()
    client = JiraClient(
        jira_settings, SubmissionJournal(jira_settings.submission_db), session=session
    )
    with pytest.raises(JiraError, match="approve"):
        client.create_issue(reviewed, mode="mock")
    session.get.assert_not_called()
    session.post.assert_not_called()


def test_success_uses_adf_and_records_duplicate_guard(jira_settings, reviewed):
    journal = SubmissionJournal(jira_settings.submission_db)
    session = session_with_metadata()
    result = JiraClient(jira_settings, journal, session=session).create_issue(
        reviewed, mode="mock", approved=True
    )
    assert result["key"] == "DEMO-42"
    assert result["url"] == "https://example.atlassian.net/browse/DEMO-42"
    payload = session.post.call_args.kwargs["json"]
    assert payload["fields"]["description"]["type"] == "doc"
    assert payload["fields"]["issuetype"] == {"id": "10001"}
    assert session.post.call_args.kwargs["allow_redirects"] is False
    assert journal.records()[0]["status"] == "created"
    # A second process sharing the same database cannot POST the same payload again.
    second = session_with_metadata()
    with pytest.raises(SubmissionBlocked, match="Already created"):
        JiraClient(
            jira_settings, SubmissionJournal(jira_settings.submission_db), session=second
        ).create_issue(reviewed, mode="mock", approved=True)
    second.post.assert_not_called()


def test_missing_required_field_blocks_post(jira_settings, reviewed):
    session = session_with_metadata(required_extra=True)
    client = JiraClient(
        jira_settings, SubmissionJournal(jira_settings.submission_db), session=session
    )
    with pytest.raises(JiraError, match="customfield_10001"):
        client.create_issue(reviewed, mode="mock", approved=True)
    session.post.assert_not_called()


def test_extra_required_field_is_configurable(jira_settings, reviewed):
    settings = replace(jira_settings, jira_extra_fields={"customfield_10001": "Support"})
    session = session_with_metadata(required_extra=True)
    client = JiraClient(settings, SubmissionJournal(settings.submission_db), session=session)
    client.create_issue(reviewed, mode="mock", approved=True)
    assert session.post.call_args.kwargs["json"]["fields"]["customfield_10001"] == "Support"


def test_metadata_paginates(jira_settings):
    session = Mock(headers={})
    session.get.side_effect = [
        response(data={"issueTypes": [{"id": "1"}], "total": 2}),
        response(data={"issueTypes": [{"id": "2"}], "total": 2}),
    ]
    client = JiraClient(
        jira_settings, SubmissionJournal(jira_settings.submission_db), session=session
    )
    assert len(client._pages("/metadata", "issueTypes")) == 2
    assert session.get.call_args.kwargs["params"]["startAt"] == 1


@pytest.mark.parametrize(
    "failure", [requests.Timeout("secret payload"), requests.ConnectionError()]
)
def test_network_failure_is_unknown_and_never_automatically_retried(
    jira_settings, reviewed, failure
):
    session = session_with_metadata()
    session.post.side_effect = failure
    journal = SubmissionJournal(jira_settings.submission_db)
    client = JiraClient(jira_settings, journal, session=session)
    with pytest.raises(SubmissionUnknown) as error:
        client.create_issue(reviewed, mode="mock", approved=True)
    assert "secret payload" not in str(error.value)
    session.post.assert_called_once()
    assert journal.records()[0]["status"] == "unknown"
    with pytest.raises(SubmissionBlocked):
        journal.reserve(journal.records()[0]["fingerprint"])


@pytest.mark.parametrize("status", [500, 502, 200, 202])
def test_ambiguous_response_retains_reservation(jira_settings, reviewed, status):
    session = session_with_metadata()
    session.post.return_value = response(status, {})
    journal = SubmissionJournal(jira_settings.submission_db)
    with pytest.raises(SubmissionUnknown):
        JiraClient(jira_settings, journal, session=session).create_issue(
            reviewed, mode="mock", approved=True
        )
    assert journal.records()[0]["status"] == "unknown"


def test_rejected_request_releases_reservation_without_echoing_body(jira_settings, reviewed):
    session = session_with_metadata()
    session.post.return_value = response(400, {"errorMessages": ["private feedback"]})
    journal = SubmissionJournal(jira_settings.submission_db)
    with pytest.raises(JiraError) as error:
        JiraClient(jira_settings, journal, session=session).create_issue(
            reviewed, mode="mock", approved=True
        )
    assert "HTTP 400" in str(error.value)
    assert "private feedback" not in str(error.value)
    assert journal.records() == []


def test_accepted_response_without_valid_key_is_unknown(jira_settings, reviewed):
    session = session_with_metadata()
    session.post.return_value = response(201, {"key": "https://evil.example"})
    journal = SubmissionJournal(jira_settings.submission_db)
    with pytest.raises(SubmissionUnknown):
        JiraClient(jira_settings, journal, session=session).create_issue(
            reviewed, mode="mock", approved=True
        )
    assert journal.records()[0]["status"] == "unknown"


def test_manual_retry_cannot_remove_successful_records(jira_settings):
    journal = SubmissionJournal(jira_settings.submission_db)
    journal.reserve("one")
    journal.record("one", "created", "DEMO-1")
    journal.allow_retry("one")
    assert journal.records()[0]["status"] == "created"
    journal.reserve("two")
    journal.record("two", "unknown")
    journal.allow_retry("two")
    assert len(journal.records()) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://example.atlassian.net",
        "https://example.atlassian.net.evil.test",
        "https://user:password@example.atlassian.net",
        "https://localhost",
    ],
)
def test_credentials_only_go_to_expected_https_cloud_tenant(jira_settings, url):
    with pytest.raises(ValueError, match="JIRA_URL"):
        replace(jira_settings, jira_url=url).validate_jira()
