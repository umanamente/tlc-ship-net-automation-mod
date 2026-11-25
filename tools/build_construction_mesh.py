"""Compile the controller's two authored LODs into a UE 5.8 builder StaticMesh.

The template is UAssetGUI's JSON for /Engine/BasicShapes/Cube on Steam build
25982825. All vertex, index, physics and native render payloads are authored
here from the same centimetre-space model used by the working controller.
"""

import argparse
import base64
import copy
import hashlib
import json
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

from cook_visual_asset import write_visual_asset
from construction_packages import imports_for

BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE / "src/ShipNetAutomation/Scripts/shipnet/rail_controller.snm"
BASIC_SOURCE = SOURCE.with_name("basic_controller.snm")
NAME = "SM_WinchAutomator"
PACKAGE = "/Game/Mods/ShipNetAutomation/" + NAME
MATERIAL = "BasicShapeMaterial"
MARKINGS = "MI_WinchMarkings"
LOD1_SCREEN_SIZE = 0.25
# (Center, full size), in cabinet-local cm. The outer lid is at Z=66.70.
# The central tread is 0.75 cm higher. Both retain the +52 cm winch clearance.
COLLISION_BOXES = (
    ((-6.0, 0.0, 35.35), (116.0, 110.0, 62.7)),
    ((-3.125, 0.0, 65.95), (110.25, 86.0, 3.0)),
)
BASIC_COLLISION_BOXES = (
    # The rear mounts seat into the drum. Keep the physical envelope on the
    # exposed panel surface, like the Advanced cabinet's separate drive arm.
    ((132.6, 110.9, -25.5), (130.4, 5.0, 27.0)),
)


def pack(fmt, *values):
    return struct.pack("<" + fmt, *values)


@dataclass
class RenderMesh:
    points: list = field(default_factory=list)
    normals: list = field(default_factory=list)
    colors: list = field(default_factory=list)
    uv: list = field(default_factory=list)
    indices: list = field(default_factory=list)
    sections: list = field(default_factory=list)


