"""Compile the cabinet's native, surface-sensitive interaction provider."""
from copy import deepcopy

from construction_packages import ADVANCED, finish, imports_for, prop, short
from construction_power import structure


BASE = "/Game/Blueprints/Interactives/Containers/BP_Container_Base"
PROVIDE = "GetInteractiveProvidedActions"
RESOLVE = "ResolveWinchSurface"
TRIGGER = "WinchControlTriggered"
OPEN = "Interact_OpenTriggered"
TEXT = "GetInteractText"
AIM = "WinchAimSurface"
ACTION = "WinchScreenAction"
AUTOMATION = "WinchAutomationEnabled"
CORE, ENGINE, VOYAGE = "/Script/CoreUObject", "/Script/Engine", "/Script/Voyage"


def op(name, **fields):
    return {"$type": f"UAssetAPI.Kismet.Bytecode.Expressions.EX_{name}, UAssetAPI", **fields}


def pointer(owner, *names):
    return {"$type": "UAssetAPI.Kismet.Bytecode.KismetPropertyPointer, UAssetAPI",
            "New": {"$type": "UAssetAPI.UnrealTypes.FFieldPath, UAssetAPI",
                    "Path": list(names), "ResolvedOwner": owner}}


def variable(kind, owner, name):
    return op(kind, Variable=pointer(owner, name))


def call(method, *args):
    return op("FinalFunction", StackNode=method, Parameters=list(args))


def vm_size(expr):
    """UE5.8 Windows in-memory Kismet sizes (FName 12, pointers 8, skips 4)."""
    kind = expr["$type"].split("EX_", 1)[1].split(",")[0]
    sizes = {"LocalVariable": 9, "LocalOutVariable": 9, "InstanceVariable": 9, "ByteConst": 2,
             "True": 1, "False": 1, "EndOfScript": 1, "Nothing": 1, "NoObject": 1, "Self": 1}
    if kind in sizes:
        return sizes[kind]
    if kind == "BindDelegate":
        return 13 + vm_size(expr["Delegate"]) + vm_size(expr["ObjectTerm"])
    if kind == "StructMemberContext":
        return 9 + vm_size(expr["StructExpression"])
    if kind in ("CallMath", "FinalFunction"):
        return 10 + sum(vm_size(x) for x in expr["Parameters"])
    if kind == "ArrayConst":
        return 14 + sum(vm_size(x) for x in expr["Elements"])
    if kind == "Let":
        return 9 + vm_size(expr["Variable"]) + vm_size(expr["Expression"])
    if kind == "JumpIfNot":
        return 5 + vm_size(expr["BooleanExpression"])
    if kind == "Return":
        return 1 + vm_size(expr["ReturnExpression"])
    raise ValueError(f"Unknown Kismet opcode size: {kind}")


