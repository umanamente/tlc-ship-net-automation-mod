"""Exercise fit reports, calibration, and the cable guard through the diagnostic session."""
import json
import tempfile
import unittest
from pathlib import Path

from lupa.lua54 import LuaRuntime
from test_observer import SCRIPTS


class FitSessionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        (self.folder / "Logs").mkdir()
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts = SCRIPTS.as_posix()
        self.lua.globals().folder = self.folder.as_posix()
        self.lua.execute("""
            package.path=scripts.."/?.lua;"..package.path
            state = {}
            offset = {X=0,Y=0,Z=0,Yaw=0}
            runtime = {}
            function runtime:status()
                return {visible=visible==true,status=visible and "shown" or "hidden",offset=offset,stockFullyRaised=raised,
                    power={status="ready",registered=true,visual=true,connected=connected,cablePresent=connected,hasPower=false}}
            end
            function runtime:report() return self:status() end
            function runtime:show(saved) visible=true; offset=saved or {X=0,Y=0,Z=0,Yaw=0}; return self:status() end
            function runtime:hide(reason)
                if connected and reason=="user" then return {visible=true,status="cable_guard"} end
                visible=false; return self:status()
            end
            function runtime:move(axis, by) offset[axis]=offset[axis]+by; return self:status() end
            function runtime:pose(h,d) return self:status() end
            function runtime:tick() end
            session=require("shipnet.fit_session").new({storage=require("shipnet.storage"),runtime=runtime,
                survey={capture=function() return {status="measured"} end},observer={sample=function() return {status="ready"} end},
                state=state,dir=folder,message=function(m) state.message=m end,version="test"})
            """)

    def go(self, command):
        self.lua.execute(command)

    def rows(self):
        return [json.loads(line) for f in sorted((self.folder / "Logs").glob("*.jsonl"))
                for line in f.read_text(encoding="utf-8").splitlines()]

    def test_report_saved_pose_and_guard(self):
        self.go('session:action("fit_show"); session:action("fit_z_plus"); session:action("fit_save"); '
                'session:action("fit_hatch"); connected=true; session:action("fit_hide")')
        self.assertTrue(self.lua.eval("state.fitVisible"))
        self.assertEqual(self.rows()[-1]["fit"]["status"], "cable_guard")
        self.assertEqual(self.rows()[-2]["hatchDegrees"], 2)
        self.go('connected=false; session:action("fit_hide"); session:action("fit_show"); session:action("fit_capture")')
        self.assertEqual(self.lua.eval("offset.Z"), 5)
        self.assertEqual(self.rows()[-1]["survey"]["status"], "measured")
        self.assertEqual(self.rows()[-1]["stock"]["status"], "ready")
        self.go('session:stop("map_change")')
        self.assertFalse(self.lua.eval("state.fitVisible"))

    def test_power_transition_is_logged_while_panel_is_closed(self):
        self.go('connected=false; session:action("fit_show"); for i=1,24 do session:tick() end; '
                'connected=true; for i=1,16 do session:tick() end; session:stop("mod_unload")')
        rows=[r for r in self.rows() if r["action"]=="status_change"]
        self.assertEqual([False,True],[r["fit"]["power"]["connected"] for r in rows])
        self.assertEqual(self.rows()[-1]["action"],"mod_unload")

    def test_live_winch_transition_captures_both_positions_once(self):
        self.go('raised=true; session:action("fit_show"); raised=false; for i=1,16 do session:tick() end; '
                'raised=true; for i=1,16 do session:tick() end')
        self.go('session:stop("user")')
        rows = [r for r in self.rows() if r["action"].startswith("winch_")]
        self.assertEqual([r["action"] for r in rows], ["winch_left_raised_position", "winch_fully_raised"])
        self.assertTrue(all("stock" in r and "survey" in r for r in rows))
