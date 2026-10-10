from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


class Labyrinth:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    plan_summary TEXT,
                    final_output TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    sheep_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    required_capability TEXT,
                    status TEXT NOT NULL,
                    result TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
                    capability TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS browser_actions (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    approval_id TEXT NOT NULL UNIQUE REFERENCES approvals(id) ON DELETE CASCADE,
                    sheep_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    url TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS internships (
                    id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    source_title TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT,
                    deadline TEXT,
                    notes TEXT,
                    stage TEXT NOT NULL,
                    analysis_status TEXT NOT NULL,
                    match_score INTEGER,
                    match_summary TEXT,
                    next_action TEXT,
                    job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
                    approval_id TEXT REFERENCES approvals(id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS resume_reviews (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    critique TEXT,
                    search_terms_json TEXT NOT NULL DEFAULT '[]',
                    target_roles_json TEXT NOT NULL DEFAULT '[]',
                    location_preferences_json TEXT NOT NULL DEFAULT '[]',
                    job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS internship_searches (
                    id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    location TEXT,
                    interval_hours INTEGER NOT NULL,
                    min_score INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    last_run_at TEXT,
                    next_run_at TEXT,
                    last_result_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alarms (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    scheduled_for TEXT NOT NULL,
                    repeat_kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_fired_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_job ON tasks(job_id, position);
                CREATE INDEX IF NOT EXISTS idx_messages_job ON messages(job_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_approvals_job ON approvals(job_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_audit_job ON audit_events(job_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_browser_actions_status
                    ON browser_actions(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_internships_stage
                    ON internships(stage, updated_at);
                CREATE INDEX IF NOT EXISTS idx_internships_source
                    ON internships(source_url);
                CREATE INDEX IF NOT EXISTS idx_resume_reviews_created
                    ON resume_reviews(created_at);
                CREATE INDEX IF NOT EXISTS idx_internship_searches_due
                    ON internship_searches(status, next_run_at);
                CREATE INDEX IF NOT EXISTS idx_alarms_due
                    ON alarms(status, scheduled_for);
                """
            )
            now = utc_now()
            db.execute(
                """UPDATE tasks
                   SET status = 'running',
                       result = 'Owner approved the action; waiting for the Chrome Bridge to execute it.',
                       updated_at = ?
                   WHERE status = 'waiting_approval'
                     AND id IN (SELECT task_id FROM browser_actions WHERE status = 'approved')""",
                (now,),
            )
            db.execute(
                """UPDATE jobs
                   SET status = 'running',
                       final_output = 'Approval recorded. Chrome has not changed yet; the approved action is waiting for the Shepard Chrome Bridge.',
                       updated_at = ?
                   WHERE status = 'waiting_approval'
                     AND id IN (SELECT job_id FROM browser_actions WHERE status = 'approved')""",
                (now,),
            )

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    def create_job(self, goal: str) -> str:
        job_id = self._id("job")
        now = utc_now()
        with self.connect() as db:
            db.execute(
                "INSERT INTO jobs (id, goal, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (job_id, goal, "planning", now, now),
            )
        self.audit(job_id, "job.created", "owner", {"goal": goal})
        return job_id

    def update_job(self, job_id: str, *, status: str, plan_summary: str | None = None,
                   final_output: str | None = None, error: str | None = None) -> None:
        fields = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status, utc_now()]
        for key, value in (("plan_summary", plan_summary), ("final_output", final_output), ("error", error)):
            if value is not None:
                fields.append(f"{key} = ?")
                values.append(value)
        values.append(job_id)
        with self.connect() as db:
            cursor = db.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown job: {job_id}")

    def create_task(self, job_id: str, position: int, sheep_id: str, title: str,
                    instructions: str, required_capability: str | None) -> str:
        task_id = self._id("task")
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO tasks
                   (id, job_id, position, sheep_id, title, instructions,
                    required_capability, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, job_id, position, sheep_id, title, instructions,
                 required_capability, "queued", now, now),
            )
        return task_id

    def update_task(self, task_id: str, status: str, result: str | None = None) -> None:
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE tasks SET status = ?, result = COALESCE(?, result), updated_at = ? WHERE id = ?",
                (status, result, utc_now(), task_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown task: {task_id}")

    def interrupt_job(self, job_id: str, reason: str = "Interrupted by owner") -> None:
        now = utc_now()
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE jobs SET status = 'interrupted', error = ?, updated_at = ? WHERE id = ?",
                (reason, now, job_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown job: {job_id}")
            db.execute(
                "UPDATE tasks SET status = 'interrupted', updated_at = ? "
                "WHERE job_id = ? AND status IN ('queued', 'running')",
                (now, job_id),
            )
        self.audit(job_id, "job.interrupted", "owner", {"reason": reason})

    def add_message(self, job_id: str, task_id: str | None, sender: str, recipient: str,
                    kind: str, content: str) -> str:
        message_id = self._id("msg")
        with self.connect() as db:
            db.execute(
                """INSERT INTO messages
                   (id, job_id, task_id, sender, recipient, kind, content, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (message_id, job_id, task_id, sender, recipient, kind, content, utc_now()),
            )
        return message_id

    def create_approval(self, job_id: str, task_id: str | None, capability: str,
                        description: str) -> str:
        approval_id = self._id("approval")
        with self.connect() as db:
            db.execute(
                """INSERT INTO approvals
                   (id, job_id, task_id, capability, description, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
                (approval_id, job_id, task_id, capability, description, utc_now()),
            )
        self.audit(job_id, "approval.requested", "gatekeeper", {
            "approval_id": approval_id,
            "capability": capability,
            "description": description,
        })
        return approval_id

    def decide_approval(self, approval_id: str, decision: str) -> dict[str, Any]:
        if decision not in {"approved", "denied"}:
            raise ValueError("Decision must be approved or denied")
        with self.connect() as db:
            approval = db.execute(
                "SELECT job_id, task_id, capability FROM approvals WHERE id = ?",
                (approval_id,),
            ).fetchone()
            if approval is None:
                raise KeyError(f"Unknown approval: {approval_id}")
            cursor = db.execute(
                "UPDATE approvals SET status = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
                (decision, utc_now(), approval_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Approval has already been decided: {approval_id}")
            browser_action = db.execute(
                "SELECT job_id, task_id FROM browser_actions WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            db.execute(
                "UPDATE browser_actions SET status = ?, updated_at = ? WHERE approval_id = ?",
                (decision, utc_now(), approval_id),
            )
            if browser_action is not None:
                if decision == "denied":
                    task_status = "cancelled"
                    task_result = "Owner denied the proposed browser action."
                    job_status = "cancelled"
                    job_result = "Owner denied the proposed browser action; Chrome was not changed."
                else:
                    task_status = "running"
                    task_result = "Owner approved the action; waiting for the Chrome Bridge to execute it."
                    job_status = "running"
                    job_result = (
                        "Approval recorded. Chrome has not changed yet; the approved action is waiting "
                        "for the Shepard Chrome Bridge."
                    )
                db.execute(
                    "UPDATE tasks SET status = ?, result = ?, updated_at = ? WHERE id = ?",
                    (task_status, task_result, utc_now(), browser_action["task_id"]),
                )
                db.execute(
                    "UPDATE jobs SET status = ?, final_output = ?, updated_at = ? WHERE id = ?",
                    (job_status, job_result, utc_now(), browser_action["job_id"]),
                )
            elif approval["task_id"]:
                task_status = "completed" if decision == "approved" else "cancelled"
                task_result = (
                    "Owner granted authorization. No external action has been executed yet."
                    if decision == "approved"
                    else "Owner denied authorization. No external action was executed."
                )
                job_status = "completed" if decision == "approved" else "cancelled"
                db.execute(
                    "UPDATE tasks SET status = ?, result = ?, updated_at = ? WHERE id = ?",
                    (task_status, task_result, utc_now(), approval["task_id"]),
                )
                db.execute(
                    "UPDATE jobs SET status = ?, final_output = ?, updated_at = ? WHERE id = ?",
                    (job_status, task_result, utc_now(), approval["job_id"]),
                )
        self.audit(approval["job_id"], f"approval.{decision}", "owner", {"approval_id": approval_id})
        return {
            "id": approval_id,
            "job_id": str(approval["job_id"]),
            "task_id": str(approval["task_id"] or ""),
            "capability": str(approval["capability"]),
            "status": decision,
        }

    def create_internship(
        self,
        *,
        source_url: str,
        source_title: str,
        source_text: str,
        title: str = "",
        company: str = "",
        deadline: str = "",
        notes: str = "",
    ) -> str:
        internship_id = self._id("internship")
        now = utc_now()
        with self.connect() as db:
            existing = db.execute(
                "SELECT id FROM internships WHERE source_url = ? AND stage != 'archived' LIMIT 1",
                (source_url,),
            ).fetchone()
            if existing is not None:
                raise ValueError(f"This job page is already in the tracker: {existing['id']}")
            db.execute(
                """INSERT INTO internships
                   (id, source_url, source_title, source_text, title, company,
                    deadline, notes, stage, analysis_status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reviewing', 'queued', ?, ?)""",
                (
                    internship_id,
                    source_url,
                    source_title[:300],
                    source_text[:50_000],
                    (title.strip() or source_title.strip() or "Untitled opportunity")[:300],
                    (company.strip() or "Company not identified")[:200],
                    deadline.strip()[:40] or None,
                    notes.strip()[:4000] or None,
                    now,
                    now,
                ),
            )
        self.audit(None, "internship.created", "owner", {
            "internship_id": internship_id,
            "source_url": source_url,
        })
        return internship_id

    def update_internship(self, internship_id: str, **changes: Any) -> None:
        allowed = {
            "title", "company", "location", "deadline", "notes", "stage",
            "analysis_status", "match_score", "match_summary", "next_action",
            "job_id", "approval_id",
        }
        fields: list[str] = []
        values: list[Any] = []
        for key, value in changes.items():
            if key not in allowed:
                raise ValueError(f"Unsupported internship field: {key}")
            fields.append(f"{key} = ?")
            values.append(value)
        if not fields:
            return
        fields.append("updated_at = ?")
        values.extend((utc_now(), internship_id))
        with self.connect() as db:
            cursor = db.execute(
                f"UPDATE internships SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown internship: {internship_id}")

    def get_internship(self, internship_id: str, *, include_source: bool = False) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM internships WHERE id = ?", (internship_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown internship: {internship_id}")
        result = dict(row)
        if not include_source:
            result.pop("source_text", None)
        if result.get("job_id"):
            try:
                result["job"] = self.get_job(str(result["job_id"]))
            except KeyError:
                result["job"] = None
        else:
            result["job"] = None
        return result

    def list_internships(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT id, source_url, source_title, title, company, location,
                          deadline, notes, stage, analysis_status, match_score,
                          match_summary, next_action, job_id, approval_id,
                          created_at, updated_at
                   FROM internships
                   ORDER BY updated_at DESC, rowid DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def internship_for_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM internships WHERE approval_id = ? LIMIT 1", (approval_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _decode_json_list(value: Any) -> list[str]:
        try:
            decoded = json.loads(str(value or "[]"))
        except json.JSONDecodeError:
            return []
        return [str(item) for item in decoded] if isinstance(decoded, list) else []

    def create_resume_review(self, filename: str, *, job_id: str | None = None) -> str:
        review_id = self._id("resume")
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO resume_reviews
                   (id, filename, status, job_id, created_at, updated_at)
                   VALUES (?, ?, 'queued', ?, ?, ?)""",
                (review_id, filename[:300], job_id, now, now),
            )
        self.audit(job_id, "resume.review_created", "owner", {
            "resume_review_id": review_id,
            "filename": filename[:300],
        })
        return review_id

    def update_resume_review(self, review_id: str, **changes: Any) -> None:
        allowed = {
            "status", "critique", "search_terms", "target_roles",
            "location_preferences", "job_id", "error",
        }
        fields: list[str] = []
        values: list[Any] = []
        for key, value in changes.items():
            if key not in allowed:
                raise ValueError(f"Unsupported resume review field: {key}")
            column = f"{key}_json" if key in {
                "search_terms", "target_roles", "location_preferences"
            } else key
            fields.append(f"{column} = ?")
            values.append(json.dumps(value, ensure_ascii=False) if column.endswith("_json") else value)
        if not fields:
            return
        fields.append("updated_at = ?")
        values.extend((utc_now(), review_id))
        with self.connect() as db:
            cursor = db.execute(
                f"UPDATE resume_reviews SET {', '.join(fields)} WHERE id = ?", values
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown resume review: {review_id}")

    def get_resume_review(self, review_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM resume_reviews WHERE id = ?", (review_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown resume review: {review_id}")
        result = dict(row)
        for field in ("search_terms", "target_roles", "location_preferences"):
            result[field] = self._decode_json_list(result.pop(f"{field}_json", "[]"))
        return result

    def latest_resume_review(self) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT id FROM resume_reviews ORDER BY created_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
        return self.get_resume_review(str(row["id"])) if row is not None else None

    def create_internship_search(
        self,
        *,
        query: str,
        location: str = "",
        interval_hours: int = 24,
        min_score: int = 55,
        status: str = "active",
        source: str = "remotive",
        next_run_at: str | None = None,
    ) -> str:
        search_id = self._id("search")
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO internship_searches
                   (id, query, location, interval_hours, min_score, status, source,
                    next_run_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    search_id, query[:500], location[:200] or None, interval_hours,
                    min_score, status, source, next_run_at or now, now, now,
                ),
            )
        self.audit(None, "internship_search.created", "owner", {
            "search_id": search_id, "query": query[:500], "source": source,
        })
        return search_id

    def update_internship_search(self, search_id: str, **changes: Any) -> None:
        allowed = {
            "query", "location", "interval_hours", "min_score", "status",
            "last_run_at", "next_run_at", "last_result_count", "last_error",
        }
        fields: list[str] = []
        values: list[Any] = []
        for key, value in changes.items():
            if key not in allowed:
                raise ValueError(f"Unsupported internship search field: {key}")
            fields.append(f"{key} = ?")
            values.append(value)
        if not fields:
            return
        fields.append("updated_at = ?")
        values.extend((utc_now(), search_id))
        with self.connect() as db:
            cursor = db.execute(
                f"UPDATE internship_searches SET {', '.join(fields)} WHERE id = ?", values
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown internship search: {search_id}")

    def get_internship_search(self, search_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM internship_searches WHERE id = ?", (search_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown internship search: {search_id}")
        return dict(row)

    def list_internship_searches(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT * FROM internship_searches
                   ORDER BY updated_at DESC, rowid DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def due_internship_searches(self, at: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT * FROM internship_searches
                   WHERE status = 'active' AND next_run_at IS NOT NULL AND next_run_at <= ?
                   ORDER BY next_run_at ASC LIMIT 10""",
                (at or utc_now(),),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_browser_action(self, job_id: str, task_id: str, approval_id: str,
                              sheep_id: str, action: str, url: str,
                              description: str) -> str:
        if action not in {"navigate", "submit"}:
            raise ValueError("Browser action must be navigate or submit")
        action_id = self._id("browser")
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO browser_actions
                   (id, job_id, task_id, approval_id, sheep_id, action, url,
                    description, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (action_id, job_id, task_id, approval_id, sheep_id, action, url,
                 description, now, now),
            )
        self.audit(job_id, "browser.action_proposed", sheep_id, {
            "browser_action_id": action_id,
            "action": action,
            "url": url,
            "approval_id": approval_id,
        })
        return action_id

    def list_browser_actions(self, status: str = "approved", limit: int = 10) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT id, job_id, task_id, approval_id, sheep_id, action, url,
                          description, status, created_at, updated_at
                   FROM browser_actions WHERE status = ?
                   ORDER BY created_at, rowid LIMIT ?""",
                (status, limit),
            )]

    def find_open_browser_action(self, action: str, url: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                """SELECT id, job_id, task_id, approval_id, sheep_id, action, url,
                          description, status, created_at, updated_at
                   FROM browser_actions
                   WHERE action = ? AND url = ? AND status IN ('pending', 'approved')
                   ORDER BY created_at DESC, rowid DESC LIMIT 1""",
                (action, url),
            ).fetchone()
        return dict(row) if row is not None else None

    def complete_browser_action(self, action_id: str, outcome: str,
                                detail: str = "") -> dict[str, Any]:
        if outcome not in {"executed", "failed"}:
            raise ValueError("Browser action outcome must be executed or failed")
        with self.connect() as db:
            action = db.execute(
                "SELECT * FROM browser_actions WHERE id = ?", (action_id,)
            ).fetchone()
            if action is None:
                raise KeyError(f"Unknown browser action: {action_id}")
            if action["status"] != "approved":
                raise ValueError("Only an approved browser action can be completed")
            db.execute(
                "UPDATE browser_actions SET status = ?, updated_at = ? WHERE id = ?",
                (outcome, utc_now(), action_id),
            )
            if outcome == "executed":
                db.execute(
                    "UPDATE tasks SET status = 'completed', result = ?, updated_at = ? WHERE id = ?",
                    (detail or f"Browser {action['action']} action executed by the owner.", utc_now(), action["task_id"]),
                )
                db.execute(
                    "UPDATE jobs SET status = 'completed', final_output = ?, updated_at = ? WHERE id = ?",
                    (detail or f"Approved browser {action['action']} action executed.", utc_now(), action["job_id"]),
                )
                duplicates = db.execute(
                    """SELECT id, job_id, task_id FROM browser_actions
                       WHERE id != ? AND action = ? AND url = ? AND status = 'approved'""",
                    (action_id, action["action"], action["url"]),
                ).fetchall()
                for duplicate in duplicates:
                    db.execute(
                        "UPDATE browser_actions SET status = 'cancelled', updated_at = ? WHERE id = ?",
                        (utc_now(), duplicate["id"]),
                    )
                    db.execute(
                        "UPDATE tasks SET status = 'cancelled', result = ?, updated_at = ? WHERE id = ?",
                        ("Duplicate approved browser action was superseded by an executed action.",
                         utc_now(), duplicate["task_id"]),
                    )
                    db.execute(
                        "UPDATE jobs SET status = 'cancelled', final_output = ?, updated_at = ? WHERE id = ?",
                        ("Duplicate browser action was superseded; Chrome was changed only once.",
                         utc_now(), duplicate["job_id"]),
                    )
            else:
                db.execute(
                    "UPDATE tasks SET status = 'failed', result = ?, updated_at = ? WHERE id = ?",
                    (detail or "Browser action failed.", utc_now(), action["task_id"]),
                )
                db.execute(
                    "UPDATE jobs SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
                    (detail or "Browser action failed.", utc_now(), action["job_id"]),
                )
        result = dict(action)
        result["status"] = outcome
        self.audit(str(action["job_id"]), f"browser.action_{outcome}", "chrome-bridge", {
            "browser_action_id": action_id,
            "detail": detail[:1000],
        })
        return result

    def audit(self, job_id: str | None, event_type: str, actor: str,
              details: dict[str, Any] | None = None) -> str:
        event_id = self._id("event")
        with self.connect() as db:
            db.execute(
                """INSERT INTO audit_events
                   (id, job_id, event_type, actor, details_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (event_id, job_id, event_type, actor,
                 json.dumps(details or {}, sort_keys=True), utc_now()),
            )
        return event_id

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self.connect() as db:
            job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if job is None:
                raise KeyError(f"Unknown job: {job_id}")
            result = dict(job)
            result["tasks"] = [dict(row) for row in db.execute(
                "SELECT * FROM tasks WHERE job_id = ? ORDER BY position", (job_id,)
            )]
            result["messages"] = [dict(row) for row in db.execute(
                "SELECT * FROM messages WHERE job_id = ? ORDER BY created_at, rowid", (job_id,)
            )]
            result["approvals"] = [dict(row) for row in db.execute(
                "SELECT * FROM approvals WHERE job_id = ? ORDER BY created_at, rowid", (job_id,)
            )]
            result["audit_events"] = [dict(row) for row in db.execute(
                "SELECT * FROM audit_events WHERE job_id = ? ORDER BY created_at, rowid", (job_id,)
            )]
            return result

    def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT id, goal, status, plan_summary, created_at, updated_at
                   FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ?""",
                (limit,),
            )]

    def list_approvals(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = """SELECT approvals.*, jobs.goal, tasks.title AS task_title
                   FROM approvals
                   JOIN jobs ON jobs.id = approvals.job_id
                   LEFT JOIN tasks ON tasks.id = approvals.task_id"""
        values: list[Any] = []
        if status is not None:
            query += " WHERE approvals.status = ?"
            values.append(status)
        query += " ORDER BY approvals.created_at DESC, approvals.rowid DESC LIMIT ?"
        values.append(limit)
        with self.connect() as db:
            return [dict(row) for row in db.execute(query, values)]

    @staticmethod
    def _alarm_time(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Alarm time must be a valid ISO date and time") from exc
        if parsed.tzinfo is None:
            raise ValueError("Alarm time must include a timezone")
        return parsed.astimezone(timezone.utc)

    def create_alarm(self, label: str, scheduled_for: str, repeat_kind: str = "none") -> dict[str, Any]:
        label = label.strip()
        if not label:
            raise ValueError("Give the alarm a name")
        if len(label) > 160:
            raise ValueError("Alarm names must be 160 characters or fewer")
        if repeat_kind not in {"none", "daily", "weekdays", "weekly"}:
            raise ValueError("Alarm repeat must be none, daily, weekdays, or weekly")
        scheduled = self._alarm_time(scheduled_for).isoformat(timespec="seconds")
        alarm_id = self._id("alarm")
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO alarms
                   (id, label, scheduled_for, repeat_kind, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'active', ?, ?)""",
                (alarm_id, label, scheduled, repeat_kind, now, now),
            )
        return self.get_alarm(alarm_id)

    def get_alarm(self, alarm_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM alarms WHERE id = ?", (alarm_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown alarm: {alarm_id}")
        return dict(row)

    def list_alarms(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT * FROM alarms
                   ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END,
                            scheduled_for ASC, updated_at DESC
                   LIMIT ?""",
                (limit,),
            )]

    def update_alarm(self, alarm_id: str, *, status: str | None = None,
                     scheduled_for: str | None = None) -> dict[str, Any]:
        fields = ["updated_at = ?"]
        values: list[Any] = [utc_now()]
        if status is not None:
            if status not in {"active", "fired", "dismissed"}:
                raise ValueError("Alarm status must be active, fired, or dismissed")
            fields.append("status = ?")
            values.append(status)
        if scheduled_for is not None:
            fields.append("scheduled_for = ?")
            values.append(self._alarm_time(scheduled_for).isoformat(timespec="seconds"))
        values.append(alarm_id)
        with self.connect() as db:
            cursor = db.execute(
                f"UPDATE alarms SET {', '.join(fields)} WHERE id = ?", values
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown alarm: {alarm_id}")
        return self.get_alarm(alarm_id)

    def fire_alarm(self, alarm_id: str) -> dict[str, Any]:
        alarm = self.get_alarm(alarm_id)
        if alarm["status"] != "active":
            return alarm
        now = datetime.now(timezone.utc)
        scheduled = self._alarm_time(str(alarm["scheduled_for"]))
        repeat_kind = str(alarm["repeat_kind"])
        if repeat_kind == "none":
            next_status = "fired"
            next_time = scheduled
        else:
            next_status = "active"
            next_time = scheduled
            step = timedelta(days=7 if repeat_kind == "weekly" else 1)
            while next_time <= now:
                next_time += step
                if repeat_kind == "weekdays":
                    while next_time.weekday() >= 5:
                        next_time += timedelta(days=1)
        with self.connect() as db:
            db.execute(
                """UPDATE alarms
                   SET status = ?, scheduled_for = ?, last_fired_at = ?, updated_at = ?
                   WHERE id = ? AND status = 'active'""",
                (
                    next_status,
                    next_time.isoformat(timespec="seconds"),
                    now.isoformat(timespec="seconds"),
                    now.isoformat(timespec="seconds"),
                    alarm_id,
                ),
            )
        return self.get_alarm(alarm_id)

    def task_results(self, job_id: str) -> Iterable[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT sheep_id, title, result FROM tasks WHERE job_id = ? AND result IS NOT NULL ORDER BY position",
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]
