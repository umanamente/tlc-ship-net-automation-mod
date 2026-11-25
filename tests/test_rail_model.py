"""Verify the shipped Blender geometry through the same Lua reader the preview uses."""
import unittest

from lupa.lua54 import LuaRuntime

from test_observer import SCRIPTS


MOCK = """
local function count(n) return {GetArrayNum=function() return n end} end
local registeredState = coroutine.running()
local api = {IsValid=function()
    assert(coroutine.running()==registeredState,"UE4SS refused an unregistered Lua state")
    return true
end}
local function object(data) return setmetatable(data or {}, {__index=api}) end
function api:MakeTransform(pos) return pos end
function api:MakeRotator(r,p,y) return {Roll=r,Pitch=p,Yaw=y} end
actor, parent, created = object(), object(), {}
function api:AddComponentByClass(class, manual, position)
    assert(not manual)
    local c = object({ProcMeshSections={}, position=position})
    created[#created+1] = c
    return c
end
function api:SetMobility(v) assert(v == 2) end
function api:SetCollisionEnabled(v) assert(v == 0) end
function api:SetGenerateOverlapEvents(v) assert(not v) end
function api:GetAttachParent() return parent end
function api:GetAddress() return tostring(self) end
function api:K2_SetRelativeRotation(p) self.rotation = p end
function api:SetRelativeScale3D(s) self.scale = s end
function api:SetVisibility(v, propagate) assert(not propagate) self.visible = v end
function api:SetMeshSectionVisible(slot, value)
    assert(self.ProcMeshSections[slot+1])
    self.ProcMeshSections[slot+1].visible=value
end
function api:K2_DestroyComponent(o) assert(o == actor) self.destroyed = true end
function api:FinishAddComponent(c) c.finished = true end
function api:SetStaticMesh(mesh) self.mesh = mesh return true end
function api:SetScalarParameterValueOnMaterials(name, v)
    assert(self.finished and name.fname == "ProgressLevel")
    self.progressLevel = v
end
function api:CreateMeshSection_LinearColor(slot, vs, ix, ns, uv0, uv1, uv2, uv3, colors, tan, collision, srgb)
    if captureFaces then
        self.faces=self.faces or {}
        self.faces[slot]={vs=vs,ix=ix}
    end
    assert(#vs > 0 and #ns == #vs and #ix % 3 == 0 and not srgb)
    if #uv0 > 0 then assert(not collision and #uv0 == #vs) end
    if collision then assert(self.bUseComplexAsSimpleCollision) end
    for _,v in ipairs(vs) do
        self.maxLocalX = math.max(self.maxLocalX or -math.huge, v.X)
        self.minLocalX = math.min(self.minLocalX or math.huge, v.X)
        self.minLocalY = math.min(self.minLocalY or math.huge, v.Y)
        self.maxLocalY = math.max(self.maxLocalY or -math.huge, v.Y)
    end
    local index_count = failUpload and 0 or #ix
    self.ProcMeshSections[slot+1] = {ProcVertexBuffer=count(#vs), ProcIndexBuffer=count(index_count), collision=collision}
end
function api:GetNumSections() return #self.ProcMeshSections end
function api:CreateDynamicMaterialInstance(slot, base, name)
    assert(type(name)=="table" and name.fname=="None")
    return object()
end
function api:SetMaterial(slot,material)
    self.materials=self.materials or {}
    self.materials[slot]=material
end
function api:SetTextureParameterValue(name, tex) assert(name.fname=="SlateUI") self.texture=tex end
function api:K2_GetTextureParameterValue(name) return self.texture end
function api:SetVectorParameterValue(name, c) assert(name.fname and c.R and c.G and c.B) end
function api:SetScalarParameterValue(name, v) assert(name.fname and type(v) == "number") end
function api:K2_GetVectorParameterValue(name) return {R=0,G=1,B=0,A=1} end
function api:GetAsset(ref)
    assert(ref.AssetName.fname == "BasicShapeMaterial")
    if not noMaterial then return object() end
end
function StaticFindObject(path)
    if (coldMaterial or noMaterial) and path:find("BasicShapeMaterial") then return nil end
    if noStockMeter and path:find("MI_PogressBar_PlayerBox_LED") then return nil end
    return object()
end
EFindName={FNAME_Find=0,FNAME_Add=1}
function FName(name) return {fname=name} end
module = require("shipnet.model")
"""


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts = SCRIPTS.as_posix()
        self.lua.execute('package.path = scripts .. "/?.lua;" .. package.path')
        self.lua.execute(MOCK)

    def test_built_lcd_sits_in_an_open_pocket_on_both_models(self):
        self.lua.execute("""
            captureFaces=true
            local function frontAt(body,x,z)
                local front=-math.huge
                for _,section in pairs(body.faces) do
                    local ix,v=section.ix,section.vs
                    for i=1,#ix,3 do
                        local a,b,c=v[1+ix[i]],v[1+ix[i+1]],v[1+ix[i+2]]
                        local dx,dz=b.X-a.X,b.Z-a.Z
                        local ex,ez=c.X-a.X,c.Z-a.Z
                        local det=dx*ez-dz*ex
                        if det>1e-8 then
                            local u=((x-a.X)*ez-(z-a.Z)*ex)/det
                            local t=(dx*(z-a.Z)-dz*(x-a.X))/det
                            if u>=0 and t>=0 and u+t<=1 then
                                front=math.max(front,a.Y+u*(b.Y-a.Y)+t*(c.Y-a.Y))
                            end
                        end
                    end
                end
                return front
            end
            for _,basic in ipairs({false,true}) do
                local m=module.build(actor,parent,basic,true)
                assert(m.ok,m.error)
                local g=m.liveGlass
                assert(g.lcdY+.04<g.lensY and g.lensY<g.rimY)
                for _,u in ipairs({.05,.5,.95}) do
                    for _,v in ipairs({.1,.5,.9}) do
                        local y=frontAt(m.body,g.minX+u*(g.maxX-g.minX),g.minZ+v*(g.maxZ-g.minZ))
                        assert(math.abs(y-(g.lcdY-.04))<.001,"Model obscures the LCD")
                    end
                end
                assert(math.abs(frontAt(m.body,g.minX-.6,(g.minZ+g.maxZ)/2)-g.rimY)<.001)
            end
        """)

    def test_upload_and_independent_pivots(self):
        self.lua.execute("""
            coldMaterial = true
            local m = module.build(actor, parent)
            assert(m.ok, m.error)
            assert(m.materialStatus == "BasicShapeMaterial")
            assert(m.stockMeter and m.screenMaterial and not m.screenError and not m.meterError)
            assert(m.triangles == 16162 and m.sections > 10 and #m.components == 5)
            assert(m.alarmCells:GetNumSections() == 1 and not m.alarmCells.visible)
            assert(math.abs(m.hatch.position.Y-module.anchors.hatch.Y) < 0.001)
            assert(math.abs(m.hatch.position.Z-module.anchors.hatch.Z) < 0.001)
            assert(m.hatch.position.Y < -50 and m.hatch.maxLocalY-m.hatch.minLocalY >= 113)
            assert(math.abs(m.drive.position.Y-module.anchors.drive.Y) < 0.001)
            assert(math.abs(m.drive.position.X+m.drive.maxLocalX-module.anchors.coupling.X) < .01)
            assert(math.abs(m.drive.position.Y-module.anchors.coupling.Y) < .001)
            assert(math.abs(m.drive.position.Z-module.anchors.coupling.Z) < .001)
            assert(math.abs(module.anchors.coupling.Z-60.2) < .001)
            assert(module.pose(m, 85, 35))
            assert(module.maxHatchDegrees == 2)
            assert(m.hatch.rotation.Roll == -2 and m.drive.rotation.Roll == 35)
            assert(module.pose(m, -5, -15))
            assert(m.hatch.rotation.Roll == 0 and m.drive.rotation.Roll == -15)
            assert(not m.body.rotation)
            module.clear(m)
            assert(not m.ok and #m.components==0 and created[4].destroyed)
        """)

    def test_basic_blinks_without_detaching_its_dynamic_materials(self):
        self.lua.execute("""
            local m = module.build(actor, parent, true)
            assert(m.ok and m.screenMaterial and m.beacon and not m.hatch and not m.fill, m.error)
            assert(module.pose(m, 0, 80) and m.drive.rotation.Roll == 80)
            local creation = m.beacon.CreateDynamicMaterialInstance
            local attached = {}
            function m.beacon:CreateDynamicMaterialInstance(slot, parent, name)
                local mid=creation(self,slot,parent,name)
                assert(not attached[slot], "a pulse replaced an already mounted material")
                attached[slot]=mid
                function mid:SetScalarParameterValue(key, value)
                    if key.fname=="EmissivePowerMin" then self.power=value end
                end
                return mid
            end
            function m.beacon:SetMaterial() error("blinking must preserve UE ownership") end
            module.setBeacon(m, false)
            local off = attached[0].power
            module.setBeacon(m, true)
            assert(m.beaconLit and attached[0].power > off)
            module.setBeacon(m, false)
            assert(not m.beaconLit and attached[0].power == off)
        """)

    def test_model_forwards_storage_weight_to_the_native_led(self):
        self.lua.execute("""
            local m = module.build(actor, parent)
            assert(m.ok and m.stockMeter and m.fill.progressLevel == 43.5/90)
            assert(module.setFill(m,.55) and m.fill.progressLevel == 66.5/90)
            assert(module.setFill(m,.55,true) and m.alarmCells.visible and not m.fill.visible)
            assert(module.setFill(m,.55,false) and not m.alarmCells.visible and m.fill.visible)
            assert(m.fill.progressLevel == 66.5/90)
            assert(module.pose(m,2,90) and not m.fill.scale)
            assert(module.setFill(m,1) and m.alarmCells.visible and not m.fill.visible)
            assert(module.setFill(m,0) and m.fill.progressLevel == 43.5/90)
            assert(not m.alarmCells.visible and m.fill.visible)
            module.clear(m)
            assert(m.fill.destroyed and not module.setFill(m,1))
        """)

    def test_legacy_strip_recovers_if_stock_meter_cannot_load(self):
        self.lua.execute("""
            noStockMeter = true
            local m = module.build(actor, parent)
            assert(m.ok and not m.stockMeter and m.meterError, m.error)
            local bar = module.fitGeometry.fillBar
            assert(not m.fill.visible and m.fillFraction == 0)
            assert(math.abs(m.fill.position.X-bar.minX) < .001)
            assert(math.abs(m.fill.position.Y-58.09) < .001)
            assert(math.abs(m.fill.position.Z-bar.Z) < .001)
            assert(math.abs(m.fill.minLocalX-.08) < .001)
            assert(math.abs(m.fill.position.X+m.fill.maxLocalX-(bar.maxX-.08)) < .001)
            assert(module.setFill(m,.55) and m.fill.visible and m.fill.scale.X == .55)
            assert(m.fill.scale.Y == 1 and m.fill.scale.Z == 1)
            assert(module.pose(m, 2, 90) and m.fill.scale.X == .55 and not m.body.scale)
            assert(module.setFill(m,2) and m.fill.scale.X == 1 and m.fillFraction == 1)
            assert(not module.setFill(m,0/0) and not module.setFill(m,1/0))
            assert(not module.setFill(m,nil) and m.fillFraction == 1)
            assert(module.setFill(m,-1) and not m.fill.visible and m.fillFraction == 0)
            assert(module.setFill(m,.001) and m.fill.visible and m.fill.scale.X == .001)
            module.clear(m)
            assert(not module.setFill(m,1))
        """)

    def test_upload_failure_cleanup_and_retry(self):
        self.lua.execute("""
            failUpload = true
            local m = module.build(actor, parent)
            assert(not m.ok and m.error:find("geometry count mismatch", 1, true))
            assert(created[1].destroyed)
            failUpload = false
            noMaterial = true
            local retry = module.build(actor, parent)
            assert(retry.ok and retry.triangles == 16162 and retry.materialStatus:find("default"))
        """)

    def test_lod_switch_preserves_pose_screen_meter_and_interaction_geometry(self):
        self.lua.execute("""
            local foreign=coroutine.create(function() actor:IsValid() end)
            local accepted, reason=coroutine.resume(foreign)
            assert(not accepted and reason:find("unregistered Lua state",1,true))
            for _,basic in ipairs({false,true}) do
                local m=module.build(actor,parent,basic,true)
                assert(m.ok,m.error)
                local body,drive,fill,beacon=m.body,m.drive,m.fill,m.beacon
                module.setScreenMounted(m,true)
                assert(module.pose(m,2,61))
                module.updateLOD(m,.50)
                assert(not m.far and m.lod==0)
                module.updateLOD(m,.33)
                assert(m.far and m.upload and m.lod==0 and m.body.visible~=false)
                for _=1,40 do module.updateLOD(m,.15) end
                assert(m.lod==1 and m.far.ok,m.lodError)
                assert(m.body==body and m.drive==drive and m.fill==fill and m.beacon==beacon)
                assert(m.body.visible==false and m.far.body.visible and m.far.drive.rotation.Roll==61)
                assert(m.far.triangles+m.sharedTriangles==(basic and 4438 or 6581))
                assert(#m.far.components==(basic and 2 or 3))
                assert(m.far.palette and m.far.body:GetNumSections()==5,m.far.paletteError)
                assert(m.far.drive:GetNumSections()==1)
                assert(m.far.drive.materials[0]==m.far.palette.material)
                if not basic then assert(m.far.hatch:GetNumSections()==1) end
                assert(m.body.ProcMeshSections[1].collision and not m.far.body.ProcMeshSections[1].collision)
                for _,s in ipairs({1,2,8}) do assert(not m.body.ProcMeshSections[s+1].collision) end
                for _,layer in ipairs({m,m.far}) do
                    for _,s in ipairs(layer.artSlots) do assert(layer.body.ProcMeshSections[s+1].visible==false) end
                    assert(layer.body.ProcMeshSections[layer.screenSlot+1].visible==false)
                end
                module.setScreenMounted(m,false)
                assert(m.far.body.ProcMeshSections[m.far.artSlots[2]+1].visible and body.ProcMeshSections[3].visible)
                assert(module.pose(m,0,-40) and drive.rotation.Roll==-40 and m.far.drive.rotation.Roll==-40)
                local allocations=#created
                module.updateLOD(m,.25);assert(m.lod==1)
                module.updateLOD(m,.30);assert(m.lod==0 and body.visible and not m.far.body.visible)
                module.updateLOD(m,.25);assert(m.lod==0)
                module.updateLOD(m,.18);assert(m.lod==1 and #created==allocations)
                local farBody=m.far.body
                module.clear(m)
                assert(farBody.destroyed and body.destroyed and not m.ok)
            end
        """)

    def test_bad_distant_asset_keeps_near_mesh_and_releases_partial_upload(self):
        self.lua.execute("""
            local m=module.build(actor,parent,false,true)
            assert(m.ok,m.error)
            module.updateLOD(m,.20)
            local partial=m.far and m.far.body
            assert(partial and m.upload)
            failUpload=true
            for _=1,40 do module.updateLOD(m,.15) end
            assert(m.lod==0 and m.ok and m.body.visible and m.lodError)
            assert(partial.destroyed and not m.far and not m.upload)
            local createdAfterFailure=#created
            module.updateLOD(m,.1)
            assert(#created==createdAfterFailure and module.pose(m,2,30))
        """)

    def test_missing_palette_preserves_distant_geometry_and_original_material_slots(self):
        self.lua.execute("""
            local find=StaticFindObject
            function StaticFindObject(path)
                if not path:find("MI_WinchPalette",1,true) then return find(path) end
            end
            function LoadAsset(path) return nil end
            local m=module.build(actor,parent,false,true)
            for _=1,40 do module.updateLOD(m,.1) end
            assert(m.lod==1 and m.far.ok and m.far.paletteError,m.lodError)
            assert(m.far.body:GetNumSections()==13 and m.far.drive:GetNumSections()==4)
            module.setScreenMounted(m,true)
            assert(not m.far.body.ProcMeshSections[2].visible)
            module.updateLOD(m,.30)
            assert(m.lod==0 and m.body.visible)
        """)

    def test_render_size_tracks_camera_distance_fov_and_viewport(self):
        self.lua.execute("""
            local m=module.build(actor,parent,true,true)
            function actor:GetTransform() return {} end
            local pc={PlayerCameraManager={
                IsValid=function() return true end,
                GetCameraLocation=function() return {X=132.6+distance,Y=105.8,Z=14.5} end,
                GetFOVAngle=function() return fov end,
            }}
            local find=StaticFindObject
            function StaticFindObject(path)
                local o=find(path)
                o.GetViewportSize=function() return {X=aspect*1000,Y=1000} end
                o.TransformLocation=function(_,frame,p) return p end
                return o
            end
            fov=90;aspect=16/9;distance=700
            local fraction=module.screenSize(m,pc)
            assert(math.abs(fraction-86.10*aspect/700)<.00001)
            fov=45;assert(module.screenSize(m,pc)>2*fraction)
            distance=1400;fov=90;assert(math.abs(module.screenSize(m,pc)-fraction/2)<.00001)
            aspect=1;assert(module.screenSize(m,pc)<fraction/3)
        """)
