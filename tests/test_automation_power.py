"""Exercise the real Lua power meter with finite external supplies and native-style cables."""
import unittest

from lupa.lua54 import LuaRuntime

from test_observer import SCRIPTS


WORLD = """
local nextId = 0
local function object(owner)
    nextId = nextId + 1
    local o = {id = nextId, owner = owner}
    function o:GetAddress() return self.id end
    function o:IsValid() return not self.invalid end
    function o:GetOwner() return self.owner end
    return o
end

function cabinet()
    local box = object()
    local module, inlet = object(box), object(box)
    box.WinchPowerInlet = inlet
    module.ConfigData = {bAcceptResourceOffer = false, bAcceptResourceOfferOff = false,
        bAcceptResourceOfferProduction = false}
    module.bHasInitialized = true
    module.amount, module.capacity, module.spent, module.switches = 0, 8, 0, 0
    function module:SetReceiveResourcesState(enabled)
        self.switches = self.switches + 1
        self.ConfigData.bAcceptResourceOffer = enabled
    end
    function module:GetResourceAmount(res) assert(res == 0); return self.amount end
    function module:GetMaxResourceAmount(res) assert(res == 0); return self.capacity end
    function module:ConnectionsChanged() end
    function module:RemoveResource(res, amount, removal)
        assert(res == 0 and removal == 1)
        if self.refuse or amount > self.amount then return false end
        if not self.noop then
            self.amount = self.amount - amount
            self.spent = self.spent + amount
        end
        return true
    end
    inlet.Port = {Type = 1, ResourceType = 0}
    function inlet:GetModule() return module end
    function inlet:GetConnectedSocket() return self.peer end
    function inlet:IsSocketConnected() return self.peer ~= nil end
    return box, module, inlet
end

function source(inlet, energy)
    local battery = object()
    local outlet = object(battery)
    local supply = object(battery)
    supply.bHasInitialized = true
    function supply:ConnectionsChanged() end
    function outlet:GetModule() return supply end
    battery.amount = energy
    inlet.peer, outlet.peer = outlet, inlet
    function outlet:GetConnectedSocket() return self.peer end
    return battery
end

function deliver(module, inlet, maxAmount)
    if not inlet.peer or not module.ConfigData.bAcceptResourceOfferOff then return end
    local battery = inlet.peer:GetOwner()
    local moved = math.min(maxAmount, battery.amount, module.capacity - module.amount)
    battery.amount = battery.amount - moved
    module.amount = module.amount + moved
end

-- Two saved cables connect the battery to a passive extender and the extender
-- to the cabinet. A stale connection cache does not remove either cable.
function savedGrid(energy, offersEnabled, cacheReady)
    local extender = object()
    local junction, output, input = object(extender), object(extender), object(extender)
    junction.bHasInitialized = true
    output.Port = {Type=2, ResourceType=0}
    function output:GetModule() return junction end
    function output:GetConnectedSocket() return self.peer end
    function output:IsSocketConnected() return self.peer ~= nil end
    output.peer, inlet.peer = inlet, output
    local upstream = source(input, energy)
    local grid = {cabinetEvents=0, extenderEvents=0, battery=upstream, output=output}
    local cabinetReady, extenderReady = cacheReady, cacheReady
    function module:ConnectionsChanged()
        grid.cabinetEvents = grid.cabinetEvents + 1
        cabinetReady = true
    end
    function junction:ConnectionsChanged()
        grid.extenderEvents = grid.extenderEvents + 1
        extenderReady = true
    end
    for key in pairs(module.ConfigData) do module.ConfigData[key] = offersEnabled end
    function grid:run(mode, polls)
        local paid = 0
        for i=1,polls do
            if cabinetReady and extenderReady and inlet.peer == output and output.peer == inlet
                and input.peer and input.peer.peer == input and module.ConfigData.bAcceptResourceOfferOff then
                local received = math.min(upstream.amount, 1, module.capacity - module.amount)
                module.amount = module.amount + received
                upstream.amount = upstream.amount - received
            end
            if tick(mode) then paid = paid + 1 end
        end
        return paid
    end
    return grid
end

box, module, inlet = cabinet()
battery = source(inlet, 100)
meter = require("shipnet.automation_power").new()
function tick(mode, dt) return meter:consume(box, dt or .25, mode) end
"""


class AutomationPowerTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts = SCRIPTS.as_posix()
        self.lua.execute('package.path = scripts .. "/?.lua;" .. package.path')
        self.lua.execute(WORLD)

    def test_loaded_extender_restarts_supply_without_replugging_either_cable(self):
        for saved_offers in (True, False):
            with self.subTest(saved_offers=saved_offers):
                self.lua.execute("box,module,inlet=cabinet(); meter:reset()")
                self.lua.globals().saved_offers = saved_offers
                self.lua.execute("""
                    grid=savedGrid(100, saved_offers, false)
                    assert(grid:run('standby', 2)==0 and grid.cabinetEvents==0)
                    assert(grid:run('standby', 1)==0 and grid.cabinetEvents==1 and grid.extenderEvents==1)
                    assert(grid:run('standby', 1)==1)
                    assert(grid:run('active', 8)==8 and grid.battery.amount<100)
                    assert(inlet:GetConnectedSocket()==grid.output and grid.output:GetConnectedSocket()==inlet)
                    assert(grid.cabinetEvents==1 and grid.extenderEvents==1)
                """)

    def test_empty_source_behind_extender_never_spends_saved_energy_as_work(self):
        self.lua.execute("""
            grid=savedGrid(0, true, false)
            module.amount=7
            assert(grid:run('active', 240)==0)
            assert(grid.cabinetEvents==1 and grid.extenderEvents==1)
            grid.battery.amount=10
            assert(grid:run('active', 8)>0)
        """)

    def test_off_disconnected_or_one_sided_cable_never_refreshes_extender(self):
        self.lua.execute("""
            grid=savedGrid(100, false, false)
            module.amount=1
            assert(grid:run('off', 48)==0)
            inlet.peer=nil
            assert(grid:run('standby', 48)==0)
            inlet.peer=grid.output; grid.output.peer=nil
            assert(grid:run('active', 48)==0)
            assert(grid.cabinetEvents==0 and grid.extenderEvents==0 and grid.battery.amount==100)
        """)

    def test_healthy_extender_keeps_delivering_without_repeated_notifications(self):
        self.lua.execute("""
            grid=savedGrid(100, false, true)
            assert(grid:run('standby', 48)>0 and grid:run('active', 8)==8)
            assert(grid.cabinetEvents==0 and grid.extenderEvents==0)
        """)

    def test_new_route_grace_applies_again_after_unplugging(self):
        self.lua.execute("""
            grid=savedGrid(100, true, true)
            assert(grid:run('standby',4)==3 and grid.cabinetEvents==0)
            inlet.peer=nil
            assert(grid:run('standby',1)==0)
            grid=savedGrid(100,true,false)
            assert(grid:run('standby',2)==0 and grid.cabinetEvents==0)
            assert(grid:run('standby',1)==0 and grid.cabinetEvents==1 and grid.extenderEvents==1)
            assert(grid:run('standby',1)==1)
        """)

    def test_late_native_cable_restore_logs_each_stage_once(self):
        self.lua.execute("""
            local events={}
            meter=require("shipnet.automation_power").new(function(message)
                events[#events+1]=message
            end)
            grid=savedGrid(100,true,false)
            inlet.peer=nil
            assert(grid:run('standby',120)==0 and #events==1)
            inlet.peer=grid.output
            assert(grid:run('standby',48)>0)
            assert(#events==3 and events[1]:find("waiting") and events[2]:find("grid update")
                and events[3]:find("supply confirmed"))
            assert(grid:run('standby',20)==20 and #events==3)
        """)

    def test_physical_supply_mode_costs_and_off(self):
        self.lua.execute("module.amount=.25")
        self.assertEqual(self.lua.eval("tick('off')"), (False, "off"))
        self.lua.execute("deliver(module, inlet, 8)")
        self.assertEqual(self.lua.eval("battery.amount"), 100)
        self.assertEqual(self.lua.eval("tick('standby')"), (False, "no_power"))
        self.assertTrue(self.lua.eval("module.ConfigData.bAcceptResourceOfferProduction"))
        self.lua.execute("""
            for i = 1, 40 do
                deliver(module, inlet, .125)
                assert(tick('standby'))
            end
            for i = 1, 40 do
                deliver(module, inlet, 1)
                assert(tick('active'))
            end
        """)
        self.assertEqual(self.lua.eval("100.25 - (battery.amount + module.amount)"), 45)
        self.assertEqual(self.lua.eval("module.spent"), 45)
        self.assertEqual(self.lua.eval("module.switches"), 1)
        self.assertEqual(self.lua.eval("tick('off')"), (False, "off"))
        self.assertFalse(self.lua.eval("module.ConfigData.bAcceptResourceOfferProduction"))
        self.lua.execute("deliver(module, inlet, 8)")
        self.assertEqual(self.lua.eval("battery.amount"), 55)
        self.assertEqual(self.lua.eval("module.switches"), 2)

    def test_empty_off_receiver_wakes_from_real_supply_then_stops_accepting(self):
        self.lua.execute("""
            grid=savedGrid(0,false,false)
            assert(grid:run('off',32)==0 and module.amount==0 and module.spent==0)
            assert(grid.cabinetEvents==1 and grid.extenderEvents==1)
            grid.battery.amount=100
            assert(grid:run('off',24)==0 and module.amount==1 and grid.battery.amount==99)
            assert(not module.ConfigData.bAcceptResourceOfferOff and module.spent==0)
            module.amount=0;grid.output.peer=nil
            assert(grid:run('off',20)==0 and module.amount==0 and grid.battery.amount==99)
            grid.output.peer=inlet
            assert(grid:run('off',20)==0 and module.amount==1 and grid.battery.amount==98)
            assert(not module.ConfigData.bAcceptResourceOfferOff and module.spent==0)
        """)

    def test_dead_replacement_and_disconnection_cannot_spend_stale_reserve(self):
        self.lua.execute("tick('active'); deliver(module, inlet, 8); assert(tick('active'))")
        self.lua.execute("inlet.peer = nil")
        self.assertEqual(self.lua.eval("tick('active')"), (False, "disconnected"))
        self.lua.execute("battery = source(inlet, 0)")
        self.lua.execute("for i = 1, 20 do deliver(module, inlet, 8); assert(not tick('active')) end")
        self.assertEqual(self.lua.eval("module.spent"), 1)
        self.lua.execute("battery.amount = 8; deliver(module, inlet, 8)")
        self.assertEqual(self.lua.eval("tick('active')"), (True, "powered"))

    def test_full_stale_buffer_bounded_request_and_brownout(self):
        self.lua.execute("module.amount = 8; battery.amount = 0")
        self.lua.execute("for i = 1, 20 do deliver(module, inlet, 2); assert(not tick('active')) end")
        self.assertEqual(self.lua.eval("module.amount"), 7)
        self.lua.execute("battery.amount = 1; deliver(module, inlet, .4)")
        self.assertEqual(self.lua.eval("tick('active')"), (False, "no_power"))
        self.lua.execute("deliver(module, inlet, .6)")
        self.assertEqual(self.lua.eval("tick('active')"), (True, "powered"))
        self.assertEqual(self.lua.eval("tick('active')"), (False, "no_power"))

    def test_zero_elapsed_failed_debits_and_missing_endpoints(self):
        self.lua.execute("tick('active'); deliver(module, inlet, 4)")
        self.assertEqual(self.lua.eval("tick('active', 0)"), (False, "no_elapsed"))
        self.assertEqual(self.lua.eval("tick('active', math.huge)"), (False, "no_elapsed"))
        self.assertEqual(self.lua.eval("tick('active', 3)"), (False, "no_power"))
        self.lua.execute("module.refuse = true")
        self.assertEqual(self.lua.eval("tick('active')"), (False, "no_power"))
        self.lua.execute("module.refuse = false; module.noop = true")
        self.assertEqual(self.lua.eval("tick('active')"), (False, "no_power"))
        self.lua.execute("module.noop = false")
        self.assertEqual(self.lua.eval("tick('active')"), (True, "powered"))
        self.lua.execute("inlet.peer.peer = nil")
        self.assertEqual(self.lua.eval("tick('active')"), (False, "disconnected"))
        self.lua.execute("module.invalid = true")
        self.assertEqual(self.lua.eval("tick('active')"), (False, "not_ready"))

    def test_reset_and_independent_cabinets(self):
        self.lua.execute("""
            tick('standby')
            other, second, socket = cabinet()
            source(socket, 100)
            meter:consume(other, .25, 'active')
            deliver(module, inlet, 5)
            assert(tick('standby'))
            assert(not meter:consume(other, .25, 'active'))
            deliver(second, socket, 1)
            assert(meter:consume(other, .25, 'active'))
            meter:reset()
        """)
        self.assertEqual(self.lua.eval("tick('standby')"), (False, "no_power"))
        self.assertEqual(self.lua.eval("meter:consume(other, .25, 'active')"), (False, "no_power"))
