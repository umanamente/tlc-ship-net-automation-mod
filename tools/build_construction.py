"""Generate and verify Voyage UE 5.8 native packages in an isolated staging directory."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from construction_packages import (ADVANCED, BASIC, VARIANTS, BOX, CABINET_HEALTH, FACTORY, FACTORY_MEMBER, GENERATOR, ITEM, PERMIT, SOCKET, STOCK_FACTORY,
                                   carrier_visuals, child_blueprint, commit_factory, engineering_skill, fixed_winch_mount, recipe_item, short)
from build_catalog_icon import cook as cook_icon
from build_construction_mesh import cook as cook_mesh
from build_control_screen import NAME as SCREEN_TEXTURE, cook as cook_screen
from build_cargo_sweep import NAME as SWEEP_TEXTURE, cook as cook_sweep
from build_markings import (DONOR as MARKING_DONOR, MATERIAL as MARKING_MATERIAL, TEXTURE as MARKING_TEXTURE,
                            PALETTE_COLOR, PALETTE_DONORS, PALETTE_MATERIAL, PALETTE_ORM,
                            cook as cook_markings, cook_material as cook_marking_material,
                            cook_palette, cook_palette_material)
from construction_registry import item_registry
from construction_power import INLET, MODULE, PLAYER_BOX, REFERENCE_MACHINE, SOCKET_TYPE, carrier_power, fields
from construction_interaction import ACTION, AIM, AUTOMATION, BASE, OPEN, PROVIDE, RESOLVE, TEXT, TRIGGER, carrier_interaction
from construction_packages import MODULE_ACTOR
from construction_basic import basic_module, verify_basic_module


CATALOGUE = Path("Voyage/Mods/ShipNetAutomationCatalogue")
PLUGIN = CATALOGUE / "ShipNetAutomationCatalogue.uplugin"
PACKAGE_NAME = "ShipNetWinch_v07_P"
BOX_WEIGHT_BASE = "BP_Inventory_Container_Base_WeightLimited"


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("retoc", "repak", "uassetgui", "jmap-dumper", "jmap", "game-paks", "stage"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output", type=Path,
                        help="Distribution root; defaults to a Voyage tree in the staging folder.")
    args = parser.parse_args()
    stage = args.stage.resolve()
    stage.mkdir(parents=True, exist_ok=True)
    ref = stage / "format-reference"
    layout_source = "BP_Physical_Recycler_Factory_Rhino_Dismantler"
    item_source = "DA_Item_Module_FoodProcessor"
    skill_source = "DA_Skill_Engineering_Food_Processor"
    run(args.retoc, "to-legacy", "--include-container", "pakchunk0-Windows.utoc",
        "--include-container", "global.utoc", "--no-shaders", "--no-script-objects",
        "--version", "UE5_8", "-f", layout_source, "-f", item_source, "-f", skill_source, "-f", short(BOX),
        "-f", "BasicShapes/Cube.uasset", "-f", "Icon_Heater_Small.uasset", "-f", MARKING_DONOR + ".uasset",
        "-f", "/gltf/Textures/T_White_srgb.uasset", "-f", "/gltf/Textures/T_White_Linear.uasset",
        "-f", short(STOCK_FACTORY) + ".uasset", "-f", short(PLAYER_BOX) + ".uasset",
        "-f", REFERENCE_MACHINE + ".uasset", "-f", short(BASE) + ".uasset",
        "-f", BOX_WEIGHT_BASE + ".uasset", args.game_paks, ref)
    mappings = stage / "VoyageAndWinch.usmap"
    reflection = load(args.jmap)
    objects = reflection["objects"]
    for package, parent in [(ADVANCED.carrier, BOX), (BASIC.carrier, MODULE_ACTOR),
                            (GENERATOR, SOCKET), (FACTORY, STOCK_FACTORY)]:
        parent_path = parent if parent == MODULE_ACTOR else f"{parent}.{short(parent)}_C"
        class_path = f"{package}.{short(package)}_C"
        objects[class_path] = {**objects[parent_path], "outer": package, "super_struct": parent_path,
                               "class_default_object": f"{package}.Default__{short(package)}_C",
                               "properties": [], "children": []}
        if package in (ADVANCED.carrier, BASIC.carrier):
            source = objects[PLAYER_BOX + "." + short(PLAYER_BOX) + "_C"]
            field = next(p for p in source["properties"] if p["name"] == "VoyageModule")
            offset = (objects[parent_path]["properties_size"] + 7) & ~7
            if package == BASIC.carrier:
                objects[class_path]["properties"].append({**field, "name": "StaticMesh", "offset": offset,
                                                          "property_class": "/Script/Engine.StaticMeshComponent"})
                offset += field["size"]
            objects[class_path]["properties"].append({**field, "name": INLET, "offset": offset,
                                                      "property_class": "/Script/Voyage." + SOCKET_TYPE})
            objects[class_path]["properties_size"] = offset + field["size"]
            byte = next(p for p in objects["/Script/Engine.Actor"]["properties"]
                        if p["type"] == "ByteProperty")
            offset += field["size"]
            action = next(p for p in objects[BASE + "." + short(BASE) + "_C:" + PROVIDE]["properties"]
                          if p["name"] == "Temp_struct_Variable")
            action_offset = (offset + 1 + 7) & ~7
            objects[class_path]["properties"].extend([{**byte, "name": AIM, "offset": offset, "enum": None},
                                                      {**action, "name": ACTION, "offset": action_offset}])
            end = action_offset + action["size"]
            saved_bool = next(p for p in objects[BASE + "." + short(BASE) + "_C"]["properties"] if p["name"] == "IsLocked")
            objects[class_path]["properties"].append({**saved_bool, "name": AUTOMATION, "offset": end})
            objects[class_path]["properties_size"] = end + saved_bool["size"]
        if package == GENERATOR:
            placement = objects["/Game/Blueprints/Fabrication/BP_FabricationPlacementComponent."
                                "BP_FabricationPlacementComponent_C"]
            class_type = next(p for p in placement["properties"] if p["name"] == "Fabricator Factory")
            offset = (objects[parent_path]["properties_size"] + 7) & ~7
            objects[class_path]["properties"] = [{**class_type, "name": FACTORY_MEMBER, "offset": offset}]
            objects[class_path]["properties_size"] = offset + class_type["size"]
        if package == FACTORY:
            bool_type = next(p for p in objects[STOCK_FACTORY + "." + short(STOCK_FACTORY)
                                                + "_C"]["properties"] if p["type"] == "BoolProperty")
            pos = objects[parent_path]["properties_size"]
            objects[class_path]["properties"] = [{**bool_type, "name": PERMIT, "offset": pos}]
            objects[class_path]["properties_size"] = pos + 1
    local_map = stage / "authoring.jmap"
    write(local_map, reflection)
    del objects, reflection
    run(args.jmap_dumper, "--jmap", local_map, mappings)
    templates = {}
    for name in (item_source, skill_source, layout_source, short(BOX), short(STOCK_FACTORY), short(PLAYER_BOX),
                 REFERENCE_MACHINE, short(BASE), BOX_WEIGHT_BASE):
        source, = ref.rglob(name + ".uasset")
        output = stage / (name + ".json")
        run(args.uassetgui, "--portable", "tojson", source, output, "5.8", mappings)
        templates[name] = load(output)
    art = stage / "legacy/Voyage/Content/Mods/ShipNetAutomation"
    for name, cooks in (("Cube", (cook_mesh,)), ("Icon_Heater_Small", (cook_icon, cook_screen, cook_sweep, cook_markings)),
                        (MARKING_DONOR, (cook_marking_material, cook_palette_material)),
                        *((donor, (cook_palette,)) for donor in PALETTE_DONORS)):
        source, = ref.rglob(name + ".uasset")
        layout = stage / (name + ".json")
        run(args.uassetgui, "--portable", "tojson", source, layout, "5.8", mappings)
        for cook in cooks:
            cook(layout, art, args.uassetgui, mappings)
    cook_mesh(stage / "Cube.json", art, args.uassetgui, mappings, basic=True)
    cook_icon(stage / "Icon_Heater_Small.json", art, args.uassetgui, mappings, basic=True)
    ancestors = [templates[name] for name in (short(BOX), short(PLAYER_BOX), BOX_WEIGHT_BASE, short(BASE))]
    packages = {GENERATOR: child_blueprint(templates[layout_source], GENERATOR, SOCKET),
                FACTORY: commit_factory(templates[layout_source], templates[short(STOCK_FACTORY)])}
    devices = {}
    for variant in VARIANTS:
        if variant.basic:
            carrier = basic_module(templates[layout_source], templates[REFERENCE_MACHINE], templates[item_source])
        else:
            carrier = child_blueprint(templates[layout_source], variant.carrier, BOX, variant)
            carrier = carrier_visuals(carrier, templates[short(BOX)], variant)
            carrier = carrier_power(carrier, templates[short(PLAYER_BOX)], templates[REFERENCE_MACHINE], variant)
        carrier = carrier_interaction(carrier, templates[short(BASE)], templates[item_source], variant)
        item = recipe_item(templates[item_source], variant)
        packages[variant.carrier] = carrier if variant.basic else fixed_winch_mount(carrier, ancestors, variant)
        packages[variant.item] = item
        packages[variant.skill] = engineering_skill(templates[skill_source], item["Exports"][0], variant)
        devices.update({key: variant for key in (variant.carrier, variant.item, variant.skill)})
    for package, data in packages.items():
        output = stage / "legacy/Voyage/Content" / (package.removeprefix("/Game/") + ".uasset")
        output.parent.mkdir(parents=True, exist_ok=True)
        source = stage / (short(package) + ".source.json")
        readback = stage / (short(package) + ".readback.json")
        write(source, data)
        output.unlink(missing_ok=True)
        output.with_suffix(".uexp").unlink(missing_ok=True)
        readback.unlink(missing_ok=True)
        run(args.uassetgui, "--portable", "fromjson", source, output, mappings, "5.8")
        if not output.is_file() or not output.with_suffix(".uexp").is_file():
            raise RuntimeError(f"The UE 5.8 writer did not produce {package}")
        run(args.uassetgui, "--portable", "tojson", output, readback, "5.8", mappings)
        reopened = load(readback)
        variant = devices.get(package)
        if variant and package == variant.skill:
            skill, = reopened["Exports"]
            properties = {p["Name"]: p["Value"] for p in skill["Data"]}
            unlock = {p["Name"]: p["Value"] for p in properties["Unlock"]}
            reward, = properties["Items"]
            imports = reopened["Imports"]
            item = imports[-1 - reward["Value"]]
            if (imports[-1 - skill["ClassIndex"]]["ObjectName"] != "VoyageSkill"
                    or unlock != {"UnlockMethod": "Tier", "Requirement": variant.level, "Cost": variant.points}
                    or item["ObjectName"] != short(variant.item) or imports[-1 - item["OuterIndex"]]["ObjectName"] != variant.item):
                raise ValueError(f"Invalid native research unlock for {variant.title}")
        if variant and package == variant.item:
            item = {p["Name"]: p["Value"] for p in reopened["Exports"][0]["Data"]}
            if item.get("bAllowPlacement") is not False:
                raise ValueError("The mounted cabinet must disable the grab tool's Place action")
            generator_index = item["CraftingLocationGenerator"]
            if not 1 <= generator_index <= len(reopened["Exports"]):
                raise ValueError("Missing winch mount generator in the recipe")
            generator = reopened["Exports"][generator_index - 1]
            if generator["ObjectName"] != "MountLocationGenerator" or generator["OuterIndex"] != 1:
                raise ValueError("The recipe must build through the winch mount generator")
            durability = {p["Name"]: p["Value"] for p in item["DestructibleObjectProperties"]}
            if (durability["Health"] != CABINET_HEALTH or item["bIsDestructible"] is not False
                    or item["bIsDismantlable"] is not True):
                raise ValueError("The cabinet needs operational health and native dismantling")
        if package in (ADVANCED.carrier, BASIC.carrier):
            enabled, = (p for p in reopened["Exports"][0]["LoadedProperties"] if p["Name"] == AUTOMATION)
            if enabled["SerializedType"] != "BoolProperty" or "CPF_SaveGame" not in enabled["PropertyFlags"]:
                raise ValueError("The cabinet must save its automation switch in the world")
            tags, = (p for p in reopened["Exports"][1]["Data"] if p["Name"] == "Tags")
            if not {"NoFabrication", "Snapped", "NoGrab"}.issubset(p["Value"] for p in tags["Value"]):
                raise ValueError("Mounted cabinet lost its construction, impact or hand-grab protection")
            methods = {e["ObjectName"]: e for e in reopened["Exports"]}
            receiver = fields(methods["ModuleComponent" if variant.basic else MODULE + "_GEN_VARIABLE"]["Data"])
            item = receiver["ItemAsset"]["Value"]
            if item >= 0 or reopened["Imports"][-1 - item]["ObjectName"] != short(variant.item):
                raise ValueError("The power inlet must display the cabinet item's name")
            if variant.basic:
                verify_basic_module(reopened)
            elif item != fields(reopened["Exports"][1]["Data"])["ContainerItem"]["Value"]:
                raise ValueError("The Advanced storage and power receiver must reference the same item")
            for e in data["Exports"]:
                if e["ObjectName"] in (PROVIDE, OPEN, TEXT, TRIGGER, RESOLVE):
                    decoded = methods[e["ObjectName"]]
                    if decoded["ScriptBytecode"] != e["ScriptBytecode"] or decoded["ScriptBytecodeSize"] != e["ScriptBytecodeSize"]:
                        raise ValueError(f"Cabinet interaction method changed during serialization: {e['ObjectName']}")
        if package == GENERATOR:
            member, = reopened["Exports"][0]["LoadedProperties"]
            if (member["Name"] != FACTORY_MEMBER or member["SerializedType"] != "ClassProperty"
                    or reopened["Imports"][-1 - member["MetaClass"]]["ObjectName"] != "VoyageFabricatorFactory"):
                raise ValueError("Generator class lost its hard factory reference")
        if package == FACTORY:
            for index, length in ((2, 5), (3, 4)):
                method = reopened["Exports"][index]
                if (method["ScriptBytecode"] != data["Exports"][index]["ScriptBytecode"]
                        or len(method["LoadedProperties"]) != length):
                    raise ValueError("The Fabricate validation graph changed during serialization")
        for original, restored in zip(data["Exports"], reopened["Exports"], strict=True):
            expected = {x["Name"]: x["Value"] for x in original["Data"]}
            actual = {x["Name"]: x["Value"] for x in restored["Data"]}
            if expected != actual or original["ObjectName"] != restored["ObjectName"]:
                raise ValueError(f"{package}: serialized properties differ from authored properties "
                                 f"({[key for key in expected.keys() | actual.keys() if expected.get(key) != actual.get(key)]})")
        print(f"{short(package)}  {output.stat().st_size} bytes header")
    textures = (SCREEN_TEXTURE, SWEEP_TEXTURE, MARKING_TEXTURE, PALETTE_COLOR, PALETTE_ORM)
    materials = (MARKING_MATERIAL, PALETTE_MATERIAL)
    allowed = {short(name) for name in packages} | set(textures) | set(materials)
    allowed.update(short(path) for variant in VARIANTS for path in (variant.mesh, variant.icon))
    legacy = stage / "legacy"
    assets = list(legacy.rglob("*.uasset"))
    if len(assets) != len(allowed) or {p.stem for p in assets} != allowed:
        raise ValueError("Unexpected input packages in the construction staging folder")
    distribution = (args.output or stage / "distribution").resolve()
    target = distribution / "Voyage/Content/Paks"
    target.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=stage) as temp:
        work = Path(temp)
        catalogue = work / "registry" / CATALOGUE / "AssetRegistry.bin"
        catalogue.parent.mkdir(parents=True)
        catalogue.write_bytes(item_registry(packages[ITEM]["Exports"][0], textures, materials=materials,
                                            additional_items=((BASIC, packages[BASIC.item]["Exports"][0]),)))
        pak = work / (PACKAGE_NAME + ".pak")
        utoc = pak.with_suffix(".utoc")
        run(args.repak, "pack", work / "registry", pak)
        run(args.retoc, "to-zen", "--no-parallel", "--version", "UE5_8", legacy, utoc)
        run(args.retoc, "verify", utoc)
        members = subprocess.check_output([args.retoc, "list", "--path", utoc], text=True)
        for file in assets:
            if "../../../" + file.relative_to(legacy).as_posix() not in members:
                raise ValueError(f"Missing packaged asset {file.name}")
        run(args.repak, "unpack", "-o", work / "reopened", pak)
        if (work / "reopened" / CATALOGUE / "AssetRegistry.bin").read_bytes() != catalogue.read_bytes():
            raise ValueError("Packaged registry differs from the item registry")
        for candidate in [pak, utoc, pak.with_suffix(".ucas")]:
            shutil.copyfile(candidate, target / candidate.name)
    descriptor = Path(__file__).resolve().parents[1] / "native" / PLUGIN
    if descriptor != distribution / PLUGIN:
        (distribution / PLUGIN).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(descriptor, distribution / PLUGIN)


if __name__ == "__main__":
    main()
