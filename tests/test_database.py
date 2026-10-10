import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shepard.database import Labyrinth


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Labyrinth(Path(self.temp.name) / "labyrinth.db")
        self.db.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def test_job_task_message_and_approval_are_persisted(self):
        job_id = self.db.create_job("Prepare an internship application")
        task_id = self.db.create_task(
            job_id, 1, "scribe", "Draft letter", "Draft only", "email.send"
        )
        self.db.add_message(job_id, task_id, "shepard", "scribe", "assignment", "Draft only")
        approval_id = self.db.create_approval(job_id, task_id, "email.send", "Send the letter")
        self.db.decide_approval(approval_id, "denied")
        job = self.db.get_job(job_id)
        self.assertEqual(job["tasks"][0]["sheep_id"], "scribe")
        self.assertEqual(job["messages"][0]["recipient"], "scribe")
        self.assertEqual(job["approvals"][0]["status"], "denied")
        self.assertGreaterEqual(len(job["audit_events"]), 3)

    def test_internship_tracker_persists_private_source_and_public_summary(self):
        internship_id = self.db.create_internship(
            source_url="https://example.com/jobs/engineering-intern",
            source_title="Engineering Intern",
            source_text="Untrusted shared-page text with qualifications.",
            company="Example Labs",
            notes="Owner prefers a summer start.",
        )
        self.db.update_internship(
            internship_id,
            location="Buffalo, NY",
            stage="reviewed",
            analysis_status="completed",
            match_score=87,
            next_action="Review the tailored application kit.",
        )
        public = self.db.get_internship(internship_id)
        private = self.db.get_internship(internship_id, include_source=True)
        self.assertNotIn("source_text", public)
        self.assertEqual(private["source_text"], "Untrusted shared-page text with qualifications.")
        self.assertEqual(public["match_score"], 87)
        self.assertEqual(self.db.list_internships()[0]["company"], "Example Labs")
        with self.assertRaisesRegex(ValueError, "already in the tracker"):
            self.db.create_internship(
                source_url="https://example.com/jobs/engineering-intern",
                source_title="Duplicate",
                source_text="Duplicate",
            )

    def test_generic_approval_records_authorization_without_claiming_execution(self):
        job_id = self.db.create_job("Authorize a specific application")
        task_id = self.db.create_task(
            job_id, 1, "steward", "Authorize", "Ask the owner", "application.submit"
        )
        approval_id = self.db.create_approval(
            job_id, task_id, "application.submit", "Prepare this application"
        )
        decision = self.db.decide_approval(approval_id, "approved")
        job = self.db.get_job(job_id)
        self.assertEqual(decision["status"], "approved")
        self.assertEqual(job["status"], "completed")
        self.assertIn("No external action has been executed", job["final_output"])

    def test_resume_review_and_active_search_are_persisted(self):
        review_id = self.db.create_resume_review("owner-resume.docx")
        self.db.update_resume_review(
            review_id,
            status="completed",
            critique="Strong foundation; quantify two project bullets.",
            search_terms=["Python", "SQL"],
            target_roles=["Software Engineering Intern"],
            location_preferences=["Remote"],
        )
        review = self.db.latest_resume_review()
        self.assertEqual(review["search_terms"], ["Python", "SQL"])
        self.assertEqual(review["target_roles"], ["Software Engineering Intern"])

        search_id = self.db.create_internship_search(
            query="software engineering intern", interval_hours=24, min_score=60
        )
        due = self.db.due_internship_searches()
        self.assertEqual(due[0]["id"], search_id)
        self.db.update_internship_search(
            search_id, status="paused", last_result_count=3, last_error=None
        )
        saved = self.db.get_internship_search(search_id)
        self.assertEqual(saved["status"], "paused")
        self.assertEqual(saved["last_result_count"], 3)

    def test_alarm_persists_fires_and_repeating_alarm_advances(self):
        soon = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        one_time = self.db.create_alarm("Submit application", soon)
        self.assertEqual(one_time["status"], "active")
        fired = self.db.fire_alarm(one_time["id"])
        self.assertEqual(fired["status"], "fired")
        self.assertIsNotNone(fired["last_fired_at"])

        overdue = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        repeating = self.db.create_alarm("Morning review", overdue, "daily")
        advanced = self.db.fire_alarm(repeating["id"])
        self.assertEqual(advanced["status"], "active")
        self.assertGreater(
            datetime.fromisoformat(advanced["scheduled_for"]), datetime.now(timezone.utc)
        )
        self.assertEqual(len(self.db.list_alarms()), 2)

    def test_alarm_requires_timezone_and_valid_repeat(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.db.create_alarm("Wake up", "2026-10-08T06:00:00")
        with self.assertRaisesRegex(ValueError, "repeat"):
            self.db.create_alarm(
                "Wake up", datetime.now(timezone.utc).isoformat(), "sometimes"
            )


if __name__ == "__main__":
    unittest.main()
