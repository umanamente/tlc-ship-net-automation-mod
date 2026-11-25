"""Check visibility and click dispatch through the real panel on fake UMG widgets."""

import unittest

from lupa.lua54 import LuaRuntime

from test_observer import SCRIPTS


UMG = r"""
local serial, methods = 0, {}
function widget()
    serial = serial + 1
    return setmetatable({id=serial, Font={}}, {__index=methods})
end
for _, method in ipairs({"SetPadding", "SetContent", "SetSize", "SetAutoSize", "SetAnchors",
        "SetAlignment", "SetPosition", "SetFont", "SetAutoWrapText", "SetColorAndOpacity",
        "SetBackgroundColor", "SetBrushColor"}) do methods[method] = function() end end
function methods:IsValid() return true end
function methods:GetAddress() return self.id end
function methods:IsInViewport() return true end
function methods:IsLocalController() return true end
function methods:GetWorld() return world end
function methods:SetVisibility(value) self.visibility = value end
function methods:SetIsEnabled(value) self.enabled = value end
function methods:SetText(value) self.text = value end
function methods:AddChild() return widget() end
methods.AddChildToCanvas = methods.AddChild
function methods:Create()
    local button = widget()
    button.Button, button.ButtonText = widget(), widget()
    return button
end
function RegisterHook(path, callback) onclick = callback; return 1, 2 end
function FText(value) return value end
function FindFirstOf() return pc end
world, pc = widget(), widget()
pc.Pawn, pc.bShowMouseCursor = widget(), true
state, actions = {debugEnabled=false, recording=false}, {}
panel = require("shipnet.panel").new({
    state = function() return state end,
    action = function(name, argument)
        table.insert(actions, {name, argument})
        if name == "set_debug" then state.debugEnabled=argument end
        if name == "start" then state.recording=true end
        if name == "stop" then state.recording=false end
    end,
    log = function(err) error(err) end,
})
v = {open=true, pending={}, controls={}, by_address={}, text_cache={}, input=widget(), root=widget(), host=widget(),
    key=pc.id .. "/" .. world.id, pawn=tostring(pc.Pawn.id), pc=pc}
panel.view = v
panel._make = function() return widget() end
panel._fit = function() end
panel:_build()
panel:_refresh()
panel:_ensure_hook()
function click_widget(obj)
    onclick({get=function() return obj end})
    panel:tick()
end
function click(id) click_widget(v.controls[id].widget) end
"""


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts = SCRIPTS.as_posix()
        self.lua.execute('package.path = scripts .. "/?.lua;" .. package.path')
        self.lua.execute(UMG)

    def test_debug_is_hidden_until_settings_explicitly_enable_it(self):
        self.assertEqual(self.lua.eval("panel.tab"), "settings")
        self.assertEqual(self.lua.eval("v.controls.debug.widget.visibility"), 1)
        self.assertEqual(self.lua.eval("v.pages.debug.visibility"), 1)
        self.lua.execute('click("debug"); click("start"); click_widget(widget())')
        self.assertEqual(self.lua.eval("panel.tab"), "settings")
        self.assertEqual(self.lua.eval("#actions"), 0)
        self.lua.execute('click("set_debug"); click("debug")')
        self.assertEqual(self.lua.eval("v.controls.debug.widget.visibility"), 0)
        self.assertEqual(self.lua.eval("v.pages.debug.visibility"), 0)
        self.assertEqual(self.lua.eval("v.pages.settings.visibility"), 1)
        self.lua.execute('click("settings"); click("set_debug"); click("debug")')
        self.assertEqual(self.lua.eval("panel.tab"), "settings")
        self.assertEqual(self.lua.eval("v.controls.debug.widget.visibility"), 1)

    def test_marker_and_stop_require_capture_and_start_cannot_double_dispatch(self):
        self.lua.execute('click("set_debug"); click("debug"); click("mark_lower"); click("stop")')
        self.assertEqual(self.lua.eval("#actions"), 1)
        self.lua.execute('click("start"); click("start"); click("mark_collect"); click("stop")')
        self.assertEqual(self.lua.eval("#actions"), 4)
        self.assertEqual(self.lua.eval("actions[3][1]"), "mark")
        self.assertEqual(self.lua.eval("actions[3][2]"), "about_to_collect")
        self.assertFalse(self.lua.eval("v.controls.mark_collected.widget.enabled"))

    def test_survey_button_dispatches_only_from_debug_with_or_without_a_recording(self):
        self.lua.execute('click("survey"); click("set_debug"); click("survey")')
        self.assertEqual(self.lua.eval("#actions"), 1)
        self.lua.execute('click("debug"); click("survey"); click("start"); click("survey")')
        self.assertEqual(self.lua.eval("#actions"), 4)
        self.assertEqual(self.lua.eval("actions[2][1]"), "survey")
        self.assertEqual(self.lua.eval("actions[4][1]"), "survey")
        self.assertTrue(self.lua.eval("state.recording"))

    def test_fit_controls_require_debug_and_a_visible_preview(self):
        self.lua.execute('click("fit"); click("fit_show"); click("set_debug"); click("fit"); click("fit_z_plus")')
        self.assertEqual(self.lua.eval("panel.tab"), "fit")
        self.assertEqual(self.lua.eval("#actions"), 1)
        self.lua.execute('click("fit_show"); state.fitVisible=true; panel:refresh(); click("fit_show"); click("fit_hatch"); click("fit_x_minus")')
        self.assertEqual(self.lua.eval('actions[2][1]'), "fit_show")
        self.assertEqual(self.lua.eval('actions[3][1]'), "fit_hatch")
        self.assertEqual(self.lua.eval('actions[4][1]'), "fit_x_minus")
        self.assertIsNone(self.lua.eval('actions[5]'))

    def test_physical_display_has_its_own_commands_and_live_storage(self):
        self.lua.execute("""
            v.device = true
            v.controls, v.by_address, v.text_cache = {}, {}, {}
            reading = {netAvailable=true, fullyRaised=false, netDropped=true, netWeightKg=11.5,
                       power={connected=true, hasPower=true}, storage={fillRatio=.375}}
            panel.callbacks.device = function() return reading end
            panel.callbacks.command = function(which) issued=which; return true, "Raising net" end
            panel:_build()
            panel:_refresh()
            click("device_lower")
            assert(not issued)
            click("device_raise")
        """)
        self.assertEqual(self.lua.eval("issued"), "raise")
        self.assertIsNone(self.lua.eval("v.controls.settings"))
        self.assertEqual(self.lua.eval("v.storage_reading.text"), "38% full")
        self.assertIn("11.5 kg", self.lua.eval("v.net_reading.text"))
        self.assertEqual(self.lua.eval("v.feedback.text"), "Raising net")

    def test_automation_switch_reports_the_saved_mode_and_actual_load(self):
        self.lua.execute("""
            v.device=true
            v.controls,v.by_address,v.text_cache={},{},{}
            reading={netAvailable=true,automationEnabled=false,automationStatus="Automation off",automationDrawKW=0}
            panel.callbacks.device=function() return reading end
            panel.callbacks.automation=function(enabled)
                reading.automationEnabled,reading.automationStatus=enabled,enabled and "Unloading catch" or "Automation off"
                reading.automationDrawKW=enabled and 4 or 0
                return true
            end
            panel:_build();panel:_refresh();click("device_auto")
            assert(reading.automationEnabled and v.controls.device_auto.widget.ButtonText.text=="Stop automation")
            assert(v.automationReading.text=="Unloading catch" and v.power_reading.text:find("4 kW",1,true))
            reading.automationDrawKW=0;reading.power={connected=false,hasPower=true};panel:refresh()
            assert(v.power_reading.text:find("Waiting for connection",1,true))
            reading.power.connected=true;panel:refresh()
            assert(v.power_reading.text:find("Cable connected",1,true))
            click("device_auto");assert(not reading.automationEnabled)
            reading.automationEnabled=nil;panel:refresh();assert(not v.controls.device_auto.active)
        """)

    def test_preview_storage_button_is_device_only_and_releases_focus_before_open(self):
        self.lua.execute("""
            checks,opened=0,0
            panel.callbacks.legacyAvailable=function() checks=checks+1;return present==true end
            panel.callbacks.openLegacy=function(player)
                assert(player==pc and not panel.view and not pc.bShowMouseCursor)
                opened=opened+1;return true,{}
            end
            panel:refresh();panel:tick()
            assert(checks==0)
            v.device=true;v.controls,v.by_address,v.text_cache={},{},{}
            v.cursor,v.previous_cursor=true,false
            function v.host:RemoveFromParent() self.removed=true end
            function v.host:IsInViewport() return not self.removed end
            panel.callbacks.device=function() return {} end
            panel:_build();panel:_refresh()
            click("device_legacy")
            assert(not v.controls.device_legacy.active and v.controls.device_legacy.widget.visibility==1 and opened==0)
            present=true;panel:refresh()
            assert(v.controls.device_legacy.active and v.controls.device_legacy.widget.visibility==0)
            present=false;click("device_legacy")
            assert(panel:is_device_open() and opened==0 and v.feedback.text=="Preview storage is unavailable.")
            present=true;panel:refresh();click("device_legacy")
            assert(not panel:is_open() and opened==1)
            local calls=checks
            panel:tick();panel:refresh()
            assert(checks==calls)
        """)


if __name__ == "__main__":
    unittest.main()
