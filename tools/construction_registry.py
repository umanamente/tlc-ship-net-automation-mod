"""Register the recipe, engineering skill, commit factory and cabinet textures."""
import io
import struct
import uuid

from cityhash import CityHash64

from construction_packages import ADVANCED, FACTORY, MOD, short


def item_records(item_export, variant):
    properties = {entry["Name"]: entry["Value"] for entry in item_export["Data"]}
    tags = {
        "bExcludeFromDemo": "False", "bExcludeFromDistribution": "False",
        "Category": "EVoyageItemCategory::" + properties["Category"],
        "CraftFilter": str(properties["CraftFilter"]),
        "IsDismantlable": str(properties["bIsDismantlable"]),
        "bIsDismantlable": str(properties["bIsDismantlable"]),
        "NativeClass": "/Script/CoreUObject.Class'/Script/Voyage.VoyageItem'",
        "Quality": "EVoyageItemQuality::" + properties["Quality"],
        "Tag": properties["Tag"], "Weight": str(properties["Weight"]),
        "VersionRange": "(InitialVersion=(MajorVersion=0,MinorVersion=0,PatchVersion=0),"
                        "bHasSunsetVersion=False,SunsetVersion=(MajorVersion=99999,MinorVersion=0,PatchVersion=0))",
    }
    item_record = (variant.item.rsplit("/", 1)[0], "/Script/Voyage", "VoyageItem", variant.item, short(variant.item))
    skill_record = (variant.skill.rsplit("/", 1)[0], "/Script/Voyage", "VoyageSkill", variant.skill, short(variant.skill))
    skill_tags = {key: tags[key] for key in ("bExcludeFromDemo", "bExcludeFromDistribution", "VersionRange")}
    skill_tags["NativeClass"] = "/Script/CoreUObject.Class'/Script/Voyage.VoyageSkill'"
    return [(item_record, tags, {"PrimaryAssetName": short(variant.item), "PrimaryAssetType": "Item"}),
            (skill_record, skill_tags, {"PrimaryAssetName": short(variant.skill), "PrimaryAssetType": "Skill"})]


def item_registry(item_export, texture_names=("T_WinchControlScreen",), *, additional_items=(), materials=()):
    records = item_records(item_export, ADVANCED)
    for variant, export in additional_items:
        records.extend(item_records(export, variant))
    factory_record = (FACTORY.rsplit("/", 1)[0], "/Script/Engine", "BlueprintGeneratedClass",
                      FACTORY, short(FACTORY) + "_C")
    records.append((factory_record, {}, {}))

    for name in texture_names:
        record = (MOD.rstrip("/"), "/Script/Engine", "Texture2D", MOD + name, name)
        records.append((record, {}, {}))
    for name in materials:
        record = (MOD.rstrip("/"), "/Script/Engine", "MaterialInstanceConstant", MOD + name, name)
        records.append((record, {}, {}))
    names = ["None"]
    name_values = []
    strings = []
    for record, text_tags, name_tags in records:
        names.extend([*text_tags, *name_tags, *name_tags.values(), *record])
        name_values.extend(name_tags.values())
        strings.extend(text_tags.values())
    names = list(dict.fromkeys(names))
    name_values = list(dict.fromkeys(name_values))
    strings = list(dict.fromkeys(strings))
    out = io.BytesIO()

    def put(fmt, *values):
        out.write(struct.pack("<" + fmt, *values))

    def align():
        out.write(bytes((-out.tell()) % 16))

    # FAssetRegistryVersion GUID is serialized as four little-endian uint32s.
    guid = uuid.UUID("717f9ee7-e9b0-493a-88b3-91321b388107").hex
    put("4I", *(int(guid[i:i + 8], 16) for i in range(0, 32, 8)))
    put("II", 24, 1)
    encoded = [name.encode("ascii") for name in names]
    put("IIQ", len(names), sum(map(len, encoded)), 0xC1640000)
    for name in encoded:
        put("Q", CityHash64(name.lower()))
    for name in encoded:
        out.write(len(name).to_bytes(2, "big"))
    out.write(b"".join(encoded))
    align()

    # Text-first fixed tag store. Primary identifiers are numberless FName
    # values, and the remaining searchable metadata uses NUL-terminated ANSI.
    text_pool = bytearray()
    offsets = []
    for value in strings:
        offsets.append(len(text_pool))
        text_pool.extend(value.encode("ascii") + b"\0")
    pairs = []
    handles = []
    for record, text_tags, name_tags in records:
        entries = [(key, strings.index(value) << 3) for key, value in text_tags.items()]
        entries.extend((key, name_values.index(value) << 3 | 2) for key, value in name_tags.items())
        handles.append(1 << 63 | len(entries) << 32 | len(pairs) if entries else 0)
        pairs.extend(sorted(entries))
    put("I11II", 0x12345679, len(name_values), 0, 0, 0, 0, len(strings), 0,
        len(text_pool), 0, len(pairs), 0, 0)
    align()
    for value in name_values:
        put("I", names.index(value))
    align()
    for offset in offsets:
        put("I", offset)
    align()
    out.write(text_pool)
    align()
    for key, value in pairs:
        put("II", names.index(key), value)
    align()
    put("II", 0x87654321, len(records))
    for (record, _, _), tag_handle in zip(records, handles, strict=True):
        for name in record:
            put("I", names.index(name))
        put("Q", tag_handle)
        put("IIII", 0, 1, 0, 0x80042200)  # no bundles, chunk 0, cooked runtime package
    put("QII", 4, 0, 0)  # empty dependency section and package data table
    return out.getvalue()
