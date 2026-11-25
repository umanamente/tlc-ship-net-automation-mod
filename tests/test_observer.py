"""Run the real passive net observer against read-only Unreal object doubles."""

from pathlib import Path
import unittest

from lupa.lua54 import LuaRuntime


SCRIPTS = Path(__file__).resolve().parents[1] / "src" / "ShipNetAutomation" / "Scripts"

WORLD = r"""
local BOAT = "/Script/Voyage.VoyageBoatPawn"
local BARGE = "/Game/Blueprints/Vehicles/BP_Boat_Barge.BP_Boat_Barge_C"
local NET = "/Script/Voyage.VoyageModuleFishingActor"
local STOCK_NET = "/Game/Blueprints/Modules/Utility/Boat/BP_Module_Fishing.BP_Module_Fishing_C"
local INVENTORY = "/Script/Voyage.VoyageBaseInventoryComponent"
local CONTAINER = "/Game/Blueprints/Interactives/Containers/BP_Container_Base.BP_Container_Base_C"
local methods, objects = {}, {}
data, scans, writes = {}, 0, {}
local serial = 0
local now = 1000
os.time = function() return now end
function advance(n) now = now + n end
function actor(name, classes)
    serial = serial + 1
    local values = {path = "/Test." .. name, address = serial, classes = classes or {}}
    local obj = setmetatable({}, {
        __index = function(self, key)
            if values[key] ~= nil then return values[key] end
            return methods[key]
        end,
        __newindex = function(self, key)
            table.insert(writes, key)
            error("unexpected gameplay write " .. key)
        end,
    })
    objects[values.path], data[obj] = obj, values
    return obj
end
function methods:IsValid() return not self.invalid end
function methods:HasAnyFlags() return false end
function methods:GetAddress() return self.address end
function methods:GetFullName() return "Class " .. self.path end
function methods:IsA(key) return self.classes[key] or false end
function methods:GetWorld() return self.world or world end
function methods:GetParentActor() return self.parent end
function methods:GetAttachParentActor() return self.attachment end
function methods:GetOwner() return self.owner end
function methods:IsLocalController() return true end
function methods:GetMovementBaseActor() return self.base end
function remote_param(value)
    -- The pinned UE4SS array pusher exposes each ObjectProperty via :get().
    return {get = function() return value end}
end
function methods:GetAllModules(result)
    for i, component in ipairs(self.modules or {}) do result[i] = remote_param(component) end
end
function methods:IsNetDropped() return self.NetDropped end
for _, key in ipairs({"LiftNet", "DropNet", "PerformLoot", "TransferSlot", "TransferItems",
        "AddItem", "RemoveItem", "SetInteractionEnabled", "ProcessEvent"}) do
    methods[key] = function()
        table.insert(writes, key)
        error("unexpected gameplay action " .. key)
    end
end
function StaticFindObject(path) return objects[path] end
function FindFirstOf(class)
    assert(class == "VoyagePlayerController")
    return controller
end
function FindAllOf(class)
    scans = scans + 1
    if class == "VoyageBoatPawn" then return boats end
    assert(class == "VoyageModuleFishingActor", class)
    return nets
end
world, controller, pawn = actor("World"), actor("Controller"), actor("Pawn")
ship = actor("Ship", {[BOAT]=true, [BARGE]=true})
net = actor("Net", {[NET]=true, [STOCK_NET]=true})
container = actor("Container", {[CONTAINER]=true})
inventory = actor("Inventory", {[INVENTORY]=true})
local component = actor("NetModuleComponent")
data[controller].Pawn = pawn
data[pawn].base, data[component].owner = ship, net
data[ship].modules = {component}
data[net].parent, data[net].InventoryComponent = ship, inventory
data[net].ContainerChildActor = {ChildActor = container}
data[net].NetDropped, data[net].FullyRaised, data[net].NetState = true, true, 2
data[net].NetWeight, data[net].InventoryMaxWeight = 12.5, 40
data[container].InteractEnabled, data[container].IsClosed = true, true
data[inventory].owner = container
entries = {{5, {AssetName="Iron", AssetType={Name="Scrap"}, Data={ItemCount=3}}},
           {1, {AssetName="Wire", AssetType={Name="Scrap"}, Data={ItemCount=4}}}}
data[inventory].Items = {ForEach = function(self, visit)
    for _, row in ipairs(entries) do
        if visit({get=function() return row[1] end}, {get=function() return row[2] end}) then break end
    end
end}
boats, nets = {ship}, {net}
function other_ship()
    local other = actor("SecondShip", {[BOAT]=true, [BARGE]=true})
    boats[2] = other
    return other
end
function other_net(boat)
    local other = actor("SecondNet", {[NET]=true, [STOCK_NET]=true})
    data[other].parent = boat
    nets[2] = other
    return other
end
"""


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts = SCRIPTS.as_posix()
        self.lua.execute('package.path = scripts .. "/?.lua;" .. package.path')
        self.lua.execute(WORLD)
        self.lua.execute('observer = require("shipnet.observer").new()')

    def sample(self):
        return self.lua.eval("observer:sample()")

    def tearDown(self):
        self.assertEqual(self.lua.eval("#writes"), 0, "observer attempted a gameplay mutation")

    def test_bound_net_returns_stock_indicators_and_all_stacks_in_slot_order(self):
        row = self.sample()
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["shipSelection"], "player_boat")
        self.assertTrue(row["interactionEnabled"])
        self.assertEqual(row["netWeight"], 12.5)
        self.assertTrue(row["inventoryReady"])
        self.assertEqual(row["inventoryTotalCount"], 7)
        self.assertEqual(
            [(item["slot"], item["itemId"], item["count"]) for item in row["items"].values()],
            [(1, "Scrap:Wire", 4), (5, "Scrap:Iron", 3)],
        )
        scans = self.lua.globals().scans
        self.lua.execute("entries[1][2].Data.ItemCount = 2; data[net].NetWeight = 10; data[net].NetDropped = false")
        updated = self.sample()
        self.assertEqual(updated["identity"], row["identity"])
        self.assertEqual(updated["inventoryTotalCount"], 6)
        self.assertEqual(updated["netWeight"], 10)
        self.assertIs(updated["netDropped"], False)
        self.assertIs(updated["isNetDropped"], False)
        self.assertEqual(self.lua.globals().scans, scans)

    def test_unavailable_player_or_world_yields_no_inventory_and_recovers(self):
        self.lua.execute("data[controller].Pawn = nil")
        self.assertEqual(self.sample()["status"], "no_world")
        self.lua.execute("data[controller].Pawn = pawn; advance(4)")
        self.assertTrue(self.sample()["inventoryReady"])

    def test_ambiguous_offboard_ship_does_not_select_a_nearby_net(self):
        self.lua.execute("data[pawn].base = nil; other_net(other_ship())")
        row = self.sample()
        self.assertEqual(row["status"], "ambiguous_ship")
        self.assertIsNone(row["identity"])
        self.assertIsNone(row["items"])

    def test_observes_only_net_on_players_ship_and_rejects_two_on_same_ship(self):
        self.lua.execute("second = other_ship(); secondNet = other_net(second)")
        self.assertEqual(self.sample()["status"], "ready")
        self.lua.execute("data[secondNet].parent = ship; advance(31)")
        row = self.sample()
        self.assertEqual(row["status"], "ambiguous_net")
        self.assertIsNone(row["items"])

    def test_native_out_array_dereferences_components_before_reading_their_owners(self):
        self.lua.execute("""
            local component = data[ship].modules[1]
            local invalid = actor("DeadComponent")
            data[invalid].invalid = true
            data[net].parent = nil
            data[ship].GetAllModules = function(self, out)
                -- Reproduce the original get-only wrapper and a mix of absent references.
                out[1] = remote_param(nil)
                out[2] = remote_param(invalid)
                out[3] = {get = function() error("expired parameter") end}
                out[4] = false
                out[5] = {}
                out[6] = remote_param(component)
            end
        """)
        row = self.sample()
        self.assertEqual(row["status"], "ready", row["detail"])
        self.assertEqual(row["netSelection"], "ship_module")
        self.assertIs(row["netAssociationVerified"], True)
        self.assertTrue(row["interactionEnabled"])
        self.assertEqual(row["netWeight"], 12.5)
        self.assertEqual(row["inventoryTotalCount"], 7)
        self.assertIsNone(row["detail"])

    def test_nonobject_optional_attachment_does_not_hide_net_and_inventory_readings(self):
        self.lua.execute("""
            data[ship].modules = {}
            data[net].parent = {}
            data[net].attachment = ship
            data[net].owner = false
        """)
        row = self.sample()
        self.assertEqual(row["status"], "ready", row["detail"])
        self.assertEqual(row["netSelection"], "ship_ancestry")
        self.assertIs(row["netAssociationVerified"], True)
        self.assertEqual(row["inventoryTotalCount"], 7)
        self.assertIs(row["fullyRaised"], True)

    def test_unexpected_discovery_error_keeps_its_reason_through_backoff_and_recovers(self):
        self.lua.execute("""
            local actual = FindFirstOf
            failed_lookups = 0
            function FindFirstOf(class)
                failed_lookups = failed_lookups + 1
                error("synthetic controller lookup failure")
            end
            function recover_lookup() FindFirstOf = actual end
        """)
        first = self.sample()
        self.assertEqual(first["status"], "error")
        self.assertIn("synthetic controller lookup failure", first["detail"])
        self.lua.execute("advance(1)")
        for _ in range(5):
            during = self.sample()
            self.assertEqual(during["status"], first["status"])
            self.assertEqual(during["detail"], first["detail"])
        self.assertEqual(self.lua.globals().failed_lookups, 1)
        self.lua.execute("recover_lookup(); advance(30)")
        recovered = self.sample()
        self.assertEqual(recovered["status"], "ready")
        self.assertIsNone(recovered["detail"])

    def test_unrelated_inventory_owner_is_unavailable_and_never_reported_as_empty(self):
        self.lua.execute("data[inventory].owner = other_ship()")
        row = self.sample()
        self.assertFalse(row["inventoryReady"])
        self.assertEqual(row["inventoryError"], "unverified_inventory_owner")
        self.assertIsNone(row["inventoryTotalCount"])

    def test_single_unbound_stock_net_is_explicitly_identified_as_unverified(self):
        self.lua.execute("data[net].parent = nil; data[ship].modules = {}")
        row = self.sample()
        self.assertEqual(row["status"], "ready")
        self.assertFalse(row["netAssociationVerified"])
        self.assertEqual(row["netSelection"], "only_world_net_unverified")
        self.assertEqual(row["inventoryTotalCount"], 7)

    def test_unbound_candidates_do_not_override_ambiguous_net_or_ship_ownership(self):
        self.lua.execute("data[net].parent=nil; data[ship].modules={}; other_net(nil)")
        self.assertIsNone(self.sample()["items"])
        self.lua.execute("nets={net}; other_ship(); observer:reset()")
        self.assertIsNone(self.sample()["items"])

    def test_distinguishes_empty_inventory_from_an_unreadable_stack(self):
        self.lua.execute("entries = {}")
        row = self.sample()
        self.assertTrue(row["inventoryReady"])
        self.assertEqual(row["inventoryTotalCount"], 0)
        self.lua.execute('entries = {{1, {AssetName = "Wire", Data = {ItemCount=-1}}}}')
        failed = self.sample()
        self.assertFalse(failed["inventoryReady"])
        self.assertIsNone(failed["items"])
        self.assertIsNone(failed["inventoryTotalCount"])


if __name__ == "__main__":
    unittest.main()
