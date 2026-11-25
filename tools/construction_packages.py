"""Author the Cooked UE 5.8 item, persistent carrier, and per-item location generator.

The two stock inputs supply the matching serializer/header layout. No executable
graphs, graphics, or authored defaults from those packages are copied to the item.
The two Blueprints inherit gameplay from external class imports in the game.
"""
from copy import deepcopy
from dataclasses import dataclass


MOD = "/Game/Mods/ShipNetAutomation/"
ITEM = "/Game/Data/Assets/Modules/DA_Item_Module_WinchAutomator"
SKILL = "/Game/Data/Assets/Skill/Modules/DA_Skill_Engineering_Winch_Automator"
CARRIER = MOD + "BP_Module_WinchAutomator"
GENERATOR = MOD + "BP_WinchMountGenerator"
FACTORY = MOD + "BP_WinchBuildFactory"
FACTORY_MEMBER = "BuildFactoryClass"
VALIDATE = "ValidateWinchBuild"
PERMIT = "bCommitAllowed"
MESH = MOD + "SM_WinchAutomator"
ICON = MOD + "T_WinchAutomator"
BOX = "/Game/Blueprints/Interactives/Containers/BP_Inventory_PlayerBox_Small"
MODULE_ACTOR = "/Script/Voyage.VoyageModuleActor"
SOCKET = "/Game/Blueprints/Fabrication/BP_CraftingLocationGenerator_SocketMatch"
STOCK_FACTORY = "/Game/Blueprints/Fabrication/BP_Physical_Fabricator_Factory"
PARTS = {"AlloyFrame": 4, "ConduitWiring": 3, "MagneticCoil": 2,
         "LogicChip": 2, "DisplayScreen": 1, "ConnectorPorts": 1}
CABINET_HEALTH = 500.0

@dataclass(frozen=True)
class WinchVariant:
    item: str
    skill: str
    carrier: str
    mesh: str
    icon: str
    title: str
    description: str
    level: int
    points: int
    parts: dict
    weight: float
    craft_time: float
    basic: bool = False


ADVANCED = WinchVariant(ITEM, SKILL, CARRIER, MESH, ICON, "Winch Automator Advanced",
                        "Mounts on the barge fishing winch. Controls the net and stores its catch.",
                        10, 2, PARTS, 110.0, 30.0)
BASIC = WinchVariant(ITEM + "Basic", SKILL + "Basic", CARRIER + "Basic", MESH + "Basic", ICON + "Basic",
                     "Winch Automator Basic",
                     "Raises a full fishing net and waits for you to empty the stock drawer. Draws 500 W.",
                     6, 1, {"AlloyFrame": 2, "ConduitWiring": 2, "MagneticCoil": 1, "LogicChip": 1,
                            "DisplayScreen": 1, "ConnectorPorts": 1}, 24.0, 20.0, True)
VARIANTS = (ADVANCED, BASIC)



def short(package):
    return package.rsplit("/", 1)[-1]


def prop(kind, name, value, **options):
    return {"$type": f"UAssetAPI.PropertyTypes.Objects.{kind}PropertyData, UAssetAPI",
            "Name": name, "ArrayIndex": 0, "PropertyGuid": None, "IsZero": False,
            "PropertyTagFlags": "None", "PropertyTypeName": None,
            "PropertyTagExtensions": "NoExtension", "Value": value, **options}


def imports_for(asset):
    entries = asset["Imports"]

    def add(name, outer, class_package, class_name):
        entry = {"$type": "UAssetAPI.Import, UAssetAPI", "ObjectName": name,
                 "OuterIndex": outer, "ClassPackage": class_package,
                 "ClassName": class_name, "PackageName": "None", "bImportOptional": False}
        if entry not in entries:
            entries.append(entry)
        return -1 - entries.index(entry)

    def reference(package, name, class_package, class_name):
        outer = add(package, 0, "/Script/CoreUObject", "Package")
        return add(name, outer, class_package, class_name)
    return reference


def finish(asset, package, initial_names):
    asset["FolderName"] = package
    # ClassExport has the cooked BlueprintType metadata key at index 1.
    names = list(dict.fromkeys(initial_names))
    for obj in asset["Imports"] + asset["Exports"]:
        for key in ("ObjectName", "ClassName", "ClassPackage", "PackageName"):
            name = obj.get(key)
            if name and name not in names:
                names.append(name)
    asset["NameMap"] = names
    asset["NamesReferencedFromExportDataCount"] = len(names)
    asset["DependsMap"] = [[] for _ in asset["Exports"]]
    asset["Generations"][0].update(ExportCount=len(asset["Exports"]), NameCount=len(names))
    return asset


