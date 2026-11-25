"""Author the carrier's persistent electrical socket and its inherited receiver."""
from copy import deepcopy
from zlib import crc32

from construction_packages import ADVANCED, finish, imports_for, prop, short


PLAYER_BOX = "/Game/Blueprints/Interactives/Containers/BP_Inventory_PlayerBox"
REFERENCE_MACHINE = "BP_Module_FoodProcessor"
INLET = "WinchPowerInlet"
MODULE = "VoyageModule"
SOCKET_TYPE = "VoyageModuleSocketViewComponent"
SOCKET_GUID = "{ADBB2018-9A93-5DA3-9522-B543C77DCEA2}"


def fields(properties):
    return {p["Name"]: p for p in properties}


def structure(format_field, name, struct_type, children):
    field = deepcopy(format_field)
    field.update(Name=name, StructType=struct_type, Value=children)
    return field


def enum(name, kind, value):
    return prop("Enum", name, value, EnumType=kind, InnerType="ByteProperty")


def receiver_data(config, item):
    # Use the stock electrical input bandwidth, as on the Food Processor. The
    # 8 kJ receiver starts empty and accepts offers only while automation is on.
    # Lua debits each interval before allowing the winch to advance.
    settings = [enum("ModuleResourceType", "EModuleResourceType", "Electricity"),
                prop("Bool", "bAcceptResourceOffer", False), prop("Bool", "bAcceptResourceOfferOff", False),
                prop("Double", "ResourceBandwidthOutput", "+0"),
                prop("Double", "DefaultResourceAmount", "+0"), prop("Double", "MaxResourceAmount", 8.0),
                prop("Double", "ResourceConsumptionStandby", "+0"), prop("Double", "ResourceConsumptionOn", "+0"),
                prop("Bool", "bShareResources", False), prop("Bool", "bShareResourcesOff", False)]
    return [
        prop("Bool", "bRegisterModule", True), prop("Bool", "bExcludeFromSharedGroups", True),
        prop("Object", "ItemAsset", item),
        structure(config, "ConfigData", "ModuleConfigData", settings),
        prop("Name", "ModuleName", MODULE)]


def socket_view(view_layout, variant):
    view = fields(deepcopy(view_layout["Data"]))
    # Use a stable template ID and SCS name. Voyage assigns its own socket ID
    # to the live instance while registering it with its owning module.
    view["SocketID"]["Value"] = crc32(f"{variant.carrier}.{INLET}".encode("ascii"))
    view["bAutoInitialize"]["Value"] = True
    port = view["Port"]
    port["Value"] = [enum("Type", "EModuleSocketType", "ST_Input"),
                     enum("ResourceType", "EModuleResourceType", "Electricity"),
                     enum("DefaultDirection", "EModuleSocketType", "ST_Input")]
    view["RelativeLocation"]["Value"][0]["Value"].update(X=-68.4, Y=-0.5, Z=29.8)
    view["RelativeRotation"]["Value"][0]["Value"].update(Pitch="+0", Yaw=90.0, Roll=-90.0)
    if variant.basic:
        view["RelativeLocation"]["Value"][0]["Value"].update(X=180.6, Y=120.4, Z=-26.9)
        view["RelativeRotation"]["Value"][0]["Value"].update(Pitch="+0", Yaw="+0", Roll=-90.0)
        scale = deepcopy(view["RelativeLocation"])
        scale["Name"] = scale["Value"][0]["Name"] = "RelativeScale3D"
        scale["Value"][0]["Value"].update(X=0.55, Y=0.55, Z=0.55)
        view[scale["Name"]] = scale
    if view["DataAsset"]["Value"]["AssetPath"]["AssetName"] != "DA_Socket_ElectricData":
        raise ValueError("The reference machine no longer uses the standard electrical input")
    return view


def socket_names(view):
    names = []
    for field in view.values():
        value = field["Value"]
        if field["$type"].endswith("SoftObjectPropertyData, UAssetAPI"):
            names.extend(value["AssetPath"].values())
    channels = fields(view["BodyInstance"]["Value"])["CollisionResponses"]
    responses = fields(channels["Value"])["ResponseArray"]["Value"]
    names.extend(fields(row["Value"])["Channel"]["Value"] for row in responses)
    return names


