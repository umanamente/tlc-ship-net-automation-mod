"""Build the stand-alone Basic winch module on Voyage's native module actor."""
from copy import deepcopy
from zlib import crc32

from construction_packages import BASIC, CABINET_HEALTH, MODULE_ACTOR, child_blueprint, finish, imports_for, prop, short
from construction_power import INLET, MODULE, SOCKET_GUID, SOCKET_TYPE, fields, receiver_data, socket_names, socket_view, structure


def basic_module(layout, machine, item_template):
    asset = child_blueprint(layout, BASIC.carrier, MODULE_ACTOR, BASIC)
    cls, cdo = asset["Exports"]
    ref = imports_for(asset)
    core, engine, voyage = "/Script/CoreUObject", "/Script/Engine", "/Script/Voyage"
    donor = {e["ObjectName"]: e for e in machine["Exports"]}
    item = ref(BASIC.item, short(BASIC.item), voyage, "VoyageItem")
    mesh = ref(BASIC.mesh, short(BASIC.mesh), engine, "StaticMesh")
    native_default = cdo["TemplateIndex"]
    names = [*asset["NameMap"], "StaticMesh", INLET, MODULE, "ObjectProperty", "NoFabrication", "Snapped", "NoGrab"]

    def append(template, name, package, kind, outer, data, dependencies=(), native=False):
        component_class = ref(package, kind, core, "Class")
        if native:
            # A native default subobject overrides the matching object on the
            # parent CDO, not the constructor of its component class.
            asset["Imports"].append({"$type": "UAssetAPI.Import, UAssetAPI", "ObjectName": name,
                                     "OuterIndex": native_default, "ClassPackage": package, "ClassName": kind,
                                     "PackageName": "None", "bImportOptional": False})
            archetype = -len(asset["Imports"])
        else:
            archetype = ref(package, "Default__" + kind, package, kind)
        entry = deepcopy(template)
        entry.update(ObjectName=name, ClassIndex=component_class, TemplateIndex=archetype, OuterIndex=outer,
                     Data=data, SerializationBeforeSerializationDependencies=([outer] if native or name.endswith("_GEN_VARIABLE") else []),
                     CreateBeforeSerializationDependencies=list(dependencies),
                     SerializationBeforeCreateDependencies=[component_class, archetype], CreateBeforeCreateDependencies=[outer])
        asset["Exports"].append(entry)
        return len(asset["Exports"])

    machine_class = next(e for e in machine["Exports"] if e["ObjectName"].endswith("FoodProcessor_C") and "ClassFlags" in e)
    cls["ClassFlags"] = machine_class["ClassFlags"]
    config = fields(donor["ModuleComponent"]["Data"])["ConfigData"]
    module = append(donor["ModuleComponent"], "ModuleComponent", voyage, "VoyageModuleComponent", 2,
                    receiver_data(config, item), [item], native=True)
    persistent = append(donor["PersistentComponent"], "PersistentComponent", voyage,
                        "VoyagePersistentActorComponent", 2, [prop("Bool", "bAlwaysPersist", True)], native=True)
    health = fields(item_template["Exports"][0]["Data"])["DestructibleObjectProperties"]
    durability = append(donor["DestructibleObjectComponent"], "DestructibleObjectComponent", voyage,
                        "VoyageDestructibleObjectComponent", 2,
                        [prop("Bool", "bIsDestructible", False), prop("Float", "Health", CABINET_HEALTH),
                         structure(health, "DestructibleObjectProperties", "VoyageDestructibleObjectProperties",
                                   [prop("Float", "Health", CABINET_HEALTH), prop("Float", "DestructionDamageThreshold", 100.0)])],
                        native=True)
    cdo["Data"] = [prop("Object", "ModuleComponent", module), prop("Object", "PersistentComponent", persistent),
                   prop("Object", "DestructibleObjectComponent", durability),
                   prop("Array", "Tags", [prop("Name", str(i), tag) for i, tag in enumerate(("NoFabrication", "Snapped", "NoGrab"))],
                        ArrayType="NameProperty")]
    cdo["CreateBeforeSerializationDependencies"] = [module, persistent, durability]

    # The SCS mesh root keeps the existing mounted coordinate frame. Only the
    # exposed panel has solid collision, authored in SM_WinchAutomatorBasic.
    mesh_template = donor["StaticMesh_GEN_VARIABLE"]
    body = fields(mesh_template["Data"])["BodyInstance"]
    mesh_component = append(mesh_template, "StaticMesh_GEN_VARIABLE", engine, "StaticMeshComponent", 1,
                            [prop("Object", "StaticMesh", mesh), structure(body, "BodyInstance", "BodyInstance", [
                                prop("Name", "CollisionProfileName", "PhysicsActor"), prop("Float", "MassInKgOverride", BASIC.weight),
                                prop("Bool", "bSimulatePhysics", False), prop("Bool", "bOverrideMass", True)])],
                            [mesh])
    names.append("PhysicsActor")
    socket_template = donor["VoyageModuleSocketView_GEN_VARIABLE"]
    view = socket_view(socket_template, BASIC)
    socket = append(socket_template, INLET + "_GEN_VARIABLE", voyage, SOCKET_TYPE, 1,
                    [*view.values(), prop("Name", "OwningModule", MODULE)])
    names.extend(socket_names(view))

    scs_index = len(asset["Exports"]) + 1
    root_node, socket_node = scs_index + 1, scs_index + 2
    def objects(name, indices):
        return prop("Array", name, [prop("Object", str(i), index) for i, index in enumerate(indices)],
                    ArrayType="ObjectProperty")
    scs = append(donor["SimpleConstructionScript_0"], "SimpleConstructionScript_0", engine, "SimpleConstructionScript", 1,
                 [objects("RootNodes", [root_node]), objects("AllNodes", [root_node, socket_node])], [root_node, socket_node])
    node_template = next(e for e in machine["Exports"] if e["ObjectName"].startswith("SCS_Node")
                         and fields(e["Data"]).get("VariableGUID"))
    for ordinal, (name, component, guid, children) in enumerate((
            ("StaticMesh", mesh_component, "{2873BE45-0BD5-4ED9-A640-3C13C22E53B7}", [socket_node]),
            (INLET, socket, SOCKET_GUID, []))):
        kind = asset["Exports"][component - 1]["ClassIndex"]
        field = deepcopy(fields(node_template["Data"])["VariableGUID"])
        field["Value"][0]["Value"] = guid
        node_data = [prop("Object", "ComponentClass", kind), prop("Object", "ComponentTemplate", component),
                     field, prop("Name", "InternalVariableName", name)]
        if children:
            node_data.append(objects("ChildNodes", children))
        append(node_template, "SCS_Node_" + str(ordinal), engine, "SCS_Node", scs, node_data, [component, *children])
    cls["Data"] = [prop("Object", "SimpleConstructionScript", scs)]
    cls["CreateBeforeSerializationDependencies"].append(scs)
    cdo["SerializationBeforeSerializationDependencies"].extend([mesh_component, socket])
    for old, new, component in (("StaticMesh", "StaticMesh", mesh_component), ("VoyageModuleSocketView", INLET, socket)):
        variable = next(field for field in machine_class["LoadedProperties"] if field["Name"] == old)
        component_class = asset["Exports"][component - 1]["ClassIndex"]
        cls["LoadedProperties"].append({**variable, "Name": new, "PropertyClass": component_class})
        cls["CreateBeforeSerializationDependencies"].append(component_class)
    return finish(asset, BASIC.carrier, names)


