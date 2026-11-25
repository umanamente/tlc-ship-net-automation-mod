"""Regression fixtures for Voyage property tags, actor uniqueness and hull-relative coordinates."""

from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import measure_saved_mount as saved


HULL = "BP_Boat_Barge_C123"
NET = HULL + "LevelInstanceBP_Module_Fishing_C_0"
CHARACTER = "BP_FirstPersonCharacter_New_C1"


def actor(name, xyz, rotation=(0, 0, 0), scale=(1, 1, 1)):
    label = saved.fstring(name)
    name_tag = saved.ACTOR_NAME + struct.pack("<IB", len(label), 0) + label + saved.TEMPLATE
    pose = struct.pack("<3d6e", *xyz, *rotation, *scale)
    return name_tag + saved.TRANSFORM + pose + saved.fstring("ComponentTransforms")


def sample(character_xyz=(90, 220, 35)):
    def field(name, kind, xyz):
        tag = saved.struct_tag(name, kind, "/Script/CoreUObject")
        return tag + struct.pack("<IB3d", 24, 8, *xyz)

    fields = field("LastLocation", "Vector", (90, 220, 35)) + field("ControllerRotation", "Rotator", (0, 180, 0))
    return (saved.PLAYER + struct.pack("<IB", len(fields), 0) + fields
            + actor(HULL, (100, 200, 30), (0, 90, 0), (2, 1, 1))
            + actor(NET, (95, 200, 30)) + actor(CHARACTER, character_xyz))


class SavedMountTests(unittest.TestCase):
    def test_rotated_scaled_hull_and_view_direction_use_different_transform_rules(self):
        report = saved.measure(sample() + saved.fstring("BP_Boat_Barge_C456"))
        self.assertEqual(report["playerOriginShipLocalCm"], {"X": 10, "Y": 10, "Z": 5})
        self.assertEqual(report["viewDirectionShipLocal"], {"X": 0, "Y": 1, "Z": 0})
        self.assertEqual(report["characterOriginCheck"]["status"], "matched")

    def test_distinct_player_data_and_actor_origin_are_flagged(self):
        report = saved.measure(sample(character_xyz=(90, 225, 35)))
        self.assertEqual(report["characterOriginCheck"]["status"], "different")
        self.assertEqual(report["characterOriginCheck"]["distanceCm"], 5)

    def test_second_barge_or_second_winch_prevents_a_measurement(self):
        for name, reason in (("BP_Boat_Barge_C456", "barge actor"),
                             (HULL + "LevelInstanceBP_Module_Fishing_C_1", "stock winch")):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, reason):
                saved.measure(sample() + actor(name, (0, 0, 0)))

    def test_actor_does_not_borrow_transform_from_next_record(self):
        payload = sample()
        first_transform = payload.index(saved.TRANSFORM)
        payload = payload[:first_transform] + payload[first_transform+len(saved.TRANSFORM):]
        with self.assertRaisesRegex(ValueError, "top-level packed transform"):
            saved.measure(payload)


if __name__ == "__main__":
    unittest.main()
