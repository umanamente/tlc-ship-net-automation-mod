"""Keep in-game label UVs aligned with the cooked mesh and its painted atlas."""
from pathlib import Path
import struct
import sys
import unittest

from lupa.lua54 import LuaRuntime
from PIL import Image

from test_observer import SCRIPTS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_markings as markings


def ink_vertices(path):
    data = path.read_bytes()
    offset = 18  # format header, body pivot and section count
    for slot in range(9):
        *_, size, indices = struct.unpack_from("<4fII", data, offset)
        offset += 24
        if slot == 8:
            return [tuple(c / 100 for c in vertex[:3]) for vertex in
                    struct.iter_unpack("<6h", data[offset:offset + 12 * size])]
        offset += size * 12 + indices * 2


class PrintedLabelTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts = SCRIPTS.as_posix()
        self.lua.execute("""
            package.path = scripts .. "/?.lua;" .. package.path
            labels = require("shipnet.printed_labels")
            loaded = {IsValid=function() return true end}
            function StaticFindObject() return loaded end
            function LoadAsset() return loaded end
            component = {}
            function component:CreateMeshSection_LinearColor(slot, vs, tris, ns, uv, _, _, _, colors, _, collision)
                assert(slot == 8 and not collision)
                self.uv, self.colors = uv, colors
            end
            function component:SetMaterial(slot, value) assert(slot == 8 and value == loaded) end
            function component:SetMeshSectionVisible(slot, flag) assert(slot == 8) self.visible = flag end
        """)

    def test_quads_map_to_same_texels_in_both_runtime_lods_and_native_mesh(self):
        bind = self.lua.eval("function(points,basic) return labels.apply(component,8,points,{},{},basic) end")
        for file in (SCRIPTS / "shipnet").glob("*controller*.snm"):
            with self.subTest(file=file.name):
                basic = file.name.startswith("basic")
                vertices = ink_vertices(file)
                self.assertEqual(len(vertices), 20 if basic else 4)
                points = self.lua.table_from([dict(zip("XYZ", p)) for p in vertices], recursive=True)
                ok, _ = bind(points, basic)
                self.assertTrue(ok)
                section = self.lua.globals().component
                for index, point in enumerate(vertices, 1):
                    u, v = markings.marking_uv(basic, point)
                    self.assertEqual((section.uv[index].X, section.uv[index].Y), (u, v))
                    self.assertEqual(section.colors[index].R, 1)

    def test_missing_material_hides_plain_rectangles(self):
        self.lua.execute("""
            loaded=nil
            local ok = labels.apply(component,8,{{X=76.61,Y=113.5,Z=-26.94}},{},{},true)
            assert(not ok and component.visible == false)
        """)

    def test_signed_artwork_has_gutters_and_alpha_coverage_in_mips(self):
        with Image.open(markings.SOURCE) as image:
            self.assertEqual(image.size, (512, 256))
            for _, name, _, _, _, _, left, top, width, height in markings.layout():
                with self.subTest(label=name):
                    bounds = tuple(map(int, (left, top, left + width, top + height)))
                    alpha = image.getchannel("A").crop(bounds)
                    self.assertEqual(alpha.getextrema(), (0, 255))
                    self.assertEqual(image.getpixel((bounds[0] - 4, bounds[1] - 4))[3], 0)
            levels = markings.mip_chain(image)
            self.assertEqual([mip.size for mip in levels],
                             [(max(1,512>>i), max(1,256>>i)) for i in range(1,10)])
            for mip in levels[:4]:
                fraction = sum(mip.getchannel("A").histogram()[128:]) / (mip.width * mip.height)
                self.assertAlmostEqual(fraction, .147, delta=.012)
