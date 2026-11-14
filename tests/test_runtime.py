import json
import tempfile
import unittest
from pathlib import Path

from shepard.config import load_settings
from shepard.database import Labyrinth
from shepard.runtime import BROWSER_EVIDENCE_MARKER, ShepardRuntime


class FakeOllama:
    def __init__(self):
        self.calls = []

    def chat(self, model, messages, *, json_mode=False, temperature=0.2, num_predict=1400):
        self.calls.append({"model": model, "messages": messages, "json_mode": json_mode})
        if json_mode:
            return json.dumps({
                "summary": "Research, draft, then review",
                "tasks": [
                    {
                        "sheep_id": "scout",
                        "title": "Find evidence",
                        "instructions": "Identify the strongest relevant facts.",
                        "required_capability": None,
                    },
                    {
                        "sheep_id": "reviewer",
                        "title": "Review evidence",
                        "instructions": "Check the prior work and identify gaps.",
                        "required_capability": None,
                    },
                ],
            })
        if len(self.calls) == 2:
            return "Scout result"
        if len(self.calls) == 3:
            self.assert_prior_result(messages)
            return "Reviewer result"
        return "Shepard final result"

    @staticmethod
    def assert_prior_result(messages):
        if "Scout result" not in messages[-1]["content"]:
            raise AssertionError("Later Sheep did not receive earlier Sheep work")


class CouncilOllama:
    def __init__(self):
        self.calls = []

    def chat(self, model, messages, *, json_mode=False, temperature=0.2, num_predict=1400):
        self.calls.append({"model": model, "messages": messages, "json_mode": json_mode})
        return f"Council report {len(self.calls)}"


class InternshipOllama:
    def __init__(self):
        self.calls = []

    def chat(self, model, messages, *, json_mode=False, temperature=0.2, num_predict=1400):
        self.calls.append({"model": model, "messages": messages})
        responses = [
            "JOB_TITLE: Software Engineering Intern\nCOMPANY: Example Labs\nLOCATION: Buffalo, NY\nDEADLINE: 2027-02-01\nFacts from the shared page.",
            "MATCH_SCORE: 86\nStrong Python match; one stated qualification is missing.",
            "Tailored summary and truthful cover-letter draft.",
            "READY WITH CHANGES: Remove one unsupported adjective.",
            "NEXT_ACTION: Review the tailored draft and confirm the deadline.\nChecklist complete.",
            "Final internship application brief.",
        ]
        return responses[min(len(self.calls) - 1, len(responses) - 1)]


class ResumeOllama:
    def __init__(self):
        self.calls = []

    def chat(self, model, messages, *, json_mode=False, temperature=0.2, num_predict=1400):
        self.calls.append({"model": model, "messages": messages})
        responses = [
            "SEARCH_TERMS: Python, SQL, Java\nTARGET_ROLES: Software Engineering Intern, Data Intern\nLOCATION_PREFERENCES: Remote\nImprove the project bullets.",
            "READY: The critique stays grounded in Scout's evidence.",
            "The résumé fits software and data internships. Quantify project impact where truthful.",
        ]
        return responses[min(len(self.calls) - 1, len(responses) - 1)]


