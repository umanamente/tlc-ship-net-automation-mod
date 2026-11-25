"""Render the item catalogue icon from the approved Blender controller model."""

from pathlib import Path

import bpy
from mathutils import Vector


def render():
    scene = bpy.context.scene
    root = bpy.data.objects["MOUNT | Rail controller"]
    camera = scene.camera
    bpy.data.objects["Studio | shadow floor"].hide_render = True
    root["Hatch opening (deg)"] = 0
    root["Cargo fill fraction"] = 0.65
    root.update_tag()
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    axes = camera.matrix_world.to_quaternion().inverted()
    points = []
    for obj in root.children_recursive:
        if obj.type not in {"MESH", "FONT"} or obj.hide_render:
            continue
        evaluated = obj.evaluated_get(graph)
        for corner in evaluated.bound_box:
            points.append(axes @ (evaluated.matrix_world @ Vector(corner) - camera.location))
    left, right = min(p.x for p in points), max(p.x for p in points)
    bottom, top = min(p.y for p in points), max(p.y for p in points)
    camera.location += axes.inverted() @ Vector(((left + right) / 2, (top + bottom) / 2, 0))
    camera.data.ortho_scale = 1.12 * max(right - left, top - bottom)
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.cycles.samples = 32
    output = Path(__file__).resolve().parents[1] / "artwork/catalog/winch-automator.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)


render()
