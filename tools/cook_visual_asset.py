"""Write and reopen one cooked UE 5.8 visual package with UAssetGUI."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def write_visual_asset(document, output, uassetgui, usmap):
    name = document["FolderName"].rsplit("/", 1)[1]
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        source, asset, check = work / "source.json", work / (name + ".uasset"), work / "check.json"
        source.write_text(json.dumps(document), encoding="utf-8")
        subprocess.run([str(uassetgui), "--portable", "fromjson", str(source), str(asset),
                        str(usmap), "5.8"], check=True)
        subprocess.run([str(uassetgui), "--portable", "tojson", str(asset), str(check),
                        "5.8", str(usmap)], check=True)
        reopened = json.loads(check.read_text(encoding="utf-8-sig"))
        if reopened["FolderName"] != document["FolderName"] or reopened["Imports"] != document["Imports"]:
            raise ValueError(f"{name}: incorrect package path or import table")
        for original, parsed in zip(document["Exports"], reopened["Exports"], strict=True):
            if any(original[k] != parsed[k] for k in ("$type", "ObjectName", "ClassIndex", "OuterIndex", "Extras")):
                raise ValueError(f"{name}: native export failed to round-trip")
        output.mkdir(parents=True, exist_ok=True)
        for file in (asset, asset.with_suffix(".uexp")):
            shutil.copyfile(file, output / file.name)