def carrier_power(asset, stock_box, stock_machine, variant=ADVANCED):
    """An inherited inventory module plus one SCS socket exist before the save loads cables."""
    ref = imports_for(asset)
    cls, cdo, handler = asset["Exports"][:3]
    stock_exports = {e["ObjectName"]: e for e in stock_box["Exports"]}
    machine_exports = {e["ObjectName"]: e for e in stock_machine["Exports"]}
    view_layout = machine_exports["VoyageModuleSocketView_GEN_VARIABLE"]
    module_layout = stock_exports[MODULE + "_GEN_VARIABLE"]
    config = fields(machine_exports["ModuleComponent"]["Data"])["ConfigData"]
    core, engine, voyage = "/Script/CoreUObject", "/Script/Engine", "/Script/Voyage"
    owner = ref(PLAYER_BOX, short(PLAYER_BOX) + "_C", engine, "BlueprintGeneratedClass")

    def append(template, role, package, kind, outer, data, dependencies=(), archetype=None):
        component_class = ref(package, kind, core, "Class")
        if archetype is None:
            archetype = ref(package, "Default__" + kind, package, kind)
        exp = deepcopy(template)
        exp.update(ObjectName=role, ClassIndex=component_class, TemplateIndex=archetype,
                   OuterIndex=outer, Data=data, CreateBeforeSerializationDependencies=list(dependencies),
                   SerializationBeforeSerializationDependencies=([1] if role.endswith("_GEN_VARIABLE") else []),
                   SerializationBeforeCreateDependencies=[component_class, archetype],
                   CreateBeforeCreateDependencies=[outer])
        asset["Exports"].append(exp)
        return len(asset["Exports"])

    # Stock PlayerBox declares an empty VoyageModule SCS template. Override it
    # through its original owner/GUID just as UE resolves inherited mesh edits.
    name = module_layout["ObjectName"]
    module_type = "VoyageModuleComponent"
    module_class = ref(voyage, module_type, core, "Class")
    asset["Imports"].append({"$type": "UAssetAPI.Import, UAssetAPI", "ObjectName": name,
                             "OuterIndex": owner, "ClassPackage": voyage, "ClassName": module_type,
                             "PackageName": "None", "bImportOptional": False})
    archetype = -len(asset["Imports"])
    item = fields(cdo["Data"])["ContainerItem"]["Value"]
    module = append(module_layout, name, voyage, module_type, 1, receiver_data(config, item),
                    dependencies=[item], archetype=archetype)
    records = handler["Data"][0]["Value"]
    record = deepcopy(records[0])
    record["Name"] = str(len(records))
    key = fields(record["Value"])
    key["ComponentClass"]["Value"], key["ComponentTemplate"]["Value"] = module_class, module
    identity = fields(key["ComponentKey"]["Value"])
    identity["OwnerClass"]["Value"], identity["SCSVariableName"]["Value"] = owner, MODULE
    module_node, = (fields(e["Data"]) for e in stock_box["Exports"]
                    if fields(e["Data"]).get("InternalVariableName", {}).get("Value") == MODULE)
    identity["AssociatedGuid"]["Value"][0]["Value"] = module_node["VariableGUID"]["Value"][0]["Value"]
    records.append(record)
    handler["CreateBeforeSerializationDependencies"].extend([module, owner])
    cdo["SerializationBeforeSerializationDependencies"].append(module)

    view = socket_view(view_layout, variant)
    socket = append(view_layout, INLET + "_GEN_VARIABLE", voyage, SOCKET_TYPE, 1,
                    [*view.values(), prop("Name", "OwningModule", MODULE)])
    socket_class = asset["Exports"][socket - 1]["ClassIndex"]
    next_index = len(asset["Exports"]) + 1
    node_id = next_index + 1
    def node_list(name):
        return prop("Array", name, [prop("Object", "0", node_id)], ArrayType="ObjectProperty")
    scs = append(stock_exports["SimpleConstructionScript_0"], "SimpleConstructionScript_0",
                 engine, "SimpleConstructionScript", 1,
                 [node_list("RootNodes"), node_list("AllNodes")], [node_id])
    guid = deepcopy(module_node["VariableGUID"])
    guid["Value"][0]["Value"] = SOCKET_GUID
    append(stock_exports["SCS_Node_0"], "SCS_Node_0", engine, "SCS_Node", scs,
           [prop("Object", "ComponentClass", socket_class), prop("Object", "ComponentTemplate", socket),
            guid, prop("Name", "InternalVariableName", INLET)], [socket])
    cls["Data"].append(prop("Object", "SimpleConstructionScript", scs))
    cls["CreateBeforeSerializationDependencies"].extend([scs, socket_class])
    cdo["SerializationBeforeSerializationDependencies"].append(socket)
    machine_class, = (e for e in stock_machine["Exports"] if e["ObjectName"] == REFERENCE_MACHINE + "_C")
    variable, = (p for p in machine_class["LoadedProperties"] if p["Name"] == "VoyageModuleSocketView")
    cls["LoadedProperties"] = [{**variable, "PropertyClass": socket_class, "Name": INLET}]

    # Soft object paths, UField names and native collision channel names use
    # the package name map even though their containing properties are unversioned.
    names = [*asset["NameMap"], INLET, MODULE, "ObjectProperty"]
    names.extend(socket_names(view))
    return finish(asset, variant.carrier, names)
