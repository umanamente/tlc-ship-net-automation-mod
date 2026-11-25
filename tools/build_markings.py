"""Bake the six source glyph meshes into a lit, alpha-tested BC3 atlas."""
import argparse
import base64
import copy
import functools
import hashlib
import json
import struct
import uuid
from pathlib import Path

from PIL import Image, ImageDraw

from build_catalog_icon import cook_texture
from cook_visual_asset import write_visual_asset


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "src/ShipNetAutomation/Scripts/shipnet/printed_labels.layout"
SOURCE = ROOT / "artwork/models/winch-markings.png"
SIZE = (512, 256)
TEXTURE = "T_WinchMarkings"
MATERIAL = "MI_WinchMarkings"
PARENT = "/InterchangeAssets/gltf/MaterialInstances/MI_Default_Mask"
MOD = "/Game/Mods/ShipNetAutomation/"
DONOR = "MI_Paper_PhotoJM5"
PALETTE_MATERIAL = "MI_WinchPalette"
PALETTE_COLOR = "T_WinchPaletteColor"
PALETTE_ORM = "T_WinchPaletteORM"
PALETTE_DONORS = ("T_White_srgb", "T_White_Linear")


@functools.cache
def layout():
    rows = []
    for line in LAYOUT.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            variant, name, *values = line.split("\t")
            rows.append((variant == "basic", name, *map(float, values)))
    return rows


def marking_uv(basic, position):
    x, y, z = position
    s = x if basic else y
    for use_basic, _, s0, s1, z0, z1, left, top, width, height in layout():
        if (basic == use_basic and s0 - .011 <= s <= s1 + .011
                and z0 - .011 <= z <= z1 + .011):
            return (left + width * (s-s0)/(s1-s0))/SIZE[0], (top + height * (z1-z)/(z1-z0))/SIZE[1]
    raise ValueError(f"Printed-label vertex outside the atlas layout: {position}")


def bake(source_dir):
    """Rebuild from the original scenes exported with SHIPNET_MARKINGS_DIR set."""
    masks = {}
    for basic, name in ((False, "rail_controller"), (True, "basic_controller")):
        masks[basic] = json.loads((source_dir / f"{name}.markings.json").read_text(encoding="utf-8"))
    ss = 8
    alpha = Image.new("L", (SIZE[0]*ss, SIZE[1]*ss))
    draw = ImageDraw.Draw(alpha)
    for basic, name, *_ in layout():
        for face in masks[basic].pop(name):
            xy = [marking_uv(basic, point) for point in face]
            draw.polygon([(u*SIZE[0]*ss, v*SIZE[1]*ss) for u,v in xy], fill=255)
    if any(masks.values()):
        raise ValueError("Missing passive label in the atlas layout")
    # Both materials use the same Blender linear ink color. Fill gutter RGB
    # with the ink too so bilinear filtering cannot pull in another color.
    rgb = tuple(round(255 * (1.055*c**(1/2.4)-.055)) for c in (.075, .095, .090))
    result = Image.new("RGB", SIZE, rgb)
    result.putalpha(alpha.resize(SIZE, Image.Resampling.LANCZOS))
    return result


