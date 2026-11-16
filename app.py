"""Run with: python -m streamlit run app.py"""

import hashlib
import uuid

import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

from signal_to_issue.analyzer import analyze_live, analyze_mock, load_examples
from signal_to_issue.config import Settings
from signal_to_issue.jira import JiraClient, JiraError
from signal_to_issue.journal import SubmissionBlocked, SubmissionJournal
from signal_to_issue.models import (
    CATEGORY_LABELS,
    AnalysisError,
    ReviewedReport,
    source_fingerprint,
)
from signal_to_issue.render import render_markdown


def lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def reset_analysis() -> None:
    for key in ("draft", "reviewed", "analysis_source", "analysis_mode", "result", "analysis_id"):
        st.session_state.pop(key, None)


def load_sample() -> None:
    examples = {e["id"]: e for e in load_examples()}
    st.session_state.feedback = examples[st.session_state.example_id]["feedback"]
    reset_analysis()


def review_form(draft) -> None:
    reviewed = st.session_state.reviewed
    key = st.session_state.analysis_id
    with st.form("review_" + key):
        title = st.text_input("Issue title", value=reviewed.title, max_chars=255)
        category = st.selectbox(
            "Suggested classification",
            list(CATEGORY_LABELS),
            index=list(CATEGORY_LABELS).index(reviewed.category),
            format_func=CATEGORY_LABELS.get,
        )
        left, right = st.columns(2)
        with left:
            actual = st.text_area("Reported behavior", value=reviewed.actual_behavior or "")
            steps = st.text_area(
                "Reproduction steps supplied · one per line",
                value="\n".join(reviewed.reproduction_steps),
            )
            impact = st.text_area("Reported impact", value=reviewed.impact or "")
        with right:
            expected = st.text_area("Expected behavior", value=reviewed.expected_behavior or "")
            environment = st.text_area(
                "Environment supplied · one per line", value="\n".join(reviewed.environment)
            )
            missing = st.text_area(
                "Missing information · one per line", value="\n".join(reviewed.missing_information)
            )
        questions = st.text_area(
            "Follow-up questions · one per line", value="\n".join(reviewed.follow_up_questions)
        )
        if st.form_submit_button("Save reviewed report", type="primary", width="stretch"):
            try:
                st.session_state.reviewed = ReviewedReport(
                    title=title,
                    category=category,
                    actual_behavior=actual.strip() or None,
                    expected_behavior=expected.strip() or None,
                    reproduction_steps=lines(steps),
                    environment=lines(environment),
                    impact=impact.strip() or None,
                    missing_information=lines(missing),
                    follow_up_questions=lines(questions),
                )
                st.success("Reviewed report saved. Exports and Jira use this saved version.")
            except ValidationError:
                st.error(
                    "Check the title and list lengths. A title is required; steps and environment "
                    "allow 15 entries, missing details 20, and questions 10."
                )
    with st.expander("Original draft evidence and classification rationale"):
        st.text(draft.rationale)
        st.caption(
            "Quotes were checked against the input. This checks text presence, not whether "
            "the interpretation is correct. Your saved edits are reviewer-authored."
        )
        for name, fact in draft.facts():
            st.text(f"{name}: {fact.value}\nSource quote: “{fact.quote}”")


def output_panel(settings: Settings, mode: str) -> None:
    reviewed = st.session_state.reviewed
    markdown = render_markdown(reviewed, mode=mode)
    st.subheader("3. Export or escalate")
    st.caption("Save edits above before exporting or submitting. Unknown fields remain explicit.")
    left, right = st.columns(2)
    left.download_button(
        "Download Markdown",
        markdown,
        "signal-to-issue-report.md",
        mime="text/markdown",
        width="stretch",
    )
    right.download_button(
        "Download reviewed JSON",
        reviewed.model_dump_json(indent=2),
        "signal-to-issue-report.json",
        mime="application/json",
        width="stretch",
    )
    with st.expander("Saved report preview"):
        st.code(markdown, language="markdown", wrap_lines=True)
    with st.expander("Optional · Create a Jira issue"):
        st.caption(
            "Uses the Jira credentials in your local .env. Only clicking Create sends "
            "the saved report to Jira. Jira may notify project watchers."
        )
        if reviewed.category != "suspected_bug":
            st.info(
                "This is not classified as a suspected bug. Review whether escalation is "
                "appropriate and choose the intended JIRA_ISSUE_TYPE in .env."
            )
        st.text(
            f"Destination: {settings.jira_url or 'Not configured'}\n"
            f"Project: {settings.jira_project_key} · Type: {settings.jira_issue_type}"
        )
        try:
            settings.validate_jira()
            configured = True
        except ValueError as exc:
            configured = False
            st.info(str(exc))
        digest = hashlib.sha256(
            (st.session_state.analysis_source + mode + markdown).encode()
        ).hexdigest()
        approved = st.checkbox(
            "I reviewed the saved report and approve creating one Jira issue.",
            key="approve_" + digest,
            disabled=not configured,
        )
        if st.button("Create Jira issue", type="primary", disabled=not (configured and approved)):
            try:
                with st.spinner("Checking project fields and submitting once…"):
                    journal = SubmissionJournal(settings.submission_db)
                    st.session_state.result = JiraClient(settings, journal).create_issue(
                        reviewed, mode=mode, approved=approved
                    )
                    st.session_state.result["report_digest"] = digest
            except (JiraError, SubmissionBlocked, ValueError, OSError) as exc:
                st.error(str(exc))
        if st.session_state.get("result", {}).get("report_digest") == digest:
            result = st.session_state.result
            st.success(f"Created {result['key']}")
            st.link_button("Open Jira issue", result["url"])


