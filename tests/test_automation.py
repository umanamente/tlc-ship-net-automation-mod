"""Check the automatic winch cycle against changing, game-owned state."""
import unittest
from lupa.lua54 import LuaRuntime
from test_observer import SCRIPTS


class AutomationFixture(unittest.TestCase):
    basic = False

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().script_root = SCRIPTS.as_posix()
        self.lua.globals().basicCheck = self.basic
        self.lua.execute(r"""
            package.path=script_root.."/?.lua;"..package.path
            charge=true; used={}; commands={}; moved=0
            cabinet={WinchAutomationEnabled=true}
            net={NetDropped=true,FullyRaised=false,NetState=2}
            switch={on=true,IsOn=function(s) return s.on end}
            catch={weight=28,capacity=30,space=true,ready=false,remaining=3,status="available"}
            time=0
            local power={consume=function(_,actor,seconds,mode)
                assert(actor==cabinet)
                if mode~="off" and seconds==0 then primed=mode;return false,"no_elapsed" end
                used[#used+1]=mode
                if mode=="off" then return false,"off" end
                return charge,charge and "powered" or "no_power"
            end,reset=function() end}
            package.loaded["shipnet.automation_power"]={new=function(_,fixed) fixedDraw=fixed;return power end}
            package.loaded["shipnet.automation_cargo"]={
                weight=function() return catch.weight,catch.capacity end,
                storageFreeWeight=function()
                    assert(not basicCheck, "Basic must never query cabinet weight")
                    return catch.freeKg or 50
                end,
                inspect=function()
                    assert(not basicCheck, "Basic must never query cabinet storage")
                    return catch
                end,
                drawerContents=function() if catch.ready then return catch.remaining end end,
                unload=function()
                    assert(charge and net.FullyRaised and catch.ready and catch.space)
                    catch.remaining=catch.remaining-1
                    catch.weight=catch.remaining==0 and 0 or catch.weight-1.25
                    moved=moved+1
                    return {status="moved",remaining=catch.remaining,movedKg=1.25}
                end,
            }
            function send(action)
                commands[#commands+1]=action
                return true
            end
            function loadCycle()
                cycle=require("shipnet.automation").new(nil,basicCheck)
            end
            loadCycle()
            function step(n, seconds)
                for i=1,n or 1 do
                    time=time+(seconds or .25)
                    cycle:tick(cabinet,net,switch,time,send)
                end
            end
            function deck()
                switch.on=false;net.NetDropped=false;net.FullyRaised=true;net.NetState=2
                catch.ready=true
            end
            step()
        """)


class AdvancedHaulTests(AutomationFixture):
    def test_first_poll_opens_receiver_before_running_the_cycle(self):
        self.lua.execute('assert(primed=="standby" and #used==0 and #commands==0)')

    def test_live_capacity_crosses_the_threshold_in_both_directions(self):
        self.lua.execute("""
            catch.freeKg=500
            catch.weight=29;step(12)
            catch.capacity=300;step(20)
            assert(#commands==0 and cycle.status=="Waiting for 299 kg")
            catch.weight=298.9999;step(16);assert(#commands==0)
            catch.weight=299;step(12);assert(#commands==0)
            step();assert(#commands==1 and commands[1]=="raise")

            loadCycle();step()
            catch.weight=2.125;step(16);assert(#commands==1)
            catch.capacity=3.125;step(12);assert(#commands==1)
            step();assert(#commands==2 and commands[2]=="raise")
        """)

    def test_each_fractional_increase_restarts_even_at_the_deadline(self):
        self.lua.execute("""
            catch.weight=29;step(12)
            catch.weight=29.875;step(8);assert(#commands==0)
            catch.weight=29.25;step()
            catch.weight=29.2501;step(12);assert(#commands==0)
            catch.weight=29.2502;step(12);assert(#commands==0)
            step();assert(#commands==1 and commands[1]=="raise")
        """)

    def test_fractional_growth_while_waiting_for_power(self):
        self.lua.execute("""
            charge=false;catch.weight=29;step(20);assert(#commands==0)
            catch.weight=29.01;step(4)
            charge=true;step(8);assert(#commands==0)
            step();assert(#commands==1 and commands[1]=="raise")
        """)

    def test_weight_can_fall_without_crossing_the_live_threshold(self):
        self.lua.execute("""
            catch.weight=29.75;step(6)
            catch.capacity=30.25;catch.weight=29.25;step(6);assert(#commands==0)
            step();assert(#commands==1 and commands[1]=="raise")
        """)

    def test_empty_small_and_unreadable_net(self):
        self.lua.execute("""
            catch.capacity=1;catch.weight=0;step(20)
            catch.capacity=.5;step(20);assert(#commands==0)
            catch.weight=.125;step(12)
            catch.weight=0;step()
            catch.weight=.125;step(12);assert(#commands==0)
            catch.capacity=nil;step(20)
            catch.capacity=0;step(20);assert(#commands==0)
            catch.capacity=.5;step(12);assert(#commands==0)
            step();assert(#commands==1 and commands[1]=="raise")
        """)

    def test_reload_uses_saved_switch_live_limit_and_fresh_wait(self):
        self.lua.execute("""
            catch.freeKg=500
            catch.weight=29;step(12)
            catch.capacity=300;loadCycle();step(20);assert(#commands==0)
            catch.weight=299;step(12)
            loadCycle();step();step(12);assert(#commands==0)
            cabinet.WinchAutomationEnabled=false;loadCycle();step(20)
            assert(#commands==0 and cycle.drawKW==0)
            cycle:setEnabled(cabinet,true);step();step(12);assert(#commands==0)
            step();assert(#commands==1 and commands[1]=="raise")
        """)


