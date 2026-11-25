-- Evaluated geometry of the original Blender model, loaded only on demand.
local M = {}
local display = require("shipnet.display")
local cargo_meter = require("shipnet.cargo_meter")
local variants = require("shipnet.variants")
local palette = require("shipnet.model_palette")
local source = debug.getinfo(1, "S").source:gsub("\\", "/")
local directory = assert(source:match("^@(.*)/model%.lua$"))
local groups = {SNR1={"body", "hatch", "drive"}, SNR2={"body", "hatch", "drive", "fill"}, SNRB={"body", "drive", "beacon"}}
local material_path = "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"
local proc_class = "/Script/ProceduralMeshComponent.ProceduralMeshComponent"

M.maxHatchDegrees = 2
M.fitGeometry = {
    halfWidthCm=68, halfDepthCm=58,
    outerSeat={minX=-66.95, maxX=-55.25, minY=-57.95, maxY=57.95},
    rightContact={Y=39.5, Z=11, surfaceX=61.2175, tipX=61.6675, insetCm=0.45,
        minY=32, maxY=47, minZ=8, maxZ=14, slopeXZ=0.2325},
    -- The screen's front plane faces the player along positive local Y.
    display={minX=-39.2, maxX=30.8, minZ=18.5, maxZ=40.5, Y=57.6,
        rimY=57.50,lensY=57.39,lcdY=57.19,rearShift=.65,bezelSlot=4,glassSlot=3},
    fillBar={minX=-38.4, maxX=30.0, Z=52.0, Y=58.165, height=2.9},
    -- Maximum case X at each height, surveyed against the stock drum across the drawer.
    rightProfileCm={
        {X=51.8,Z=0}, {X=54.5,Z=8}, {X=57.2,Z=16}, {X=59.9,Z=24},
        {X=62.6,Z=32}, {X=64.1,Z=36}, {X=66.6,Z=39}, {X=68,Z=41},
    },
}
M.anchors = {
    coupling = {X=125.71, Y=100.80, Z=60.2},
    inlet = {X=-68.4, Y=-0.5, Z=29.8},
    hatch = {X=0, Y=-54.5, Z=63.7},
    drive = {X=86.7, Y=100.80, Z=60.2},
    display = {X=-4.2, Y=57.6, Z=29.5},
    rightContact = {X=61.6675, Y=39.5, Z=11},
}

local function valid(object)
    return object and object:IsValid()
end

local function read_asset(basic, distant)
    local name = (basic and "basic_controller" or "rail_controller") .. (distant and "_lod1.snm" or ".snm")
    local file = assert(io.open(directory .. "/" .. name, "rb"))
    local data = file:read("a")
    file:close()
    assert(data and groups[data:sub(1, 4)], "invalid rail geometry header")
    return data
end

local function basic_material()
    local material = StaticFindObject(material_path)
    if not valid(material) then
        local registry = StaticFindObject("/Script/AssetRegistry.Default__AssetRegistryHelpers")
        if valid(registry) then
            material = registry:GetAsset({
                PackageName=FName("/Engine/BasicShapes/BasicShapeMaterial", EFindName.FNAME_Add),
                AssetName=FName("BasicShapeMaterial", EFindName.FNAME_Add),
            })
        end
    end
    if valid(material) then return material end
end

local function section_material(result, component, slot, base, red, green, blue, roughness)
    if not base then return end
    local key = string.pack("<ffff", red, green, blue, roughness)
    local instance = result.materials[key]
    if valid(instance) then
        component:SetMaterial(slot, instance)
        return
    end
    instance = component:CreateDynamicMaterialInstance(slot, base, FName("None", EFindName.FNAME_Find))
    assert(valid(instance), "could not create preview material")
    instance:SetVectorParameterValue(FName("Color", EFindName.FNAME_Add), {R=red, G=green, B=blue, A=1})
    instance:SetScalarParameterValue(FName("Roughness", EFindName.FNAME_Add), roughness)
    result.materials[key] = instance
end

