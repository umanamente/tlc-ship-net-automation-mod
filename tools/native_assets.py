"""Check committed asset hashes or rebuild them from the local Steam installation."""
import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from game_build import APP_ID, detected_identity, installed_build

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("native/build-manifest.json")
MODEL_NAMES = ("basic-winch-automator-v01.blend", "rail-controller-v05.blend")
SCRIPTS = Path("src/ShipNetAutomation/Scripts/shipnet")
MODELS = tuple(Path("3d_models") / name for name in MODEL_NAMES)
ATLAS = Path("artwork/models/winch-markings.png")
EXPORT_INPUTS = (*MODELS, Path("tools/export_rail_model.py"), Path("tools/rail_model_detail.py"),
                 Path("tools/build_markings.py"), SCRIPTS / "printed_labels.layout")
EXPORT_OUTPUTS = (ATLAS, *(SCRIPTS / name for name in (
    "basic_controller.snm", "basic_controller_lod1.snm", "rail_controller.snm", "rail_controller_lod1.snm",
)))
NATIVE_TOOLS = tuple(Path("tools") / f"{name}.py" for name in (
    "build_construction", "build_construction_mesh", "build_catalog_icon", "build_control_screen",
    "build_cargo_sweep", "build_markings", "cook_visual_asset", "construction_basic",
    "construction_interaction", "construction_packages", "construction_power", "construction_registry",
))
DESCRIPTOR = Path("native/Voyage/Mods/ShipNetAutomationCatalogue/ShipNetAutomationCatalogue.uplugin")
NATIVE_INPUTS = (*EXPORT_OUTPUTS, SCRIPTS / "printed_labels.layout", SCRIPTS / "pbr_palette.layout",
                 Path("artwork/catalog/winch-automator.png"), Path("artwork/catalog/winch-automator-basic.png"),
                 DESCRIPTOR, *NATIVE_TOOLS)
PACKAGES = tuple(Path("native/Voyage/Content/Paks") / f"ShipNetWinch_v07_P.{ext}"
                 for ext in ("pak", "ucas", "utoc"))
TOOLS = ("blender", "retoc", "repak", "uassetgui", "jmap-dumper")


