import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import nexus_release
from package_mod import MOD
from release import format_game_build_notes


class NexusReleaseTests(unittest.TestCase):
    def test_bootstrap_replaces_only_the_known_preview(self):
        preview = {"version": "0.1.0", "category": "main", "game_scoped_id": "1832"}
        release = {**preview, "game_scoped_id": "2000"}
        self.assertIsNone(nexus_release.main_version([preview], "0.1.0", "1832"))
        self.assertIs(nexus_release.main_version([preview, release], "0.1.0", "1832"), release)
        self.assertIs(nexus_release.main_version([preview], "0.1.0"), preview)

    def test_rejects_upload_of_an_older_version(self):
        with self.assertRaisesRegex(ValueError, "newer Nexus main file"):
            nexus_release.main_version([{"version": "0.2.0", "category": "main"}], "0.1.0")

    def test_changelog_uses_the_archive_builds_and_is_idempotent(self):
        built = {"game_version": "0.10.0.653173", "steam_build_id": "25982825"}
        other = {"game_version": "0.10.1.700000", "steam_build_id": "27123456"}
        feature = "Adds a reading."
        with TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "ShipNetAutomation-0.1.0.zip"
            changelog = root / "CHANGELOG.md"
            changelog.write_text(
                "## 0.1.0\n\n### Features\n\n* **Adds a reading.**\n\n"
                + format_game_build_notes(built, [built, other]) + "\n",
                encoding="utf-8",
            )
            with ZipFile(archive, "w") as file:
                file.writestr((MOD / "BUILDINFO.json").as_posix(), json.dumps({
                    "mod_version": "0.1.0", "built_against": built, "tested_game_builds": [built, other],
                }))
            line = (
                "ⓘ [Built on]  0.10.0.653173 (BuildID 25982825) | Tested: "
                "✓ 0.10.0.653173 (BuildID 25982825), ✓ 0.10.1.700000 (BuildID 27123456)"
            )
            saved = {feature, line}
            with patch.object(nexus_release, "existing_notes", side_effect=[set(), saved, saved]), \
                    patch.object(nexus_release, "request") as request:
                nexus_release.sync_notes("123", "0.1.0", changelog, archive, before_upload=True)
                nexus_release.sync_notes("123", "0.1.0", changelog, archive, before_upload=False)
            request.assert_called_once_with("/mods/123/changelogs", "0.1.0", {
                "version": "0.1.0", "changelog": f"{feature}\n{line}",
            })

    def test_feature_notes_skip_legacy_game_build_lists(self):
        changelog = """## 0.1.0

- Adds a reading.

<!-- game-builds:start -->

- Built against The Last Caretaker `0.10.0.653173` (Steam BuildID `25982825`).
- Tested on The Last Caretaker `0.10.0.653173` (Steam BuildID `25982825`).

<!-- game-builds:end -->
"""
        self.assertEqual(nexus_release.notes_lines(changelog, "0.1.0"), ["Adds a reading."])