def carrier_interaction(asset, stock, item, variant=ADVANCED):
    ref = imports_for(asset)
    cls, cdo = asset["Exports"][:2]
    original = {e["ObjectName"]: e for e in stock["Exports"]}
    base = (ref(VOYAGE, "InteractiveInterface", CORE, "Class") if variant.basic else
            ref(BASE, short(BASE) + "_C", ENGINE, "BlueprintGeneratedClass"))
    function = ref(CORE, "Function", CORE, "Class")
    default = ref(CORE, "Default__Function", CORE, "Function")

    def member(outer, name):
        asset["Imports"].append({"$type": "UAssetAPI.Import, UAssetAPI", "ObjectName": name,
                                 "OuterIndex": outer, "ClassPackage": CORE, "ClassName": "Function",
                                 "PackageName": "None", "bImportOptional": False})
        return -len(asset["Imports"])

    parent = {name: member(base, name) for name in ((PROVIDE,) if variant.basic else (PROVIDE, OPEN, TEXT))}
    math = ref(ENGINE, "KismetMathLibrary", CORE, "Class")
    equal = member(math, "EqualEqual_ByteByte")
    view = original[PROVIDE]
    action_type = ref(VOYAGE, "PlayerInputInterfaceAction", CORE, "ScriptStruct")
    input_path = "/Game/Game/Input/Character/IAV_Interact"
    interact = ref(input_path, short(input_path), VOYAGE, "VoyageInputAction")

    def signature(name):
        return deepcopy([p for p in original[name]["LoadedProperties"]
                         if "CPF_Parm" in p["PropertyFlags"].split(", ")])

    def import_fields(field, used):
        if "Inner" in field:
            import_fields(field["Inner"], used)
        for key in ("PropertyClass", "Struct", "SignatureFunction"):
            if key in field:
                entry = stock["Imports"][-field[key] - 1]
                namespace = stock["Imports"][-entry["OuterIndex"] - 1]["ObjectName"]
                typename = "ScriptStruct" if key == "Struct" else entry["ClassName"]
                field[key] = ref(namespace, entry["ObjectName"], CORE, typename)
                used.append(field[key])

    template = deepcopy(next(p for p in view["LoadedProperties"] if p["Name"] == "Temp_struct_Variable"))
    template.update(Name=ACTION, Struct=action_type)
    byte_type = dict(template, Name=AIM, SerializedType="ByteProperty", ElementSize=1,
                     PropertyFlags="CPF_Transient, CPF_BlueprintVisible", Enum=0)
    byte_type["$type"] = "UAssetAPI.FieldTypes.FByteProperty, UAssetAPI"
    del byte_type["Struct"]
    saved_bool = next(p for p in original[short(BASE) + "_C"]["LoadedProperties"] if p["Name"] == "IsLocked")
    cls["LoadedProperties"].extend([byte_type, template, {**saved_bool, "Name": AUTOMATION}])
    cls["CreateBeforeSerializationDependencies"].append(action_type)
    label = deepcopy(next(p for p in item["Exports"][0]["Data"] if p["Name"] == "Name"))
    label.update(Name="Text", HistoryType="None", Flags="CultureInvariant",
                 Value=None, CultureInvariantString="Winch settings")
    label.pop("TableId", None)
    struct = next(p for e in asset["Exports"] for p in e["Data"] if p["Name"] == "ConfigData")
    cdo["Data"].append(structure(struct, ACTION, "PlayerInputInterfaceAction", [
        prop("Object", "InputAction", interact), prop("Str", "Name", "WinchControl"),
        label, prop("Bool", "bEnabled", True), prop("Bool", "bAppendTargetName", False),
        prop("Bool", "bTriggerOnce", True)]))
    if not variant.basic:
        next(p for p in cdo["Data"] if p["Name"] == "InteractEnabled")["Value"] = True
    cdo["CreateBeforeSerializationDependencies"].extend([interact, action_type])
    methods = {}
    originals = {PROVIDE: PROVIDE, RESOLVE: PROVIDE, TRIGGER: OPEN}
    if not variant.basic:
        originals.update({OPEN: OPEN, TEXT: TEXT})
    for name, source in originals.items():
        method_id = len(asset["Exports"]) + 1
        sig = signature(source)
        if name == RESOLVE:
            sig = sig[:2]
        used = []
        for field in sig:
            import_fields(field, used)
        exp = deepcopy(original[source])
        super_method = parent.get(name, 0)
        exp.update(ObjectName=name, OuterIndex=1, ClassIndex=function, TemplateIndex=default,
                   SuperStruct=super_method, SuperIndex=super_method, LoadedProperties=sig,
                   SerializationBeforeSerializationDependencies=[super_method] if super_method else [],
                   CreateBeforeSerializationDependencies=list(dict.fromkeys(used)),
                   SerializationBeforeCreateDependencies=[function, default],
                   CreateBeforeCreateDependencies=[1], ScriptBytecodeRaw=None)
        if name in (TRIGGER, RESOLVE):
            exp["FunctionFlags"] = "FUNC_Public, FUNC_BlueprintCallable" + (", FUNC_HasOutParms" if name == TRIGGER else "")
        asset["Exports"].append(exp)
        cls["Children"].append(method_id)
        cls["FuncMap"].append([name, method_id])
        cls["CreateBeforeSerializationDependencies"].append(method_id)
        methods[name] = method_id

    aim = variable("InstanceVariable", 1, AIM)
    action = variable("InstanceVariable", 1, ACTION)
    none = op("NoObject")
    unused = op("Return", ReturnExpression=op("Nothing"))
    def set_aim():
        return op("Let", Value=pointer(1, AIM), Variable=aim, Expression=op("ByteConst", Value=2 if variant.basic else 0))
    def test(value):
        return op("CallMath", StackNode=equal, Parameters=[aim, op("ByteConst", Value=value)])
    def ret(expression):
        return op("Return", ReturnExpression=expression)
    def guarded(code, value, body):
        jump = op("JumpIfNot", CodeOffset=0, BooleanExpression=test(value))
        code.extend([jump, *body])
        jump["CodeOffset"] = sum(vm_size(x) for x in code)

    for name, ix in methods.items():
        exp = asset["Exports"][ix - 1]
        args = [variable("LocalOutVariable" if "CPF_OutParm" in f["PropertyFlags"] else "LocalVariable",
                         ix, f["Name"]) for f in exp["LoadedProperties"] if f["Name"] != "ReturnValue"]
        if name in (TRIGGER, RESOLVE):
            code = [unused]
        else:
            code = [set_aim(), call(methods[RESOLVE], *(args[:2] if name == PROVIDE else [none, none]))]
            exp["CreateBeforeSerializationDependencies"].extend([methods[RESOLVE], equal])
            if name == PROVIDE:
                field = op("StructMemberContext", StructMemberExpression=pointer(action_type, "OnTriggered"),
                           StructExpression=action)
                bind = op("BindDelegate", FunctionName=TRIGGER, Delegate=field, ObjectTerm=op("Self"))
                def actions(elements):
                    return op("Let", Value=pointer(ix, "OutActions"), Variable=args[2],
                              Expression=op("ArrayConst", InnerProperty=pointer(ix, "OutActions", "OutActions"),
                                            Elements=elements, Value=None))
                guarded(code, 1, [bind, actions([action]), ret(op("True"))])
                if variant.basic:
                    code.extend([actions([]), ret(op("False"))])
                else:
                    guarded(code, 2, [actions([]), ret(op("False"))])
                    code.append(ret(call(parent[name], *args)))
                exp["CreateBeforeSerializationDependencies"].extend([action_type, methods[TRIGGER]])
            elif name == OPEN:
                guarded(code, 1, [call(methods[TRIGGER], *args), unused])
                if not variant.basic:
                    guarded(code, 0, [call(parent[name], *args), unused])
                code.append(unused)
                exp["CreateBeforeSerializationDependencies"].append(methods[TRIGGER])
            else:
                if not variant.basic:
                    guarded(code, 0, [ret(call(parent[name], *args))])
                code.append(ret(op("False")))
        code.append(op("EndOfScript"))
        exp.update(ScriptBytecode=code, ScriptBytecodeSize=sum(vm_size(x) for x in code))
    names = [*asset["NameMap"], AIM, ACTION, AUTOMATION, "BoolProperty", "ByteProperty", "ObjectProperty", "StructProperty",
             "OnTriggered", "WinchControl"]
    for id_ in methods.values():
        for f in asset["Exports"][id_ - 1]["LoadedProperties"]:
            names.extend([f["Name"], f["SerializedType"]])
    return finish(asset, variant.carrier, names)