def sha256(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def fingerprints(root, paths):
    return {path.as_posix(): sha256(root / path) for path in sorted(paths)}


def read_manifest(root=ROOT):
    return json.loads((root / MANIFEST).read_text(encoding="utf-8"))


def check(root=ROOT):
    manifest = read_manifest(root)
    identity = manifest.get("built_against", {})
    if (manifest.get("schema") != 1 or identity.get("steam_app_id") != APP_ID
            or not identity.get("steam_build_id") or not identity.get("game_version")):
        raise ValueError("Invalid asset build manifest or missing game identity")
    groups = [
        ("export", "inputs", EXPORT_INPUTS), ("export", "outputs", EXPORT_OUTPUTS),
        ("native", "inputs", NATIVE_INPUTS), ("native", "outputs", PACKAGES),
    ]
    problems = []
    for step, kind, paths in groups:
        recorded = manifest.get(step, {}).get(kind, {})
        expected_paths = {path.as_posix() for path in paths}
        for extra in sorted(recorded.keys() - expected_paths):
            problems.append(f"{step} {kind}: unexpected manifest entry {extra}")
        for path in paths:
            file = root / path
            if not file.is_file():
                problems.append(f"{step} {kind}: missing {path.as_posix()}")
            elif sha256(file) != recorded.get(path.as_posix()):
                problems.append(f"{step} {kind}: SHA-256 mismatch for {path.as_posix()}")
    if problems:
        raise ValueError("\n".join(problems) + "\nRun tools/native_assets.py rebuild locally and commit the regenerated files.")


def command(argv, **kwargs):
    return subprocess.run([str(value) for value in argv], check=True, **kwargs)


def export_models(root, blender, scratch):
    args = [blender, "--background", "--factory-startup", "--disable-autoexec"]
    env = dict(os.environ)
    env.pop("SHIPNET_MARKINGS_DIR", None)
    contours = scratch / "contours"
    for model in MODELS:
        script = [*args, root / model, "--python-exit-code", "1", "--python", root / "tools/export_rail_model.py"]
        command(script, env=env)
        command(script, env={**env, "SHIPNET_MARKINGS_DIR": str(contours)})
    command([sys.executable, root / "tools/build_markings.py", contours])


def rebuild(options):
    tools = {name: Path(getattr(options, name.replace("-", "_"))).resolve(strict=True) for name in TOOLS}
    game = options.game_root.resolve(strict=True)
    jmap = options.jmap.resolve(strict=True)
    identity = detected_identity(game, options.version_report)
    game_paks = game / "Voyage/Content/Paks"
    upstream_paths = [game_paks / name for name in ("global.utoc", "pakchunk0-Windows.utoc")]
    upstream = {"reflection_sha256": sha256(jmap),
                "game_indexes": {path.name: sha256(path) for path in upstream_paths}}
    provenance = {
        "blender": command([tools["blender"], "--version"], capture_output=True, text=True).stdout.splitlines()[0],
        "python": platform.python_version(),
        "pillow": version("Pillow"),
        "cityhash": version("cityhash"),
        "executables_sha256": {name: sha256(path) for name, path in tools.items()},
    }
    manifest_path = ROOT / MANIFEST
    previous = read_manifest() if manifest_path.is_file() else {}
    with TemporaryDirectory(prefix="shipnet-rebuild-") as temp:
        scratch = Path(temp)
        stage = scratch / "source"
        for path in sorted(set((*EXPORT_INPUTS, *NATIVE_INPUTS))):
            (stage / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, stage / path)
        export_models(stage, tools["blender"], scratch)
        export = {"inputs": fingerprints(stage, EXPORT_INPUTS), "outputs": fingerprints(stage, EXPORT_OUTPUTS)}
        inputs = fingerprints(stage, NATIVE_INPUTS)
        previous_native = previous.get("native", {})
        can_reuse = (
            not options.force_native and identity == previous.get("built_against")
            and provenance == previous.get("toolchain") and upstream == previous.get("upstream")
            and inputs == previous_native.get("inputs")
            and all((ROOT / path).is_file() for path in PACKAGES)
            and fingerprints(ROOT, PACKAGES) == previous_native.get("outputs")
        )
        if can_reuse:
            print("Native inputs and package hashes match. Reusing the Unreal package set.")
            outputs = previous_native["outputs"]
        else:
            argv = [sys.executable, stage / "tools/build_construction.py",
                    "--stage", scratch / "cook", "--output", stage / "native",
                    "--game-paks", game_paks, "--jmap", jmap]
            for name in TOOLS[1:]:
                argv.extend((f"--{name}", tools[name]))
            command(argv)
            outputs = fingerprints(stage, PACKAGES)
        if installed_build(game) != identity["steam_build_id"]:
            raise ValueError("Steam build changed during the cook. Run the build again using a fresh version report.")
        if export["inputs"] != fingerprints(ROOT, EXPORT_INPUTS):
            raise ValueError("Blender inputs changed during the export. Run the build again.")
        handwritten = set(NATIVE_INPUTS) - set(EXPORT_OUTPUTS)
        if fingerprints(ROOT, handwritten) != fingerprints(stage, handwritten):
            raise ValueError("Native inputs changed during the cook. Run the build again.")
        manifest = {
            "schema": 1, "built_against": identity, "upstream": upstream, "toolchain": provenance,
            "export": export, "native": {"inputs": inputs, "outputs": outputs},
        }
        paths = EXPORT_OUTPUTS if can_reuse else (*EXPORT_OUTPUTS, *PACKAGES)
        for path in paths:
            if not (ROOT / path).is_file() or sha256(stage / path) != sha256(ROOT / path):
                destination = ROOT / path
                candidate = destination.with_suffix(destination.suffix + ".tmp")
                shutil.copyfile(stage / path, candidate)
                candidate.replace(destination)
        candidate = manifest_path.with_suffix(".json.tmp")
        candidate.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        candidate.replace(manifest_path)
    check()
    print(f"Verified asset manifest for {identity['game_version']} (Steam {identity['steam_build_id']}).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("check", help="verify committed files without Blender or the game")
    build = sub.add_parser("rebuild", help="export Blender masters and rebuild stale packages locally")
    build.add_argument("--game-root", type=Path, required=True)
    build.add_argument("--version-report", type=Path)
    build.add_argument("--jmap", type=Path, required=True)
    build.add_argument("--force-native", action="store_true")
    for name in TOOLS:
        build.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "check":
            check()
            print("Asset hashes verified.")
        else:
            rebuild(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
