"""A durable local guard against repeating identical Jira POST requests."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path


class SubmissionBlocked(ValueError):
    pass


class SubmissionJournal:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS submissions (
                fingerprint TEXT PRIMARY KEY, status TEXT NOT NULL, issue_key TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, fingerprint: str) -> None:
        try:
            with self.connection() as db:
                db.execute(
                    "INSERT INTO submissions(fingerprint, status) VALUES (?, 'pending')",
                    (fingerprint,),
                )
        except sqlite3.IntegrityError as exc:
            with self.connection() as db:
                row = db.execute(
                    "SELECT status, issue_key FROM submissions WHERE fingerprint=?", (fingerprint,)
                ).fetchone()
            detail = (
                f"Already created: {row[1]}."
                if row and row[0] == "created"
                else (
                    "An earlier submission may have reached Jira. "
                    "Check Jira before allowing a retry."
                )
            )
            raise SubmissionBlocked(f"{detail} Submission ID: {fingerprint}") from exc

    def record(self, fingerprint: str, status: str, issue_key: str | None = None) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE submissions SET status=?, issue_key=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE fingerprint=?",
                (status, issue_key, fingerprint),
            )

    def release(self, fingerprint: str) -> None:
        with self.connection() as db:
            db.execute("DELETE FROM submissions WHERE fingerprint=?", (fingerprint,))

    def records(self) -> list[dict]:
        with self.connection() as db:
            db.row_factory = sqlite3.Row
            return [
                dict(row) for row in db.execute("SELECT * FROM submissions ORDER BY updated_at")
            ]

    def allow_retry(self, fingerprint: str) -> None:
        with self.connection() as db:
            db.execute(
                "DELETE FROM submissions WHERE fingerprint=? AND status IN ('pending', 'unknown')",
                (fingerprint,),
            )
