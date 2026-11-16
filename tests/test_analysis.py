import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from signal_to_issue.analyzer import analyze_live, analyze_mock, load_examples
from signal_to_issue.config import Settings
from signal_to_issue.models import AnalysisError, TriageReport, validate_grounding


@pytest.mark.parametrize("example", load_examples(), ids=lambda e: e["id"])
def test_fixtures_are_valid_and_quotes_exist(example):
    report = analyze_mock(example["feedback"])
    validate_grounding(report, example["feedback"])
    assert report.category == example["report"]["category"]


def test_unknown_expected_behavior_is_not_fabricated(example):
    assert analyze_mock(example["feedback"]).expected_behavior is None


def test_mock_never_pretends_to_analyze_arbitrary_input():
    with pytest.raises(AnalysisError, match="only replays"):
        analyze_mock("This is a completely different problem with my account.")


@pytest.mark.parametrize("text", ["", "too short", "x" * 12001])
def test_input_bounds(text):
    with pytest.raises(AnalysisError, match="12,000"):
        analyze_mock(text)


def test_rejects_fabricated_source_quote(example):
    data = example["report"].copy()
    data["impact"] = {"value": "All customers are blocked", "quote": "all customers are blocked"}
    with pytest.raises(AnalysisError, match="absent"):
        validate_grounding(TriageReport.model_validate(data), example["feedback"])


def test_rejects_invalid_category_and_extra_actions(example):
    with pytest.raises(ValidationError):
        TriageReport.model_validate({**example["report"], "category": "confirmed_bug"})
    with pytest.raises(ValidationError):
        TriageReport.model_validate({**example["report"], "create_issue_now": True})


def fake_client(response):
    return SimpleNamespace(responses=SimpleNamespace(parse=Mock(return_value=response)))


def test_live_uses_schema_no_tools_and_keeps_feedback_as_data(example):
    response = SimpleNamespace(status="completed", output_parsed=example["report"])
    client = fake_client(response)
    report = analyze_live(example["feedback"], Settings(openai_api_key="test-key"), client=client)
    assert report.category == "suspected_bug"
    kwargs = client.responses.parse.call_args.kwargs
    assert kwargs["store"] is False
    assert "tools" not in kwargs
    assert kwargs["text_format"] is TriageReport
    assert json.loads(kwargs["input"][1]["content"])["feedback"] == example["feedback"]


@pytest.mark.parametrize("status,parsed", [("incomplete", None), ("completed", None)])
def test_incomplete_and_refused_outputs_fail_safely(example, status, parsed):
    client = fake_client(SimpleNamespace(status=status, output_parsed=parsed))
    with pytest.raises(AnalysisError, match="complete report"):
        analyze_live(example["feedback"], Settings(openai_api_key="test-key"), client=client)


def test_live_requires_key_before_network(example):
    client = fake_client(None)
    with pytest.raises(AnalysisError, match="OPENAI_API_KEY"):
        analyze_live(example["feedback"], Settings(), client=client)
    client.responses.parse.assert_not_called()


def test_injected_instructions_do_not_become_actions_in_demo():
    sample = next(e for e in load_examples() if e["id"] == "untrusted")
    report = analyze_mock(sample["feedback"])
    assert "critical" not in report.title
    assert not hasattr(report, "priority")
    assert not hasattr(report, "create_issue")
