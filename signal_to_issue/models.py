"""Typed boundaries between untrusted feedback, AI output, and reviewed reports."""

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["suspected_bug", "configuration_issue", "feature_request", "unclear"]
CATEGORY_LABELS = {
    "suspected_bug": "Suspected bug",
    "configuration_issue": "Possible configuration issue",
    "feature_request": "Feature request",
    "unclear": "Needs clarification",
}


class SourcedFact(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    value: str = Field(min_length=1, max_length=2000)
    quote: str = Field(min_length=1, max_length=2000)


class TriageReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: Category
    rationale: str = Field(min_length=1, max_length=1200)
    title: str = Field(min_length=1, max_length=255)
    actual_behavior: SourcedFact | None
    expected_behavior: SourcedFact | None
    reproduction_steps: list[SourcedFact] = Field(max_length=15)
    environment: list[SourcedFact] = Field(max_length=15)
    impact: SourcedFact | None
    missing_information: list[str] = Field(max_length=20)
    follow_up_questions: list[str] = Field(max_length=10)

    def facts(self) -> list[tuple[str, SourcedFact]]:
        entries = [
            ("actual_behavior", self.actual_behavior),
            ("expected_behavior", self.expected_behavior),
            ("impact", self.impact),
        ]
        entries.extend(
            (f"reproduction_steps[{i}]", f) for i, f in enumerate(self.reproduction_steps)
        )
        entries.extend((f"environment[{i}]", f) for i, f in enumerate(self.environment))
        return [(name, fact) for name, fact in entries if fact is not None]


class ReviewedReport(BaseModel):
    """Edits are reviewer-authored; never attribute them to the model's original quotes."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: Category
    title: str = Field(min_length=1, max_length=255)
    actual_behavior: str | None
    expected_behavior: str | None
    reproduction_steps: list[str] = Field(max_length=15)
    environment: list[str] = Field(max_length=15)
    impact: str | None
    missing_information: list[str] = Field(max_length=20)
    follow_up_questions: list[str] = Field(max_length=10)

    @classmethod
    def from_draft(cls, report: TriageReport) -> "ReviewedReport":
        return cls(
            category=report.category,
            title=report.title,
            actual_behavior=report.actual_behavior.value if report.actual_behavior else None,
            expected_behavior=report.expected_behavior.value if report.expected_behavior else None,
            reproduction_steps=[f.value for f in report.reproduction_steps],
            environment=[f.value for f in report.environment],
            impact=report.impact.value if report.impact else None,
            missing_information=report.missing_information,
            follow_up_questions=report.follow_up_questions,
        )


class AnalysisError(ValueError):
    """A safe, user-facing analysis failure without provider payloads or credentials."""


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def validate_feedback(text: str) -> str:
    text = text.strip()
    if not 20 <= len(text) <= 12000:
        raise AnalysisError("Enter between 20 and 12,000 characters of feedback.")
    return text


def validate_grounding(report: TriageReport, feedback: str) -> None:
    """Check quote presence only. This cannot prove a paraphrase is factually correct."""
    source = normalize(feedback)
    for name, fact in report.facts():
        if normalize(fact.quote) not in source:
            raise AnalysisError(f"Draft rejected: {name} cites text absent from the feedback.")


def source_fingerprint(feedback: str) -> str:
    return hashlib.sha256(normalize(feedback).encode()).hexdigest()
