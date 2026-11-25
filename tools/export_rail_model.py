"""Export the evaluated Blender fit model for Voyage's procedural mesh component.

Run Blender in background with the approved .blend open and this script via -P.
Writes near and distant geometry in centimetres. Set SHIPNET_MARKINGS_DIR to export
the original printed contours there instead, for baking the shared ink atlas.
"""

import hashlib
import json
import os
import sys
import struct
from collections import defaultdict
from pathlib import Path

import bpy


sys.path.insert(0, str(Path(__file__).resolve().parent))
from rail_model_detail import label_quad, led_quad, radial_detail, simplified_settings

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src/ShipNetAutomation/Scripts/shipnet/rail_controller.snm"
BASIC_OUTPUT = OUTPUT.with_name("basic_controller.snm")
BASIC_ROOT = "MOUNT | Basic Winch Automator"
PIVOTS = {
    "body": "MOUNT | Rail controller",
    "hatch": "PIVOT | roof lid",
    "drive": "PIVOT | drive shaft",
    "fill": "PIVOT | cargo fill",
}


def unreal_xyz(vector, factor=1):
    return (factor * vector.x, -factor * vector.y, factor * vector.z)


def export(far=False, markings_dir=None):
    stock = bpy.data.objects
    pivot_names = PIVOTS.copy()
    basic = BASIC_ROOT in stock
    output = BASIC_OUTPUT if basic else OUTPUT
    if far:
        output = output.with_stem(output.stem + "_lod1")
    if basic:
        pivot_names = {"body": BASIC_ROOT, "drive": PIVOTS["drive"], "beacon": BASIC_ROOT}
    has_fill = not basic and pivot_names["fill"] in stock
    if has_fill:
        root = stock[pivot_names["body"]]
        root["Cargo fill fraction"] = 1.0
        root.update_tag()
        bpy.context.view_layer.update()
    elif not basic:
        del pivot_names["fill"]
    if not basic and pivot_names["hatch"] not in stock and "PIVOT | front hatch" in stock:
        pivot_names["hatch"] = "PIVOT | front hatch"  # Earlier saved revisions.
    pivots = {key: stock[name].matrix_world.translation.copy() for key, name in pivot_names.items()}
    if any(abs(stock[pivot_names["body"]].get(key, 0)) > 0.001 for key in ("Hatch opening (deg)", "Drive rotation (deg)")):
        raise ValueError("Export the model in its closed, zero-angle pose")

    kinds = {"MESH", "FONT"} if basic else {"MESH"}
    model = [o for o in stock[pivot_names["body"]].children_recursive
             if o.type in kinds and o.name in bpy.context.scene.objects]
    groups = {o.name: key for key in ("hatch", "drive", "fill") if key in pivot_names
              for o in stock[pivot_names[key]].children_recursive}
    if basic:
        # Runtime supplies the game's cable receptacle at the same datum.
        model = [o for o in model if not o.name.startswith("Power inlet |")
                 or o.name.startswith(("Power inlet | adapter", "Power inlet | fixed adapter"))]
        groups.update({o.name: "beacon" for o in model
                       if o.name.startswith(("Beacon | amber dome", "Beacon | molded"))})
    # A single bevel segment retains the real edge breaks at gameplay viewing distance.
    # These adjustments live only in this background Blender process.
    for obj in model:
        if not markings_dir and obj.type == "FONT" and obj.name == "Settings | illuminated button":
            obj.data.resolution_u = 2 if far else 4
        if not markings_dir and obj.type == "MESH":
            reduced = radial_detail(obj, far)
            if reduced is not None:
                obj.data = reduced
        # Small edge breaks retain their full shapes up close. At distance
        # their edge breaks lie below the pixel grid; keep the original cage.
        distant_flat = far and obj.name.startswith(("Motor |", "Roof hinge |", "Rotating |",
            "Drive |", "Drive mount |", "Reach arm |", "Port side |", "Lid |", "Corner |",
            "Lateral mount |", "Sleeve |", "Rear left |", "Rear right |"))
        for modifier in obj.modifiers:
            if modifier.type == "BEVEL":
                modifier.segments = 1
                if distant_flat:
                    modifier.show_viewport = False

    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    markings = {}
    sections = defaultdict(dict)
    for obj in sorted(model, key=lambda obj: obj.name):
        group = groups.get(obj.name, "body")
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh() if obj.type == "FONT" else evaluated.data
        ink = len(mesh.materials) == 1 and mesh.materials[0].name == "Markings | ink"
        if markings_dir and not ink:
            if obj.type == "FONT":
                evaluated.to_mesh_clear()
            continue
        override = None
        if not markings_dir:
            if ink:
                override = label_quad(mesh)
            elif group == "fill":
                override = led_quad(obj.data)
            elif obj.name == "Terminal | SETTINGS":
                override = simplified_settings(mesh, 0.00015 if far else 0.000035)
        if override:
            mesh = override
        mesh.calc_loop_triangles()
        transform = evaluated.matrix_world
        normal_transform = transform.to_3x3().inverted().transposed()
        for triangle in mesh.loop_triangles:
            material = mesh.materials[triangle.material_index]
            section = sections[group].setdefault(material.name, ({}, []))
            vertices, indices = section
            # Mirroring Blender Y gives UE's handedness and clockwise front faces.
            corners = []
            for loop_index in triangle.loops:
                corner = mesh.loops[loop_index]
                vertex = mesh.vertices[corner.vertex_index]
                position = transform @ vertex.co - pivots[group]
                normal_correction = 0.0
                if basic:
                    # Clear the stock drum's front collision while keeping the
                    # shared shaft on the switch axis. The support slopes back
                    # to the drive saddle and follows the panel at its lower end.
                    if any(collection.name.startswith(("01 ", "03 ")) for collection in obj.users_collection):
                        position.y -= 0.17
                    elif any(collection.name.startswith("02 ") for collection in obj.users_collection):
                        position.y -= 0.17 * max(0.0, min(1.0, (0.46 - position.z) / 0.41))
                        normal_correction = 0.17 / 0.41 if 0.05 < position.z < 0.46 else 0.0

                normal = normal_transform @ mesh.corner_normals[loop_index].vector
                normal.z -= normal.y * normal_correction
                normal.normalize()
                # 0.01 cm position precision and signed 16-bit normals. UVs are unnecessary
                # for this prototype's constant-colour materials.
                key = (*[round(v * 100) for v in unreal_xyz(position, 100)],
                       *[round(v * 32767) for v in unreal_xyz(normal)])
                corners.append(key)
            # Quantisation can collapse the shortest edges of the bevelled fasteners.
            # Unreal drops degenerate triangles when creating the section.
            if len({corner[:3] for corner in corners}) < 3:
                continue
            if markings_dir:
                markings.setdefault(obj.name, []).append([
                    [value / 100 for value in corner[:3]] for corner in corners])
            for corner in corners:
                indices.append(vertices.setdefault(corner, len(vertices)))

        if override:
            bpy.data.meshes.remove(override)
        if obj.type == "FONT":
            evaluated.to_mesh_clear()

    if markings_dir:
        destination = Path(markings_dir) / (output.stem + ".markings.json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(markings), encoding="utf-8")
        return

    blob = bytearray(b"SNRB" if basic else b"SNR2" if has_fill else b"SNR1")
    for group in pivot_names:
        blob.extend(struct.pack("<3fH", *unreal_xyz(pivots[group], 100), len(sections[group])))
        for name, (vertices, indices) in sorted(sections[group].items()):
            bsdf = bpy.data.materials[name].node_tree.nodes.get("Principled BSDF")
            color = tuple(bsdf.inputs["Base Color"].default_value)[:3]
            if group == "beacon":
                # Resting lens. The game supplies its brighter phase at runtime.
                color = tuple(c * 0.22 for c in color)
            roughness = bsdf.inputs["Roughness"].default_value
            if len(vertices) > 65535:
                raise ValueError(f"Too many vertices in section {name}")
            blob.extend(struct.pack("<4fII", *color, roughness, len(vertices), len(indices)))
            for point in vertices:
                blob.extend(struct.pack("<6h", *point))
            blob.extend(struct.pack(f"<{len(indices)}H", *indices))
    output.write_bytes(blob)
    triangles = sum(len(idx)//3 for group in sections.values() for _, idx in group.values())
    print(f"{output}: {len(model)} parts, {triangles} triangles, {len(blob):,} bytes, sha256={hashlib.sha256(blob).hexdigest()}")


def main():
    # Keep both exports independent. The scene and the original datablocks are
    # never saved; the same masters can generate LODs or the color atlas.
    directory = os.getenv("SHIPNET_MARKINGS_DIR")
    if directory:
        export(markings_dir=directory)
        return
    source = [(o, o.data) for o in bpy.context.scene.objects if o.type == "MESH"]
    export()
    for obj, mesh in source:
        obj.data = mesh
    export(far=True)


main()
