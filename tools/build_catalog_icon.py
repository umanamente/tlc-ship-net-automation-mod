"""Cook the cabinet's catalogue icon and other inline BC3 textures for Voyage.

Supply the UAssetGUI JSON of /Game/AssetSets/Modules/Heater/Icons/Icon_Heater_Small
from build 25982825. Only the Texture2D serialization layout is retained.
"""

import argparse
import base64
import copy
import hashlib
import io
import json
import struct
import uuid
from pathlib import Path

from PIL import Image
from cook_visual_asset import write_visual_asset


NAME = "T_WinchAutomator"
SOURCE = Path(__file__).resolve().parents[1] / "artwork/catalog/winch-automator.png"


def cook_texture(template, output, uassetgui, usmap, name, image, imported_size, *, mipmaps=()):
    document = json.loads(template.read_text(encoding="utf-8-sig"))
    texture, = document["Exports"]
    if texture["ObjectName"] != "Icon_Heater_Small":
        raise ValueError("Expected the stock 25982825 small heater UI texture layout")
    resource, = document["DataResources"]
    extras = bytearray(base64.b64decode(texture["Extras"]))
    prefix, pixels, suffix = 80, 65536, 24
    if (resource["SerialSize"] != pixels or len(extras) != prefix + pixels + suffix
            or extras[60:68] != b"PF_DXT5\0" or struct.unpack_from("<II", extras, 44) != (256, 256)):
        raise ValueError("Unexpected single-mip 256 px DXT5 serialization")

    width, height = image.size
    if width % 4 or height % 4:
        raise ValueError("BC3 texture dimensions must be multiples of four")
    skip, = struct.unpack_from("<q", extras, 20)
    if skip != 76 + pixels or struct.unpack_from("<III", extras, prefix + pixels) != (256, 256, 1):
        raise ValueError("Unexpected inline platform data or mip layout")
    trailer = extras[-12:]
    platform = extras[:76]
    levels = [image, *mipmaps]
    struct.pack_into("<II", platform, 44, width, height)
    struct.pack_into("<I", platform, 72, len(levels))
    resources = document["DataResources"] = []
    content_id = hashlib.sha256()
    for level, mip in enumerate(levels):
        w, h = mip.size
        if (w, h) != (max(1, width >> level), max(1, height >> level)):
            raise ValueError("Invalid mip dimensions")
        stream = io.BytesIO()
        mip.convert("RGBA").save(stream, format="DDS", pixel_format="DXT5")
        dds = stream.getvalue()
        size = ((w + 3) // 4) * ((h + 3) // 4) * 16
        if len(dds) != 128 + size or dds[84:88] != b"DXT5":
            raise ValueError("Invalid BC3-encoded image")
        content_id.update(dds)
        platform += struct.pack("<I", level)
        entry = copy.copy(resource)
        entry.update(SerialOffset=resource["SerialOffset"] + len(platform) - prefix,
                     SerialSize=size, RawSize=size)
        resources.append(entry)
        platform += dds[128:] + struct.pack("<III", w, h, 1)
    platform += trailer
    struct.pack_into("<q", platform, 20, len(platform) - 28)
    texture["Extras"] = base64.b64encode(platform).decode()
    properties = {entry["Name"]: entry for entry in texture["Data"]}
    properties["ImportedSize"]["Value"][0]["Value"] = list(imported_size)
    if mipmaps:
        properties["LODGroup"]["Value"] = "TEXTUREGROUP_World"
    lighting_id = uuid.UUID(bytes=content_id.digest()[:16])
    properties["LightingGuid"]["Value"][0]["Value"] = "{" + str(lighting_id).upper() + "}"
    names = document["NameMap"]
    package = "/Game/Mods/ShipNetAutomation/" + name
    names[names.index(document["FolderName"])] = package
    names[names.index(texture["ObjectName"])] = name
    document["FolderName"], texture["ObjectName"] = package, name

    write_visual_asset(document, output, uassetgui, usmap)


def cook(template, output, uassetgui, usmap, *, basic=False):
    source = SOURCE.with_name("winch-automator-basic.png") if basic else SOURCE
    name = NAME + "Basic" if basic else NAME
    with Image.open(source) as image:
        icon = image.convert("RGBA").resize((256, 256), Image.Resampling.LANCZOS)
        cook_texture(template, output, uassetgui, usmap, name, icon, image.size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("template", "output", "uassetgui", "usmap"):
        parser.add_argument("--" + option, type=Path, required=True)
    cook(**vars(parser.parse_args()))
