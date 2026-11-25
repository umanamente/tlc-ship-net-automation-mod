"""Apply a release plan or prepare a verified GitHub Release archive."""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from native_assets import ROOT, read_manifest, sha256
from package_mod import LUA, metadata, package, verified_builds

STABLE_TAG = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
CHANGELOG = ROOT / "CHANGELOG.md"
BUILD_START = "<!-- game-builds:start -->"
BUILD_END = "<!-- game-builds:end -->"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def format_game_build_notes(built_against, tested_builds):
    def display(identity):
        return f"`{identity['game_version']}` (BuildID `{identity['steam_build_id']}`)"

    built = display(built_against)
    tested = list(dict.fromkeys(map(display, tested_builds)))
    if tested == [built]:
        lines = [f"> **Built and tested on** ✅ {built}"]
    else:
        lines = [f"> **Built on** {built}", ">"]
        if len(tested) > 1:
            lines.extend(["> **Tested on**", ">"])
            lines.extend(f"> - ✅ {build}" for build in tested)
        elif tested:
            lines.append(f"> **Tested on** ✅ {tested[0]}")
        else:
            lines.append("> **Testing pending**")
    return "\n".join([BUILD_START, "", *lines, "", BUILD_END])


def game_build_notes(mod):
    return format_game_build_notes(read_manifest()["built_against"], verified_builds(mod))


def changelog_entry(changelog, version):
    match = re.search(
        rf"^## {re.escape(version)}(?: \([^\n]*\))?\n\n(.*?)(?=^## |\Z)",
        changelog, flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise ValueError(f"No notes in CHANGELOG.md for v{version}")
    return match


def refresh_draft():
    mod = metadata()
    tag = f"v{mod['version']}"
    tagged = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"],
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if tagged.returncode == 0:
        print(f"{tag} is already tagged. Its changelog entry stays tied to that release.")
        return
    changelog = CHANGELOG.read_text(encoding="utf-8")
    entry = changelog_entry(changelog, mod["version"])
    body = entry.group(1).rstrip()
    body = re.sub(rf"(?:\n\n)?{BUILD_START}.*?{BUILD_END}", "", body, flags=re.DOTALL).rstrip()
    body += "\n\n" + game_build_notes(mod) + "\n"
    if entry.end(1) < len(changelog):
        body += "\n"
    CHANGELOG.write_text(changelog[:entry.start(1)] + body + changelog[entry.end(1):],
                         encoding="utf-8", newline="\n")


def apply_plan(tag):
    plan = json.loads((ROOT / "dist/release-plan.json").read_text(encoding="utf-8"))
    release_version = tag[1:]
    if plan["base"] != git("rev-parse", "HEAD") or release_version != plan["version"]:
        raise ValueError("Release plan points to a different tag or commit")
    mod = metadata()
    entry = LUA / "Scripts/main.lua"
    contents = entry.read_text(encoding="utf-8")
    original = f'local version = "{mod["version"]}"'
    if contents.count(original) != 1:
        raise ValueError("Lua version and mod.json disagree")
    changelog = CHANGELOG.read_text(encoding="utf-8")
    if not changelog.startswith("# Changelog\n\n"):
        raise ValueError("Unexpected changelog heading")
    mod["version"] = release_version
    notes = re.sub(r"^#{1,3} .*\n+", "", plan["notes"].strip(), count=1)
    release_date = os.environ.get("SHIPNET_RELEASE_DATE", date.today().isoformat())
    CHANGELOG.write_text("# Changelog\n\n" + f"## {release_version} ({release_date})\n\n"
                         + notes + "\n\n" + game_build_notes(mod) + "\n\n" + changelog.removeprefix("# Changelog\n\n"),
                         encoding="utf-8", newline="\n")
    entry.write_text(contents.replace(original, f'local version = "{release_version}"'), encoding="utf-8", newline="\n")
    (ROOT / "mod.json").write_text(json.dumps(mod, indent=2) + "\n", encoding="utf-8", newline="\n")


def release_files(tag):
    if tag != f'v{metadata()["version"]}':
        raise ValueError("Tag and mod metadata differ")
    archive = package(require_tested=True)
    checksum = archive.with_suffix(".zip.sha256")
    checksum.write_text(f"{sha256(archive)}  {archive.name}\n", encoding="utf-8", newline="\n")
    changelog = CHANGELOG.read_text(encoding="utf-8")
    body = changelog_entry(changelog, tag[1:]).group(1).rstrip()
    if game_build_notes(metadata()) not in body:
        raise ValueError(f"Game build notes are missing or stale for {tag}")
    notes = ROOT / "dist/release-notes.md"
    notes.write_text(body + "\n", encoding="utf-8", newline="\n")
    return archive, checksum, notes


def publish(tag):
    archive, checksum, notes = release_files(tag)
    options = {"cwd": ROOT}
    command = ["gh", "release"]
    result = subprocess.run([*command, "view", tag, "--json", "assets"], capture_output=True, text=True, **options)
    if result.returncode != 0:
        if "release not found" not in result.stderr.lower():
            result.check_returncode()
        subprocess.run([*command, "create", tag, archive, checksum, "--verify-tag",
                        "--title", f"Ship Net Automation {tag[1:]}", "--notes-file", notes], check=True, **options)
    else:
        names = {asset["name"] for asset in json.loads(result.stdout)["assets"]}
        missing = [path for path in (archive, checksum) if path.name not in names]
        if missing:
            subprocess.run([*command, "upload", tag, *missing], check=True, **options)
    with TemporaryDirectory(prefix="shipnet-release-check-") as temp:
        for file in (archive, checksum):
            subprocess.run([*command, "download", tag, "--pattern", file.name, "--dir", temp], check=True, **options)
            if sha256(Path(temp) / file.name) != sha256(file):
                raise ValueError(f"Published asset differs from the verified local {file.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "package", "publish", "refresh-draft"))
    parser.add_argument("tag", nargs="?")
    args = parser.parse_args()
    if args.action == "refresh-draft":
        refresh_draft()
        return
    if not args.tag or not STABLE_TAG.fullmatch(args.tag):
        parser.error("expected a stable version tag, for example v0.1.0")
    actions = {"prepare": apply_plan, "package": release_files, "publish": publish}
    try:
        actions[args.action](args.tag)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
