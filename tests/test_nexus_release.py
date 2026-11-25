from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from nexus_release import main_version, notes_lines


class NexusReleaseTests(unittest.TestCase):
    def test_bootstrap_replaces_only_the_known_preview(self):
        preview = {"version": "0.1.0", "category": "main", "game_scoped_id": "1832"}
        release = {**preview, "game_scoped_id": "2000"}
        self.assertIsNone(main_version([preview], "0.1.0", "1832"))
        self.assertIs(main_version([preview, release], "0.1.0", "1832"), release)
        self.assertIs(main_version([preview], "0.1.0"), preview)

    def test_rejects_upload_of_an_older_version(self):
        with self.assertRaisesRegex(ValueError, "newer Nexus main file"):
            main_version([{"version": "0.2.0", "category": "main"}], "0.1.0")

    def test_changelog_retains_build_and_test_versions_as_plain_text(self):
        changelog = """## 0.1.0

<!-- game-builds:start -->

- Built against The Last Caretaker `0.10.0.653173` (Steam BuildID `25982825`).
- Tested on The Last Caretaker `0.10.0.653173` (Steam BuildID `25982825`).

<!-- game-builds:end -->
"""
        self.assertEqual(notes_lines(changelog, "0.1.0"), [
            "Built against The Last Caretaker 0.10.0.653173 (Steam BuildID 25982825).",
            "Tested on The Last Caretaker 0.10.0.653173 (Steam BuildID 25982825).",
        ])
