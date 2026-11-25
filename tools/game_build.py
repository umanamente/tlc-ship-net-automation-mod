"""Read the installed Steam build and validate a game version captured by UE4SS."""
import argparse
import json
from pathlib import Path
import re

APP_ID = 1783560
MOD = Path("Voyage/Binaries/Win64/ue4ss/Mods/ShipNetAutomation")
BUILD_REPORT = MOD / "Logs/game-version.json"
ROOT = Path(__file__).resolve().parents[1]


def installed_build(game_root):
    root = Path(game_root).resolve()
    manifest = root.parent.parent / f"appmanifest_{APP_ID}.acf"
    if root.parent.name.lower() != "common" or not (root / "Voyage/Content/Paks").is_dir():
        raise ValueError(f"Expected a Steam game root containing Voyage/Content/Paks: {root}")
    contents = manifest.read_text(encoding="utf-8-sig")

    def field(name):
        return match.group(1) if (match := re.search(rf'"{name}"\s+"([^"]*)"', contents)) else None

    if field("appid") != str(APP_ID) or (field("installdir") or "").lower() != root.name.lower():
        raise ValueError(f"{manifest.name} does not describe {root.name}")
    build = field("buildid")
    if not build or not build.isdecimal():
        raise ValueError(f"No numeric buildid in {manifest.name}")
    target = field("TargetBuildID")
    if target and target not in ("0", build):
        raise ValueError(f"Steam update pending: installed build {build}, target {target}")
    return build


def detected_identity(game_root, report=None):
    build = installed_build(game_root)
    report = Path(report) if report else Path(game_root) / BUILD_REPORT
    try:
        observation = json.loads(report.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Start the game with the mod enabled to generate {report}") from exc
    if (not isinstance(observation, dict)
            or (observation.get("schema"), observation.get("steam_app_id"), observation.get("steam_build_id")) != (1, APP_ID, build)):
        raise ValueError(f"{report.name} does not match installed Steam build {build}. Start the mod on that build.")
    version = observation.get("game_version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)*", version):
        raise ValueError(f"Invalid Voyage project version in {report.name}")
    project = observation.get("project_version")
    if not isinstance(project, str) or not re.fullmatch(r"\d+\.\d+\.\d+", project):
        raise ValueError(f"Invalid Voyage project version in {report.name}. Capture a fresh report.")
    if version != project and not version.startswith(project + "."):
        raise ValueError(f"Voyage release and project versions disagree in {report.name}")
    return {"steam_app_id": APP_ID, "steam_build_id": build, "game_version": version,
            "project_version": project}


def record_tested(game_root, report=None):
    from package_mod import runtime_fingerprint

    path = Path(report) if report else game_root / BUILD_REPORT
    identity = detected_identity(game_root, path)
    report_version = json.loads(path.read_text(encoding="utf-8")).get("mod_version")
    metadata = ROOT / "mod.json"
    record = json.loads(metadata.read_text(encoding="utf-8"))
    if report_version != record["version"]:
        raise ValueError(f"Run the current candidate {record['version']} before recording a gameplay check")
    fingerprint = runtime_fingerprint()
    if runtime_fingerprint(game_root) != fingerprint:
        raise ValueError("Installed Lua and Unreal files differ from the current candidate")
    if record.get("tested_payload_sha256") != fingerprint:
        record["tested_payload_sha256"] = fingerprint
        record["tested_game_builds"] = []
    if identity not in record["tested_game_builds"]:
        record["tested_game_builds"].append(identity)
        candidate = metadata.with_suffix(".json.tmp")
        candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
        candidate.replace(metadata)
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--version-report", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--build-only", action="store_true")
    mode.add_argument("--record-tested", action="store_true", help="record identity after a completed gameplay check")
    args = parser.parse_args()
    try:
        if args.build_only:
            print(installed_build(args.game_root))
        else:
            read = record_tested if args.record_tested else detected_identity
            print(json.dumps(read(args.game_root, args.version_report), indent=2))
            if args.record_tested:
                from release import refresh_draft
                refresh_draft()
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
