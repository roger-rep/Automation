"""CLI demos, genuine live evaluation, and explicit uncertain-submission recovery."""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .analyzer import analyze_live, analyze_mock, load_examples
from .config import Settings
from .journal import SubmissionJournal
from .models import AnalysisError, ReviewedReport
from .render import render_markdown


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Signal to Issue: support feedback → reviewed drafts"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser(
        "analyze", help="Analyze one example or a text file; never writes to Jira"
    )
    source = analyze.add_mutually_exclusive_group(required=True)
    source.add_argument("--example", choices=[e["id"] for e in load_examples()])
    source.add_argument("--file", type=Path)
    analyze.add_argument("--live", action="store_true", help="Send text to the configured AI API")
    analyze.add_argument("--output", type=Path, help="Write the draft as Markdown")
    evaluate = sub.add_parser("evaluate", help="Check fixtures, or evaluate live classification")
    evaluate.add_argument("--live", action="store_true", help="Makes five paid AI requests")
    sub.add_parser("submissions", help="List local submission IDs, status, and issue keys")
    retry = sub.add_parser(
        "allow-retry", help="Release an uncertain submission after checking Jira"
    )
    retry.add_argument("submission_id")
    retry.add_argument(
        "--checked-jira",
        action="store_true",
        required=True,
        help="Confirm that you checked Jira and the issue does not already exist",
    )
    args = parser.parse_args()
    load_dotenv()
    try:
        settings = Settings.from_env()
        if args.command == "analyze":
            feedback = (
                args.file.read_text(encoding="utf-8")
                if args.file
                else next(e["feedback"] for e in load_examples() if e["id"] == args.example)
            )
            draft = analyze_live(feedback, settings) if args.live else analyze_mock(feedback)
            markdown = render_markdown(
                ReviewedReport.from_draft(draft), mode="live" if args.live else "mock"
            )
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(markdown, encoding="utf-8")
                print(f"Draft written to {args.output}. Human review is still required.")
            else:
                print(markdown)
        elif args.command == "evaluate":
            results = []
            for example in load_examples():
                try:
                    report = (
                        analyze_live(example["feedback"], settings)
                        if args.live
                        else analyze_mock(example["feedback"])
                    )
                    results.append(
                        {
                            "id": example["id"],
                            "valid_and_grounded": True,
                            "category_matches_reference": report.category
                            == example["report"]["category"],
                        }
                    )
                except AnalysisError:
                    results.append(
                        {
                            "id": example["id"],
                            "valid_and_grounded": False,
                            "category_matches_reference": False,
                        }
                    )
            print(
                json.dumps(
                    {
                        "mode": "live model evaluation"
                        if args.live
                        else "fixture validation only; not AI accuracy",
                        "model": settings.openai_model if args.live else None,
                        "cases": results,
                        "passed": sum(
                            r["valid_and_grounded"] and r["category_matches_reference"]
                            for r in results
                        ),
                        "total": len(results),
                    },
                    indent=2,
                )
            )
            if not all(
                r["valid_and_grounded"] and r["category_matches_reference"] for r in results
            ):
                raise SystemExit(1)
        elif args.command == "submissions":
            print(json.dumps(SubmissionJournal(settings.submission_db).records(), indent=2))
        elif args.command == "allow-retry":
            SubmissionJournal(settings.submission_db).allow_retry(args.submission_id)
            print(
                "Uncertain reservation released if present. "
                "Successful submissions remain protected."
            )
    except (AnalysisError, ValueError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")
