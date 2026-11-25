"""Read the primary IDs used by the shipped Research and Build catalogues."""
import io
from pathlib import Path
import struct
import unittest


REGISTRY_GUID = bytes.fromhex("e79e7f713a49b0e93291b3880781381b")
PAK = Path(__file__).resolve().parents[1] / "native/Voyage/Content/Paks/ShipNetWinch_v07_P.pak"


def catalogue_records():
    packed = PAK.read_bytes()
    registry = io.BytesIO(packed[packed.index(REGISTRY_GUID):])

    def read(fmt):
        return struct.unpack(fmt, registry.read(struct.calcsize(fmt)))

    def align():
        registry.seek((-registry.tell()) % 16, io.SEEK_CUR)

    registry.seek(16)
    version, _, name_count, _, _ = read("<IIIIQ")
    assert version == 24
    registry.seek(8 * name_count, io.SEEK_CUR)
    lengths = read(f">{name_count}H")
    names = [registry.read(size).decode("ascii") for size in lengths]
    align()
    magic, *counts, _ = read("<13I")
    assert magic == 0x12345679
    align()
    typed_names = [names[index] for index in read(f"<{counts[0]}I")]
    align()
    registry.seek(4 * counts[5], io.SEEK_CUR)
    align()
    registry.seek(counts[7], io.SEEK_CUR)
    align()
    pairs = [read("<II") for _ in range(counts[9])]
    align()
    magic, size = read("<II")
    assert magic == 0x87654321
    results = {}
    for _ in range(size):
        _, _, cls, package, asset = [names[index] for index in read("<5I")]
        handle, _, _, _, _ = read("<Q4I")
        offset = handle & 0xFFFFFFFF
        count = (handle >> 32) & 0xFFFF
        tags = {names[key]: typed_names[value >> 3] for key, value in pairs[offset:offset + count]
                if value & 7 == 2}
        results[asset] = (cls, package, tags)
    return results


class ResearchCatalogueTest(unittest.TestCase):
    def test_asset_manager_can_enumerate_skill_and_item_independently(self):
        records = catalogue_records()
        for name, native_class, primary_type, folder in [
            ("DA_Skill_Engineering_Winch_Automator", "VoyageSkill", "Skill", "Skill/Modules"),
            ("DA_Item_Module_WinchAutomator", "VoyageItem", "Item", "Modules"),
            ("DA_Skill_Engineering_Winch_AutomatorBasic", "VoyageSkill", "Skill", "Skill/Modules"),
            ("DA_Item_Module_WinchAutomatorBasic", "VoyageItem", "Item", "Modules"),
        ]:
            self.assertEqual(records[name], (native_class, f"/Game/Data/Assets/{folder}/{name}",
                                             {"PrimaryAssetName": name, "PrimaryAssetType": primary_type}))
        self.assertIn("BP_WinchBuildFactory_C", records)

    def test_runtime_can_load_the_crt_artwork_by_object_path(self):
        self.assertEqual(catalogue_records()["T_WinchControlScreen"],
                         ("Texture2D", "/Game/Mods/ShipNetAutomation/T_WinchControlScreen", {}))