def mip_chain(image):
    alpha = image.getchannel("A")
    coverage = sum(alpha.histogram()[128:]) / (alpha.width * alpha.height)
    width, height = image.size
    levels = []
    while width > 1 or height > 1:
        width, height = max(1, width//2), max(1, height//2)
        reduced = alpha.resize((width, height), Image.Resampling.LANCZOS)
        if min(width, height) >= 8:
            # Preserve ink coverage at the material's 0.5 alpha threshold.
            histogram = reduced.histogram()
            target = round(coverage * width * height)
            threshold = min(range(64, 193), key=lambda t: (abs(sum(histogram[t:]) - target), abs(t - 128)))
            reduced = reduced.point([min(255, round(a*128/threshold)) for a in range(256)])
        level = Image.new("RGB", (width, height), image.getpixel((0,0))[:3])
        level.putalpha(reduced)
        levels.append(level)
    return levels


def cook(template, output, uassetgui, usmap):
    with Image.open(SOURCE) as image:
        if image.mode != "RGBA" or image.size != SIZE:
            raise ValueError("Unexpected marking atlas format or size")
        cook_texture(template, output, uassetgui, usmap, TEXTURE, image, SIZE, mipmaps=mip_chain(image))


def parameter(template, index, name, value):
    entry = copy.deepcopy(template)
    entry["Name"] = str(index)
    fields = {p["Name"]: p for p in entry["Value"]}
    identity = fields["ParameterInfo"]["Value"]
    next(p for p in identity if p["Name"] == "Name")["Value"] = name
    fields["ParameterValue"].update(Value=value, IsZero=False)
    fields["ExpressionGUID"].update(Value=[], IsZero=True)
    return entry


def material_instance(template, output, uassetgui, usmap, name, parent, textures, controls):
    """Reuse the stock runtime glTF shader and its precompiled texture switches."""
    document = json.loads(template.read_text(encoding="utf-8-sig"))
    export, = document["Exports"]
    if export["ObjectName"] != DONOR:
        raise ValueError("Unexpected material-instance authoring template")
    props = {p["Name"]: p for p in export["Data"]}
    if props["Parent"]["Value"] != -2:
        raise ValueError("Unexpected material parent import")
    imports = document["Imports"]
    original_parent = imports[1]["ObjectName"]
    original_texture = imports[6]["ObjectName"]
    first_texture = next(iter(textures.values()))
    rename = {original_parent: parent.rsplit("/",1)[-1], imports[3]["ObjectName"]: parent,
              original_texture: first_texture, imports[4]["ObjectName"]: MOD+first_texture,
              DONOR: name, document["FolderName"]: MOD+name}
    for imp in imports:
        for field in ("ObjectName","PackageName"):
            imp[field] = rename.get(imp[field], imp[field])
    if parent == PARENT:
        imports[1]["ClassName"] = "MaterialInstanceConstant"
    document["NameMap"] = [rename.get(n,n) for n in document["NameMap"]]
    document["FolderName"], export["ObjectName"] = MOD+name, name
    scalar, = props["ScalarParameterValues"]["Value"]
    tex, = props["TextureParameterValues"]["Value"]
    props["ScalarParameterValues"]["Value"] = [parameter(scalar, i, name, value)
        for i,(name,value) in enumerate(controls.items())]
    overrides = [parameter(tex, 0, next(iter(textures)), -7)]
    for index, (key, texture) in enumerate(list(textures.items())[1:], start=1):
        imports.append(dict(imports[4], ObjectName=MOD+texture, PackageName=MOD+texture))
        imports.append(dict(imports[6], ObjectName=texture, PackageName=texture, OuterIndex=-len(imports)))
        overrides.append(parameter(tex, index, key, -len(imports)))
        export["CreateBeforeSerializationDependencies"].append(-len(imports))
        document["NameMap"].extend((texture, MOD+texture))
    props["TextureParameterValues"]["Value"] = overrides
    document["NameMap"].extend([*controls, *textures])
    # IoStore keeps only this prefix of NameMap when converting legacy exports.
    document["NamesReferencedFromExportDataCount"] = len(document["NameMap"])
    document["Generations"][0]["NameCount"] = len(document["NameMap"])
    export["Data"] = [props[key] for key in ("Parent","ScalarParameterValues","TextureParameterValues")]
    write_visual_asset(document, output, uassetgui, usmap)


def cook_material(template, output, uassetgui, usmap):
    material_instance(template, output, uassetgui, usmap, MATERIAL, PARENT, {"BaseColorTexture": TEXTURE},
                      {"MetallicFactor": 0.0, "RoughnessFactor": .45, "AlphaCutoff": .5})


def cook_palette_material(template, output, uassetgui, usmap):
    material_instance(template, output, uassetgui, usmap, PALETTE_MATERIAL, "/InterchangeAssets/gltf/M_Default",
                      {"BaseColorTexture": PALETTE_COLOR, "MetallicRoughnessTexture": PALETTE_ORM},
                      {"MetallicFactor": 0.0, "RoughnessFactor": 1.0})


def cook_palette(template, output, uassetgui, usmap):
    document = json.loads(template.read_text(encoding="utf-8-sig"))
    texture, = document["Exports"]
    original = texture["ObjectName"]
    if original not in PALETTE_DONORS:
        raise ValueError(f"Unexpected palette template {original}")
    linear = original == "T_White_Linear"
    name = PALETTE_ORM if linear else PALETTE_COLOR
    props = {p["Name"]: p for p in texture["Data"]}
    if bool(props.get("SRGB", {}).get("Value", True)) == linear:
        raise ValueError("Palette template has an incompatible color space")
    image = Image.new("RGBA", (16,16), (255,255,255,255))
    seen = set()
    for line in LAYOUT.with_name("pbr_palette.layout").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        r,g,b,rough,u,v = map(float, line.split("\t"))
        xy = int(u*16), int(v*16)
        if xy in seen or (u,v) != ((xy[0]+.5)/16,(xy[1]+.5)/16):
            raise ValueError("Palette UV must select a unique texel center")
        seen.add(xy)
        rgb = (255,round(255*rough),0) if linear else tuple(
            round(255*(1.055*c**(1/2.4)-.055 if c>.0031308 else 12.92*c)) for c in (r,g,b))
        image.putpixel(xy, (*rgb,255))
    data = image.tobytes("raw","BGRA")
    raw = bytearray(base64.b64decode(texture["Extras"]))
    if len(raw) != 112 or raw[60:72] != b"PF_B8G8R8A8\0" or raw[84:88] != bytes([255])*4:
        raise ValueError("Expected the stock 1x1 BGRA8 glTF texture")
    raw[84:88] = data
    struct.pack_into("<q", raw, 20, len(raw)-28)
    struct.pack_into("<II", raw, 44, *image.size)
    struct.pack_into("<II", raw, 84+len(data), *image.size)
    resource, = document["DataResources"]
    resource["SerialSize"] = resource["RawSize"] = len(data)
    props["ImportedSize"]["Value"][0]["Value"] = list(image.size)
    texture["Extras"] = base64.b64encode(raw).decode()
    guid = uuid.UUID(bytes=hashlib.sha256(data).digest()[:16])
    props["LightingGuid"]["Value"][0]["Value"] = "{" + str(guid).upper() + "}"
    names = document["NameMap"]
    names[names.index(document["FolderName"])] = MOD+name
    names[names.index(original)] = name
    document["FolderName"], texture["ObjectName"] = MOD+name, name
    write_visual_asset(document, output, uassetgui, usmap)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path, help="directory containing both *.markings.json exports")
    parser.add_argument("--output", type=Path, default=SOURCE)
    options = parser.parse_args()
    bake(options.source_dir).save(options.output)
