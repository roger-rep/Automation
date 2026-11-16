import json

import pytest

from signal_to_issue.config import Settings
from signal_to_issue.render import render_markdown, to_adf


def test_export_preserves_unknowns_and_provenance(reviewed):
    text = render_markdown(reviewed, mode="mock")
    assert "prerecorded fixture" in text
    assert "## Expected behavior\n\nNot provided." in text
    assert "confirmed diagnosis" in text


def test_jira_document_has_headings_and_lists(reviewed):
    document = to_adf(render_markdown(reviewed, mode="mock"))
    assert document["version"] == 1
    assert document["content"][0]["type"] == "heading"
    assert any(n["type"] == "bulletList" for n in document["content"])
    assert any(n["type"] == "orderedList" for n in document["content"])
    assert "Blocked dates" in json.dumps(document)


@pytest.mark.parametrize("value", ["[]", "not-json", '{"summary":"override"}', '{"project":{}}'])
def test_invalid_extra_fields_are_rejected(monkeypatch, value):
    monkeypatch.setenv("JIRA_EXTRA_FIELDS", value)
    with pytest.raises(ValueError, match="JIRA_EXTRA_FIELDS"):
        Settings.from_env()


def test_secrets_are_not_in_settings_repr():
    settings = Settings(
        openai_api_key="openai-secret",
        jira_api_token="jira-secret",
        jira_email="private@example.test",
    )
    assert "openai-secret" not in repr(settings)
    assert "jira-secret" not in repr(settings)
    assert "private@example.test" not in repr(settings)
