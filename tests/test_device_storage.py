"""The native device box is save-owned and independent of the disposable mesh."""

import unittest

from lupa.lua54 import LuaRuntime

from test_observer import SCRIPTS


FIXTURE = """
world={}; objects={}; boxes={}; created=0
local serial=0
local function obj(path,class,outer)
    serial=serial+1
    local a={path=path,cls=class,outer=outer,id=serial,tags={}}
    objects[path]=a
    function a:IsValid() return true end
    function a:GetAddress() return self.id end
    function a:IsA(name) return self.cls==name end
    function a:HasAnyFlags() return false end
    function a:GetFullName() return "Object "..self.path end
    function a:GetOwner() return self.outer end
    function a:GetWorld() return self.world or world end
    function a:GetAttachParentActor() return self.parent end
    function a:GetTransform() return {owner=self} end
    function a:K2_GetRootComponent() return {actor=self} end
    function a:ActorHasTag(t)
        for _,v in ipairs(self.Tags) do if v:ToString()==t:ToString() then return true end end
        return false
    end
    a.Tags={GetArrayNum=function(s) return #s end}
    return a
end
world=obj("/World","World")
local barge="/Game/Blueprints/Vehicles/BP_Boat_Barge.BP_Boat_Barge_C"
local boxclass="/Game/Blueprints/Interactives/Containers/BP_Inventory_PlayerBox_Small.BP_Inventory_PlayerBox_Small_C"
local invclass="/Script/Voyage.VoyageInventoryWeightLimitedComponent"
obj(boxclass,"Class")
ship=obj("/World.Barge",barge)
otherShip=obj("/World.Barge2",barge)
function newPreview(ship) local p=obj("/World.Preview"..serial,"Mesh");p.parent=ship;return p end
preview=newPreview(ship)
pc=obj("/World.PC","PC")
function pc:IsLocalController() return true end
function pc:OnPlayerInteraction(actor,interactive) assert(interactive.outer==actor); self.opened=actor end
function FName(s) return {ToString=function() return s end} end
function FText(s) return s end
function StaticFindObject(p) return objects[p] end
function FindAllOf(_) return boxes end
sub=obj("/Script/Voyage.Default__VoyagePersistentSubsystem","sub")
function sub:GetPersistentSubsystem(w) assert(w==world); return self end
function sub:GetPersistentActorComponent(a) return {PersistentUniqueIdRuntime=a.nativeId or a.id} end
function sub:IsPersistentActor(a) return a.persistent==true end
function sub:AttachActor(box,root,fx)
    if attachFails then return false end
    assert(not fx); box.parent=root.actor; return true
end
function sub:SerializeActor(a) a.serialized=true; return true end
misc=obj("/Script/Voyage.Default__VoyageMiscBlueprintFunctionLibrary","misc")
function misc:SpawnRuntimeActorFromClass(w,cls,at,flags,template,ship)
    assert(w==world and cls==objects[boxclass] and flags.Value==0 and template==nil)
    assert(at.owner.parent==ship)
    created=created+1
    local box=obj("/World.Box"..created,boxclass,ship);boxes[#boxes+1]=box
    box.persistent=true;box.IsLocked=false
    function box:SetActorHiddenInGame(v) self.hidden=v end
    function box:SetActorEnableCollision(v) self.collision=v end
    local iv=obj(box.path..".Inventory",invclass,box); iv.Access=2; iv.weight=0
    function iv:SetInventoryName(name) self.name=name end
    function iv:GetTotalWeight() return self.weight end
    function iv:GetCurrentMaxWeightLimit() return 50 end
    function iv:GetPercentWeightUsed() return self.weight/50 end
    function iv:GetTotalNumItems() return self.weight>0 and 1 or 0 end
    box.VoyageInventoryWeightLimited=iv;box.InteractiveObject=obj(box.path..".Interactive","interaction",box)
    return box
end
Storage=require("shipnet.device_storage")
s=Storage.new()
"""


class DeviceStorageTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts = SCRIPTS.as_posix()
        self.lua.execute('package.path=scripts.."/?.lua;"..package.path')
        self.lua.execute(FIXTURE)

    def test_real_owner_native_ui_and_measured_capacity(self):
        before = self.lua.eval("s:inspect(preview,ship)")
        self.assertEqual(before.status, "uncreated")
        self.assertEqual(before.fillRatio, 0)
        ok, report = self.lua.eval("s:open(pc,preview,ship)")
        self.assertTrue(ok, report)
        self.assertEqual(report.capacityKg, 50)
        self.lua.execute("assert(pc.opened==boxes[1] and ship.serialized and boxes[1].serialized); boxes[1].VoyageInventoryWeightLimited.weight=6")
        report = self.lua.eval("s:inspect(preview,ship)")
        self.assertAlmostEqual(report.fillRatio, 0.12)
        self.assertEqual(report.itemCount, 1)

    def test_rebuilt_preview_and_reloaded_storage_instance_reuse_contents(self):
        self.lua.execute("assert(s:open(pc,preview,ship)); boxes[1].VoyageInventoryWeightLimited.weight=6; s=Storage.new(); preview=newPreview(ship)")
        ok, report = self.lua.eval("s:open(pc,preview,ship)")
        self.assertTrue(ok, report)
        self.assertEqual(report.weightKg, 6)
        self.assertEqual(self.lua.eval("created"), 1)
        # Reload can change mutable actor tags; the ship's saved native ID still identifies its box.
        self.lua.execute("table.remove(boxes[1].Tags); s=Storage.new()")
        self.assertEqual(self.lua.eval("s:inspect(preview,ship).weightKg"), 6)

    def test_missing_or_detached_link_does_not_duplicate_or_retarget(self):
        self.lua.execute("assert(s:open(pc,preview,ship)); local box=boxes[1]; boxes={}; s=Storage.new()")
        ok, _ = self.lua.eval("s:open(pc,preview,ship)")
        self.assertFalse(ok)
        self.assertEqual(self.lua.eval("created"), 1)
        self.lua.execute("boxes[1]=objects['/World.Box1']; boxes[1].parent=otherShip")
        ok, _ = self.lua.eval("s:open(pc,preview,ship)")
        self.assertFalse(ok)
        self.assertEqual(self.lua.eval("created"), 1)

    def test_distinct_barges_and_worlds(self):
        self.lua.execute("assert(s:open(pc,preview,ship)); second=newPreview(otherShip); assert(s:open(pc,second,otherShip))")
        self.assertEqual(self.lua.eval("created"), 2)
        ok, _ = self.lua.eval("s:open(pc,preview,otherShip)")
        self.assertFalse(ok)
        self.lua.execute("pc.world=otherShip")
        ok, _ = self.lua.eval("s:open(pc,preview,ship)")
        self.assertFalse(ok)

    def test_built_inventory_is_owned_by_the_purchased_controller(self):
        self.lua.execute("""
            carrier=misc:SpawnRuntimeActorFromClass(world,objects['/Game/Blueprints/Interactives/Containers/BP_Inventory_PlayerBox_Small.BP_Inventory_PlayerBox_Small_C'],preview:GetTransform(),{Value=0},nil,ship)
            carrier.VoyageInventoryWeightLimited.weight=6
            built=Storage.forCarrier(carrier,sub)
        """)
        ok, report=self.lua.eval("built:open(pc,carrier,ship)")
        self.assertTrue(ok)
        self.assertEqual(report.weightKg,6)
        self.assertEqual(self.lua.eval("carrier.VoyageInventoryWeightLimited.Access"),0)
        self.assertTrue(self.lua.eval("pc.opened==carrier and carrier.hidden==nil and #ship.Tags==0"))
        self.assertFalse(self.lua.eval("built:open(pc,preview,ship)")[0])
        self.assertEqual(self.lua.eval("created"),1)

    def test_recover_only_an_existing_legacy_box_on_the_bound_controllers_ship(self):
        self.lua.execute("""
            manager=require("shipnet.built_controller").new({handlers={}})
            carrier=newPreview(ship)
            local function ref(obj) return {path=obj.path,address=obj:GetAddress()} end
            local runtime=manager.runtime
            runtime.built=true;runtime.actorRef=ref(carrier);runtime.mountRef=ref(ship);runtime.shipRef=ref(ship)
        """)
        self.assertFalse(self.lua.eval("manager:hasLegacyStorage()"))
        self.assertFalse(self.lua.eval("manager:openLegacyStorage(pc)")[0])
        self.assertEqual(self.lua.eval("created"),0)
        self.lua.execute("assert(s:open(pc,preview,ship)); boxes[1].VoyageInventoryWeightLimited.weight=6")
        self.assertTrue(self.lua.eval("manager:hasLegacyStorage()"))
        ok, report=self.lua.eval("manager:openLegacyStorage(pc)")
        self.assertTrue(ok)
        self.assertEqual(report.weightKg,6)
        self.assertTrue(self.lua.eval("pc.opened==boxes[1] and created==1"))
        self.lua.execute("boxes[1].parent=otherShip")
        self.assertFalse(self.lua.eval("manager:hasLegacyStorage()"))
        self.assertFalse(self.lua.eval("manager:openLegacyStorage(pc)")[0])
        self.lua.execute("carrier.parent=nil")
        self.assertFalse(self.lua.eval("manager:openLegacyStorage(pc)")[0])
        self.assertEqual(self.lua.eval("created"),1)

    def test_partial_attach_retries_only_its_original_native_actor(self):
        self.lua.execute("attachFails=true")
        ok, _ = self.lua.eval("s:open(pc,preview,ship)")
        self.assertFalse(ok)
        self.lua.execute("attachFails=false")
        ok, report = self.lua.eval("s:open(pc,preview,ship)")
        self.assertTrue(ok, report)
        self.assertEqual(self.lua.eval("created"), 1)


if __name__ == "__main__":
    unittest.main()
