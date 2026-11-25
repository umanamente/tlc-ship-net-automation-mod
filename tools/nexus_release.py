"""Send the verified GitHub release to the configured Nexus file."""
import argparse
import json
import os
import re
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from native_assets import ROOT, sha256
from release import CHANGELOG, STABLE_TAG, changelog_entry

DIST = ROOT / "dist"


def output(name, value):
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as file:
        print(f"{name}={value}", file=file)


def positive_id(name):
    value = os.environ.get(name, "").strip()
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise ValueError(f"Set {name} to the Nexus API identifier")
    return value


def request(path, version, payload=None):
    key = os.environ.get("NEXUSMODS_API_KEY", "").strip()
    if not key:
        raise ValueError("Missing secret NEXUSMODS_API_KEY in the nexus environment")
    headers = {"apikey": key, "Accept": "application/json", "Application-Name": "Ship Net Automation Release",
               "Application-Version": version}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    with urlopen(Request("https://api.nexusmods.com/v3" + path, headers=headers, data=data), timeout=30) as reply:
        return json.load(reply)


def main_version(records, version, preview_id=None):
    if not records:
        raise ValueError("Nexus returned no versions for the configured file")
    target = tuple(map(int, version.split(".")))
    existing = []
    for item in records:
        if item["category"] != "main":
            continue
        current = STABLE_TAG.fullmatch(f"v{item['version']}")
        if current and tuple(map(int, current.groups())) > target:
            raise ValueError("A newer Nexus main file is already present")
        if item["version"] != version or (preview_id and str(item["game_scoped_id"]) == preview_id):
            continue
        existing.append(item)
    if len(existing) > 1:
        raise ValueError(f"There is more than one Nexus main file for {version}")
    return existing[0] if existing else None


def notes_lines(changelog, version):
    notes = changelog_entry(changelog, version).group(1)
    lines = []
    for line in notes.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "<!--")):
            continue
        line = re.sub(r"^[-*+] ", "", line)
        line = re.sub(r"\s*\(\[[0-9a-f]{7,40}\]\(https://github\.com/[^\s)]+/commit/[0-9a-f]+\)\)$", "", line)
        line = re.sub(r"\[([^]]+)\]\(https://github\.com/[^\s)]+\)", r"\1", line)
        lines.append(line.replace("`", "").replace("**", ""))
    return list(dict.fromkeys(lines))


def existing_notes(path, version):
    page = 1
    count = 0
    while True:
        response = request(f"{path}?page={page}&page_size=100", version)
        records = response["data"]
        for record in records:
            if record["version"] == version:
                return {line.strip() for entry in record["entries"] for line in entry.splitlines() if line.strip()}
        count += len(records)
        total = response["meta"]["total_count"]
        if count == total:
            return set()
        if not records or count > total:
            raise ValueError("Nexus returned incomplete changelog pagination")
        page += 1


def sync_notes(mod_id, version, *, before_upload):
    path = f"/mods/{mod_id}/changelogs"
    expected = notes_lines(CHANGELOG.read_text(encoding="utf-8"), version)
    present = existing_notes(path, version)
    missing = [line for line in expected if line not in present]
    if not missing:
        return
    try:
        request(path, version, {"version": version, "changelog": "\n".join(missing)})
    except HTTPError as exc:
        if exc.code == 422 and before_upload:
            print("Nexus requires the new file before its changelog. Will retry after upload.")
            return
        if exc.code < 500:
            raise
        print("Nexus returned an uncertain changelog response. Checking the saved entry.")
    except OSError:
        print("Nexus returned an uncertain changelog response. Checking the saved entry.")
    for delay in (0, 2, 5, 10):
        time.sleep(delay)
        if set(expected) <= existing_notes(path, version):
            return
    raise ValueError("Nexus did not confirm the changelog after one append")


def github_archive(tag):
    name = f"ShipNetAutomation-{tag[1:]}.zip"
    DIST.mkdir(exist_ok=True)
    subprocess.run(["gh", "release", "download", tag, "--pattern", name, "--pattern", name + ".sha256",
                    "--dir", DIST, "--clobber"], cwd=ROOT, check=True)
    archive = DIST / name
    expected = (DIST / (name + ".sha256")).read_text(encoding="utf-8").split()
    digest = sha256(archive)
    if expected != [digest, name]:
        raise ValueError("GitHub release ZIP differs from its checksum")
    return archive, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "verify"))
    parser.add_argument("tag")
    args = parser.parse_args()
    if not STABLE_TAG.fullmatch(args.tag):
        parser.error("expected a stable vMAJOR.MINOR.PATCH tag")
    version = args.tag[1:]
    try:
        mod_id, file_id = map(positive_id, ("NEXUSMODS_MOD_ID", "NEXUSMODS_FILE_ID"))
        files = request(f"/mods/{mod_id}/files", version)["data"]["mod_files"]
        if not any(str(file["id"]) == file_id for file in files):
            raise ValueError("The configured Nexus file is not part of the configured mod")
        records = request(f"/mod-files/{file_id}/versions", version)["data"]["versions"]
        preview = os.environ.get("NEXUSMODS_BOOTSTRAP_PREVIEW_ID") if version == "0.1.0" else None
        existing = main_version(records, version, preview)
        if args.phase == "prepare":
            archive, digest = github_archive(args.tag)
            sync_notes(mod_id, version, before_upload=existing is None)
            output("upload", str(existing is None).lower())
            output("archive", archive.relative_to(ROOT).as_posix())
            output("digest", digest)
            output("version", version)
        else:
            uploaded_id = os.environ.get("NEXUS_UPLOADED_VERSION_ID", "").strip()
            if existing is None or (uploaded_id and str(existing["id"]) != uploaded_id):
                raise ValueError(f"Nexus has not confirmed the uploaded main file for {version}")
            if preview and any(str(item["game_scoped_id"]) == preview and item["category"] == "main" for item in records):
                raise ValueError("The original preview is still listed as a main file")
            sync_notes(mod_id, version, before_upload=False)
            print(f"Verified Nexus main file {existing['game_scoped_id']} for {version} and its changelog.")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
