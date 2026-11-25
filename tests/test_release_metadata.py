import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import package_mod
import release


class ReleaseMetadataTests(unittest.TestCase):
    def setUp(self):
        self.built = {"game_version": "0.10.0.653173", "steam_build_id": "25982825"}
        self.tested = {"game_version": "0.10.1.700000", "steam_build_id": "27123456"}
        manifest = patch.object(release, "read_manifest", return_value={"built_against": self.built})
        manifest.start()
        self.addCleanup(manifest.stop)
        checks = patch.object(release, "verified_builds", side_effect=lambda mod: mod["tested_game_builds"])
        checks.start()
        self.addCleanup(checks.stop)

    def test_new_changelog_entry_keeps_both_game_identities_and_preserves_history(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "dist").mkdir()
            (root / "Scripts").mkdir()
            (root / "Scripts/main.lua").write_text('local version = "0.1.0"\n', encoding="utf-8")
            mod = {"version": "0.1.0", "tested_game_builds": [self.tested]}
            (root / "mod.json").write_text(json.dumps(mod), encoding="utf-8")
            (root / "dist/release-plan.json").write_text(json.dumps({
                "base": "abc", "version": "0.2.0", "notes": "# 0.2.0\n\n- Adds a reading.",
            }), encoding="utf-8")
            changelog = root / "CHANGELOG.md"
            history = "## 0.1.0\n\n- Original release.\n"
            changelog.write_text("# Changelog\n\n" + history, encoding="utf-8")
            with patch.multiple(release, ROOT=root, LUA=root, CHANGELOG=changelog), \
                    patch.object(release, "metadata", return_value=mod), \
                    patch.object(release, "git", return_value="abc"):
                release.apply_plan("v0.2.0")
            document = changelog.read_text(encoding="utf-8")
            notes = release.changelog_entry(document, "0.2.0").group(1)
            self.assertIn("> **Built on** `0.10.0.653173` (BuildID `25982825`)", notes)
            self.assertIn("> **Tested on** ✅ `0.10.1.700000` (BuildID `27123456`)", notes)
            self.assertTrue(document.endswith(history))

    def test_github_compatibility_quote_merges_the_same_build_and_lists_multiple_builds(self):
        combined = release.format_game_build_notes(self.built, [self.built])
        self.assertEqual(combined.splitlines()[2:-2], [
            "> **Built and tested on** ✅ `0.10.0.653173` (BuildID `25982825`)",
        ])
        same_version_other_build = {**self.built, "steam_build_id": "25982900"}
        multiple = release.format_game_build_notes(self.built, [same_version_other_build, self.tested])
        self.assertEqual(multiple.splitlines()[2:-2], [
            "> **Built on** `0.10.0.653173` (BuildID `25982825`)",
            ">",
            "> **Tested on**",
            ">",
            "> - ✅ `0.10.0.653173` (BuildID `25982900`)",
            "> - ✅ `0.10.1.700000` (BuildID `27123456`)",
        ])
        pending = release.format_game_build_notes(self.built, [])
        self.assertIn("> **Testing pending**", pending)

    def test_github_notes_are_the_changelog_entry_for_that_tag(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            dist = root / "dist"
            dist.mkdir()
            archive = dist / "ShipNetAutomation-0.1.0.zip"
            archive.write_bytes(b"verified zip")
            mod = {"version": "0.1.0", "tested_game_builds": [self.tested]}
            notes = "- First release.\n\n" + release.game_build_notes(mod)
            changelog = root / "CHANGELOG.md"
            changelog.write_text("# Changelog\n\n## 0.1.0\n\n" + notes + "\n", encoding="utf-8")
            with patch.multiple(release, ROOT=root, CHANGELOG=changelog), \
                    patch.object(release, "metadata", return_value=mod), \
                    patch.object(release, "package", return_value=archive):
                _, _, release_notes = release.release_files("v0.1.0")
            self.assertEqual(release_notes.read_text(encoding="utf-8"), notes + "\n")


    def test_runtime_fingerprint_survives_version_stamp_but_detects_code_change(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "main.lua"
            installed = root / "installed" / package_mod.ENTRY
            installed.parent.mkdir(parents=True)
            source.write_bytes(b'local version = "0.1.0"\nreturn true\n')
            installed.write_bytes(b'local version = "0.2.0"\nreturn true\n')
            with patch.object(package_mod, "runtime_files", return_value={package_mod.ENTRY: source}):
                self.assertEqual(package_mod.runtime_fingerprint(), package_mod.runtime_fingerprint(root / "installed"))
                installed.write_bytes(b'local version = "0.2.0"\nreturn false\n')
                self.assertNotEqual(package_mod.runtime_fingerprint(), package_mod.runtime_fingerprint(root / "installed"))

    def test_vortex_override_keeps_lua_and_native_files_at_their_game_paths(self):
        paths = [
            r"Voyage\Binaries\Win64\ue4ss\Mods\ShipNetAutomation\Scripts\main.lua",
            r"Voyage\Content\Paks\ShipNetWinch_P.pak",
            r"Voyage\Mods\ShipNetAutomationCatalogue\ShipNetAutomationCatalogue.uplugin",
        ]
        members = [path.replace("\\", "/") for path in reversed(paths)]
        instructions = json.loads(package_mod.vortex_override(members))

        self.assertEqual(instructions[0], {"type": "setmodtype", "value": "thelastcaretaker-root"})
        self.assertEqual(instructions[1:], [
            {"type": "copy", "source": path, "destination": path} for path in paths
        ])
