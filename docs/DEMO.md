# A 60-second portfolio walkthrough

Use only the included fictional examples. Start the app with `python -m streamlit run app.py`.

| Time | Action | What to say |
| --- | --- | --- |
| 0–10 s | Show the calendar feedback in Mock demo | “Support agents spend time turning incomplete customer feedback into clear escalation reports.” |
| 10–25 s | Click Replay mock analysis | “This is a prerecorded demonstration. Live mode uses structured AI extraction, while this walkthrough works without credentials.” |
| 25–40 s | Open the original draft evidence and inspect missing details | “Extracted facts link to customer quotes. Unknown details stay unknown. The classification is a suggestion, not a confirmed bug.” |
| 40–50 s | Edit the title, save the report, and download Markdown | “A reviewer controls the final report and can export it without connecting Jira.” |
| 50–60 s | Show the optional Jira destination and approval control | “With a personal Jira demo project configured, explicit approval triggers field checks and one submission attempt. A local journal protects identical retries.” |

If you demonstrate a real Jira submission, use your own demo project and actually show the returned issue link. Do not imply that mocked API tests prove a live integration was exercised.

## Discussion prompts

- Why distinguish source facts from reviewer edits?
- What happens if an AI response invents a source quote?
- Why does a timeout leave the Jira submission marked uncertain?
- Why are five successful fixture checks not a model-accuracy benchmark?
- What would need to change before deploying this to a shared support team?
