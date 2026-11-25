"""Check the native placement geometry and UE5.8 buffer layout without a game."""

from pathlib import Path
import json
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_construction_mesh as construction


class ConstructionMeshTest(unittest.TestCase):
    def test_cooked_case_clears_the_winch_and_supports_both_lid_surfaces(self):
        def vector(name):
            return {"Name": name, "Value": [{"Name": name, "Value": dict.fromkeys("XYZ", 0)}]}

        box = {"Value": [vector("Center"), *({"Name": axis, "Value": 1} for axis in "XYZ")]}
        body = {"Data": [{"Value": [{"Value": [box]}]}]}
        mesh = {"Data": [{"Name": "StaticMaterials", "Value": [{"Value": []}]},
                         {"Name": "ExtendedBounds", "Value": [vector("BoxExtent"), {"Name": "SphereRadius"}]}]}
        cube = {"FolderName": "/Engine/BasicShapes/Cube", "Exports": [body, {}, mesh],
                "Imports": [], "NameMap": ["WorldGridMaterial"], "Generations": []}
        with tempfile.TemporaryDirectory() as folder, patch.object(construction, "write_visual_asset") as write:
            template = Path(folder) / "cube.json"
            template.write_text(json.dumps(cube), encoding="utf-8")
            with patch("builtins.print"):
                construction.cook(template, Path(folder), None, None)
        lower, tread = write.call_args.args[0]["Exports"][0]["Data"][0]["Value"][0]["Value"]
        fields = {field["Name"]: field["Value"] for field in lower["Value"]}
        center = fields["Center"][0]["Value"]
        right = center["X"] + fields["X"] / 2
        bottom = center["Z"] - fields["Z"] / 2
        # The stock drum's third collision box reaches X=61.83, and the visual
        # shell reaches X=56.5 at the cabinet's lower edge. The rail tops at Z=-0.15.
        self.assertGreater(61.83 - right, 2)
        self.assertGreater(56.5 - right, 2)
        self.assertGreater(bottom + .15, 1)
        self.assertGreaterEqual(fields["X"] * fields["Y"] * fields["Z"], .90 * 128 * 110 * 60)
        self.assertAlmostEqual(center["X"] - fields["X"] / 2, -64)
        self.assertAlmostEqual(bottom, 4)
        self.assertAlmostEqual(right, 52)

        def bounds(box):
            values = {p["Name"]: p["Value"] for p in box["Value"]}
            pos = values["Center"][0]["Value"]
            return [(pos[k] - values[k] / 2, pos[k] + values[k] / 2) for k in "XYZ"]

        base, cap = bounds(lower), bounds(tread)
        for axis in (0, 1):
            self.assertGreaterEqual(cap[axis][0], base[axis][0])
            self.assertLessEqual(cap[axis][1], base[axis][1])
        self.assertLess(cap[2][0], base[2][1])
        points, _, _, indices = construction.geometry()
        for x, y in [(0, 0), (30, -25), (-30, 25), (-61, -47), (50, 49)]:
            surfaces = []
            for index in range(0, len(indices), 3):
                a, b, c = (points[i] for i in indices[index:index+3])
                if not (min(a[0],b[0],c[0]) <= x <= max(a[0],b[0],c[0]) and
                        min(a[1],b[1],c[1]) <= y <= max(a[1],b[1],c[1])):
                    continue
                dx1, dy1 = b[0]-a[0], b[1]-a[1]
                dx2, dy2 = c[0]-a[0], c[1]-a[1]
                area = dx1*dy2 - dy1*dx2
                if abs(area) < 1e-6:
                    continue
                u = ((x-a[0])*dy2 - (y-a[1])*dx2) / area
                v = (dx1*(y-a[1]) - dy1*(x-a[0])) / area
                if u >= 0 and v >= 0 and u+v <= 1:
                    surfaces.append(a[2] + u*(b[2]-a[2]) + v*(c[2]-a[2]))
            support = max(z[1] for xs, ys, z in (base, cap)
                          if xs[0] <= x <= xs[1] and ys[0] <= y <= ys[1])
            self.assertAlmostEqual(support, max(surfaces), places=2, msg=f"foot position ({x}, {y})")

    def test_closed_pose_continuously_matches_the_runtime_model(self):
        points, normals, colors, triangles = construction.geometry()
        self.assertEqual(len(points), 29286)
        self.assertEqual(len(triangles), 16074 * 3)
        self.assertEqual(len(normals), len(points))
        self.assertEqual(len(colors), len(points))
        self.assertLess(max(triangles), len(points))
        # Catch a mirrored inlet or a drive exported about its local pivot.
        self.assertAlmostEqual(min(x for x, _, _ in points), -68.69, places=2)
        self.assertAlmostEqual(max(x for x, _, _ in points), 125.71, places=2)

    def test_fascia_seats_the_meter_and_centers_the_button(self):
        points, _, _, _ = construction.geometry()
        # The 5.5 cm meter housing bites 0.05 cm into the vertical fascia at Y55.80.
        housing = [(x, z) for x, y, z in points if abs(y - 55.75) < .005
                   and -43 < x < 35 and 49 <= z <= 55]
        self.assertTrue(housing)
        self.assertAlmostEqual(min(z for x, z in housing), 49.25, delta=.3)
        self.assertAlmostEqual(max(z for x, z in housing), 54.75, delta=.3)
        for plane, width, height in ((57.68, 29.9, 6.8), (57.72, 23.7, 3.24)):
            button = [(x, z) for x, y, z in points if abs(y - plane) < .005
                      and -39.2 < x < 30.8 and 18.5 < z < 40.5]
            self.assertTrue(button)
            xs, zs = zip(*button)
            self.assertAlmostEqual((min(xs) + max(xs)) / 2, -4.2, places=2)
            self.assertAlmostEqual((min(zs) + max(zs)) / 2, 29.5, places=2)
            self.assertAlmostEqual(max(xs) - min(xs), width, places=2)
            self.assertAlmostEqual(max(zs) - min(zs), height, places=2)

    def test_two_native_lods_have_correct_buffers_sections_and_screen_sizes(self):
        for source, section_triangles in ((construction.SOURCE, 2), (construction.BASIC_SOURCE, 10)):
            with self.subTest(model=source.name):
                meshes = [construction.read_lod(path) for path in (source, source.with_stem(source.stem + "_lod1"))]
                payload = construction.render_payload(meshes, [(-5, 9), (-12, 18)], bytes(16))
                self.assertEqual(struct.unpack_from("<i", payload, 34)[0], 2)
                pos = 38
                self.assertLess(len(meshes[1].indices), len(meshes[0].indices) * .60)
                for mesh in meshes:
                    self.assertEqual(struct.unpack_from("<2Bi", payload, pos), (5, 0, 2))
                    pos += 6
                    for section in mesh.sections:
                        values = struct.unpack_from("<10i", payload, pos)
                        pos += 40
                        self.assertEqual(values[:5], section)
                        self.assertEqual(values[5:7], (int(section[0] == 0),) * 2)
                    slot, first, n, _, _ = mesh.sections[1]
                    self.assertEqual((slot, n), (1, section_triangles))
                    self.assertEqual(first + n * 3, len(mesh.indices))
                    pos += 56 + 16  # source bounds, deviation, cooked/inline/RT flags
                    count = len(mesh.points)
                    self.assertEqual(struct.unpack_from("<2B4I", payload, pos), (5, 12, 12, count, 12, count))
                    pos += 18
                    for i in (0, count // 2, count - 1):
                        for a, b in zip(struct.unpack_from("<3f", payload, pos + 12*i), mesh.points[i]):
                            self.assertAlmostEqual(a, b, places=4)
                    pos += 12 * count
                    self.assertEqual(struct.unpack_from("<2B6I", payload, pos), (5, 0, 1, count, 0, 0, 8, count))
                    pos += 26 + 8 * count
                    self.assertEqual(struct.unpack_from("<2I", payload, pos), (4, count))
                    pos += 8
                    for i in set(mesh.indices[first:]):
                        u, v = struct.unpack_from("<2e", payload, pos + 4*i)
                        self.assertTrue(0 <= u <= 1 and 0 <= v <= 1)
                        self.assertAlmostEqual(mesh.uv[i][0], u, delta=.0005)
                        self.assertAlmostEqual(mesh.uv[i][1], v, delta=.0005)
                    pos += 4 * count
                    self.assertEqual(struct.unpack_from("<2B4I", payload, pos), (5, 0, 4, count, 4, count))
                    pos += 18
                    self.assertEqual(struct.unpack_from("<4B", payload, pos), (*mesh.colors[0], 255))
                    pos += 4 * count
                    size = 2 * len(mesh.indices)
                    self.assertEqual(struct.unpack_from("<3I", payload, pos), (0, 1, size))
                    self.assertEqual(struct.unpack_from(f"<{len(mesh.indices)}H", payload, pos+12), tuple(mesh.indices))
                    pos += 12 + size + 4 + 16 + 36
                    self.assertEqual(struct.unpack_from("<3I", payload, pos), (28*count + size, 0, 0))
                    pos += 12
                self.assertEqual(payload[pos], 2)  # both inline
                pos += 1 + 6 + 2*(2 + 4*len(meshes)) + 56 + 1
                self.assertEqual([struct.unpack_from("<if", payload, pos + i*8) for i in range(8)],
                                 [(1, 1.0), (1, .25)] + [(1, 0)] * 6)
                pos += 64
                self.assertEqual(struct.unpack_from("<2B2i", payload, pos), (5, 0, 0, 2))
                self.assertEqual(struct.unpack_from("<2i", payload, pos + 10), (-5, 9))
                self.assertEqual(struct.unpack_from("<2i", payload, pos + 50), (-12, 18))
                self.assertEqual(len(payload), pos + 90)
