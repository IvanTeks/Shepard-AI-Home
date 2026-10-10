import json
import base64
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from shepard.webapp import (
    _outlook_pages_for_request,
    _validated_browser_target,
    _validated_public_url,
    create_server,
)
from shepard.config import load_settings


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        raw = json.loads(Path("config/default.json").read_text(encoding="utf-8"))
        raw["database"] = str(root / "labyrinth.db")
        self.config_path = root / "config" / "default.json"
        self.config_path.parent.mkdir(parents=True)
        self.config_path.write_text(json.dumps(raw), encoding="utf-8")
        self.environment = mock.patch.dict(
            "os.environ", {
                "GOOGLE_CLIENT_ID": "", "GOOGLE_CLIENT_SECRET": "", "ANTHROPIC_API_KEY": "",
                "GEMINI_API_KEY": "",
            }
        )
        self.environment.start()
        self.server = create_server("127.0.0.1", 0, self.config_path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.environment.stop()
        self.temp.cleanup()

    def request(self, path, payload=None, headers=None, method=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method or ("GET" if payload is None else "POST"),
            headers=request_headers,
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_connectors_report_setup_state_without_claiming_access(self):
        status, payload = self.request("/api/connectors")
        google = next(item for item in payload["connectors"] if item["id"] == "google-calendar")
        claude = next(item for item in payload["connectors"] if item["id"] == "claude")
        gemini = next(item for item in payload["connectors"] if item["id"] == "gemini")
        chrome = next(item for item in payload["connectors"] if item["id"] == "chrome")
        linkedin = next(item for item in payload["connectors"] if item["id"] == "linkedin-jobs")
        self.assertEqual(status, 200)
        self.assertEqual(google["status"], "setup_required")
        self.assertEqual(claude["status"], "ready_to_connect")
        self.assertEqual(gemini["status"], "ready_to_connect")
        self.assertEqual(chrome["status"], "setup_required")
        self.assertEqual(linkedin["status"], "manual_only")
        outlook = next(item for item in payload["connectors"] if item["id"] == "outlook-web")
        self.assertEqual(outlook["status"], "needs_chrome")
        self.assertTrue(payload["google_redirect_uri"].endswith("/oauth/google-calendar/callback"))

    def test_projected_labyrinth_renderer_is_served_as_javascript(self):
        with urllib.request.urlopen(self.base_url + "/labyrinth-scene.js", timeout=3) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("javascript", response.headers.get_content_type())
        self.assertIn("class ShepardLabyrinthScene", body)
        self.assertIn("positionBillboards", body)

    def test_alarm_api_creates_lists_fires_and_snoozes(self):
        scheduled = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        status, alarm = self.request("/api/alarms", {
            "label": "Check the internship tracker",
            "scheduled_for": scheduled,
            "repeat_kind": "none",
        })
        self.assertEqual(status, 201)
        self.assertEqual(alarm["status"], "active")

        _, listing = self.request("/api/alarms")
        self.assertEqual(listing["alarms"][0]["label"], "Check the internship tracker")

        _, fired = self.request(f"/api/alarms/{alarm['id']}/fire", {})
        self.assertEqual(fired["status"], "fired")

        snoozed_for = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        _, snoozed = self.request(
            f"/api/alarms/{alarm['id']}",
            {"status": "active", "scheduled_for": snoozed_for},
            method="PATCH",
        )
        self.assertEqual(snoozed["status"], "active")

    def test_outlook_uses_only_explicitly_shared_matching_pages(self):
        pages = [
            {"url": "https://example.com/", "title": "Other"},
            {"url": "https://outlook.office.com/mail/inbox", "title": "Inbox"},
            {"url": "https://outlook.office.com/calendar/view/week", "title": "Calendar"},
        ]
        self.assertEqual(
            [item["title"] for item in _outlook_pages_for_request(pages, "What is in my inbox?")],
            ["Inbox"],
        )
        self.assertEqual(
            [item["title"] for item in _outlook_pages_for_request(pages, "What is on my calendar?")],
            ["Calendar"],
        )
        self.assertEqual(
            _outlook_pages_for_request(
                [{"url": "https://evil.example/outlook/calendar", "title": "Fake"}],
                "What is on my calendar?",
            ),
            [],
        )

    def test_gemini_connection_validates_and_saves_key_locally(self):
        with mock.patch("shepard.webapp.GeminiClient.list_models", return_value=["gemini-flash"]):
            status, payload = self.request(
                "/api/connectors/gemini/connect", {"api_key": "test-gemini-key-long-enough"}
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload["model_names"], ["gemini:gemini-flash"])
        secret = Path(self.temp.name) / "secrets" / "gemini.json"
        self.assertTrue(secret.is_file())
        self.assertEqual(
            json.loads(secret.read_text(encoding="utf-8"))["api_key"],
            "test-gemini-key-long-enough",
        )

    def test_chrome_bridge_requires_pairing_and_accepts_explicit_page_share(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/browser/ping", {})
        self.assertEqual(error.exception.code, 401)
        error.exception.close()

        _, pair = self.request("/api/connectors/chrome/pair", {})
        token = pair["pairing_code"]
        headers = {"X-Shepard-Bridge": token}
        status, ping = self.request("/api/browser/ping", {}, headers)
        self.assertEqual(status, 200)
        self.assertEqual(ping["status"], "connected")

        status, shared = self.request("/api/browser/pages", {
            "url": "https://example.com/page#private-fragment",
            "title": "Example",
            "text": "A page the owner explicitly shared.",
        }, headers)
        self.assertEqual(status, 200)
        self.assertEqual(shared["status"], "shared")
        self.assertEqual(self.server.browser_pages[-1]["url"], "https://example.com/page")
        self.assertEqual(
            Path(pair["extension_path"]).resolve(),
            (Path(self.temp.name) / "chrome-extension").resolve(),
        )
        self.assertTrue((Path(self.temp.name) / "secrets" / "chrome-bridge.json").is_file())

    def test_approved_browser_action_is_exposed_then_completed(self):
        _, pair = self.request("/api/connectors/chrome/pair", {})
        headers = {"X-Shepard-Bridge": pair["pairing_code"]}
        proposal = self.server.propose_browser_action(
            "navigate", "https://example.com/roles", "Open the approved roles page"
        )

        _, pending = self.request("/api/browser/actions", headers=headers)
        self.assertEqual(pending["actions"], [])

        self.request(
            f"/api/approvals/{proposal['approval_id']}", {"decision": "approved"}
        )
        _, current_approvals = self.request("/api/approvals")
        self.assertEqual(current_approvals["approvals"], [])
        _, approval_history = self.request("/api/approvals?status=all")
        self.assertEqual(approval_history["approvals"][0]["status"], "approved")
        approved_job = self.server.labyrinth.get_job(proposal["job_id"])
        self.assertEqual(approved_job["status"], "running")
        self.assertIn("Chrome has not changed yet", approved_job["final_output"])
        _, approved = self.request("/api/browser/actions", headers=headers)
        self.assertEqual(len(approved["actions"]), 1)
        self.assertEqual(approved["actions"][0]["action"], "navigate")

        status, completed = self.request(
            f"/api/browser/actions/{proposal['action_id']}/complete",
            {"outcome": "executed", "detail": "Opened in the active Chrome tab"},
            headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(completed["status"], "executed")
        self.assertEqual(self.server.labyrinth.get_job(proposal["job_id"])["status"], "completed")

    def test_repeat_navigation_reuses_open_action_and_approval_followup_is_truthful(self):
        first_status, first = self.request("/api/chat", {
            "messages": [{"role": "user", "content": "Open https://example.com in Chrome"}]
        })
        second_status, second = self.request("/api/chat", {
            "messages": [{"role": "user", "content": "Open https://example.com in Chrome"}]
        })
        self.assertEqual(first_status, 202)
        self.assertEqual(second_status, 202)
        self.assertEqual(first["approval_id"], second["approval_id"])
        self.request(f"/api/approvals/{first['approval_id']}", {"decision": "approved"})
        status, followup = self.request("/api/chat", {
            "messages": [{"role": "user", "content": "I just approved it"}]
        })
        self.assertEqual(status, 200)
        self.assertIn("Chrome has not moved yet", followup["reply"])
        self.assertIn("Chrome Bridge", followup["reply"])

    def test_chat_turns_explicit_submit_request_into_wayfinder_approval(self):
        self.server.browser_pages.append({
            "url": "https://example.com/application",
            "title": "Application",
            "description": "Explicitly shared from Chrome",
            "text": "Application form",
            "shared_at": time.time(),
        })
        status, result = self.request("/api/chat", {
            "messages": [{"role": "user", "content": "Submit this application form"}]
        })
        self.assertEqual(status, 202)
        job = self.server.labyrinth.get_job(result["job_id"])
        self.assertEqual(job["status"], "waiting_approval")
        self.assertEqual(job["tasks"][0]["sheep_id"], "browser")
        self.assertEqual(job["approvals"][0]["capability"], "browser.submit")

    def test_google_connect_requires_local_oauth_credentials(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/connectors/google-calendar/connect", {})
        self.assertEqual(error.exception.code, 409)
        error.exception.close()

    def test_chat_rejects_an_empty_history(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/chat", {"messages": []})
        self.assertEqual(error.exception.code, 400)
        error.exception.close()

    def test_web_reader_rejects_private_network_urls(self):
        with self.assertRaisesRegex(ValueError, "private network"):
            _validated_public_url("http://127.0.0.1/private")

    def test_browser_target_allows_visible_local_navigation_without_server_fetch(self):
        self.assertEqual(
            _validated_browser_target("http://127.0.0.1:8765/jobs#today"),
            "http://127.0.0.1:8765/jobs#today",
        )
        with self.assertRaisesRegex(ValueError, "credentials"):
            _validated_browser_target("https://owner:secret@example.com/")

    def test_chat_navigation_prepares_approval_without_fetching_the_page(self):
        with mock.patch("shepard.webapp._extract_webpage") as extract:
            status, result = self.request("/api/chat", {
                "messages": [{"role": "user", "content": "Open http://127.0.0.1:9999/private in Chrome"}]
            })
        self.assertEqual(status, 202)
        pending = self.server.labyrinth.list_browser_actions("pending")
        self.assertEqual(result["browser_action_id"], pending[0]["id"])
        self.assertEqual(pending[0]["url"], "http://127.0.0.1:9999/private")
        extract.assert_not_called()

    def test_web_reader_requires_a_url(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/web/extract", {"url": ""})
        self.assertEqual(error.exception.code, 400)
        error.exception.close()

    def test_internship_intake_requires_an_explicitly_shared_page(self):
        status, empty = self.request("/api/internships")
        self.assertEqual(status, 200)
        self.assertEqual(empty["internships"], [])
        self.assertIsNone(empty["shared_page"])
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/internships", {"notes": "Summer role"})
        self.assertEqual(error.exception.code, 400)
        error.exception.close()

    def test_internship_intake_starts_fixed_review_and_returns_saved_record(self):
        self.server.browser_pages.append({
            "url": "https://example.com/jobs/software-intern",
            "title": "Software Engineering Intern",
            "description": "Explicitly shared from Chrome",
            "text": "Example Labs seeks a software engineering intern in Buffalo.",
            "shared_at": time.time(),
        })
        started = threading.Event()

        def finish_review(runtime, internship_id, *, job_id):
            started.set()
            return None

        with mock.patch(
            "shepard.webapp.ShepardRuntime.run_internship_review", autospec=True,
            side_effect=finish_review,
        ):
            status, result = self.request("/api/internships", {
                "company": "Example Labs",
                "deadline": "2027-02-01",
                "notes": "Prefer Buffalo or remote.",
            })
            self.assertTrue(started.wait(timeout=2))
        self.assertEqual(status, 202)
        saved = self.server.labyrinth.get_internship(result["internship_id"])
        self.assertEqual(saved["source_url"], "https://example.com/jobs/software-intern")
        self.assertEqual(saved["company"], "Example Labs")
        self.assertEqual(saved["stage"], "reviewing")
        self.assertEqual(saved["job_id"], result["job_id"])

    def test_resume_upload_stays_local_and_starts_critique(self):
        started = threading.Event()

        def finish_review(runtime, review_id, *, job_id):
            started.set()
            return None

        resume_text = (
            "Ivan Tekenah\nSoftware student with Python, Java, SQL, web development, "
            "team projects, technical writing, and application development experience."
        )
        with mock.patch(
            "shepard.webapp.ShepardRuntime.run_resume_review", autospec=True,
            side_effect=finish_review,
        ):
            status, result = self.request("/api/resume", {
                "filename": "Ivan Resume.txt",
                "content_base64": base64.b64encode(resume_text.encode()).decode(),
            })
            self.assertTrue(started.wait(timeout=2))
        self.assertEqual(status, 202)
        settings = load_settings(self.config_path)
        self.assertEqual(settings.owner_profile_path.read_text(encoding="utf-8").strip(), resume_text)
        _, payload = self.request("/api/resume")
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["review"]["id"], result["review_id"])

    def test_active_scout_uses_public_feed_and_saves_pre_scored_discovery(self):
        settings = load_settings(self.config_path)
        settings.owner_profile_path.parent.mkdir(parents=True, exist_ok=True)
        settings.owner_profile_path.write_text(
            "Python SQL software engineering web application project experience", encoding="utf-8"
        )
        review_id = self.server.labyrinth.create_resume_review("resume.txt")
        self.server.labyrinth.update_resume_review(
            review_id,
            status="completed",
            search_terms=["Python", "SQL", "software engineering"],
            target_roles=["Software Engineering Intern"],
        )
        jobs = [{
            "url": "https://remotive.com/remote-jobs/software-dev/example-intern-1",
            "title": "Software Engineering Intern",
            "company": "Example Labs",
            "location": "Remote",
            "description": "Internship building Python and SQL services with a software engineering team.",
        }]
        with mock.patch("shepard.webapp.fetch_remotive_jobs", return_value=jobs), mock.patch(
            "shepard.webapp.fetch_simplify_internships", return_value=[]
        ):
            status, result = self.request("/api/internship-searches", {
                "query": "software engineering intern",
                "interval_hours": 24,
                "min_score": 40,
            })
            search_id = result["search"]["id"]
            deadline = time.time() + 2
            while time.time() < deadline:
                if self.server.labyrinth.get_internship_search(search_id)["last_run_at"]:
                    break
                time.sleep(0.02)
        self.assertEqual(status, 202)
        search = self.server.labyrinth.get_internship_search(search_id)
        self.assertEqual(search["last_result_count"], 1)
        saved = self.server.labyrinth.list_internships()[0]
        self.assertEqual(saved["stage"], "discovered")
        self.assertEqual(saved["analysis_status"], "pre_scored")
        self.assertGreaterEqual(saved["match_score"], 40)

    def test_application_authorization_is_specific_and_does_not_claim_submission(self):
        internship_id = self.server.labyrinth.create_internship(
            source_url="https://example.com/jobs/approved-role",
            source_title="Approved Role",
            source_text="Role details",
            company="Example Labs",
        )
        self.server.labyrinth.update_internship(
            internship_id,
            analysis_status="completed",
            stage="reviewed",
            match_summary="Reviewed",
        )
        status, request = self.request(f"/api/internships/{internship_id}/approval", {})
        self.assertEqual(status, 202)
        approval_job = self.server.labyrinth.get_job(request["job_id"])
        self.assertEqual(approval_job["status"], "waiting_approval")
        self.assertIn("No application has been submitted", approval_job["final_output"])

        self.request(f"/api/approvals/{request['approval_id']}", {"decision": "approved"})
        saved = self.server.labyrinth.get_internship(internship_id)
        self.assertEqual(saved["stage"], "approved_to_apply")
        self.assertIn("separate final", saved["next_action"])

        _, patched = self.request(
            f"/api/internships/{internship_id}", {"stage": "applied"}, method="PATCH"
        )
        self.assertEqual(patched["stage"], "applied")
        self.assertIn("follow-up", patched["next_action"])

    def test_weather_rejects_invalid_coordinates_before_network_access(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/weather?lat=wrong&lon=10")
        self.assertEqual(error.exception.code, 400)
        error.exception.close()


if __name__ == "__main__":
    unittest.main()
