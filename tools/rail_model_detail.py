"""Runtime detail levels derived from the high-detail Blender masters."""

import bpy
from mathutils import geometry


def compact_mesh(source, name, coordinates, faces, originals):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(coordinates, [], faces)
    for material in source.materials:
        mesh.materials.append(material)
    for face, original in zip(mesh.polygons, originals, strict=True):
        face.material_index = original.material_index
        face.use_smooth = original.use_smooth
    mesh.update()
    return mesh


def reduced_rings(obj, sectors, stride, paired):
    # Blender cylinders interleave their two caps. The bespoke lathed parts
    # store one entire ring at each cross-section of the shaft, screw or lens.
    source = obj.data
    count = len(source.vertices)
    if count % sectors or sectors % stride:
        raise ValueError(f"Unexpected radial topology on {obj.name}")
    rows = count // sectors

    def at(row, sector):
        return sector * rows + row if paired else row * sectors + sector

    coordinates, remap = [], {}
    for row in range(rows):
        for sector in range(0, sectors, stride):
            idx = len(coordinates)
            coordinates.append(source.vertices[at(row, sector)].co.copy())
            for offset in range(stride):
                remap[at(row, sector + offset)] = idx
    faces, originals = [], []
    for face in source.polygons:
        indices = list(dict.fromkeys(remap[i] for i in face.vertices))
        if len(indices) >= 3:
            faces.append(indices)
            originals.append(face)
    return compact_mesh(source, obj.name + " radial LOD", coordinates, faces, originals)


def socket_cap(obj):
    mesh = obj.data
    # A closed hexagonal impression has six walls and two caps. Some Basic
    # screws are flat annuli with a real hole; preserve those intact.
    if len(mesh.vertices) != 12 or len(mesh.polygons) != 8:
        return None
    caps = [face for face in mesh.polygons if len(face.vertices) == 6]
    head = bpy.data.objects.get(obj.name.replace(" | socket", ""))
    if len(caps) != 2 or head is None:
        return None
    outward = (obj.matrix_world.translation - head.matrix_world.translation).normalized()
    normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
    front = [face for face in caps if (normal_matrix @ face.normal).normalized().dot(outward) > .999]
    if len(front) != 1:
        return None
    face = front[0]
    corners = [mesh.vertices[i].co.copy() for i in face.vertices]
    return compact_mesh(mesh, "Socket impression cap", corners, [tuple(range(6))], [face])


def radial_detail(obj, far):
    mesh = obj.data
    name = obj.name
    size = len(mesh.vertices)
    if far and name.rpartition(" | ")[2].partition(".")[0] == "socket":
        return socket_cap(obj)
    # These two rings of vertices and two cap ngons identify an unmodified
    # Blender cylinder; other machined parts can contain openings and flanges.
    if size in (40, 96):
        sectors = size // 2
        caps = [p for p in mesh.polygons if len(p.vertices) == sectors]
        if len(caps) == 2 and len(mesh.polygons) == sectors + 2:
            if sectors == 48 and name.startswith("Roof hinge |"):
                stride = 6 if far else 3
            else:
                stride = 4 if far else 2
            return reduced_rings(obj, sectors, stride, True)
    if name == "Rotating | bored coupling":
        return reduced_rings(obj, 48, 4 if far else 2, False)
    if name in ("Beacon | black weather gasket", "Beacon | flanged retaining ring",
                "Beacon | amber dome"):
        return reduced_rings(obj, 64, 2, False)
    if size == 96 and name.startswith(("Panel | captive fastener", "Settings | corner screw",
            "Power inlet | adapter screw", "Sleeve | raceway fastener")):
        return reduced_rings(obj, 24, 4 if far else 2, False)
    return None


def label_quad(mesh):
    # All six printed legends lie in their local XY plane, front normal +Z.
    xs, ys, zs = zip(*(v.co for v in mesh.vertices))
    if max(zs) - min(zs) > 1e-5:
        raise ValueError("Ink atlas expects a planar label")
    x0, x1, y0, y1, z = min(xs), max(xs), min(ys), max(ys), zs[0]
    return compact_mesh(mesh, "Ink label", [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)],
                        [(0, 1, 2, 3)], [mesh.polygons[0]])


def led_quad(mesh):
    # Reuse the exact outward face of each cell, preserving its spacing and
    # the animated fill-group pivot at both levels.
    face = min(mesh.polygons, key=lambda p: p.normal.y)
    return compact_mesh(mesh, "LED face", [mesh.vertices[i].co.copy() for i in face.vertices],
                        [(0, 1, 2, 3)], [face])


def simplify_outline(points, tolerance):
    """Keep endpoints and bound the error of each approximated contour span."""
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    chord = b - a
    length_squared = chord.length_squared

    def distance(point):
        t = max(0., min(1., (point - a).dot(chord) / length_squared)) if length_squared else 0.
        return (point - a - t * chord).length_squared

    split = max(range(1, len(points) - 1), key=lambda i: distance(points[i]))
    if distance(points[split]) <= tolerance * tolerance:
        return [a, b]
    return simplify_outline(points[:split + 1], tolerance)[:-1] + simplify_outline(points[split:], tolerance)


def simplified_settings(mesh, tolerance):
    # This label was converted to triangles in the master. Preserve its
    # original glyphs, holes and extrema; simplify only their planar outlines.
    edges = {}
    for face in mesh.polygons:
        for a, b in zip(face.vertices, (*face.vertices[1:], face.vertices[0])):
            if (b, a) in edges:
                del edges[b, a]
            else:
                edges[a, b] = True
    following = {a: b for a, b in edges}
    if len(following) != len(edges):
        raise ValueError("SETTINGS outlines must be manifold")
    vertices, lines = [], []
    while following:
        i = start = next(iter(following))
        contour = []
        while True:
            contour.append(mesh.vertices[i].co.to_2d())
            i = following.pop(i)
            if i == start:
                break
        anchors = sorted({func(range(len(contour)), key=lambda j: contour[j][axis])
                          for func in (min, max) for axis in (0, 1)})
        reduced = []
        for lo, hi in zip(anchors, anchors[1:] + [anchors[0] + len(contour)]):
            span = [contour[j % len(contour)] for j in range(lo, hi + 1)]
            reduced.extend(simplify_outline(span, tolerance)[:-1])
        start = len(vertices)
        vertices.extend(reduced)
        lines.extend((start + i, start + (i + 1) % len(reduced)) for i in range(len(reduced)))
    # Constraints split triangles at every contour. The even/odd rule excludes
    # both the exterior and any enclosed glyph counters.
    xy, _, triangles, *_ = geometry.delaunay_2d_cdt(vertices, lines, [], 0, 1.e-8, False)

    def inside(p):
        crossings = 0
        for i, j in lines:
            a, b = vertices[i], vertices[j]
            if (a.y > p.y) != (b.y > p.y):
                x = a.x + (p.y - a.y) * (b.x - a.x) / (b.y - a.y)
                crossings += x > p.x
        return crossings % 2

    faces = [t for t in triangles if inside((xy[t[0]] + xy[t[1]] + xy[t[2]]) / 3)]
    if not faces:
        raise ValueError("Failed to triangulate SETTINGS label")
    return compact_mesh(mesh, "SETTINGS glyphs", [(v.x, v.y, 0.0) for v in xy], faces,
                        [mesh.polygons[0]] * len(faces))
