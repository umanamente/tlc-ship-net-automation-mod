"""The fit actor owns the probe, including partial installs and cable cleanup guards."""

import unittest

from lupa.lua54 import LuaRuntime

from test_observer import SCRIPTS


WORLD = r"""
objects, loaded, additions = {}, {}, 0
local sequence=0
function object(path, owner)
    sequence=sequence+1
    local obj={path=path, serial=sequence, owner=owner}
    function obj:GetAddress() return self.serial end
    function obj:IsValid() return not self.invalid end
    function obj:GetFullName() return "Object "..self.path end
    function obj:GetOwner() return self.owner end
    objects[path]=obj
    return obj
end
function StaticFindObject(path) return objects[path] end
function LoadAsset(path)
    loaded[path]=true
    return object(path)
end
local moduleClass=object("/Script/Voyage.VoyageModuleComponent")
local socketClass=object("/Script/Voyage.VoyageModuleSocketViewComponent")
local staticClass=object("/Script/Engine.StaticMeshComponent")
local system=object("/Script/Engine.Default__KismetSystemLibrary")
function system:Conv_ObjectToSoftObjectReference(obj) return {asset=obj} end
function system:Conv_SoftObjectReferenceToObject(soft) return soft.asset end
local mathlib=object("/Script/Engine.Default__KismetMathLibrary")
function mathlib:MakeRotator(roll,pitch,yaw) return {pitch=pitch,Yaw=yaw,Roll=roll} end
function mathlib:MakeTransform(v,r,s) return {p=v,r=r,s=s} end
function mathlib:ComposeRotators(a,b) return {base=a,view=b} end
local mesh="/Game/AssetSets/Sockets/SM_Socket_Electrical_Output.SM_Socket_Electrical_Output"
preview=object("/Test.Preview")
function preview:AddComponentByClass(cls,manual,transform,deferred)
    assert(self==preview and manual==false and deferred==true)
    additions=additions+1
    local obj=object(self.path.."."..additions,self)
    function obj:SetMobility(value) self.mobility=value end
    function obj:SetStaticMesh(value) self.StaticMesh=value; return true end
    function obj:SetCollisionEnabled(value) self.collision=value end
    if cls==moduleClass then
        receiver=obj
        obj.ConfigData={}
        function obj:SetupNewResource(res,cap,input,output,direction,shared)
            assert(self.finished and res==0 and cap==1 and input==1 and output==0 and direction==1 and not shared)
        end
        obj.Sockets={items={}}
        function obj.Sockets:ForEach(f)
            for i,o in ipairs(self.items) do if f(i,{get=function() return o end}) then break end end
        end
        function obj:AddExternalSocket(socket)
            for _,o in ipairs(self.Sockets.items) do assert(o~=socket,"double registration") end
            table.insert(self.Sockets.items,socket)
        end
        function obj:HasPower() return self.powered==true end
        function obj:GetResourceAmount(res) assert(res==0); return self.charge or 0 end
    elseif cls==socketClass then
        view=obj
        obj.Port={Bandwidth={}}
        function obj:InitializeSockets(module)
            assert(self.finished and self.DataAsset and self.bAutoInitialize==false)
            self.receiver=module
            if alreadyListed then module:AddExternalSocket(self) end
        end
        function obj:ReloadMesh()
            assert(self.finished and self.receiver)
            if failReload then error("reload failed") end
            self.mesh=object(self.path..".Mesh",self.owner)
            self.mesh.StaticMesh=objects[mesh]
        end
        function obj:GetModule() return self.receiver end
        function obj:IsSocketConnected() return self.connected==true end
        function obj:IsSocketConnectedOrHasCable()
            if self.unreadable then error("cable state unavailable") end
            return self.cable==true or self.connected==true
        end
        function obj:GetConnectedSocket() return self.peer end
        function obj:HasInputConnection() return self.input==true end
        function obj:GetCollisionEnabled() return 1 end
    else assert(cls==staticClass) end
    return obj
end
function preview:FinishAddComponent(obj,manual,transform)
    assert(obj.owner==self and manual==false)
    obj.finished=true; obj.transform=transform
end
probe=require("shipnet.fit_power").new()
function cookedCabinet(moduleName)
    local shell=object("/Test.PersistentCabinet")
    moduleName=moduleName or "VoyageModule"
    local module=object(shell.path.."."..moduleName,shell)
    local inlet=object(shell.path..".WinchPowerInlet",shell)
    function module:IsA(class) return class==moduleClass.path end
    function inlet:IsA(class) return class==socketClass.path end
    shell[moduleName]=module
    module.bHasInitialized=true
    module.Sockets={items={},ForEach=function(self,f)
        for i,o in ipairs(self.items) do if f(i,{get=function() return o end}) then break end end
    end}
    function module:AddExternalSocket(view)
        assert(#self.Sockets.items==0);self.Sockets.items[1]=view
    end
    function module:HasPower() return true end
    function module:GetResourceAmount() return 0.75 end
    local data="/Game/Data/Assets/ModuleSockets/DA_Socket_ElectricData.DA_Socket_ElectricData"
    inlet.DataAsset={asset=object(data)}
    inlet.Port={Type=1,ResourceType=0}
    function inlet:GetModule() return self.module end
    function inlet:InitializeSockets(m) self.inits=(self.inits or 0)+1;self.module=m end
    function inlet:IsSocketConnectedOrHasCable() return self.connected==true end
    function inlet:IsSocketConnected() return self.connected==true end
    function inlet:ReloadMesh()
        self.reloads=(self.reloads or 0)+1
        self.mesh=object(self.path..".Mesh",shell);self.mesh.StaticMesh=object(mesh)
    end
    return shell,module,inlet
end
"""


class FitPowerTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts = SCRIPTS.as_posix()
        self.lua.execute('package.path = scripts .. "/?.lua;" .. package.path')
        self.lua.execute(WORLD)

    def test_native_receiver_on_left_with_independent_measurements(self):
        row = self.lua.eval("probe:mount(preview)")
        self.assertEqual(row.status, "native_input", row.detail)
        self.assertEqual(row.socketData, "/Game/Data/Assets/ModuleSockets/DA_Socket_ElectricData.DA_Socket_ElectricData")
        for field in ("registered", "visual", "socketDataApplied"):
            self.assertIs(row[field], True)
        for field in ("connected", "cablePresent", "hasInputConnection", "hasPower"):
            self.assertIs(row[field], False)
        self.assertEqual(self.lua.eval("view.transform.p.X"), -68.4)
        self.assertEqual(self.lua.eval("view.transform.p.Y"), -0.5)
        self.assertEqual(self.lua.eval("view.transform.p.Z"), 29.8)
        self.assertEqual(self.lua.eval("view.transform.r.pitch"), 0)
        self.assertEqual(self.lua.eval("view.transform.r.Yaw"), 90)
        self.assertEqual(self.lua.eval("view.transform.r.Roll"), -90)
        self.assertEqual(self.lua.eval("view.Port.DefaultDirection"), 1)
        self.assertEqual(self.lua.eval("receiver.ConfigData.ResourceBandwidthOutput"), 0)
        self.lua.execute("view.connected=true; receiver.charge=0.25")
        row = self.lua.eval("probe:inspect(preview)")
        self.assertIs(row.connected, True)
        self.assertIs(row.hasPower, False)
        self.assertEqual(row.electricity, 0.25)

    def test_initialization_and_multiple_mounts_do_not_duplicate_components(self):
        self.lua.execute("alreadyListed=true; probe:mount(preview); probe:mount(preview)")
        self.assertEqual(self.lua.eval("additions"), 2)
        self.assertEqual(self.lua.eval("#receiver.Sockets.items"), 1)

    def test_restore_indestructible_saved_zero_health_from_native_item_only(self):
        self.lua.execute("""
            box,mod,inlet=cookedCabinet()
            function FName(name) return name end
            function box:ActorHasTag(name) return self.recycling and name=="Recycling" end
            local item=object("/Game/Data/Assets/Modules/DA_Item_Module_WinchAutomator.DA_Item_Module_WinchAutomator")
            box.ContainerItem=item
            item.bIsDestructible=false
            item.DestructibleObjectProperties={Health=500}
            component=object("/Test.PersistentCabinet.VoyageDestructibleObject",box)
            box.VoyageDestructibleObject=component
            mod.DestructibleObjectReference=component
            component.Health=0;component.DestructibleObjectProperties={Health=0};component.bIsDestructible=false
            function mod:GetMaxDurability() return component.DestructibleObjectProperties.Health end
            function mod:GetDurability() return component.Health end
            function component:UpdateDestructibleObjectProperties(s) error("unsafe native struct copy") end
            function component:OverrideHealth(h) self.Health=h;self.applied=(self.applied or 0)+1 end
            box.recycling=true
            assert(probe:bindBuilt(box).status=="native_input" and component.Health==0)
            box.recycling=false;component.bIsDestructible=true
            probe:builtStatus(box);assert(component.Health==0)
            component.bIsDestructible=false;component.Health=23
            probe:builtStatus(box);assert(component.Health==23 and mod:GetMaxDurability()==500)
            component.Health=0;mod.DestructibleObjectReference=box
            probe:builtStatus(box);assert(component.Health==0)
            mod.DestructibleObjectReference=component
            probe:builtStatus(box);probe:bindBuilt(box);probe:builtStatus(box)
            assert(mod:GetMaxDurability()==500 and component.Health==500 and component.applied==1)
            component.DestructibleObjectProperties.Health=0
            probe:builtStatus(box);assert(mod:GetMaxDurability()==500 and component.Health==500 and component.applied==1)
            component.DestructibleObjectProperties.Health=0;component.Health=0
            probe:bindBuilt(box);assert(mod:GetMaxDurability()==500 and component.Health==500 and component.applied==2)
            assert(not component.bIsDestructible and inlet.inits==1 and additions==0)
        """)

    def test_finished_socket_initializes_existing_pair_once_and_survives_rebind(self):
        self.lua.execute("box,mod,inlet=cookedCabinet(); mod.bHasInitialized=false")
        self.assertEqual(self.lua.eval("probe:bindBuilt(box).status"), "waiting_for_socket")
        self.assertIsNone(self.lua.eval("inlet.inits"))
        self.lua.execute("mod.bHasInitialized=true")
        self.assertEqual(self.lua.eval("probe:bindBuilt(box).status"), "native_input")
        self.lua.execute("inlet.connected=true; probe:reset(); probe:bindBuilt(box); probe:bindBuilt(box)")
        row = self.lua.eval("probe:builtStatus(box)")
        self.assertEqual(row.electricity, 0.75)
        self.assertIs(row.connected, True)
        self.assertEqual(self.lua.eval("inlet.inits"), 1)
        self.assertEqual(self.lua.eval("inlet.reloads"), 1)
        self.assertEqual(self.lua.eval("#mod.Sockets.items"), 1)
        self.assertEqual(self.lua.eval("additions"), 0)

    def test_basic_uses_native_module_and_keeps_the_saved_endpoint_and_nonzero_health(self):
        self.lua.execute("""
            kind=require("shipnet.variants").basic
            shell,mod,inlet=cookedCabinet("ModuleComponent")
            shell.WinchPowerInlet=inlet
            mod.ItemAsset=object(kind.item)
            mod.ItemAsset.bIsDestructible=false
            mod.ItemAsset.DestructibleObjectProperties={Health=500}
            local health=object(shell.path..".DestructibleObjectComponent",shell)
            shell.DestructibleObjectComponent=health
            mod.DestructibleObjectReference=health
            health.Health=337
            health.DestructibleObjectProperties={Health=500}
            health.bIsDestructible=false
            function mod:GetMaxDurability() return health.DestructibleObjectProperties.Health end
            function mod:GetDurability() return health.Health end
            function health:OverrideHealth(v) self.Health=v end
            function shell:ActorHasTag() return false end
            function FName(name) return name end
            inlet.SocketID=1155321963
            inlet.connected=true
            assert(probe:bindBuilt(shell,kind).status=="waiting_for_socket")
            assert(not inlet.inits and not inlet.reloads)
            inlet.module=mod
            mod.Sockets.items={inlet}
            inlet:ReloadMesh()
            assert(probe:bindBuilt(shell,kind).status=="native_input")
            assert(probe:builtStatus(shell).connected and health.Health==337)
            assert(inlet.SocketID==1155321963 and not inlet.inits and inlet.reloads==1 and additions==0)
            health.Health=0
            probe:builtStatus(shell)
            assert(health.Health==500)
        """)

    def test_removed_or_wrong_owner_socket_cannot_masquerade_as_live_connection(self):
        self.lua.execute("box,mod,inlet=cookedCabinet();probe:bindBuilt(box);mod.Sockets.items={}")
        self.assertEqual(self.lua.eval("probe:builtStatus(box).status"), "waiting_for_socket")
        self.lua.execute("foreign=object('/Other.Module'); inlet.module=foreign; probe:bindBuilt(box)")
        self.assertEqual(self.lua.eval("#mod.Sockets.items"), 0)
        self.assertEqual(self.lua.eval("inlet.inits"), 1)
        self.lua.execute("inlet.invalid=true")
        self.assertEqual(self.lua.eval("probe:bindBuilt(box).status"), "waiting_for_socket")
        self.assertEqual(self.lua.eval("additions"), 0)

    def test_cable_restores_before_its_module_without_reinitializing_the_endpoint(self):
        self.lua.execute("box,mod,inlet=cookedCabinet();inlet.connected=true")
        self.assertEqual(self.lua.eval("probe:bindBuilt(box).status"), "waiting_for_socket")
        self.lua.execute("probe:inspect(box);probe:builtStatus(box);probe:bindBuilt(box)")
        self.assertIsNone(self.lua.eval("inlet.inits"))
        self.assertIsNone(self.lua.eval("inlet.reloads"))
        self.lua.execute("inlet.module=mod; mod.Sockets.items={inlet}; inlet:ReloadMesh()")
        self.assertEqual(self.lua.eval("probe:bindBuilt(box).status"), "native_input")
        self.lua.execute("probe:inspect(box);probe:inspect(box)")
        self.assertIs(self.lua.eval("probe:builtStatus(box).connected"), True)
        self.assertIsNone(self.lua.eval("inlet.inits"))
        self.assertEqual(self.lua.eval("inlet.reloads"), 1)
        self.assertEqual(self.lua.eval("additions"), 0)

    def test_loose_plug_and_unknown_status_block_interactive_removal(self):
        self.lua.execute("probe:mount(preview); view.cable=true")
        self.assertEqual(self.lua.eval("probe:before_remove(preview).status"), "detach_cable_first")
        self.lua.execute("view.cable=false; view.unreadable=true")
        self.assertEqual(self.lua.eval("probe:before_remove(preview).status"), "connection_unknown")
        self.lua.execute("view.unreadable=false")
        self.assertIs(self.lua.eval("probe:before_remove(preview).allowed"), True)

    def test_rendered_mesh_plane_and_bounds_on_rotated_moving_host(self):
        self.lua.execute("""
            probe:mount(preview)
            local mathlib = StaticFindObject("/Script/Engine.Default__KismetMathLibrary")
            function preview:GetTransform() return {tag="actor"} end
            function view.mesh:K2_GetComponentToWorld() return {tag="mesh"} end
            -- Actor has yaw +90 and world origin (10,20,30).
            -- Actual mesh origin is (-68.4,-0.5,29.8) in the actor frame.
            function mathlib:InverseTransformLocation(t,p)
                assert(t.tag=="actor")
                return {X=p.Y-20,Y=10-p.X,Z=p.Z-30}
            end
            function mathlib:TransformLocation(t,p)
                assert(t.tag=="mesh")
                if wrongPlane then return {X=10.5+p.Y,Y=-48.4-p.X,Z=59.8+p.Z} end
                if outward then return {X=10.5-p.X,Y=-48.4-p.Y,Z=59.8+p.Z} end
                return {X=10.5+p.X,Y=-48.4+p.Y,Z=59.8+p.Z}
            end
            function view.mesh.StaticMesh:GetBounds()
                return {Origin={X=0,Y=-1.982,Z=0},BoxExtent={X=12.685,Y=7.958,Z=12.685}}
            end
        """)
        fit = self.lua.eval("probe:inspect(preview).renderedMeshFit")
        self.assertEqual(fit.status, "measured")
        self.assertAlmostEqual(fit.shortAxisLocal.X, 1.0)
        self.assertAlmostEqual(fit.planeErrorDeg, 0.0)
        self.assertAlmostEqual(fit.matingFaceErrorDeg, 180.0)
        self.assertAlmostEqual(fit.originLocalCm.X, -68.4)
        self.assertAlmostEqual(fit.centerLocalCm.X, -70.382)
        self.assertAlmostEqual(fit.centerLocalCm.Z, 29.8)
        self.assertAlmostEqual(fit.matingSideBoundLocalCm.X, -62.424)
        self.assertAlmostEqual(fit.backSideBoundLocalCm.X, -78.340)
        self.lua.execute("outward=true")
        fit = self.lua.eval("probe:inspect(preview).renderedMeshFit")
        self.assertAlmostEqual(fit.planeErrorDeg, 0.0)
        self.assertAlmostEqual(fit.matingFaceErrorDeg, 0.0)
        self.assertAlmostEqual(fit.markUpLocal.Z, 1.0)
        self.assertAlmostEqual(fit.markUpErrorDeg, 0.0)
        self.assertAlmostEqual(fit.matingSideBeyondPivotCm, 5.976)
        self.assertAlmostEqual(fit.backSideBeyondPivotCm, -9.940)
        self.lua.execute("wrongPlane=true")
        fit = self.lua.eval("probe:inspect(preview).renderedMeshFit")
        self.assertAlmostEqual(fit.shortAxisLocal.Y, -1.0)
        self.assertAlmostEqual(fit.planeErrorDeg, 90.0)
        self.lua.execute("view.mesh.StaticMesh.GetBounds=nil")
        fit = self.lua.eval("probe:inspect(preview).renderedMeshFit")
        self.assertEqual(fit.status, "axis_only")
        self.assertIsNone(fit.centerLocalCm)

    def test_missing_mesh_transform_does_not_substitute_requested_rotation(self):
        fit = self.lua.eval("probe:mount(preview).renderedMeshFit")
        self.assertEqual(fit.status, "unavailable")
        self.assertIsNone(fit.planeErrorDeg)
        self.assertIsNone(fit.shortAxisLocal)

    def test_missing_native_api_creates_identifiable_visual_only_fallback(self):
        self.lua.execute('objects["/Script/Voyage.VoyageModuleSocketViewComponent"]=nil')
        row = self.lua.eval("probe:mount(preview)")
        self.assertEqual(row.status, "visual_only")
        self.assertTrue(row.visual)
        self.assertFalse(row.registered)
        self.assertIsNone(row.connected)
        self.assertIsNotNone(row.detail)
        self.assertTrue(self.lua.eval("probe:before_remove(preview).allowed"))

    def test_incomplete_socket_no_duplicate_and_no_foreign_reuse(self):
        self.lua.execute("failReload=true; probe:mount(preview)")
        row = self.lua.eval("probe:inspect(preview)")
        self.assertEqual(row.status, "socket_setup_incomplete")
        self.assertFalse(row.visual)
        self.assertEqual(self.lua.eval("additions"), 2)
        self.lua.execute('other=object("/Test.Preview")')
        self.assertEqual(self.lua.eval("probe:inspect(other).status"), "no_preview")
        self.assertFalse(self.lua.eval("probe:before_remove(other).allowed"))
        self.lua.execute("probe:reset()")
        self.assertEqual(self.lua.eval("probe:inspect(preview).status"), "no_preview")


if __name__ == "__main__":
    unittest.main()
