import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import native_assets as assets


class NativeManifestTests(unittest.TestCase):
    def test_reports_changed_blender_input_and_missing_binary(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for path in set((*assets.EXPORT_INPUTS, *assets.NATIVE_INPUTS, *assets.PACKAGES)):
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_bytes(path.as_posix().encode())
            manifest = {
                "schema": 1,
                "built_against": {"steam_app_id": 1783560, "steam_build_id": "25982825",
                                  "game_version": "0.10.0.653173", "project_version": "0.10.0"},
                "export": {"inputs": assets.fingerprints(root, assets.EXPORT_INPUTS),
                           "outputs": assets.fingerprints(root, assets.EXPORT_OUTPUTS)},
                "native": {"inputs": assets.fingerprints(root, assets.NATIVE_INPUTS),
                           "outputs": assets.fingerprints(root, assets.PACKAGES)},
            }
            (root / assets.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
            assets.check(root)
            model = assets.MODELS[0]
            binary = assets.PACKAGES[0]
            (root / model).write_bytes(b"another Blender scene")
            (root / binary).unlink()
            with self.assertRaises(ValueError) as failure:
                assets.check(root)
            self.assertIn(f"SHA-256 mismatch for {model.as_posix()}", str(failure.exception))
            self.assertIn(f"missing {binary.as_posix()}", str(failure.exception))
