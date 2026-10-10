import json
import tempfile
import unittest
from pathlib import Path

from shepard.config import add_sheep, load_settings, update_persona


class ConfigTests(unittest.TestCase):
    def test_default_configuration_loads(self):
        settings = load_settings()
        self.assertEqual(settings.shepard.id, "shepard")
        self.assertIn("scout", {profile.id for profile in settings.sheep})
        self.assertIn("profile.resume.read", settings.agent("scout").capabilities)
        self.assertEqual(settings.owner_profile_path.name, "resume.txt")
        self.assertIn("email.send", settings.approval_required)
        self.assertEqual(
            set(settings.agent("browser").capabilities),
            {"browser.read", "browser.navigate", "browser.submit"},
        )
        self.assertIn("browser.submit", settings.approval_required)

    def test_persona_update_does_not_change_capabilities(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = json.loads(Path("config/default.json").read_text(encoding="utf-8"))
            original["database"] = str(Path(directory) / "labyrinth.db")
            path.write_text(json.dumps(original), encoding="utf-8")
            before = load_settings(path).agent("scout")
            after = update_persona(path, "scout", name="Mara", persona="Fearless and precise")
            self.assertEqual(after.name, "Mara")
            self.assertEqual(after.capabilities, before.capabilities)

    def test_new_sheep_is_saved_with_a_unique_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = json.loads(Path("config/default.json").read_text(encoding="utf-8"))
            original["database"] = str(Path(directory) / "labyrinth.db")
            path.write_text(json.dumps(original), encoding="utf-8")
            profile = add_sheep(
                path,
                name="Path Finder",
                role="Map difficult routes and dependencies.",
                persona="Quick, cheerful, and exact.",
            )
            self.assertEqual(profile.id, "path-finder")
            self.assertIn("artifact.draft", profile.capabilities)
            self.assertEqual(load_settings(path).agent("path-finder").name, "Path Finder")


if __name__ == "__main__":
    unittest.main()
