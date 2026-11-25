import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import game_build


class GameBuildTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.steamapps = Path(temp.name)
        self.root = self.steamapps / "common/Voyage"
        (self.root / "Voyage/Content/Paks").mkdir(parents=True)
        self.report = self.steamapps / "game-version.json"
        self.identity = {
            "steam_app_id": 1783560,
            "steam_build_id": "25982825",
            "game_version": "0.10.0.653173",
            "project_version": "0.10.0",
        }
        self.runtime = {**self.identity, "schema": 1, "mod_version": "0.1.0"}
        self.write_manifest()
        self.write_report()

    def write_manifest(self, target="25982825"):
        path = self.steamapps / "appmanifest_1783560.acf"
        path.write_text(f'"AppState" {{ "appid" "1783560" "installdir" "Voyage" '
                        f'"buildid" "25982825" "TargetBuildID" "{target}" }}', encoding="utf-8")

    def write_report(self):
        self.report.write_text(json.dumps(self.runtime), encoding="utf-8")

    def test_preserves_full_release_and_project_versions(self):
        self.assertEqual(game_build.detected_identity(self.root, self.report), self.identity)

    def test_rejects_stale_report_after_steam_update(self):
        self.runtime["steam_build_id"] = "25191271"
        self.write_report()
        with self.assertRaisesRegex(ValueError, "does not match installed Steam build 25982825"):
            game_build.detected_identity(self.root, self.report)

    def test_rejects_pending_update(self):
        self.write_manifest(target="25982826")
        with self.assertRaisesRegex(ValueError, "Steam update pending"):
            game_build.detected_identity(self.root, self.report)

    def test_accepts_project_version_if_optional_revision_is_unavailable(self):
        self.runtime["game_version"] = "0.10.0"
        self.write_report()
        self.assertEqual(game_build.detected_identity(self.root, self.report)["game_version"], "0.10.0")

    def test_records_gameplay_identity_once_for_matching_candidate(self):
        metadata = self.steamapps / "mod.json"
        metadata.write_text('{"version": "0.1.0", "tested_game_builds": []}', encoding="utf-8")
        with (patch.object(game_build, "ROOT", self.steamapps),
              patch("package_mod.runtime_fingerprint", return_value="fingerprint")):
            game_build.record_tested(self.root, self.report)
            game_build.record_tested(self.root, self.report)
        stored = json.loads(metadata.read_text(encoding="utf-8"))
        self.assertEqual(stored["tested_game_builds"], [self.identity])
        self.assertEqual(stored["tested_payload_sha256"], "fingerprint")
