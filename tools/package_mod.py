"""Create the installable ZIP from the Lua mod and the verified Voyage content."""
import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from native_assets import DESCRIPTOR, PACKAGES, ROOT, check, read_manifest

LUA = ROOT / "src/ShipNetAutomation"
MOD = Path("Voyage/Binaries/Win64/ue4ss/Mods/ShipNetAutomation")
ENTRY = MOD / "Scripts/main.lua"
VORTEX_OVERRIDE = "vortex_override_instructions.json"


def metadata():
    return json.loads((ROOT / "mod.json").read_text(encoding="utf-8"))


def version_from_lua():
    entry = (LUA / "Scripts/main.lua").read_text(encoding="utf-8")
    return re.search(r'^local version = "([0-9a-z.-]+)"$', entry, re.MULTILINE).group(1)


def runtime_files():
    files = {MOD / "enabled.txt": LUA / "enabled.txt"}
    for path in (LUA / "Scripts").rglob("*"):
        if path.is_file() and path.suffix in (".lua", ".snm", ".layout"):
            files[MOD / path.relative_to(LUA)] = path
    for path in (*PACKAGES, DESCRIPTOR):
        files[path.relative_to("native")] = ROOT / path
    return files


def runtime_fingerprint(installed_at=None):
    digest = hashlib.sha256()
    for destination, source in sorted(runtime_files().items()):
        data = (installed_at / destination if installed_at is not None else source).read_bytes()
        if destination == ENTRY:
            data = re.sub(rb'^local version = "[0-9a-z.-]+"$', b'local version = ""', data, flags=re.MULTILINE)
        digest.update(destination.as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def verified_builds(mod):
    if mod.get("tested_payload_sha256") == runtime_fingerprint():
        return mod["tested_game_builds"]
    return []


def vortex_override(members):
    # The ModKit installer flattens the UE4SS Mods directory into Voyage/Mods.
    # Vortex matches override sources against Windows-normalized archive paths.
    instructions = [{"type": "setmodtype", "value": "thelastcaretaker-root"}]
    for member in sorted(members):
        path = str(PureWindowsPath(member))
        instructions.append({"type": "copy", "source": path, "destination": path})
    return (json.dumps(instructions, indent=2) + "\n").encode("utf-8")


def package(require_tested=False):
    check()
    mod = metadata()
    version = version_from_lua()
    if version != mod["version"]:
        raise ValueError("mod.json and main.lua describe different mod versions")
    built_against = read_manifest()["built_against"]
    tested = verified_builds(mod)
    if require_tested and not tested:
        raise ValueError("Record an in-game compatibility check before releasing this runtime payload")
    files = runtime_files()
    files[MOD / "Logs/.gitkeep"] = LUA / "Logs/.gitkeep"
    files[MOD / "LICENSE"] = ROOT / "LICENSE"
    files[MOD / "installation.md"] = ROOT / "docs/gamers/installation.md"
    payloads = {path.as_posix(): source.read_bytes() for path, source in files.items()}
    payloads[(MOD / "BUILDINFO.json").as_posix()] = (
        json.dumps({"mod_version": version, "built_against": built_against, "tested_game_builds": tested},
                   indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    payloads[VORTEX_OVERRIDE] = vortex_override(payloads)
    archive = ROOT / "dist" / f"ShipNetAutomation-{version}.zip"
    archive.parent.mkdir(exist_ok=True)
    with NamedTemporaryFile(dir=archive.parent, prefix="shipnet-", suffix=".zip", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        with ZipFile(path, "w") as zipfile:
            for name, data in sorted(payloads.items()):
                member = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                member.create_system = 3
                member.external_attr = 0o100644 << 16
                zipfile.writestr(member, data, compress_type=ZIP_DEFLATED, compresslevel=7)
        with ZipFile(path) as zipfile:
            for name, data in payloads.items():
                if zipfile.read(name) != data:
                    raise ValueError(f"Archive mismatch for {name}")
        path.replace(archive)
    finally:
        path.unlink(missing_ok=True)
    print(f"{archive} ({len(payloads)} verified files)")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-tested", action="store_true", help="require recorded in-game release validation")
    args = parser.parse_args()
    try:
        package(args.require_tested)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
