"""Check the stock fishing CRT's UV orientation, asset binding and error cleanup."""
import unittest

from lupa.lua54 import LuaRuntime

from test_observer import SCRIPTS


class DisplayTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts = SCRIPTS.as_posix()
        self.lua.execute("""
            package.path = scripts .. "/?.lua;" .. package.path
            display = require("shipnet.display")
            glass = {minX=-39.2, maxX=30.8, minZ=18.5, maxZ=40.5, Y=57.6}
            EFindName = {FNAME_Find=0, FNAME_Add=1}
            function FName(name) return name end
            function asset(id)
                return {IsValid=function() return true end, GetAddress=function() return id end}
            end
            texture, crt, mid = asset(1), asset(2), asset(3)
            function StaticFindObject(path)
                if path == "/Game/UI/Terminal/Materials/M_Terminal_Retainer_Widget_ForcePower.M_Terminal_Retainer_Widget_ForcePower" then return crt end
            end
            function LoadAsset(path)
                assert(path == "/Game/Mods/ShipNetAutomation/T_WinchControlScreen.T_WinchControlScreen")
                return texture
            end
            body = {GetNumSections=function() return 13 end}
            function body:CreateMeshSection_LinearColor(s, vs, ix, ns, uv, _, _, _, _, _, collision)
                assert(s == 13 and not collision and #vs == 4 and #ix == 6)
                for i,v in ipairs(vs) do
                    assert(v.Y > 57.66 and ns[i].Y == 1)
                    assert(uv[i].X == (v.X == glass.minX and 0 or 1))
                    assert(uv[i].Y == (v.Z == glass.maxZ and 0 or 1))
                end
                for i=1,#ix,3 do
                    local a,b,c = vs[ix[i]+1], vs[ix[i+1]+1], vs[ix[i+2]+1]
                    assert((b.Z-a.Z)*(c.X-a.X) - (b.X-a.X)*(c.Z-a.Z) < 0)
                end
                self.section = s
            end
            function body:ClearMeshSection(s) assert(self.section == s) self.section = nil end
            function body:CreateDynamicMaterialInstance(s, parent, name)
                assert(s == self.section and parent == crt and name == "None")
                return mid
            end
            function mid:SetTextureParameterValue(input, image)
                assert(input == "SlateUI" and image == texture)
                self.image = image
            end
            function mid:K2_GetTextureParameterValue(input)
                assert(input == "SlateUI")
                return self.image
            end
        """)

    def test_native_surface_faces_player_and_displays_our_artwork(self):
        self.lua.execute("assert(display.apply(body, glass) == mid and body.section == 13 and mid.image == texture)")

    def test_failed_material_binding_reveals_original_lettering(self):
        self.lua.execute("""
            function mid:K2_GetTextureParameterValue() return nil end
            local ok, message = pcall(display.apply, body, glass)
            assert(not ok and message:find("SlateUI") and body.section == nil)
        """)