def read_lod(source):
    from build_markings import marking_uv

    data = source.read_bytes()
    groups = {b"SNR2": ("body", "hatch", "drive", "fill"), b"SNRB": ("body", "drive", "beacon")}
    if data[:4] not in groups:
        raise ValueError("Unknown winch model format")
    cursor = 4
    mesh = RenderMesh()
    material_indices = [[], []]
    for group in groups[data[:4]]:
        x, y, z, sections = struct.unpack_from("<3fH", data, cursor)
        cursor += 14
        for slot in range(sections):
            red, green, blue, _, count, length = struct.unpack_from("<4fII", data, cursor)
            cursor += 24
            # Empty cargo is the default pose for a newly built controller.
            keep = group != "fill"
            if keep:
                first = len(mesh.points)
                printed = group == "body" and slot == 8
                vertex_color = tuple(round(255 * min(1.0, max(0.0, c))) for c in (blue, green, red))
                for px, py, pz, nx, ny, nz in struct.iter_unpack("<6h", data[cursor:cursor + 12 * count]):
                    point = (px / 100 + x, py / 100 + y, pz / 100 + z)
                    mesh.points.append(point)
                    mesh.normals.append((nx / 32767, ny / 32767, nz / 32767))
                    mesh.colors.append((255, 255, 255) if printed else vertex_color)
                    mesh.uv.append(marking_uv(data[:4] == b"SNRB", point) if printed else
                                   (point[0] / 128, (point[1] + point[2]) / 128))
            cursor += 12 * count
            if keep:
                section_indices = struct.unpack_from(f"<{length}H", data, cursor)
                if length % 3 or (length and max(section_indices) >= count):
                    raise ValueError(f"Invalid {source.name} {group} section {slot}")
                material_indices[int(printed)].extend(first + i for i in section_indices)
            cursor += 2 * length
    if cursor != len(data) or len(mesh.points) > 65535:
        raise ValueError("Invalid controller geometry")
    for material, indices in enumerate(material_indices):
        if indices:
            mesh.sections.append((material, len(mesh.indices), len(indices) // 3, min(indices), max(indices)))
            mesh.indices.extend(indices)
    return mesh


def geometry(source=SOURCE):
    """Closed LOD0 geometry used to bake the fallback display."""
    mesh = read_lod(source)
    return mesh.points, mesh.normals, mesh.colors, mesh.indices


def bounds(points):
    axes = list(zip(*points))
    extent = [(max(axis) - min(axis)) / 2 for axis in axes]
    origin = [min(axis) + size for axis, size in zip(axes, extent)]
    radius = max(math.dist(point, origin) for point in points)
    return origin, extent, radius


def tangent_basis(normal):
    nx, ny, nz = normal
    # Pick a stable perpendicular tangent even on horizontal surfaces.
    tangent = (-ny, nx, 0) if abs(nz) < 0.9 else (nz, 0, -nx)
    mag = math.hypot(*tangent)
    encode = lambda value: round(max(-1, min(1, value)) * 127)
    return pack("8b", *(encode(v / mag) for v in tangent), 0, *(encode(v) for v in normal), 127)


def inline_buffers(mesh):
    size = len(mesh.points)
    buf = bytearray(pack("2B4I", 5, 12, 12, size, 12, size))  # CPU positions, no reversed/RT buffers
    for point in mesh.points:
        buf.extend(pack("3f", *point))
    buf.extend(pack("2B6I", 5, 0, 1, size, 0, 0, 8, size))
    for normal in mesh.normals:
        buf.extend(tangent_basis(normal))
    buf.extend(pack("2I", 4, size))
    for uv in mesh.uv:
        buf.extend(pack("2e", *uv))
    buf.extend(pack("2B4I", 5, 0, 4, size, 4, size))
    for color in mesh.colors:
        buf.extend(pack("4B", *color, 255))
    index_data = pack(f"{len(mesh.indices)}H", *mesh.indices)
    buf.extend(pack("3I", 0, 1, len(index_data)) + index_data + pack("I", 0))
    buf.extend(pack("4I", 0, 1, 0, 0))  # empty depth index buffer
    buf.extend(bytes(12 * (len(mesh.sections) + 1)))  # area samplers for each section and whole mesh
    return buf


def render_payload(lods, materials, guid):
    origin, extent, radius = bounds(lods[0].points)
    box = pack("7d", *origin, *extent, radius)
    result = bytearray(pack("2B3i", 5, 0, 1, 1, 0) + guid + pack("2i", 0, len(lods)))
    for mesh in lods:
        result.extend(pack("2Bi", 5, 0, len(mesh.sections)))
        for section in mesh.sections:
            solid = int(section[0] == 0)
            result.extend(pack("10i", *section, solid, solid, 0, 0, 0))
        result.extend(box + pack("f3i", 0, 0, 1, 0))
        result.extend(inline_buffers(mesh))
        resident_bytes = 28 * len(mesh.points) + 2 * len(mesh.indices)
        result.extend(pack("3I", resident_bytes, 0, 0))
    result.extend(pack("B2Bi", len(lods), 7, 0, 0))  # inline LOD count, stripped Nanite, no RT proxy
    for _ in range(2):  # absent mesh cards and distance fields, each with one flag per LOD
        result.extend(pack("2B", 5, 0) + bytes(4 * len(lods)))
    result.extend(box + pack("B", 1))
    for screen_size in (1.0, LOD1_SCREEN_SIZE, 0, 0, 0, 0, 0, 0):
        result.extend(pack("if", 1, screen_size))
    result.extend(pack("2B2i", 5, 0, 0, len(materials)))
    for index, slot_name in materials:
        result.extend(pack("5i4fi", index, slot_name, 0, 1, 0, 128, 0, 0, 0, 0))
    return result


def vector_property(example, name, values):
    prop = copy.deepcopy(example)
    prop["Name"] = prop["Value"][0]["Name"] = name
    prop["Value"][0]["Value"].update(zip(("X", "Y", "Z"), values))
    return prop


def cook(template, output, uassetgui, usmap, *, basic=False):
    source = BASIC_SOURCE if basic else SOURCE
    name = NAME + "Basic" if basic else NAME
    package = PACKAGE + "Basic" if basic else PACKAGE
    collision = BASIC_COLLISION_BOXES if basic else COLLISION_BOXES
    a = json.loads(template.read_text(encoding="utf-8-sig"))
    if a["FolderName"] != "/Engine/BasicShapes/Cube":
        raise ValueError("Expected the 25982825 Engine cube package layout")
    body, _, mesh = a["Exports"]
    far_source = source.with_stem(source.stem + "_lod1")
    lods = [read_lod(path) for path in (source, far_source)]
    origin, extent, radius = bounds(lods[0].points)
    shape_data = b"".join(pack("6d", *center, *size) for center, size in collision)
    guid = hashlib.sha256(source.read_bytes() + far_source.read_bytes() + shape_data).digest()[:16]
    names = {"WorldGridMaterial": MATERIAL, "/Engine/EngineMaterials/WorldGridMaterial":
             "/Engine/BasicShapes/" + MATERIAL, "Cube": name, "/Engine/BasicShapes/Cube": package}
    a["NameMap"] = [names.get(n, n) for n in a["NameMap"]]
    for entry in a["Imports"]:
        for field in ("ObjectName", "PackageName"):
            entry[field] = names.get(entry[field], entry[field])
    ink_import = imports_for(a)("/Game/Mods/ShipNetAutomation/" + MARKINGS, MARKINGS,
                                "/Script/Engine", "MaterialInstanceConstant")
    for entry in a["Imports"]:
        for field in ("ObjectName", "ClassName", "ClassPackage", "PackageName"):
            if entry[field] not in a["NameMap"]:
                a["NameMap"].append(entry[field])

    properties = {p["Name"]: p for p in mesh["Data"]}
    box = properties["ExtendedBounds"]["Value"]
    ref_vector = next(p for p in box if p["Name"] == "BoxExtent")
    sphere = next(p for p in box if p["Name"] == "SphereRadius")
    sphere["Value"] = radius
    properties["ExtendedBounds"]["Value"] = [
        vector_property(ref_vector, "Origin", origin), vector_property(ref_vector, "BoxExtent", extent), sphere]
    slots = properties["StaticMaterials"]["Value"]
    slots.append(copy.deepcopy(slots[0]))
    materials = []
    for i, (material, import_index) in enumerate(((MATERIAL, -5), (MARKINGS, ink_import))):
        slots[i]["Name"] = str(i)
        for field in slots[i]["Value"]:
            if field["Name"] in ("MaterialSlotName", "ImportedMaterialSlotName"):
                field["Value"] = material
            if field["Name"] == "MaterialInterface":
                field["Value"] = import_index
            if field["Name"] == "UVChannelData":
                for v in field["Value"]:
                    if v["Name"] == "LocalUVDensities":
                        v["Value"] = 128.0 if v["ArrayIndex"] == 0 else 0.0
        materials.append((import_index, a["NameMap"].index(material)))
    mesh["Data"] = [properties["StaticMaterials"], properties["ExtendedBounds"]]
    mesh["ObjectName"] = name
    mesh["CreateBeforeSerializationDependencies"] = [-5, ink_import, 1]
    mesh["Extras"] = base64.b64encode(render_payload(lods, materials, guid)).decode()
    body["CreateBeforeCreateDependencies"], body["OuterIndex"] = [2], 2
    boxes = body["Data"][0]["Value"][0]["Value"]
    template_box, = boxes
    boxes.clear()
    for index, (center, size) in enumerate(collision):
        hull = copy.deepcopy(template_box)
        hull["Name"] = str(index)
        fields = {p["Name"]: p for p in hull["Value"]}
        fields["Center"] = vector_property(ref_vector, "Center", center)
        for dimension, length in zip(("X", "Y", "Z"), size):
            fields[dimension]["Value"] = length
        hull["Value"] = list(fields.values())
        boxes.append(hull)
    body["Extras"] = base64.b64encode(guid + pack("3i", 1, 0, 0)).decode()  # analytic boxes, no triangle soup
    a.update(FolderName=package, Exports=[body, mesh], DataResources=[], DependsMap=[[], []])
    for generation in a["Generations"]:
        generation["ExportCount"] = 2
        generation["NameCount"] = len(a["NameMap"])
    a["NamesReferencedFromExportDataCount"] = len(a["NameMap"])

    write_visual_asset(a, output, uassetgui, usmap)
    print(f"{name}: " + ", ".join(f"LOD{i} {len(lod.indices) // 3} triangles"
                                   for i, lod in enumerate(lods)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("template", "output", "uassetgui", "usmap"):
        parser.add_argument("--" + option, type=Path, required=True)
    cook(**vars(parser.parse_args()))