def child_blueprint(template, package, parent, variant=ADVANCED):
    asset = deepcopy(template)
    cls, cdo = asset["Exports"]
    name = short(package) + "_C"
    parent_name = short(parent) + "_C"
    asset["Imports"] = []
    ref = imports_for(asset)
    if parent == MODULE_ACTOR:
        namespace, parent_name = parent.split(".")
        super_cls = ref(namespace, parent_name, "/Script/CoreUObject", "Class")
        super_cdo = ref(namespace, "Default__" + parent_name, namespace, parent_name)
    else:
        super_cls = ref(parent, parent_name, "/Script/Engine", "BlueprintGeneratedClass")
        super_cdo = ref(parent, "Default__" + parent_name, parent, parent_name)
    meta = ref("/Script/Engine", "BlueprintGeneratedClass", "/Script/CoreUObject", "Class")
    default_meta = ref("/Script/Engine", "Default__BlueprintGeneratedClass",
                       "/Script/Engine", "BlueprintGeneratedClass")
    within = ref("/Script/CoreUObject", "Object", "/Script/CoreUObject", "Class")
    cls.update(ObjectName=name, SuperStruct=super_cls, SuperIndex=super_cls,
               ClassIndex=meta, TemplateIndex=default_meta, ClassWithin=within,
               SerializationBeforeSerializationDependencies=[super_cls, super_cdo],
               SerializationBeforeCreateDependencies=[meta, default_meta],
               CreateBeforeCreateDependencies=[super_cls])
    cdo.update(ObjectName="Default__" + name, TemplateIndex=super_cdo,
               SerializationBeforeCreateDependencies=[1, super_cdo], Data=[])
    if package == variant.carrier and parent != MODULE_ACTOR:
        item = ref(variant.item, short(variant.item), "/Script/Voyage", "VoyageItem")
        cdo["CreateBeforeSerializationDependencies"] = [item]
        cdo["Data"] = [prop("Object", "ContainerItem", item), prop("Bool", "InteractEnabled", False)]
    elif package == GENERATOR:
        tags = [prop("Name", "0", "ShipNetAutomation.WinchMount")]
        factory_class = ref(FACTORY, short(FACTORY) + "_C", "/Script/Engine", "BlueprintGeneratedClass")
        meta = ref("/Script/Voyage", "VoyageFabricatorFactory", "/Script/CoreUObject", "Class")
        class_type = ref("/Script/CoreUObject", "Class", "/Script/CoreUObject", "Class")
        cls["LoadedProperties"] = [{
            "$type": "UAssetAPI.FieldTypes.FClassProperty, UAssetAPI",
            "MetaClass": meta, "PropertyClass": class_type, "ArrayDim": "TArray", "ElementSize": 8,
            "PropertyFlags": "CPF_Edit, CPF_BlueprintVisible, CPF_DisableEditOnInstance, CPF_UObjectWrapper",
            "RepIndex": 0, "RepNotifyFunc": "None", "BlueprintReplicationCondition": "COND_None",
            "RawValue": None, "SerializedType": "ClassProperty", "Name": FACTORY_MEMBER,
            "Flags": "RF_NoFlags", "MetaDataMap": None,
        }]
        cls["CreateBeforeSerializationDependencies"].extend([meta, class_type])
        cdo["CreateBeforeSerializationDependencies"].append(factory_class)
        cdo["Data"] = [prop("Object", FACTORY_MEMBER, factory_class),
                       prop("Array", "MatchedSocketTags", tags, ArrayType="NameProperty")]
        cls["ClassFlags"] = "CLASS_EditInlineNew, CLASS_CompiledFromBlueprint, CLASS_DefaultToInstanced"
    return finish(asset, package, [parent, "BlueprintType", "Engine", "None",
                                   "ShipNetAutomation.WinchMount", package, FACTORY_MEMBER, "ClassProperty"])