class RuntimeTests(unittest.TestCase):
    def test_private_resume_is_visible_only_to_authorized_scout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = json.loads(Path("config/default.json").read_text(encoding="utf-8"))
            raw["database"] = str(root / "labyrinth.db")
            raw["owner_profile"] = str(root / "resume.txt")
            (root / "resume.txt").write_text("PRIVATE_RESUME_MARKER", encoding="utf-8")
            config_path = root / "config.json"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            settings = load_settings(config_path)
            runtime = ShepardRuntime(settings, labyrinth=Labyrinth(root / "runtime.db"), ollama=FakeOllama())
            self.assertIn("PRIVATE_RESUME_MARKER", runtime._private_owner_profile(settings.agent("scout")))
            self.assertEqual(runtime._private_owner_profile(settings.agent("scribe")), "")

    def test_raw_browser_evidence_is_visible_only_to_browser_reader(self):
        settings = load_settings()
        goal = "Compare this role" + BROWSER_EVIDENCE_MARKER + "PRIVATE_PAGE_MARKER"
        browser_goal = ShepardRuntime._goal_visible_to(settings.agent("browser"), goal)
        scribe_goal = ShepardRuntime._goal_visible_to(settings.agent("scribe"), goal)
        self.assertIn("PRIVATE_PAGE_MARKER", browser_goal)
        self.assertNotIn("PRIVATE_PAGE_MARKER", scribe_goal)
        self.assertIn("Wayfinder's recorded result", scribe_goal)

    def test_weekly_council_gives_every_sheep_a_review_task(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = json.loads(Path("config/default.json").read_text(encoding="utf-8"))
            raw["shepard"]["model"] = "qwen3:8b"
            for profile in raw["sheep"]:
                profile["model"] = "qwen3:8b"
            config_path = root / "config.json"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            settings = load_settings(config_path)
            db = Labyrinth(root / "labyrinth.db")
            fake = CouncilOllama()
            result = ShepardRuntime(settings, labyrinth=db, ollama=fake).run_council()
            job = db.get_job(result.job_id)
            self.assertEqual(result.status, "completed")
            self.assertTrue(job["goal"].startswith("Weekly Sunday Council"))
            self.assertEqual(
                [task["sheep_id"] for task in job["tasks"]],
                [profile.id for profile in settings.sheep],
            )
            self.assertTrue(all(task["status"] == "completed" for task in job["tasks"]))
            self.assertEqual(len(fake.calls), len(settings.sheep) + 1)

    def test_market_briefing_routes_hen_through_independent_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = json.loads(Path("config/default.json").read_text(encoding="utf-8"))
            raw["shepard"]["model"] = "qwen3:8b"
            for profile in raw["sheep"]:
                profile["model"] = "qwen3:8b"
            config_path = root / "config.json"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            settings = load_settings(config_path)
            db = Labyrinth(root / "labyrinth.db")
            fake = CouncilOllama()
            evidence = (
                "Collected: 2026-11-10T14:00:00+00:00\n"
                "| F | 2026-11-09 | $12.00 | source=https://example.test/f |"
            )
            result = ShepardRuntime(settings, labyrinth=db, ollama=fake).run_market_briefing(
                evidence=evidence
            )
            job = db.get_job(result.job_id)
            self.assertEqual([task["sheep_id"] for task in job["tasks"]], ["hen", "reviewer"])
            self.assertTrue(all(task["status"] == "completed" for task in job["tasks"]))
            self.assertIn("not a trade instruction", result.final_output)
            self.assertIn("CURRENT PUBLIC EVIDENCE", fake.calls[0]["messages"][-1]["content"])

    def test_goal_runs_through_multiple_sheep(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings()
            db = Labyrinth(Path(directory) / "labyrinth.db")
            fake = FakeOllama()
            result = ShepardRuntime(settings, labyrinth=db, ollama=fake).run("Test a collaboration")
            self.assertEqual(result.status, "completed")
            self.assertEqual(result.final_output, "Shepard final result")
            job = db.get_job(result.job_id)
            self.assertEqual([task["status"] for task in job["tasks"]], ["completed", "completed"])
            self.assertEqual(len(job["messages"]), 6)

    def test_context_preserves_each_sheep_when_reports_are_long(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings()
            db = Labyrinth(Path(directory) / "labyrinth.db")
            db.initialize()
            job_id = db.create_job("Test fair context")
            for position, (sheep_id, marker) in enumerate(
                (("scout", "SCOUT_MARKER"), ("scribe", "SCRIBE_MARKER"), ("reviewer", "REVIEWER_MARKER")),
                start=1,
            ):
                task_id = db.create_task(job_id, position, sheep_id, marker, marker, None)
                db.update_task(task_id, "completed", marker + (" x" * 20000))
            runtime = ShepardRuntime(settings, labyrinth=db, ollama=FakeOllama())
            context = runtime._context(job_id)
            self.assertIn("SCOUT_MARKER", context)
            self.assertIn("SCRIBE_MARKER", context)
            self.assertIn("REVIEWER_MARKER", context)
            self.assertLessEqual(len(context), settings.max_context_characters)

    def test_internship_review_runs_the_fixed_five_sheep_route(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = json.loads(Path("config/default.json").read_text(encoding="utf-8"))
            raw["database"] = str(root / "labyrinth.db")
            raw["owner_profile"] = str(root / "resume.txt")
            (root / "resume.txt").write_text("Python project experience", encoding="utf-8")
            config_path = root / "config.json"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            settings = load_settings(config_path)
            db = Labyrinth(root / "labyrinth.db")
            db.initialize()
            internship_id = db.create_internship(
                source_url="https://example.com/jobs/software-intern",
                source_title="Shared role",
                source_text="UNTRUSTED_JOB_PAGE: Example Labs seeks a Python intern.",
            )
            job_id = db.create_job("Internship Command Center review")
            db.update_internship(internship_id, job_id=job_id)
            fake = InternshipOllama()

            result = ShepardRuntime(settings, labyrinth=db, ollama=fake).run_internship_review(
                internship_id, job_id=job_id
            )

            saved = db.get_internship(internship_id)
            job = db.get_job(job_id)
            self.assertEqual(result.status, "completed")
            self.assertEqual(
                [task["sheep_id"] for task in job["tasks"]],
                ["browser", "scout", "scribe", "reviewer", "steward"],
            )
            self.assertEqual(saved["title"], "Software Engineering Intern")
            self.assertEqual(saved["company"], "Example Labs")
            self.assertEqual(saved["match_score"], 86)
            self.assertEqual(saved["stage"], "reviewed")
            self.assertIn("Review the tailored draft", saved["next_action"])
            self.assertEqual(len(fake.calls), 6)

    def test_resume_review_builds_search_profile_without_exposing_raw_file_to_reviewer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = json.loads(Path("config/default.json").read_text(encoding="utf-8"))
            raw["database"] = str(root / "labyrinth.db")
            raw["owner_profile"] = str(root / "resume.txt")
            (root / "resume.txt").write_text(
                "PRIVATE_RESUME_MARKER Python SQL Java project experience", encoding="utf-8"
            )
            config_path = root / "config.json"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            settings = load_settings(config_path)
            db = Labyrinth(root / "labyrinth.db")
            db.initialize()
            job_id = db.create_job("Résumé Desk review")
            review_id = db.create_resume_review("resume.docx", job_id=job_id)
            fake = ResumeOllama()

            result = ShepardRuntime(settings, labyrinth=db, ollama=fake).run_resume_review(
                review_id, job_id=job_id
            )

            saved = db.get_resume_review(review_id)
            job = db.get_job(job_id)
            self.assertEqual(result.status, "completed")
            self.assertEqual([task["sheep_id"] for task in job["tasks"]], ["scout", "reviewer"])
            self.assertEqual(saved["search_terms"], ["Python", "SQL", "Java"])
            self.assertEqual(saved["target_roles"][0], "Software Engineering Intern")
            self.assertIn("PRIVATE_RESUME_MARKER", fake.calls[0]["messages"][0]["content"])
            self.assertNotIn("PRIVATE_RESUME_MARKER", fake.calls[1]["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
