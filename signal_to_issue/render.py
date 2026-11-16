"""Portable Markdown export and Jira's required Atlassian Document Format."""

import re

from .models import CATEGORY_LABELS, ReviewedReport


def render_markdown(report: ReviewedReport, *, mode: str) -> str:
    provenance = (
        "Mock demo: prerecorded fixture, edited by reviewer"
        if mode == "mock"
        else ("AI-assisted report, edited by reviewer")
    )
    sections = [
        f"# {report.title}",
        f"**Category:** {CATEGORY_LABELS[report.category]}",
        f"**Origin:** {provenance}",
    ]
    for heading, value in [
        ("Reported behavior", report.actual_behavior),
        ("Expected behavior", report.expected_behavior),
        ("Reported impact", report.impact),
    ]:
        sections.append(f"## {heading}\n\n{value or 'Not provided.'}")
    for heading, items, numbered in [
        ("Reproduction steps supplied", report.reproduction_steps, True),
        ("Environment supplied", report.environment, False),
        ("Missing information", report.missing_information, False),
        ("Follow-up questions", report.follow_up_questions, False),
    ]:
        body = (
            "\n".join(f"{i + 1}. {v}" if numbered else f"- {v}" for i, v in enumerate(items))
            or "Not provided."
        )
        sections.append(f"## {heading}\n\n{body}")
    sections.append(
        "---\nPrepared with Signal to Issue. Classification is a triage suggestion, "
        "not a confirmed diagnosis. No priority or root cause was assigned automatically."
    )
    return "\n\n".join(sections) + "\n"


def to_adf(markdown: str) -> dict:
    """Serialize the app's headings, labels, and lists; other inline markup stays literal."""
    nodes = []
    for line in markdown.splitlines():
        if not line:
            continue
        if line == "---":
            nodes.append({"type": "rule"})
            continue
        heading = re.match(r"^(#{1,2}) (.*)$", line)
        if heading:
            nodes.append(
                {
                    "type": "heading",
                    "attrs": {"level": len(heading[1])},
                    "content": [{"type": "text", "text": heading[2]}],
                }
            )
            continue
        bullet, numbered = line.startswith("- "), re.match(r"^\d+\. (.*)$", line)
        if bullet or numbered:
            kind = "bulletList" if bullet else "orderedList"
            text = line[2:] if bullet else numbered[1]
            item = {
                "type": "listItem",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
            }
            if nodes and nodes[-1]["type"] == kind:
                nodes[-1]["content"].append(item)
            else:
                nodes.append({"type": kind, "content": [item]})
            continue
        label = re.match(r"^\*\*([^*]+)\*\*\s*(.*)$", line)
        content = [{"type": "text", "text": line}]
        if label:
            content = [{"type": "text", "text": label[1], "marks": [{"type": "strong"}]}]
            if label[2]:
                content.append({"type": "text", "text": " " + label[2]})
        nodes.append({"type": "paragraph", "content": content})
    return {"type": "doc", "version": 1, "content": nodes}