class BasicHaulTests(AdvancedHaulTests):
    basic = True


class AutomationTest(AutomationFixture):
    def test_basic_haul_waits_for_all_items_and_draws_half_a_kilowatt(self):
        self.lua.execute("""
            basicCheck=true;cycle=require("shipnet.automation").new(nil,true)
            assert(fixedDraw==.5)
            catch.weight=29.5;step();step(12);assert(#commands==0 and cycle.drawKW==.5)
            step();assert(#commands==1 and commands[1]=="raise" and cycle.drawKW==.5)
            switch.on=false;net.NetDropped=false;step(5);assert(not cycle.drawerWaitingSince)
            net.FullyRaised=true;step(5);assert(not cycle.drawerWaitingSince and #commands==1)
            catch.ready=true;step()
            local firstPulse=cycle.drawerWaitingSince
            catch.remaining=1;step(15)
            assert(firstPulse and cycle.drawerWaitingSince==firstPulse and moved==0 and #commands==1)
            catch.ready=false;step(2);assert(not cycle.drawerWaitingSince and #commands==1)
            catch.ready=true;catch.remaining=0;charge=false;step(5);assert(#commands==1)
            charge=true;step();assert(#commands==2 and commands[2]=="lower" and cycle.drawKW==.5 and moved==0)
        """)

    def test_basic_disabled_does_not_move_or_load_when_the_player_handles_the_lever(self):
        self.lua.execute("""
            basicCheck=true;cycle=require("shipnet.automation").new(nil,true)
            step();cycle:setEnabled(cabinet,false);deck();step(12)
            assert(#commands==0 and moved==0 and used[#used]=="off" and not cycle.drawerWaitingSince)
        """)

    def test_basic_starts_a_fresh_lowering_delay_when_player_empties_drawer_again(self):
        self.lua.execute("""
            basicCheck=true;loadCycle();deck();step(2)
            catch.remaining=0;step(4);assert(#commands==0)
            catch.remaining=1;step();assert(cycle.drawerWaitingSince)
            catch.remaining=0;step(4);assert(#commands==0 and moved==0)
            step();assert(#commands==1 and commands[1]=="lower")
        """)

    def test_both_delays_restart_if_drawer_access_is_lost(self):
        self.lua.execute("""
            deck();catch.remaining=1;step(4);assert(moved==0)
            catch.ready=false;step(5)
            catch.ready=true;step(4);assert(moved==0)
            step();assert(moved==1 and #commands==0)
            step(3);catch.ready=false;step(5)
            catch.ready=true;step(4);assert(#commands==0)
            step();assert(#commands==1 and commands[1]=="lower")
        """)

    def test_near_capacity_catch_one_command_each_way_and_real_empty_before_lower(self):
        self.lua.execute("""
            step(3); assert(#commands==0 and used[#used]=="standby")
            catch.weight=29.9; step(12); assert(#commands==0 and used[#used]=="standby")
            step(); assert(#commands==1 and commands[1]=="raise")
            switch.on=false; net.NetDropped=false; step(2); assert(moved==0)
            net.FullyRaised=true; step(2); assert(moved==0)
            catch.ready=true;step()
            step(12,.0625);assert(moved==0 and used[#used]=="standby")
            step();assert(moved==1)
            step(2);assert(moved==3 and #commands==1)
            step(15,.0625);assert(#commands==1 and used[#used]=="standby")
            step(1,.0625);assert(#commands==2 and commands[2]=="lower")
            net.FullyRaised=false; net.NetDropped=true; switch.on=true
            catch.ready=false; catch.weight=0; step(3)
            assert(#commands==2 and cabinet.WinchAutomationEnabled)
            catch.weight=29;catch.remaining=1;step(12);assert(#commands==2)
            step();assert(#commands==3 and commands[3]=="raise")
        """)

    def test_delay_requires_fresh_qualifying_weight_and_resets_on_lost_reading(self):
        self.lua.execute("""
            catch.weight=28.9999;step(20);assert(#commands==0)
            catch.weight=29;step(12);assert(#commands==0)
            catch.weight=28.99;step()
            catch.weight=30;step(12);assert(#commands==0)
            catch.weight=nil;step()
            catch.weight=29;step(8);catch.weight=29.9;step(4)
            assert(#commands==0 and cycle.status=="Confirming catch weight")
            step(8);assert(#commands==0)
            step();assert(#commands==1 and commands[1]=="raise")
        """)

    def test_delay_checks_net_storage_and_power_again_before_hauling(self):
        self.lua.execute("""
            catch.weight=29;step(12)
            net.NetDropped=false;step();assert(#commands==0)
            net.NetDropped=true;step(12);assert(#commands==0)
            catch.space=false;step();assert(#commands==0 and cycle.status=="Empty the cabinet")
            catch.space=true;charge=false;step(4);assert(#commands==0)
            charge=true;step();assert(#commands==1 and commands[1]=="raise")
        """)

    def test_stopping_during_delay_requires_a_new_confirmation_after_restart(self):
        self.lua.execute("""
            catch.weight=29.9;step(12);cycle:setEnabled(cabinet,false)
            step(20);assert(#commands==0)
            cycle:setEnabled(cabinet,true);step();step(12);assert(#commands==0)
            step();assert(#commands==1 and commands[1]=="raise")
        """)

    def test_power_loss_and_partial_storage(self):
        self.lua.execute("""
            charge=false;catch.weight=30;step(20);assert(#commands==0)
            charge=true;step();deck();step(5);assert(moved==1)
            catch.space=false;catch.weight=29;step(5);assert(moved==1 and #commands==1 and used[#used]=="standby")
            charge=false;catch.space=true;step(4);assert(moved==1 and #commands==1)
            charge=true;step(2);assert(catch.remaining==0)
            catch.space=false;step(3);assert(#commands==1)
            step();assert(#commands==2 and commands[2]=="lower")
        """)

    def test_early_haul_requires_exact_or_greater_weight_a_fitting_item_and_power(self):
        self.lua.execute("""
            catch.capacity=300;catch.weight=49.875;catch.freeKg=50
            step(20);assert(#commands==0)
            catch.weight=50;catch.space=false
            step();assert(#commands==0 and cycle.status=="Empty the cabinet")
            catch.space=true;charge=false
            step();assert(#commands==0)
            catch.freeKg=0;catch.space=false;charge=true
            step();assert(#commands==0)
            catch.freeKg=50;catch.space=true
            step();assert(#commands==1 and commands[1]=="raise")
        """)

    def test_automatic_haul_redeploys_with_remainder_and_does_not_repeat_at_full_cabinet(self):
        self.lua.execute("""
            catch.capacity=300;catch.weight=55;catch.freeKg=50
            step();assert(#commands==1 and commands[1]=="raise")
            deck()
            catch.weight=5;catch.remaining=4;catch.space=false;catch.freeKg=0
            step(4);assert(#commands==1 and moved==0)
            step();assert(#commands==2 and commands[2]=="lower")
            net.FullyRaised=false;net.NetDropped=true;switch.on=true;catch.ready=false
            catch.weight=6;step(20)
            assert(#commands==2 and catch.remaining==4 and cabinet.WinchAutomationEnabled)
            catch.freeKg=5;catch.space=true
            step();assert(#commands==3 and commands[3]=="raise")
        """)

    def test_raised_blocked_net_uses_live_capacity_and_rechecks_before_lowering(self):
        self.lua.execute("""
            deck();catch.capacity=300;catch.weight=299;catch.space=false;catch.freeKg=0
            step(12);assert(#commands==0 and cycle.status=="Empty the cabinet")
            catch.capacity=310;step(3);assert(#commands==0)
            catch.space=true;catch.freeKg=10;step()
            assert(#commands==0 and moved==1)
            catch.space=false;catch.freeKg=0;charge=false
            step(8);assert(#commands==0)
            charge=true;step();assert(#commands==1 and commands[1]=="lower")
        """)

    def test_cable_travel_then_standby_with_netdown_still_selected(self):
        self.lua.execute("""
            net.NetState=0;net.MaxLength=2000;net.CurrentLength=600;step(4)
            assert(used[#used]=="standby")
            for i=1,4 do net.CurrentLength=net.CurrentLength+20;step() end
            assert(used[#used]=="active" and cycle.status=="Lowering net")
            step(5);assert(used[#used]=="standby" and cycle.status=="Waiting for 29 kg")
            net.CurrentLength=1973;step();assert(used[#used]=="active")
            net.CurrentLength=2000;step();assert(used[#used]=="standby")
            assert(#commands==0)
        """)

    def test_full_box_before_haul_and_physical_switch_override(self):
        self.lua.execute("""
            catch.weight=30;catch.space=false;step(13);assert(#commands==0)
            catch.space=true;step();switch.on=false;net.NetDropped=false;step()
            switch.on=true;net.NetDropped=true;step()
            assert(not cabinet.WinchAutomationEnabled and #commands==1 and used[#used]=="off")
            step(5);assert(#commands==1)
        """)

    def test_stock_lever_raise_waits_for_drawer_without_sending_another_raise(self):
        self.lua.execute("""
            catch.weight=30;step(12)
            switch.on=false;step(20)
            assert(cabinet.WinchAutomationEnabled and not cycle.haulCheck and #commands==0 and moved==0)
            net.NetDropped=false;net.FullyRaised=true;step(4)
            assert(moved==0 and cycle.status=="Waiting for the catch drawer")
            catch.ready=true;step(4);assert(moved==0)
            step(3);assert(moved==3 and #commands==0)
            step(4);assert(#commands==1 and commands[1]=="lower")
            switch.on=true;net.NetDropped=true;net.FullyRaised=false;catch.weight=0;step(8)
            assert(cabinet.WinchAutomationEnabled and #commands==1 and cycle.status=="Waiting for 29 kg")
        """)

    def test_stock_lever_raise_off_unloads_only_with_power_and_leaves_drawer_up(self):
        self.lua.execute("""
            cycle:setEnabled(cabinet,false)
            charge=false;deck();step(6)
            assert(moved==0 and #commands==0 and cycle.status=="Waiting for external power")
            charge=true;step(10)
            assert(moved==3 and #commands==0 and net.FullyRaised and not cabinet.WinchAutomationEnabled)
            assert(used[#used]=="off" and cycle.drawKW==0 and cycle.status=="Automation off")
        """)

    def test_disabled_cabinet_loading_an_already_raised_drawer_waits_for_a_new_manual_haul(self):
        self.lua.execute("""
            cabinet.WinchAutomationEnabled=false;deck()
            cycle=require("shipnet.automation").new();step(8)
            assert(moved==0 and #commands==0 and #used>0 and cycle.drawKW==0)
            for _,mode in ipairs(used) do assert(mode=="off") end
        """)

    def test_player_reverses_command_before_next_poll(self):
        self.lua.execute("""
            function send(action)
                commands[#commands+1]=action
                switch.on=false;net.NetDropped=false
                return true
            end
            catch.weight=30;step(13);switch.on=true;net.NetDropped=true
            step(20);assert(not cabinet.WinchAutomationEnabled and #commands==1)
        """)

    def test_reload_on_deck_recovers_from_actual_inventory(self):
        self.lua.execute("""
            deck();net.NetDropped=true;switch.on=true
            catch.remaining=1;step(4);assert(moved==0)
            step()
            assert(moved==1 and #commands==0 and cabinet.WinchAutomationEnabled)
            step(4);assert(#commands==1 and commands[1]=="lower")
        """)

    def test_unconfirmed_transfer_pauses_before_retry_or_lowering(self):
        self.lua.execute("""
            deck(); catch.remaining=1
            package.loaded["shipnet.automation_cargo"].unload=function()
                moved=moved+1;catch.remaining=0;return {status="unconfirmed"}
            end
            step(8)
            assert(moved==1 and #commands==0 and not cabinet.WinchAutomationEnabled)
            switch.on=true;net.FullyRaised=false;net.NetDropped=true;step()
            deck();catch.remaining=1;step(8)
            assert(moved==1 and #commands==0 and cycle.status=="Check both inventories before restarting")
        """)

    def test_saved_off_never_operates(self):
        self.lua.execute("""
            cabinet.WinchAutomationEnabled=false;catch.weight=30;step(6)
            assert(#commands==0 and #used==6 and cycle.drawKW==0)
            for _,mode in ipairs(used) do assert(mode=="off") end
            cycle:setEnabled(cabinet,true);step(14);assert(#commands==1)
        """)
