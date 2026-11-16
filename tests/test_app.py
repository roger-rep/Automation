"""Exercise real Streamlit widgets without a browser or external API calls."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture
def app(monkeypatch):
    for key in ("OPENAI_API_KEY", "JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_EXTRA_FIELDS"):
        monkeypatch.delenv(key, raising=False)
    return AppTest.from_file(APP).run(timeout=15)


def test_mock_review_edit_and_export_flow(app):
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert app.text_input[0].value.startswith("Blocked dates")
    app.text_input[0].set_value("Reviewed calendar availability mismatch")
    save = next(button for button in app.button if button.label == "Save reviewed report")
    save.click().run()
    assert app.session_state["reviewed"].title == "Reviewed calendar availability mismatch"
    assert not app.exception


def test_source_edit_blocks_stale_report(app):
    app.button[0].click().run()
    app.text_area[0].set_value("This is different feedback that has not been analyzed yet.").run()
    assert any("Analyze again" in warning.value for warning in app.warning)
    assert not any(button.label == "Create Jira issue" for button in app.button)


def test_switching_example_clears_previous_draft(app):
    app.button[0].click().run()
    app.sidebar.selectbox[0].select("feature").run()
    assert "CSV export" in app.text_area[0].value
    assert not any(button.label == "Create Jira issue" for button in app.button)
    app.button[0].click().run()
    assert app.session_state["draft"].category == "feature_request"


def test_live_mode_without_key_displays_helpful_error(app):
    app.sidebar.radio[0].set_value("Live AI").run()
    app.button[0].click().run()
    assert any("OPENAI_API_KEY" in error.value for error in app.error)
    assert not app.exception