def main() -> None:
    load_dotenv()
    st.set_page_config(page_title="Signal to Issue", page_icon="↗", layout="wide")
    st.markdown(
        """<style>
      .block-container { max-width: 1160px; padding-top: 2.5rem; }
      h1 { letter-spacing: -0.045em; }
      [data-testid="stSidebar"] { background: #edf3f6; }
      .eyebrow { color: #157f78; font-weight: 700; letter-spacing: .15em; font-size: .75rem; }
      .hero-note { color: #5b6e7e; font-size: 1.1rem; max-width: 700px; }
    </style>""",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="eyebrow">SUPPORT → PRODUCT → ENGINEERING</div>', unsafe_allow_html=True
    )
    st.title("Signal to Issue")
    st.markdown(
        '<p class="hero-note">Turn messy feedback into a clear escalation. '
        "Keep the evidence. Review the decision.</p>",
        unsafe_allow_html=True,
    )
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        st.error(str(exc))
        return
    examples = load_examples()
    by_id = {example["id"]: example for example in examples}
    with st.sidebar:
        st.header("Your workspace")
        selected_mode = st.radio("Analysis mode", ["Mock demo", "Live AI"], key="mode")
        mode = "mock" if selected_mode == "Mock demo" else "live"
        if mode == "mock":
            st.info(
                "Offline walkthrough. Five fictional examples with prerecorded outputs. "
                "No model or Jira calls happen during analysis."
            )
        else:
            st.info(
                "Live analysis sends the submitted text to OpenAI. Remove private data "
                "and only use information you are authorized to share."
            )
            st.text(f"Model: {settings.openai_model}")
        st.selectbox(
            "Load a fictional example",
            list(by_id),
            key="example_id",
            format_func=lambda x: by_id[x]["label"],
            on_change=load_sample,
        )
        st.divider()
        st.caption("WORKFLOW")
        st.write(
            "1. Add feedback\n\n2. Review evidence and edit\n\n3. Export or approve Jira submission"
        )
        st.divider()
        st.caption("Built by Nestor Rogel · v0.1.0\n\nFictional examples. No employer data.")
    if "feedback" not in st.session_state:
        st.session_state.feedback = examples[0]["feedback"]
    st.subheader("1. Start with the customer’s words")
    feedback = st.text_area(
        "Customer feedback",
        key="feedback",
        height=160,
        max_chars=12000,
        help="20–12,000 characters. In mock mode, use an included example.",
    )
    action, note = st.columns([1, 2])
    with action:
        analyze = st.button(
            "Replay mock analysis" if mode == "mock" else "Analyze with OpenAI",
            type="primary",
            width="stretch",
        )
    with note:
        st.caption("Analysis prepares a draft. It does not create a Jira issue.")
    if analyze:
        reset_analysis()
        try:
            with st.spinner("Preparing the report…"):
                report = (
                    analyze_mock(feedback) if mode == "mock" else analyze_live(feedback, settings)
                )
            st.session_state.draft = report
            st.session_state.reviewed = ReviewedReport.from_draft(report)
            st.session_state.analysis_source = source_fingerprint(feedback)
            st.session_state.analysis_mode = mode
            st.session_state.analysis_id = uuid.uuid4().hex
        except AnalysisError as exc:
            st.error(str(exc))
    if "draft" not in st.session_state:
        st.divider()
        st.caption(
            "A useful escalation names the behavior, preserves the evidence, "
            "and asks for what is missing."
        )
        return
    if (
        st.session_state.analysis_source != source_fingerprint(feedback)
        or st.session_state.analysis_mode != mode
    ):
        st.warning(
            "Feedback or mode changed. Analyze again to refresh the report before exporting."
        )
        return
    draft = st.session_state.draft
    st.divider()
    st.subheader("2. Review the report")
    st.caption(
        "Blank fields mean the customer did not provide that detail. "
        "Add verified information as needed, then save your edits."
    )
    st.info(CATEGORY_LABELS[draft.category])
    review_form(draft)
    st.divider()
    output_panel(settings, mode)


if __name__ == "__main__":
    main()
