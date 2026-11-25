"""Exercise the installed Lua entry point with an isolated filesystem and UE4SS callbacks."""

import json
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
import unittest

from lupa.lua54 import LuaRuntime


SOURCE = Path(__file__).resolve().parents[1] / "src" / "ShipNetAutomation"

HOST = r"""
Key = {F4 = 115, ESCAPE = 27}
ModifierKey = {CONTROL = 1, SHIFT = 2, ALT = 3}
ModRef = {}
buttons, loops = {}, {}
messages = {}
function print(message) table.insert(messages, tostring(message)) end
function RegisterKeyBind(key, modifiers, handler)
    buttons[key] = handler or modifiers
end
function IsKeyBindRegistered(key) return buttons[key] ~= nil end
function LoopInGameThreadWithDelay(interval, callback)
    table.insert(loops, callback)
    return #loops
end
function CancelDelayedAction(handle) loops[handle] = nil return true end
function RegisterLoadMapPreHook(callback) before_map_load = callback end
function RegisterLoadMapPostHook(callback) after_map_load = callback end

local now = 1785000000
local real_time = os.time
os.time = function(date) if date then return real_time(date) end return now end
os.clock = function() return now - 1785000000 end
function pump()
    now = now + 1
    for _, callback in pairs(loops) do callback() end
end

scans, surveys, toggles, net_weight, net_length = 0, 0, 0, 8, 5
package.preload["shipnet.survey"] = function()
    return {capture = function()
        surveys = surveys + 1
        if survey_error then error("synthetic unavailable anchor") end
        return {status="no_net", world="TestSea", ship="SurveyBarge", anchors={}}
    end}
end
package.preload["shipnet.observer"] = function()
    return {valid = function(o) return o ~= nil and type(o.IsValid) == "function" and o:IsValid() end, new = function()
        return {
            sample = function()
                scans = scans + 1
                if sample_error then return {status="error", detail="Unable to inspect a module"} end
                return {status="ready", ship="TestBarge", net="TestNet", identity="world/ship/net",
                    netDropped=true, fullyRaised=false, netState=2, netWeight=net_weight, currentLength=net_length,
                    inventoryMaxWeight=100, inventoryReady=true, inventoryTotalCount=2,
                    items={{slot=0, itemId="TestScrap", count=2}}}
            end,
            reset = function() end,
        }
    end}
end
package.preload["shipnet.panel"] = function()
    return {new = function(options)
        ui = options
        return {
            toggle=function() toggles = toggles + 1 end, refresh=function() end,
            close=function() end, tick=function() end,
        }
    end}
end
"""


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.mod = Path(directory.name) / "ue4ss" / "Mods" / "ShipNetAutomation"
        copytree(SOURCE, self.mod)
        (self.mod / "Logs").mkdir(exist_ok=True)
        self.boot()

    def boot(self, world=None):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts = (self.mod / "Scripts").as_posix()
        self.lua.execute('package.path = scripts .. "/?.lua;" .. package.path')
        self.lua.execute(HOST)
        if world is not None:
            self.lua.execute('package.preload["shipnet.survey"]=nil; package.preload["shipnet.observer"]=nil')
            self.lua.execute(world)
        self.lua.execute('dofile(scripts .. "/main.lua")')
        self.assertTrue(self.lua.eval('ui ~= nil and type(ui.state) == "function"'))

    def step(self, count=1):
        for _ in range(count):
            self.lua.globals().pump()

    def action(self, name, arg=None):
        self.lua.globals().ui.action(name, arg)
        self.step()

    def setting(self, name):
        return self.lua.globals().ui.state()[name]

    def traces(self):
        return sorted((self.mod / "Logs").glob("*.jsonl"))

    @staticmethod
    def records(file):
        return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()]

    def test_disabled_debug_blocks_capture_and_scanning_including_direct_ui_actions(self):
        self.lua.execute("buttons[Key.F4]()")
        self.step()
        self.assertEqual(self.lua.globals().toggles, 1)
        self.assertFalse(self.setting("debugEnabled"))
        for name in ("start", "snapshot", "mark", "stop", "survey"):
            self.action(name, "about_to_collect")
        self.step(20)
        self.assertEqual(self.traces(), [])
        self.assertEqual(self.lua.globals().scans, 0)
        self.assertEqual(self.lua.globals().surveys, 0)

    def test_idle_survey_is_written_once_without_starting_the_cycle_recorder(self):
        self.action("set_debug", True)
        self.step(20)
        self.assertEqual(self.lua.globals().surveys, 0)
        self.assertEqual(self.traces(), [])
        self.action("survey")
        survey_file, = self.traces()
        survey_row, = self.records(survey_file)
        self.assertEqual(survey_row["kind"], "mount_survey")
        self.assertTrue(survey_file.name.startswith("mount-survey-"))
        self.assertEqual(survey_row["survey"]["ship"], "SurveyBarge")
        self.assertEqual(survey_row["survey"]["anchors"], [])
        self.assertFalse(self.setting("recording"))
        self.step(20)
        self.assertEqual(self.lua.globals().surveys, 1)
        self.assertEqual(self.lua.globals().scans, 0)
        self.assertEqual(self.records(survey_file), [survey_row])

    def test_fresh_installed_entry_writes_real_survey_from_weak_owned_actor(self):
        from test_observer import WORLD
        from test_survey import SURVEY_WORLD

        self.boot(world=WORLD + SURVEY_WORLD)
        self.assertFalse(self.setting("debugEnabled"))
        self.action("set_debug", True)
        self.action("survey")
        path, = self.traces()
        row, = self.records(path)
        self.assertEqual(row["kind"], "mount_survey")
        survey = row["survey"]
        self.assertEqual(survey["status"], "measured")
        self.assertEqual(survey["candidates"][0]["association"], "level_instance_owned")
        winch = next(anchor for anchor in survey["anchors"] if anchor["role"] == "winch")
        self.assertAlmostEqual(winch["shipLocalCm"]["X"], 120)
        self.assertFalse(self.setting("recording"))

    def test_active_survey_has_its_own_file_and_keeps_the_same_cycle_recording(self):
        self.action("set_debug", True)
        self.action("start")
        cycle_file, = self.traces()
        previous_name = self.setting("logName")
        self.action("survey")
        self.assertTrue(self.setting("recording"))
        self.assertEqual(self.setting("logName"), previous_name)
        survey_file, = set(self.traces()) - {cycle_file}
        survey_bytes = survey_file.read_bytes()
        self.assertEqual([r["kind"] for r in self.records(survey_file)], ["mount_survey"])
        self.lua.globals().net_weight = 19
        self.step(3)
        self.action("mark", "collected")
        self.action("stop")
        rows = self.records(cycle_file)
        self.assertEqual(rows[0]["kind"], "start")
        self.assertEqual(rows[-1]["kind"], "stop")
        self.assertEqual([r["marker"] for r in rows if r["kind"] == "mark"], ["collected"])
        self.assertTrue(any(r["state"]["netWeight"] == 19 for r in rows if r["kind"] == "sample"))
        self.assertNotIn("mount_survey", [r["kind"] for r in rows])
        self.assertEqual(survey_file.read_bytes(), survey_bytes)
        self.assertEqual(self.lua.globals().surveys, 1)

    def test_survey_failure_is_preserved_as_evidence_without_ending_the_cycle(self):
        self.action("set_debug", True)
        self.action("start")
        cycle_file, = self.traces()
        self.lua.globals().survey_error = True
        self.action("survey")
        survey_file, = set(self.traces()) - {cycle_file}
        survey_row, = self.records(survey_file)
        self.assertEqual(survey_row["survey"]["status"], "error")
        self.assertIn("synthetic unavailable anchor", survey_row["survey"]["detail"])
        self.assertTrue(self.setting("recording"))
        self.action("stop")
        self.assertEqual(self.records(cycle_file)[-1]["reason"], "user")

    def test_missing_weight_is_visible_during_capture_and_counted_at_stop(self):
        self.lua.globals().sample_error = True
        self.action("set_debug", True)
        self.action("start")
        self.assertEqual(self.setting("signal"), "Waiting for net weight")
        self.action("stop")
        trace, = self.traces()
        self.assertEqual(self.records(trace)[-1]["weightPolls"], 0)
        self.assertIn("no net weight readings", self.setting("message"))
        self.action("start")
        self.lua.globals().sample_error = False
        self.step()
        self.assertEqual(self.setting("signal"), "Receiving net weight")
        self.assertIn("8 / 100 kg", self.setting("summary"))
        self.action("stop")
        self.assertGreater(self.records(self.traces()[-1])[-1]["weightPolls"], 0)

    def test_enabled_preference_survives_restart_without_restarting_capture(self):
        self.action("set_debug", True)
        self.assertTrue(self.setting("debugEnabled"))
        self.action("start")
        self.assertTrue(self.setting("recording"))
        self.action("stop")
        self.assertFalse(self.setting("recording"))
        self.boot()
        self.assertTrue(self.setting("debugEnabled"))
        self.assertFalse(self.setting("recording"))
        self.step(20)
        self.assertEqual(self.lua.globals().scans, 0)
        self.action("set_debug", False)
        self.boot()
        self.assertFalse(self.setting("debugEnabled"))

    def test_unchanged_readings_are_quiet_and_changes_are_written(self):
        self.action("set_debug", True)
        self.action("start")
        self.step(10)
        trace, = self.traces()
        baseline = self.records(trace)
        self.assertTrue(baseline)
        self.assertGreater(self.lua.globals().scans, 0)
        self.step(10)
        self.assertEqual(self.records(trace), baseline)
        self.lua.globals().net_weight = 17
        self.step(10)
        changes = self.records(trace)[len(baseline):]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["kind"], "sample")
        self.assertEqual(changes[0]["state"]["netWeight"], 17)
        self.step(10)
        self.assertEqual(self.records(trace), baseline + changes)
        self.action("stop")
        stopped = self.records(trace)
        scans = self.lua.globals().scans
        self.step(20)
        self.assertEqual(self.records(trace), stopped)
        self.assertEqual(self.lua.globals().scans, scans)

    def test_disabling_debug_stops_recording_without_appending_new_samples(self):
        self.action("set_debug", True)
        self.action("start")
        self.step(5)
        self.action("set_debug", False)
        self.assertFalse(self.setting("recording"))
        self.assertFalse(self.setting("debugEnabled"))
        trace, = self.traces()
        at_stop = trace.read_bytes()
        self.lua.globals().net_weight = 18
        self.action("snapshot")
        self.action("mark", "about_to_raise")
        self.step(20)
        self.assertEqual(self.traces(), [trace])
        self.assertEqual(trace.read_bytes(), at_stop)

    def test_standalone_snapshot_creates_a_separate_trace_without_starting_a_session(self):
        self.action("set_debug", True)
        self.action("snapshot")
        first, = self.traces()
        self.assertTrue(self.records(first))
        self.assertFalse(self.setting("recording"))
        before = first.read_bytes()
        self.action("snapshot")
        self.assertEqual(len(self.traces()), 2)
        self.assertEqual(first.read_bytes(), before)
        self.assertFalse(self.setting("recording"))

    def test_manual_markers_and_snapshot_capture_the_current_state_in_order(self):
        self.action("set_debug", True)
        self.action("start")
        markers = ["about_to_lower", "about_to_raise", "about_to_collect", "collected"]
        for value, marker in enumerate(markers, 20):
            self.lua.globals().net_weight = value
            self.action("mark", marker)
        self.action("snapshot")
        self.action("stop")
        trace, = self.traces()
        rows = self.records(trace)
        self.assertEqual(rows[0]["kind"], "start")
        self.assertEqual(rows[-1]["kind"], "stop")
        self.assertTrue(rows[-1]["reason"])
        self.assertEqual(rows[-2]["kind"], "sample")
        self.assertEqual(rows[-2]["state"]["netWeight"], 23)
        seq = [row["seq"] for row in rows]
        self.assertEqual(seq, sorted(set(seq)))
        self.assertTrue(all(row["utc"] for row in rows))
        marked = [row for row in rows if row["kind"] == "mark"]
        self.assertEqual([row["marker"] for row in marked], markers)
        self.assertEqual([row["state"]["netWeight"] for row in marked], list(range(20, 24)))
        snapshots = [row for row in rows if row["kind"] == "snapshot"]
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["state"]["items"][0]["itemId"], "TestScrap")

    def test_new_session_leaves_completed_diagnostic_trace_intact(self):
        self.action("set_debug", True)
        self.action("start")
        self.action("start")
        first, = self.traces()
        self.action("stop")
        before = first.read_bytes()
        self.action("start")
        self.action("stop")
        self.assertEqual(len(self.traces()), 2)
        self.assertEqual(first.read_bytes(), before)

    def test_trace_path_failure_leaves_recorder_idle_and_retryable(self):
        self.action("set_debug", True)
        logs = self.mod / "Logs"
        parked = self.mod / "existing_logs"
        logs.rename(parked)
        logs.write_text("unrelated data", encoding="utf-8")
        self.action("start")
        self.assertFalse(self.setting("recording"))
        self.assertEqual(logs.read_text(encoding="utf-8"), "unrelated data")
        logs.unlink()
        parked.rename(logs)
        self.action("start")
        self.assertTrue(self.setting("recording"))
        self.action("stop")
        trace, = self.traces()
        self.assertEqual(self.records(trace)[-1]["kind"], "stop")

    def test_map_travel_stops_capture_before_the_old_world_disappears(self):
        self.action("set_debug", True)
        self.action("start")
        scans = self.lua.globals().scans
        self.lua.globals().before_map_load()
        self.assertFalse(self.setting("recording"))
        self.action("snapshot")
        self.action("start")
        self.lua.globals().after_map_load()
        self.step(12)
        self.assertEqual(self.lua.globals().scans, scans)
        first, = self.traces()
        self.assertEqual(self.records(first)[-1]["reason"], "map_change")
        self.action("start")
        self.action("stop")
        self.assertEqual(len(self.traces()), 2)

    def test_unload_closes_and_flushes_the_trace_without_sampling_torn_down_objects(self):
        self.action("set_debug", True)
        self.action("start")
        scans = self.lua.globals().scans
        self.lua.globals().ModRef.OnUnload()
        self.action("snapshot")
        self.step(12)
        self.assertEqual(self.lua.globals().scans, scans)
        trace, = self.traces()
        self.assertEqual(self.records(trace)[-1]["reason"], "mod_unload")

    def test_moving_line_length_is_kept_in_heartbeat_without_flooding_the_trace(self):
        self.action("set_debug", True)
        self.action("start")
        trace, = self.traces()
        baseline = self.records(trace)
        for length in range(6, 76):
            self.lua.globals().net_length = length
            self.step()
        extra = self.records(trace)[len(baseline):]
        self.assertEqual([row["reason"] for row in extra], ["heartbeat"])
        self.assertGreater(extra[0]["state"]["currentLength"], 5)
        self.action("snapshot")
        self.assertEqual(self.records(trace)[-1]["state"]["currentLength"], 75)
        self.action("stop")


if __name__ == "__main__":
    unittest.main()