def commit_factory(template, stock):
    """Only the native Blueprint VM passes the fabricated site object to its caller."""
    asset = child_blueprint(template, FACTORY, STOCK_FACTORY)
    ref = imports_for(asset)
    cls = asset["Exports"][0]
    original = next(entry for entry in stock["Exports"] if entry["ObjectName"] == "Fabricate")
    method = deepcopy(original)
    cls["FuncMap"] = [["Fabricate", 3], [VALIDATE, 4]]
    cls["Children"] = [3, 4]
    cls["CreateBeforeSerializationDependencies"].extend([3, 4])
    cls["LoadedProperties"] = [{
        "$type": "UAssetAPI.FieldTypes.FBoolProperty, UAssetAPI", "FieldSize": 1,
        "ByteOffset": 0, "ByteMask": 1, "FieldMask": 255, "NativeBool": True, "Value": False,
        "ArrayDim": "TArray", "ElementSize": 1, "PropertyFlags": "CPF_Transient, CPF_BlueprintVisible",
        "RepIndex": 0, "RepNotifyFunc": "None", "BlueprintReplicationCondition": "COND_None",
        "RawValue": None, "SerializedType": "BoolProperty", "Name": PERMIT,
        "Flags": "RF_NoFlags", "MetaDataMap": None,
    }]
    asset["Imports"].append({"$type": "UAssetAPI.Import, UAssetAPI", "ObjectName": "Fabricate",
                             "OuterIndex": cls["SuperIndex"], "ClassPackage": "/Script/CoreUObject",
                             "ClassName": "Function", "PackageName": "None", "bImportOptional": False})
    parent_method = -len(asset["Imports"])
    core = "/Script/CoreUObject"
    method_class = ref(core, "Function", core, "Class")
    default_method = ref(core, "Default__Function", core, "Function")
    signature = [p for p in method["LoadedProperties"] if "CPF_Parm" in p["PropertyFlags"].split(", ")]
    if [p["Name"] for p in signature] != ["Owner", "Item", "Transform", "AttachTo", "ReturnValue"]:
        raise ValueError("Voyage Fabricate signature changed")
    types = []
    for field in signature:
        key = "Struct" if field["SerializedType"] == "StructProperty" else "PropertyClass"
        source = stock["Imports"][-1 - field[key]]
        package = stock["Imports"][-1 - source["OuterIndex"]]["ObjectName"]
        field[key] = ref(package, source["ObjectName"], source["ClassPackage"], source["ClassName"])
        types.append(field[key])
    def op(name, **kwargs):
        return {"$type": f"UAssetAPI.Kismet.Bytecode.Expressions.EX_{name}, UAssetAPI", **kwargs}

    def variable(opcode, owner, name):
        pointer = {"$type": "UAssetAPI.Kismet.Bytecode.KismetPropertyPointer, UAssetAPI",
                   "New": {"$type": "UAssetAPI.UnrealTypes.FFieldPath, UAssetAPI",
                           "Path": [name], "ResolvedOwner": owner}}
        return op(opcode, Variable=pointer)

    permit = variable("InstanceVariable", 1, PERMIT)
    clear = op("LetBool", VariableExpression=permit, AssignmentExpression=op("False"))
    parameters = [variable("LocalOutVariable" if p["Name"] == "Transform" else "LocalVariable",
                           3, p["Name"]) for p in signature[:-1]]
    validate = op("FinalFunction", StackNode=4, Parameters=parameters)
    build = op("FinalFunction", StackNode=parent_method, Parameters=parameters)
    # In the UE5.8 x64 VM, a resolved field/function pointer occupies eight
    # bytes. Each variable reference is its opcode plus that pointer. A function
    # call ends with EX_EndFunctionParms. Branch addresses are VM memory offsets.
    variable_bytes = 1 + 8
    clear_bytes = 1 + variable_bytes + 1
    call_bytes = 1 + 8 + variable_bytes * len(parameters) + 1
    branch_bytes = 1 + 4 + variable_bytes
    rejection = clear_bytes + call_bytes + branch_bytes + clear_bytes + 1 + call_bytes
    code = [clear, validate, op("JumpIfNot", CodeOffset=rejection, BooleanExpression=permit),
            clear, op("Return", ReturnExpression=build),
            op("Return", ReturnExpression=op("NoObject")), op("EndOfScript")]
    method.update(ClassIndex=method_class, TemplateIndex=default_method, SuperStruct=parent_method,
                  SuperIndex=parent_method, LoadedProperties=signature,
                  ScriptBytecode=code, ScriptBytecodeRaw=None, ScriptBytecodeSize=rejection + 3,
                  SerializationBeforeCreateDependencies=[method_class, default_method],
                  SerializationBeforeSerializationDependencies=[parent_method],
                  CreateBeforeSerializationDependencies=[*types, 4], CreateBeforeCreateDependencies=[1])
    # Lua hooks this void function. Absence or failure of the callback leaves
    # the per-call permit false. Fabricate clears it again before calling Super.
    validator = deepcopy(method)
    validator.update(ObjectName=VALIDATE, SuperIndex=0, SuperStruct=0,
                     FunctionFlags="FUNC_Public, FUNC_HasOutParms, FUNC_BlueprintCallable",
                     LoadedProperties=deepcopy(signature[:-1]), SerializationBeforeSerializationDependencies=[],
                     CreateBeforeSerializationDependencies=types[:-1], ScriptBytecodeSize=3,
                     ScriptBytecode=[op("Return", ReturnExpression=op("Nothing")), op("EndOfScript")])
    asset["Exports"].extend([method, validator])
    signature_names = [p[key] for p in signature for key in ("Name", "SerializedType")]
    return finish(asset, FACTORY, [*asset["NameMap"], *signature_names, PERMIT, "BoolProperty"])


