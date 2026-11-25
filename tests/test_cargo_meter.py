"""Exercise the player-box LED meter, including a failed application on a live actor."""
import unittest

from lupa.lua54 import LuaRuntime

from test_observer import SCRIPTS


class CargoMeterTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts = SCRIPTS.as_posix()
        self.lua.execute("""
            package.path = scripts .. "/?.lua;" .. package.path
            meter = require("shipnet.cargo_meter")
            local api = {}
            local function object(fields)
                return setmetatable(fields or {}, {__index=api})
            end
            function api:IsValid() return not self.destroyed end
            function api:GetAddress() return tostring(self) end
            function api:GetAttachParent() return root end
            function api:MakeRotator(roll, pitch, yaw) return {roll=roll,pitch=pitch,yaw=yaw} end
            function api:MakeTransform(p, r, s) return {p=p,r=r,s=s} end
            function api:AddComponentByClass(class,manual,transform,deferred)
                assert(class == meshClass and not manual and deferred)
                added = object({transform=transform,values={}})
                return added
            end
            function api:SetMobility(v) assert(v == 2) end
            function api:SetCollisionEnabled(v) assert(v == 0) end
            function api:SetGenerateOverlapEvents(value) assert(value == false) end
            function api:CreateMeshSection_LinearColor(slot,vertices,tris,normals,uv,_,_,_,_,_,collision,srgb)
                assert(normals[1].Y==1 and self.registered and not collision and not srgb)
                if slot==1 then
                    assert(#normals==#vertices and #uv==#vertices and #tris==#vertices*1.5)
                    self.sweepVertices,self.sweepUV=vertices,uv
                    self.sweepWrites=(self.sweepWrites or 0)+1
                    return
                end
                assert(slot==0 and #vertices==4 and #normals==4 and #uv==4 and #tris==6)
                self.vertices,self.uv=vertices,uv
            end
            function api:GetNumSections() return self.vertices and 1 or 0 end
            function api:CreateDynamicMaterialInstance(slot, asset, name)
                if slot==1 then
                    assert(self==added and asset==sweepMaterial and name=="None")
                    self.sweepMid=object({vectors={},scalars={},textures={}})
                    return self.sweepMid
                end
                assert(slot==0 and name=="None")
                assert((self==added and asset==stockMaterial) or (self==cells and asset==buoyMaterial))
                self.binds = (self.binds or 0) + 1
                self.mid = object({vectors={},scalars={}})
                return self.mid
            end
            function api:SetVectorParameterValue(name,value) self.vectors[name]=value end
            function api:SetScalarParameterValue(name,value) self.scalars[name]=value end
            function api:SetTextureParameterValue(name,value) self.textures[name]=value end
            function api:K2_GetTextureParameterValue(name) return self.textures[name] end
            function api:SetMeshSectionVisible(slot,visible) assert(slot==1) self.sweepVisible=visible end
            function api:SetVisibility(visible, propagate)
                assert(propagate==false)
                self.visible = visible
                self.visibilityWrites = (self.visibilityWrites or 0) + 1
            end
            function api:FinishAddComponent(c, manual, transform)
                assert(c == added and not manual and transform == c.transform)
                c.registered = true
            end
            function api:SetScalarParameterValueOnMaterials(name, value)
                assert(self.registered and name == "ProgressLevel")
                assert(not rejectScalar, "scalar failed")
                table.insert(self.values,value)
            end
            function api:K2_DestroyComponent(owner) assert(owner == actor) self.destroyed=true end
            root, actor, maths, meshClass, stockMaterial = object(),object(),object(),object(),object()
            local base = "/Game/Materials/Modules/"
            local materialPath = base .. "MI_PogressBar_PlayerBox_LED.MI_PogressBar_PlayerBox_LED"
            local buoyPath = "/Game/AssetSets/Launch_site/Materials/M_Master_Emissive_Buoy.M_Master_Emissive_Buoy"
            local sweepPath = "/Game/AssetSets/Sockets/M_SocketInteractionVis.M_SocketInteractionVis"
            local sweepTexturePath = "/Game/Mods/ShipNetAutomation/T_WinchCargoSweep.T_WinchCargoSweep"
            sweepMaterial,sweepTexture=object(),object()
            cells,buoyMaterial = object({visible=false}),object()
            function StaticFindObject(path)
                if path == "/Script/ProceduralMeshComponent.ProceduralMeshComponent" then return meshClass end
                if path == sweepPath then return sweepMaterial end
                if path == sweepTexturePath then return sweepTexture end
                if path == buoyPath then return nil end
                assert(path == materialPath)
            end
            function LoadAsset(path)
                if path==buoyPath then
                    if missingBuoy then return nil end
                    return buoyMaterial
                end
                assert(path == materialPath) return stockMaterial
            end
            EFindName = {FNAME_Find=0}
            function FName(name,lookup) assert(lookup == 0) return name end
            bar = {minX=-38.4,maxX=30,Y=58.165,Z=52,height=2.9}
            result = {ok=true,components={},alarmCells=cells}
        """)

    def test_gpu_sweep_covers_only_filled_cells_and_stops_for_alarm(self):
        self.lua.execute("""
            meter.mount(result,actor,root,maths,bar)
            assert(meter.setFill(result,0,false,true) and not added.sweepMid)
            assert(meter.setFill(result,.5,false,true))
            local mid=added.sweepMid
            assert(mid.scalars.USpeed<0 and mid.scalars.Panning==1 and mid.textures.Texture==sweepTexture)
            local activeColor = added.mid.vectors.ColorFull
            assert(activeColor.R>.8 and activeColor.G>.5 and activeColor.B<.1 and mid.vectors.Color.G>.7)
            assert(added.sweepVisible and #added.sweepVertices==21*4 and added.sweepVertices[83].X<0)
            assert(added.sweepWrites==1 and added.visible~=false)
            assert(meter.setFill(result,.501,false,true) and added.sweepWrites==1)
            assert(meter.setFill(result,.5,false,false) and not added.sweepVisible)
            assert(added.mid.vectors.ColorFull.R<.1 and added.mid.vectors.ColorFull.G>.7)
            assert(meter.setFill(result,.5,false,true) and added.sweepVisible and added.sweepMid==mid)
            assert(meter.setFill(result,.5,true,true) and not added.sweepVisible and cells.visible)
        """)

    def test_cropped_stock_shader_fits_the_track_and_keeps_its_size_at_every_weight(self):
        self.lua.execute("""
            meter.mount(result,actor,root,maths,bar)
            local transform = added.transform
            local p,r,s = transform.p,transform.r,transform.s
            assert(s.X==1 and s.Y==1 and s.Z==1)
            assert(math.abs(p.X+added.vertices[1].X-bar.minX)<1e-6 and math.abs(p.X+added.vertices[2].X-bar.maxX)<1e-6)
            assert(math.abs(p.Z+added.vertices[1].Z-50.55)<1e-6 and math.abs(p.Z+added.vertices[3].Z-53.45)<1e-6)
            assert(math.abs(p.Y-58.165)<1e-6 and r.roll==0 and r.pitch==0 and r.yaw==0)
            assert(added.uv[1].X==44/90 and added.uv[2].X==86/90)
            assert(added.uv[3].Y==44/90 and added.uv[2].Y==45/90 and added.mid.scalars.ScaleX==90)
            assert(result.fill==added and #result.components==1 and added.values[1]==43.5/90)
            for _,value in ipairs({.53,.53,3,-1}) do assert(meter.setFill(result,value)) end
            assert(not meter.setFill(result,0/0) and not meter.setFill(result,math.huge))
            assert(#added.values==4 and added.values[2]==65.5/90 and added.values[3]==85.5/90 and added.values[4]==43.5/90)
            assert(result.fillFraction==0 and added.transform==transform)
        """)

    def test_full_weight_uses_one_gpu_pulse_material_on_all_cells(self):
        self.lua.execute("""
            meter.mount(result,actor,root,maths,bar)
            assert(added.mid.vectors.ColorFull.G>.5 and added.mid.vectors.ColorLow.G==0)
            assert(added.mid.scalars.Glow>0)
            assert(meter.setFill(result,.9999) and not cells.visible and not cells.mid)
            local level = added.values[#added.values]
            assert(math.abs(added.mid.scalars.Glow*level*level-.02)<1e-8)
            assert(meter.setFill(result,1) and cells.visible and not added.visible)
            assert(cells.mid.scalars.BlinkingSpeed==1/1.3 and cells.mid.scalars.IsEmpty==0)
            assert(cells.mid.scalars.EmissivePowerMin>0 and cells.mid.scalars.EmissivePowerMax>1)
            assert(cells.mid.vectors["Emissive Color"].R>.7 and cells.mid.vectors["Emissive Color"].G<.02)
            assert(cells.mid.vectors["Emissive Color Empty"]==cells.mid.vectors["Emissive Color"])
            for i=1,30 do assert(meter.setFill(result,1)) end
            assert(#added.values==3 and cells.binds==1 and cells.visibilityWrites==1)
            assert(meter.setFill(result,.99) and not cells.visible and added.visible)
            assert(meter.setFill(result,1) and cells.visible and cells.binds==1)
            assert(meter.setFill(result,0) and not cells.visible and added.visible)
        """)

    def test_missing_pulse_asset_shows_steady_red_and_retries_on_next_alarm(self):
        self.lua.execute("""
            meter.mount(result,actor,root,maths,bar)
            missingBuoy = true
            assert(meter.setFill(result,0,true) and not cells.visible and added.visible and result.meterAlarmError)
            assert(added.mid.vectors.ColorLow.R==0 and added.mid.vectors.ColorFull.R>.7 and added.values[2]==85.5/90)
            missingBuoy = false
            assert(meter.setFill(result,.5,true) and not cells.mid and #added.values==2)
            assert(meter.setFill(result,.5,false) and not result.meterAlarmError)
            assert(added.mid.vectors.ColorFull.G>.5 and added.values[3]==64.5/90)
            assert(meter.setFill(result,1) and cells.visible and not added.visible)
        """)

    def test_visible_columns_match_every_weight_step_at_constant_emission(self):
        self.lua.execute("""
            meter.mount(result,actor,root,maths,bar)
            for expected=0,42 do
                local fraction=math.min(1,(expected+.25)/42)
                assert(meter.setFill(result,fraction))
                local material=added.mid
                local level=added.values[#added.values]
                local lit=0
                assert(math.abs(level*material.scalars.ScaleX-(43.5+expected))<1e-8)
                for i=0,41 do
                    local u=added.uv[1].X+(i+.5)/42*(added.uv[2].X-added.uv[1].X)
                    if math.floor(u*material.scalars.ScaleX)/material.scalars.ScaleX <= level then lit=lit+1 end
                end
                assert(lit==expected and math.abs(level*level*material.scalars.Glow-.02)<1e-8)
            end
        """)

    def test_failed_mount_preserves_the_previous_display_and_is_retryable(self):
        self.lua.execute("""
            local previous = {}
            result.fill,result.fillFraction,result.components[1] = previous,.27,previous
            rejectScalar = true
            assert(not pcall(meter.mount,result,actor,root,maths,bar))
            assert(added.destroyed and result.fill==previous and result.fillFraction==.27 and #result.components==1)
            rejectScalar = false
            meter.mount(result,actor,root,maths,bar)
            assert(#result.components==2 and result.fill==added and result.fillFraction==0)
            rejectScalar = true
            assert(not meter.setFill(result,.27) and result.fillFraction==0)
            rejectScalar = false
            assert(meter.setFill(result,.27) and result.fillFraction==.27)
        """)