def verify_basic_module(asset):
    exports, imports = asset["Exports"], asset["Imports"]
    cls, cdo = exports[:2]
    by_name = {e["ObjectName"]: e for e in exports}
    parent = imports[-1 - cls["SuperStruct"]]
    if (parent["ObjectName"] != "VoyageModuleActor" or imports[-1 - parent["OuterIndex"]]["ObjectName"] != "/Script/Voyage"
            or any(word in entry["ObjectName"] for entry in imports for word in
                   ("Inventory", "PlayerBox", "Container", "Grabbable", "VoyageDynamicCollision", "Buoyancy", "UnWeld"))):
        raise ValueError("Basic must be a native Voyage module without stock crate dependencies")

    for role in ("ModuleComponent", "PersistentComponent", "DestructibleObjectComponent"):
        entry = exports[fields(cdo["Data"])[role]["Value"] - 1]
        archetype = imports[-1 - entry["TemplateIndex"]]
        if (entry["OuterIndex"] != 2 or entry["ObjectName"] != role or archetype["ObjectName"] != role
                or archetype["OuterIndex"] != cdo["TemplateIndex"]):
            raise ValueError(f"Basic must override the native {role} default subobject")

    scs = fields(by_name["SimpleConstructionScript_0"]["Data"])
    root, = scs["RootNodes"]["Value"]
    root_node = fields(exports[root["Value"] - 1]["Data"])
    child, = root_node["ChildNodes"]["Value"]
    child_node = fields(exports[child["Value"] - 1]["Data"])
    port = fields(by_name[INLET + "_GEN_VARIABLE"]["Data"])
    if (len(scs["AllNodes"]["Value"]) != 2 or root_node["InternalVariableName"]["Value"] != "StaticMesh"
            or child_node["InternalVariableName"]["Value"] != INLET or child_node["VariableGUID"]["Value"][0]["Value"] != SOCKET_GUID
            or port["SocketID"]["Value"] != crc32(f"{BASIC.carrier}.{INLET}".encode("ascii"))
            or port["OwningModule"]["Value"] != MODULE or fields(by_name["ModuleComponent"]["Data"])["ModuleName"]["Value"] != MODULE):
        raise ValueError("Basic must retain its physical mesh root and persistent electrical inlet identity")