def carrier_visuals(asset, stock_box, variant=ADVANCED):
    """Override mesh archetypes looked up by the native fabrication renderer."""
    ref = imports_for(asset)
    cls, cdo = asset["Exports"]
    mesh_class = ref("/Script/Engine", "StaticMeshComponent", "/Script/CoreUObject", "Class")
    stock_class = ref(BOX, short(BOX) + "_C", "/Script/Engine", "BlueprintGeneratedClass")
    mesh = ref(variant.mesh, short(variant.mesh), "/Script/Engine", "StaticMesh")
    handler_class = ref("/Script/Engine", "InheritableComponentHandler", "/Script/CoreUObject", "Class")
    default_handler = ref("/Script/Engine", "Default__InheritableComponentHandler",
                          "/Script/Engine", "InheritableComponentHandler")
    stock_handler = next(e for e in stock_box["Exports"] if e["ObjectName"] == "InheritableComponentHandler")
    handler = deepcopy(stock_handler)
    handler.update(ClassIndex=handler_class, TemplateIndex=default_handler,
                   CreateBeforeSerializationDependencies=[],
                   SerializationBeforeCreateDependencies=[handler_class, default_handler])
    asset["Exports"].append(handler)
    cls["Data"] = [prop("Object", "InheritableComponentHandler", 3)]
    cls["CreateBeforeSerializationDependencies"].append(3)
    records = handler["Data"][0]["Value"]
    handler["Data"][0]["Value"] = []
    role_names = []
    for record in records:
        fields = {entry["Name"]: entry for entry in record["Value"]}
        key = {entry["Name"]: entry for entry in fields["ComponentKey"]["Value"]}
        role = key["SCSVariableName"]["Value"]
        stock_template = stock_box["Exports"][fields["ComponentTemplate"]["Value"] - 1]
        stock_type = stock_box["Imports"][-1 - stock_template["ClassIndex"]]["ObjectName"]
        is_inventory = variant.basic and stock_type == "VoyageInventoryWeightLimitedComponent"
        if stock_type != "StaticMeshComponent" and not is_inventory:
            continue
        role_names.append(role)
        name = stock_template["ObjectName"]
        # Imports address templates below the stock BPGC, not below the package.
        asset["Imports"].append({"$type": "UAssetAPI.Import, UAssetAPI", "ObjectName": name,
                                 "OuterIndex": stock_class, "ClassPackage": "/Script/Voyage" if is_inventory else "/Script/Engine",
                                 "ClassName": stock_type, "PackageName": "None", "bImportOptional": False})
        archetype = -len(asset["Imports"])
        owner = stock_box["Imports"][-1 - key["OwnerClass"]["Value"]]
        owner_package = stock_box["Imports"][-1 - owner["OuterIndex"]]["ObjectName"]
        owner_index = ref(owner_package, owner["ObjectName"], "/Script/Engine", "BlueprintGeneratedClass")
        component = deepcopy(stock_template)
        component_class = mesh_class
        data = [prop("Object", "StaticMesh", mesh if role == "StaticMesh" else 0)]
        if is_inventory:
            component_class = ref("/Script/Voyage", stock_type, "/Script/CoreUObject", "Class")
            maximum = next(p for p in component["Data"] if p["Name"] == "MaxWeightLimit")
            data = [{**maximum, "Value": "+0"}]
        component.update(ClassIndex=component_class, TemplateIndex=archetype, Data=data,
                         SerializationBeforeCreateDependencies=[archetype, component_class],
                         CreateBeforeSerializationDependencies=[mesh] if role == "StaticMesh" else [])
        asset["Exports"].append(component)
        new_index = len(asset["Exports"])
        key["OwnerClass"]["Value"] = owner_index
        fields["ComponentTemplate"]["Value"] = new_index
        fields["ComponentClass"]["Value"] = component_class
        record["Name"] = str(len(handler["Data"][0]["Value"]))
        handler["Data"][0]["Value"].append(record)
        handler["CreateBeforeSerializationDependencies"].extend([new_index, owner_index])
        cdo["SerializationBeforeSerializationDependencies"].append(new_index)
    if len(handler["Data"][0]["Value"]) != (6 if variant.basic else 5):
        raise ValueError("Unexpected stock player-box component archetypes")
    return finish(asset, variant.carrier, [*asset["NameMap"], *role_names])


