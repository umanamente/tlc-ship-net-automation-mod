"""Mounting surveys on a translated and rotated vessel with UE4SS-style weak references."""

import unittest

from lupa.lua54 import LuaRuntime

from test_observer import SCRIPTS, WORLD


SURVEY_WORLD = r"""
data[net].parent = nil
data[ship].modules = {}
local level = actor("BargeLevelInstanceComponent", {["/Script/Voyage.VoyageLevelInstanceComponent"]=true})
data[ship].LevelInstanceComponent = level
data[level].owner = ship
owned = {false, net} -- An expired weak pointer followed by the live winch.
local array_methods = {GetArrayNum=function() return #owned end}
function array_methods:ForEach()
    table.insert(writes, "unsupported weak-array iteration")
    error("WeakObjectProperty does not support GetParam")
end
data[level].OwnedActors = setmetatable({}, {
    __index=function(_, key)
        if type(key) ~= "number" then return array_methods[key] end
        if key < 1 or key > #owned then
            table.insert(writes, "out-of-range array access")
            error("UE4SS grows a native array on out-of-range index")
        end
        return {Get = function() return owned[key] or nil end}
    end,
})
direct = {}
local find = FindAllOf
function FindAllOf(name)
    if name == "VoyageBoatPawn" then return find(name) end
    return direct[name]
end

function xyz(x,y,z) return {X=x, Y=y, Z=z} end
function rot(p,y,r) return {Pitch=p, Yaw=y, Roll=r} end
local mathlib = actor("KismetMathLibrary")
local find_object = StaticFindObject
function StaticFindObject(path)
    if path == "/Script/Engine.Default__KismetMathLibrary" then return mathlib end
    return find_object(path)
end
function set_pose(x, y, z, yaw)
    local half = math.rad(yaw/2)
    pose = {Translation=xyz(x,y,z), Rotation={X=0,Y=0,Z=math.sin(half),W=math.cos(half)}, Scale3D=xyz(1,1,1)}
    ship_yaw = yaw
end
set_pose(1000, -2000, 80, 90)
data[ship].GetTransform = function() return pose end
data[ship].K2_GetActorLocation = function() return pose.Translation end
data[ship].K2_GetActorRotation = function() return rot(0,ship_yaw,0) end
function survey_position(actor_object, location, rotation)
    data[actor_object].K2_GetActorLocation = function() return location end
    data[actor_object].K2_GetActorRotation = function() return rotation end
end
survey_position(net, xyz(1040,-1880,95), rot(0,105,0))
survey_position(pawn, xyz(960,-2050,125), rot(0,90,0))
local container_socket = actor("LandingPoint", {["/Script/Engine.SceneComponent"]=true})
data[net].ContainerLocation, data[container_socket].owner = container_socket, net
function set_landing(location, rotation)
    data[container_socket].K2_GetComponentLocation = function() return location end
    data[container_socket].K2_GetComponentRotation = function() return rotation end
end
set_landing(xyz(1045,-1875,90), rot(0,135,0))
data[mathlib].InverseTransformLocation = function(self, transform, v)
    assert(transform == pose, "measurement must use the hull transform")
    local dx, dy = v.X-transform.Translation.X, v.Y-transform.Translation.Y
    local a = math.rad(ship_yaw)
    return xyz(dx*math.cos(a)+dy*math.sin(a), -dx*math.sin(a)+dy*math.cos(a), v.Z-transform.Translation.Z)
end
data[mathlib].InverseTransformRotation = function(self, transform, r)
    assert(transform == pose, "rotation must be relative to the hull frame")
    return rot(r.Pitch, (r.Yaw-ship_yaw+180)%360-180, r.Roll)
end
"""


class SurveyTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts = SCRIPTS.as_posix()
        self.lua.execute('package.path = scripts .. "/?.lua;" .. package.path')
        self.lua.execute(WORLD)
        self.lua.execute(SURVEY_WORLD)
        self.lua.execute('survey = require("shipnet.survey")')

    def capture(self):
        return self.lua.eval("survey.capture()")

    def tearDown(self):
        self.assertEqual(self.lua.eval("#writes"), 0, "survey attempted a gameplay mutation")

    @staticmethod
    def anchors(row):
        return {item["role"]: item for item in row["anchors"].values()}

    def assert_xyz(self, vector, xyz):
        self.assertIsNotNone(vector)
        for axis, expected in zip("XYZ", xyz):
            self.assertAlmostEqual(vector[axis], expected, places=5)

    def test_verified_weak_owned_winch_and_player_positions_use_the_moving_ship_frame(self):
        first = self.capture()
        self.assertEqual(first["status"], "measured", first["detail"])
        self.assertEqual(first["probes"]["owned"]["raw"], 2)
        self.assertEqual(first["probes"]["owned"]["matched"], 1)
        self.assertEqual(first["probes"]["native"]["raw"], 0)
        self.assertEqual(first["candidates"][1]["association"], "level_instance_owned")
        anchors = self.anchors(first)
        winch = anchors["winch"]
        self.assert_xyz(winch["worldCm"], (1040, -1880, 95))
        self.assert_xyz(winch["shipLocalCm"], (120, -40, 15))
        self.assertAlmostEqual(winch["shipLocalRotationDeg"]["Yaw"], 15)
        self.assert_xyz(anchors["player_origin"]["shipLocalCm"], (-50, 40, 45))
        self.assert_xyz(anchors["container_location"]["shipLocalCm"], (125, -45, 10))

        # Same deck positions after translating the barge and turning it 180 degrees.
        self.lua.execute("""
            set_pose(-300, 400, 110, -90)
            survey_position(net, xyz(-340,280,125), rot(0,-75,0))
            survey_position(pawn, xyz(-260,450,155), rot(0,-90,0))
            set_landing(xyz(-345,275,120), rot(0,-45,0))
        """)
        second = self.capture()
        self.assertEqual(second["status"], "measured")
        anchors = self.anchors(second)
        self.assert_xyz(anchors["winch"]["worldCm"], (-340, 280, 125))
        self.assert_xyz(anchors["winch"]["shipLocalCm"], (120, -40, 15))
        self.assertAlmostEqual(anchors["winch"]["shipLocalRotationDeg"]["Yaw"], 15)
        self.assert_xyz(anchors["player_origin"]["shipLocalCm"], (-50, 40, 45))
        self.assert_xyz(anchors["container_location"]["shipLocalCm"], (125, -45, 10))

    def test_missing_transform_prevents_classifying_world_positions_as_measurements(self):
        self.lua.execute("data[ship].GetTransform = function() return nil end")
        row = self.capture()
        self.assertEqual(row["status"], "transform_unavailable", row["detail"])
        for anchor in row["anchors"].values():
            self.assertIsNone(anchor["shipLocalCm"])

    def test_lowercase_pitch_from_shipped_rotator_is_a_valid_measurement(self):
        self.lua.execute("""
            function shipped_rot(p,y,r)
                return setmetatable({pitch=p,Yaw=y,Roll=r}, {
                    __index=function(_,k) error("unknown Rotator field "..k) end})
            end
            data[net].K2_GetActorRotation=function() return shipped_rot(2,105,4) end
            local m=StaticFindObject("/Script/Engine.Default__KismetMathLibrary")
            data[m].InverseTransformRotation=function(_,t,r)
                return shipped_rot(r.pitch or r.Pitch,r.Yaw-ship_yaw,r.Roll)
            end
        """)
        result=self.capture()
        self.assertEqual(result["status"],"measured")
        winch=self.anchors(result)["winch"]
        self.assertAlmostEqual(winch["worldRotationDeg"]["Pitch"],2)
        self.assertAlmostEqual(winch["shipLocalRotationDeg"]["Pitch"],2)

    def test_multiple_distinct_owned_winches_cannot_supply_a_verified_mounting_point(self):
        self.lua.execute("table.insert(owned, other_net(nil))")
        row = self.capture()
        self.assertEqual(row["status"], "ambiguous_net", row["detail"])
        self.assertNotIn("winch", self.anchors(row))

    def test_survey_reports_a_missing_winch_without_substituting_the_player_as_mount(self):
        self.lua.execute("owned = {}")
        row = self.capture()
        self.assertEqual(row["status"], "no_net", row["detail"])
        self.assertNotIn("winch", self.anchors(row))

    def test_visible_winch_with_no_ship_link_is_reported_as_an_unverified_candidate(self):
        self.lua.execute('owned = {}; direct["BP_Module_Fishing_C"] = {net}')
        row = self.capture()
        self.assertEqual(row["status"], "unverified_net", row["detail"])
        self.assertEqual(row["probes"]["blueprint"]["matched"], 1)
        self.assertIsNone(row["candidates"][1]["association"])
        self.assertNotIn("winch", self.anchors(row))

    def test_piloting_the_barge_does_not_report_its_origin_as_the_player_deck_point(self):
        self.lua.execute("data[controller].Pawn = ship")
        row = self.capture()
        self.assertNotIn("player_origin", self.anchors(row))

    def test_deck_contact_requires_walkable_blocking_floor_on_this_barge(self):
        self.lua.execute("""
            floor = {bBlockingHit=true, bWalkableFloor=true,
                HitResult={bBlockingHit=true, ImpactPoint=xyz(960,-2050,20), ImpactNormal=xyz(0,0,1)}}
            data[pawn].CharacterMovement = {CurrentFloor=floor}
        """)
        anchors = self.anchors(self.capture())
        self.assert_xyz(anchors["deck_contact"]["shipLocalCm"], (-50, 40, -60))
        self.assert_xyz(anchors["player_origin"]["shipLocalCm"], (-50, 40, 45))
        self.lua.execute("floor.bWalkableFloor = false")
        self.assertNotIn("deck_contact", self.anchors(self.capture()))
        self.lua.execute("floor.bWalkableFloor = true; data[pawn].base = nil")
        self.assertNotIn("deck_contact", self.anchors(self.capture()))

    def test_ownership_alone_does_not_verify_coordinates_in_another_world(self):
        self.lua.execute('data[net].world = actor("StreamingWorld")')
        row = self.capture()
        self.assertEqual(row["status"], "frame_unverified")
        self.assertEqual(row["coordinateFrame"], "ship_owned_world_unverified")


if __name__ == "__main__":
    unittest.main()