-- The shell, glass backing, structural joints and shaft still answer the game's traces.
-- Printed faces, recessed screw impressions and the painted shaft stripe sit on those surfaces.
local decorativeSlots = {
    body={[1]=true,[2]=true,[8]=true},
    hatch={[2]=true},
    drive={[1]=true,[2]=true},
}

local function read_section(result, component, group, slot, data, pos, base, collision, batch)
    local red, green, blue, roughness, vertices, indices
    red, green, blue, roughness, vertices, indices, pos = string.unpack("<ffffI4I4", data, pos)
    assert(vertices > 0 and vertices <= 65535 and indices > 0 and indices % 3 == 0,
        "invalid section dimensions")
    assert(pos + vertices * 12 + indices * 2 <= #data + 1, "truncated mesh section")
    if not component then return pos + vertices * 12 + indices * 2 end
    local positions, normals, triangles = {}, {}, {}
    for i=1,vertices do
        local x, y, z, nx, ny, nz
        x, y, z, nx, ny, nz, pos = string.unpack("<i2i2i2i2i2i2", data, pos)
        positions[i] = {X=x/100, Y=y/100, Z=z/100}
        normals[i] = {X=nx/32767, Y=ny/32767, Z=nz/32767}
    end
    for i=1,indices do
        local index
        index, pos = string.unpack("<I2", data, pos)
        assert(index < vertices, "triangle index exceeds vertex count")
        triangles[i] = index
    end
    local glass = group == "body" and result.liveGlass
    if glass then
        if slot==glass.bezelSlot then
            triangles=display.openBezel(glass,positions,normals,triangles)
            vertices,indices=#positions,#triangles
        elseif slot==glass.glassSlot or slot==1 or slot==2 then
            -- The original smoked backing and both printed SETTINGS sections.
            for _,v in ipairs(positions) do v.Y=v.Y-glass.rearShift end
        end
    end
    local bodyInk = group == "body" and slot == 8
    result.triangles = result.triangles + indices // 3
    result.vertices = result.vertices + vertices
    -- Keep controls and independently textured labels addressable; the opaque rigid surfaces can share one draw.
    local screenArt = group == "body" and (slot == 1 or slot == 2)
    if batch and not bodyInk and not screenArt then
        palette.append(batch,result.palette,positions,normals,triangles,red,green,blue,roughness)
        return pos
    end
    local target = component:GetNumSections()
    if screenArt then result.artSlots[#result.artSlots+1] = target end
    local labels = result.basic and 5 or 1
    local printed = bodyInk and vertices == labels * 4 and indices == labels * 6
    if printed then
        local ok, err = require("shipnet.printed_labels").apply(component,target,positions,triangles,normals,result.basic)
        if not ok then result.labelError = tostring(err) end
    else
        local decorative = (decorativeSlots[group] and decorativeSlots[group][slot])
            or (result.basic and group == "body" and slot == 6)
        component:CreateMeshSection_LinearColor(target, positions, triangles, normals, {}, {}, {}, {}, {}, {},
            collision and not decorative, false)
    end
    assert(component:GetNumSections() == target + 1, "procedural section was not created")
    local created = component.ProcMeshSections[target + 1]
    local actual_vertices = created.ProcVertexBuffer:GetArrayNum()
    local actual_indices = created.ProcIndexBuffer:GetArrayNum()
    assert(actual_vertices == vertices and actual_indices == indices,
        ("geometry count mismatch at slot %d (vertices %d/%d, indices %d/%d)"):format(
            slot, actual_vertices, vertices, actual_indices, indices))
    if not printed then
        local ok, err = pcall(section_material, result, component, target, base, red, green, blue, roughness)
        if not ok then result.materialStatus = "engine default; " .. tostring(err) end
    end
    result.sections = result.sections + 1
    return pos
end

local function add_group(result, actor, root, class, maths, group, pivot)
    local transform = maths:MakeTransform(pivot, {Pitch=0,Yaw=0,Roll=0}, {X=1,Y=1,Z=1})
    local component = actor:AddComponentByClass(class, false, transform, false)
    assert(valid(component), "cannot create " .. group .. " procedural component")
    result.components[#result.components + 1] = component
    result[group] = component
    component:SetMobility(2)
    component:SetCollisionEnabled(0)
    component:SetGenerateOverlapEvents(false)
    component.bUseComplexAsSimpleCollision = true
    local parent = component:GetAttachParent()
    assert(valid(parent) and parent:GetAddress() == root:GetAddress(),
        "automatic " .. group .. " attachment has unexpected parent")
    return component
end

local function start_geometry(result, actor, rootComponent, basic, near)
    assert(valid(actor) and valid(rootComponent), "preview actor or root component is unavailable")
    local data = read_asset(basic, near ~= nil)
    result.format = data:sub(1,4)
    result.artSlots = {}
    assert(not near or near.format == result.format, "LOD geometry is from a different controller")
    local class = StaticFindObject(proc_class)
    local maths = StaticFindObject("/Script/Engine.Default__KismetMathLibrary")
    assert(valid(class), "procedural mesh class is unavailable")
    assert(valid(maths), "transform library is unavailable")
    local material_ok, base = pcall(basic_material)
    if not material_ok or not base then
        result.materialStatus = "engine default; BasicShapeMaterial unavailable"
        base = nil
    end
    local pos = 5
    local function start_group(group)
        local x, y, z, count
        x, y, z, count, pos = string.unpack("<fffI2", data, pos)
        local shared = group == "fill" or group == "beacon"
        local sharedStart, sharedSections = result.triangles, result.sections
        if not near and group == "fill" then
            local ok, err = pcall(cargo_meter.mount, result, actor, rootComponent, maths, M.fitGeometry.fillBar)
            result.stockMeter = ok
            if ok then
                result.triangles = result.triangles + 2
                result.vertices = result.vertices + 4
                result.sections = result.sections + 1
            else
                result.meterError = tostring(err)
            end
        end
        local name, material = group, base
        if group == "fill" and result.stockMeter then
            name, material = "alarmCells", nil
        end
        local component
        if not (near and shared) then
            component = add_group(result, actor, rootComponent, class, maths, name, {X=x,Y=y,Z=z})
            if near or name == "alarmCells" then component:SetVisibility(false, false) end
        end
        local batch = component and result.palette and palette.newBatch()
        assert(count > 0, "empty geometry group")
        local slot = 0
        return function()
            pos = read_section(result, component, group, slot, data, pos, material, not near and not shared,batch)
            slot = slot + 1
            if slot < count then return false end
            if batch then
                palette.upload(batch,component,result.palette)
                result.sections = result.sections + 1
            else
                assert(not component or component:GetNumSections() == count, group .. " section count mismatch")
            end
            if not near and shared then
                result.sharedTriangles = result.triangles - sharedStart
                result.sharedSections = result.sections - sharedSections
            end
            return true
        end
    end
    local order, groupIndex, advanceSection = groups[result.format], 1, nil
    -- UE4SS reflection accepts its registered Lua state only. The cursor is an ordinary closure
    -- called on the original game-thread callback, retaining partial buffers between polls.
    return function(vertexBudget)
        local limit = result.vertices + vertexBudget
        repeat
            advanceSection = advanceSection or start_group(order[groupIndex])
            if advanceSection() then
                groupIndex = groupIndex + 1
                advanceSection = nil
            end
        until groupIndex > #order or result.vertices >= limit
        if groupIndex <= #order then return false end
        assert(pos == #data + 1, "unexpected trailing model data")
        if result.fill and not result.stockMeter then
            result.fill:SetVisibility(false, false)
            result.fillFraction = 0
        end
        if result.fill or basic or (near and near.fill) then
            local glass = basic and variants.basic.geometry.fitGeometry.display or M.fitGeometry.display
            result.screenSlot=result.body:GetNumSections()
            local ok, material = pcall(display.apply, result.body, glass,result.liveGlass and glass.lcdY-.04)
            if ok then
                result.screenMaterial = material
                result.triangles = result.triangles + 2
                result.vertices = result.vertices + 4
                result.sections = result.sections + 1
            else
                result.screenError = tostring(material)
            end
        end
        return true
    end
end

function M.clear(result)
    if not result or not result.components then return end
    if result.far then
        result.upload = nil
        M.clear(result.far)
        result.far = nil
    end
    for i = #result.components, 1, -1 do
        local component = result.components[i]
        pcall(function()
            if valid(component) then component:K2_DestroyComponent(result.actor) end
        end)
        result.components[i] = nil
    end
    result.ok = false
end

function M.build(actor, rootComponent, basic, built)
    local result = {actor=actor, root=rootComponent, basic=basic==true, components={}, materials={},
        triangles=0, vertices=0, sections=0, lod=0, materialStatus="BasicShapeMaterial"}
    if built then result.liveGlass=(basic and variants.basic.geometry or M).fitGeometry.display end
    local ok, err = pcall(function()
        local upload = start_geometry(result,actor,rootComponent,basic)
        upload(math.huge)
    end)
    if not ok then
        M.clear(result)
        result.error = tostring(err)
    else
        result.ok = true
    end
    return result
end

local function screen_art(layer, visible)
    for _,slot in ipairs(layer.artSlots) do
        layer.body:SetMeshSectionVisible(slot, visible)
    end
    if layer.screenMaterial then layer.body:SetMeshSectionVisible(layer.screenSlot,visible) end
end

function M.setScreenMounted(result, mounted)
    result.screenMounted = mounted
    screen_art(result, not mounted)
    if result.far and result.far.ok then screen_art(result.far, not mounted) end
end

local function pose_layer(layer, hatch, drive)
    if valid(layer.hatch) then
        layer.hatch:K2_SetRelativeRotation({Pitch=0, Yaw=0, Roll=-hatch}, false, {}, true)
    end
    layer.drive:K2_SetRelativeRotation({Pitch=0, Yaw=0, Roll=drive}, false, {}, true)
end

function M.pose(result, hatchDegrees, driveDegrees)
    return pcall(function()
        assert(result and result.ok and valid(result.drive), "preview is unavailable")
        assert(type(hatchDegrees) == "number" and type(driveDegrees) == "number", "expected two angles")
        result.hatchAngle = math.max(0, math.min(M.maxHatchDegrees, hatchDegrees))
        result.driveAngle = driveDegrees
        pose_layer(result, result.hatchAngle, driveDegrees)
        if result.lod == 1 then pose_layer(result.far, result.hatchAngle, driveDegrees) end
    end)
end

local function visible_layer(layer, visible)
    for _,name in ipairs({"body","hatch","drive"}) do
        if valid(layer[name]) then layer[name]:SetVisibility(visible,false) end
    end
end

-- Project the surveyed model bounds in the actual camera. Use the larger viewport projection scale,
-- as UE does for static mesh sphere screen size. The focus camera always keeps the near model.
local lodBounds = {
    advanced={center={X=28.51,Y=25.875,Z=34.55},radius=130.77},
    basic={center={X=132.6,Y=105.8,Z=14.5},radius=86.10},
}
function M.screenSize(result, pc)
    local camera = pc.PlayerCameraManager
    if not valid(camera) then return end
    local maths = StaticFindObject("/Script/Engine.Default__KismetMathLibrary")
    local bounds = result.basic and lodBounds.basic or lodBounds.advanced
    local center = maths:TransformLocation(result.actor:GetTransform(),bounds.center)
    local eye = camera:GetCameraLocation()
    local dx,dy,dz = center.X-eye.X,center.Y-eye.Y,center.Z-eye.Z
    local distance = math.sqrt(dx*dx + dy*dy + dz*dz)
    local layout = StaticFindObject("/Script/UMG.Default__WidgetLayoutLibrary")
    local viewport = valid(layout) and layout:GetViewportSize(pc)
    local aspect = viewport and viewport.Y > 0 and viewport.X > 0 and viewport.X/viewport.Y or 16/9
    local fov = camera:GetFOVAngle()
    if type(fov) ~= "number" or fov <= 0 or fov >= 179 then return end
    return bounds.radius * math.max(1,aspect) / (math.max(distance,1) * math.tan(math.rad(fov)/2))
end

local function update_lod(result, size)
    if not result.far and size < .36 then
        local far = {actor=result.actor, basic=result.basic, liveGlass=result.liveGlass, materials=result.materials,
            components={}, triangles=0, vertices=0, sections=0}
        if result.paletteError then
            far.paletteError = result.paletteError
        else
            local ok, style = pcall(palette.load)
            if ok then far.palette = style else far.paletteError = tostring(style) end
        end
        result.far = far
        result.upload = start_geometry(far,result.actor,result.root,result.basic,result)
    end
    local far = result.far
    if result.upload and result.upload(1800) then
        if result.screenMounted then screen_art(far,false) end
        far.ok = true
        result.upload = nil
    end
    if not far or not far.ok then return end
    if result.lod == 0 and size < .22 then
        pose_layer(far,result.hatchAngle or 0,result.driveAngle or 0)
        visible_layer(far,true)
        visible_layer(result,false)
        result.lod = 1
    elseif result.lod == 1 and size > .28 then
        visible_layer(result,true)
        visible_layer(far,false)
        result.lod = 0
    end
end

function M.updateLOD(result, size)
    if not result or not result.ok or result.lodError or type(size) ~= "number" or size ~= size then return end
    result.screenFraction = size
    local ok, why = pcall(update_lod,result,size)
    if not ok then
        -- A bad optional palette can still use the original per-section materials. Retry once.
        if result.far and result.far.palette and not result.paletteError then
            result.paletteError = tostring(why)
        else
            result.lodError = tostring(why)
        end
        result.upload = nil
        pcall(visible_layer,result,true)
        M.clear(result.far)
        result.far = nil
        result.lod = 0
    end
end

function M.setBeacon(result, lit)
    if not result or not valid(result.beacon) or result.beaconLit == lit then return end
    if not result.beaconMaterials then
        local path = "/Game/AssetSets/Launch_site/Materials/M_Master_Emissive_Buoy.M_Master_Emissive_Buoy"
        local parent = StaticFindObject(path)
        if not valid(parent) then parent = LoadAsset(path) end
        if not valid(parent) then parent = basic_material() end
        assert(valid(parent), "Basic amber light material unavailable")
        local beacon = result.beacon
        local materials = {}
        for slot=0,beacon:GetNumSections()-1 do
            local material = beacon:CreateDynamicMaterialInstance(slot, parent, FName("None", EFindName.FNAME_Find))
            assert(valid(material), "Basic amber light material unavailable")
            materials[#materials+1] = material
        end
        -- Leave each MID on its mesh section. UE can collect a dynamic
        -- material detached from its component even if Lua still has a wrapper.
        result.beaconMaterials = materials
    end
    local color = lit and {R=1,G=.31,B=.016,A=1} or {R=.23,G=.055,B=.006,A=1}
    local power = lit and 2.3 or .025
    for _,material in ipairs(result.beaconMaterials) do
        for _,field in ipairs({"Color", "Emissive Color", "Emissive Color Empty"}) do
            material:SetVectorParameterValue(FName(field, EFindName.FNAME_Add), color)
        end
        for _,field in ipairs({"EmissivePowerMin", "EmissivePowerMax"}) do
            material:SetScalarParameterValue(FName(field, EFindName.FNAME_Add), power)
        end
    end
    result.beaconLit = lit
end

function M.setFill(result, fraction, alarm, unloading)
    if result and result.ok and result.stockMeter then return cargo_meter.setFill(result, fraction, alarm, unloading) end
    return pcall(function()
        assert(result and result.ok and valid(result.fill), "cargo indicator is unavailable")
        assert(type(fraction) == "number" and math.abs(fraction) < math.huge, "expected a finite fill fraction")
        local clamped = math.max(0, math.min(1, fraction))
        if clamped == result.fillFraction then return end
        if clamped > 0 then
            result.fill:SetRelativeScale3D({X=clamped, Y=1, Z=1})
        end
        result.fill:SetVisibility(clamped > 0, false)
        result.fillFraction = clamped
    end)
end

return M