def fixed_winch_mount(asset, stock_ancestors, variant=ADVANCED):
    """Keep the mounted cabinet fixed while leaving its native salvage action available."""
    # Actor tag arrays override the parent array. Carry forward the closest
    # authored defaults before adding Voyage's tag for a fixed snap mount.
    for ancestor in stock_ancestors:
        cdo, = (e for e in ancestor["Exports"] if e["ObjectName"].startswith("Default__"))
        inherited = next((p for p in cdo["Data"] if p["Name"] == "Tags"), None)
        if inherited is not None:
            break
    else:
        raise ValueError("The player box no longer has its native actor tags")
    # Voyage's hand tool checks the target actor for NoGrab before offering
    # Grab or Detach. Snapped separately protects the mount against impacts.
    tags = list(dict.fromkeys([p["Value"] for p in inherited["Value"]] + ["Snapped", "NoGrab"]))
    asset["Exports"][1]["Data"].append(prop("Array", "Tags",
        [prop("Name", str(index), tag) for index, tag in enumerate(tags)], ArrayType="NameProperty"))
    return finish(asset, variant.carrier, [*asset["NameMap"], *tags])


def soft_path(package, object_name):
    return {"$type": "UAssetAPI.PropertyTypes.Objects.FSoftObjectPath, UAssetAPI",
            "AssetPath": {"$type": "UAssetAPI.PropertyTypes.Objects.FTopLevelAssetPath, UAssetAPI",
                          "PackageName": package, "AssetName": object_name},
            "SubPathString": None}


def engineering_skill(layout, item_export, variant=ADVANCED):
    """Build a normal Engineering tier purchase with the cabinet as its single reward."""
    asset = deepcopy(layout)
    asset["Imports"] = []
    skill, = asset["Exports"]
    ref = imports_for(asset)
    skill_class = ref("/Script/Voyage", "VoyageSkill", "/Script/CoreUObject", "Class")
    skill_default = ref("/Script/Voyage", "Default__VoyageSkill", "/Script/Voyage", "VoyageSkill")
    icon = ref(variant.icon, short(variant.icon), "/Script/Engine", "Texture2D")
    reward = ref(variant.item, short(variant.item), "/Script/Voyage", "VoyageItem")
    fields = {p["Name"]: p for p in skill["Data"]}
    unlock = fields["Unlock"]
    method = next(p for p in unlock["Value"] if p["Name"] == "UnlockMethod")
    method["Value"] = "Tier"
    unlock["Value"] = [method, prop("Int", "Cost", variant.points), prop("Int", "Requirement", variant.level)]
    item_text = [deepcopy(p) for p in item_export["Data"] if p["Name"] in ("Name", "Description")]
    skill.update(ObjectName=short(variant.skill), ClassIndex=skill_class, TemplateIndex=skill_default,
                 Data=[unlock, prop("Array", "Items", [prop("Object", "0", reward)], ArrayType="ObjectProperty"),
                       prop("Object", "Icon", icon), *item_text],
                 CreateBeforeSerializationDependencies=[reward, icon],
                 SerializationBeforeCreateDependencies=[skill_class, skill_default])
    return finish(asset, variant.skill, ["None", variant.skill, "Tier"])


def recipe_item(template, device=ADVANCED):
    asset = deepcopy(template)
    item = asset["Exports"][0]
    generator = deepcopy(item)
    fields = {field["Name"]: field for field in item["Data"]}
    asset["Exports"] = [item, generator]
    asset["Imports"] = []
    ref = imports_for(asset)
    item_cls = ref("/Script/Voyage", "VoyageItem", "/Script/CoreUObject", "Class")
    item_cdo = ref("/Script/Voyage", "Default__VoyageItem", "/Script/Voyage", "VoyageItem")
    generator_name = short(GENERATOR) + "_C"
    gen_cls = ref(GENERATOR, generator_name, "/Script/Engine", "BlueprintGeneratedClass")
    gen_cdo = ref(GENERATOR, "Default__" + generator_name, GENERATOR, generator_name)
    factory = ref(FACTORY, short(FACTORY) + "_C", "/Script/Engine", "BlueprintGeneratedClass")
    category = "/Game/Data/Assets/ItemCategories/DA_ItemCategory_Module"
    cat = ref(category, short(category), "/Script/Voyage", "VoyageItemCategoryAsset")
    icon = ref(device.icon, short(device.icon), "/Script/Engine", "Texture2D")
    parts = {}
    for suffix, count in device.parts.items():
        name = "DA_Part_" + suffix
        part = ref("/Game/Data/Assets/Parts/" + name, name, "/Script/Voyage", "VoyageItemPart")
        parts[part] = count
    ingredients = [[prop("Object", "Components", key), prop("Int", "Components", count)]
                   for key, count in parts.items()]
    variant = fields["DropVariations"]
    render = next(field for field in variant["Value"][0]["Value"] if field["Name"] == "RenderAsset")
    render["Value"] = soft_path(device.mesh, short(device.mesh))
    title = fields["Name"]
    description = fields["Description"]
    for field, text in [(title, device.title), (description, device.description)]:
        field.update(HistoryType="None", Flags=2, TableId=None, Value=None, CultureInvariantString=text)
    fields["CraftTime"]["Value"] = device.craft_time
    # The container copies this maximum into its destructible component.
    # Even for an indestructible item Voyage's module rejects power at zero health.
    durability = fields["DestructibleObjectProperties"]
    durability["Value"] = [prop("Float", "Health", CABINET_HEALTH),
                           prop("Float", "DestructionDamageThreshold", 100.0)]
    item["Data"] = [prop("Object", "Icon", icon), fields["Category"], prop("Object", "CategoryAsset", cat),
                    fields["Quality"], prop("Bool", "bIsDismantlable", True),
                    prop("Bool", "bIsDestructible", False), durability,
                    prop("Float", "Weight", device.weight), fields["Tag"], fields["CraftTime"],
                    # The Build menu uses the recipe's generator. The grab tool reads
                    # bAllowPlacement to offer Place on an existing world item.
                    fields["CraftElectricityCost"], prop("Bool", "bAllowPlacement", False),
                    fields["CraftFilter"], prop("Object","CraftingLocationGenerator", 2),
                    prop("Map", "Components", ingredients, KeysToRemove=[]),
                    fields["DismantleDuration"], fields["DismantleElectricityCost"],
                    variant, prop("SoftObject", "DroppedActor", soft_path(device.carrier, short(device.carrier) + "_C")),
                    prop("Map", "properties", [], KeysToRemove=[]), title, description]
    item.update(ObjectName=short(device.item), ClassIndex=item_cls, TemplateIndex=item_cdo,
                CreateBeforeSerializationDependencies=[cat, icon, *parts, 2],
                SerializationBeforeCreateDependencies=[item_cls, item_cdo])
    generator.update(ObjectName="MountLocationGenerator", ClassIndex=gen_cls, TemplateIndex=gen_cdo,
                     OuterIndex=1, Data=[prop("Object", FACTORY_MEMBER, factory)],
                     ObjectFlags="RF_Transactional", bIsAsset=False,
                     CreateBeforeSerializationDependencies=[factory], SerializationBeforeCreateDependencies=[gen_cls, gen_cdo],
                     CreateBeforeCreateDependencies=[1], Extras="")
    return finish(asset, device.item, ["None", "Module", "Uncommon", device.carrier,
                                     short(device.carrier) + "_C", device.mesh, short(device.mesh), device.item])
