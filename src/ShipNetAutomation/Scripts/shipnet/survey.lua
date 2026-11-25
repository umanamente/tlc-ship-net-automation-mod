-- A single game-thread survey requested from the diagnostic panel.
local observer = require("shipnet.observer")
local M = {}
local valid = observer.valid
local NET = "/Script/Voyage.VoyageModuleFishingActor"
local STOCK_NET = "/Game/Blueprints/Modules/Utility/Boat/BP_Module_Fishing.BP_Module_Fishing_C"
local BOX = "/Game/Blueprints/Interactives/Containers/BP_Inventory_Container_Fishing.BP_Inventory_Container_Fishing_C"
local MATH = "/Script/Engine.Default__KismetMathLibrary"
local LIMIT = 4096

local function opt(fn)
    local ok, value = pcall(fn)
    if ok then return value end
    return nil
end

local function name(object)
    if valid(object) then return opt(function() return object:GetFullName() end) end
end

local function short(object)
    return opt(function() return object:GetFName():ToString() end)
        or (name(object) or ""):match("%.([%w_%-]+)$")
end

local function same(a, b)
    return valid(a) and valid(b) and a:GetAddress() == b:GetAddress()
end

local function is_a(obj, class)
    return valid(obj) and opt(function() return obj:IsA(class) end) == true
end

local function numbers(value, a, b, c)
    return opt(function()
        local out = {}
        for _, key in ipairs({a, b, c}) do
            -- The shipped CoreUObject.Rotator uses lowercase "pitch" in
            -- reflection. Native copies and other engine builds may use "Pitch".
            local n = opt(function() return value[key] end)
            if n == nil and key == "Pitch" then n = value.pitch end
            if type(n) ~= "number" or n ~= n or math.abs(n) == math.huge then return nil end
            out[key] = n
        end
        return out
    end)
end

local function anchor(result, role, obj, component, transform, mathlib)
    if not valid(obj) then return end
    local row = {role = role, object = name(obj)}
    local location, rotation
    if component then
        location = opt(function() return obj:K2_GetComponentLocation() end)
        rotation = opt(function() return obj:K2_GetComponentRotation() end)
    else
        location = opt(function() return obj:K2_GetActorLocation() end)
        rotation = opt(function() return obj:K2_GetActorRotation() end)
    end
    row.worldCm = numbers(location, "X", "Y", "Z")
    row.worldRotationDeg = numbers(rotation, "Pitch", "Yaw", "Roll")
    if transform and valid(mathlib) then
        if row.worldCm then
            local local_point = opt(function() return mathlib:InverseTransformLocation(transform, location) end)
            row.shipLocalCm = numbers(local_point, "X", "Y", "Z")
        end
        if row.worldRotationDeg then
            local local_rotation = opt(function() return mathlib:InverseTransformRotation(transform, rotation) end)
            row.shipLocalRotationDeg = numbers(local_rotation, "Pitch", "Yaw", "Roll")
        end
    end
    result.anchors[#result.anchors + 1] = row
    return row
end

local function deck_contact(result, ship, pawn, transform, mathlib)
    local movement_base = opt(function() return pawn:GetMovementBaseActor(pawn) end)
    if not same(opt(function() return observer.boat_ancestor(movement_base) end), ship) then return end
    local floor = opt(function() return pawn.CharacterMovement.CurrentFloor end)
    if not floor or not opt(function() return floor.bBlockingHit and floor.bWalkableFloor end) then return end
    local hit = opt(function() return floor.HitResult end)
    if not hit or opt(function() return hit.bBlockingHit end) ~= true then return end
    local point = opt(function() return hit.ImpactPoint end)
    local world_point = numbers(point, "X", "Y", "Z")
    if not world_point then return end
    local row = {role = "deck_contact", object = name(pawn), movementBase = name(movement_base),
        worldCm = world_point, worldNormal = numbers(opt(function() return hit.ImpactNormal end), "X", "Y", "Z")}
    if transform and valid(mathlib) then
        row.shipLocalCm = numbers(opt(function() return mathlib:InverseTransformLocation(transform, point) end), "X", "Y", "Z")
    end
    result.anchors[#result.anchors + 1] = row
end

local function query(result, key, work)
    local probe = {raw = 0, live = 0, matched = 0, sameWorld = 0}
    result.probes[key] = probe
    local ok, err = pcall(work, probe)
    if not ok then probe.error = tostring(err) end
    return probe
end

local function capture()
    local result = {status = "no_world", candidates = {}, anchors = {}, probes = {}}
    local ctx, selection = observer.survey_context()
    if not ctx then return result end
    local ship, pawn, world = ctx.ship, ctx.pawn, ctx.world
    result.world = name(world)
    if not valid(ship) then result.status = selection; return result end
    result.ship, result.shipSelection = name(ship), selection
    if not is_a(ship, "/Game/Blueprints/Vehicles/BP_Boat_Barge.BP_Boat_Barge_C") then
        result.status = "unsupported_ship"
        return result
    end
    local transform = opt(function() return ship:GetTransform() end)
    local mathlib = opt(function() return StaticFindObject(MATH) end)
    result.shipWorldCm = numbers(opt(function() return ship:K2_GetActorLocation() end), "X", "Y", "Z")
    result.shipWorldRotationDeg = numbers(opt(function() return ship:K2_GetActorRotation() end), "Pitch", "Yaw", "Roll")
    if not same(ship, pawn) then
        anchor(result, "player_origin", pawn, false, transform, mathlib)
        deck_contact(result, ship, pawn, transform, mathlib)
    end

    local li = opt(function() return ship.LevelInstanceComponent end)
    local component_owned = valid(li) and same(opt(function() return li:GetOwner() end), ship)
    local stream = component_owned and opt(function() return li.LoadingLevel end)
    local loaded = valid(stream) and opt(function() return stream:GetLoadedLevel() end)
    result.levelInstanceComponent, result.loadedLevel = name(li), name(loaded)
    local owned, saved, by_id, handles, containers = {}, {}, {}, {}, {}
    local function add(obj, source, probe)
        if not valid(obj) or obj:HasAnyFlags(0x30) then return end
        probe.live = probe.live + 1
        local ow = opt(function() return obj:GetWorld() end)
        local in_world = same(ow, world)
        if in_world then probe.sameWorld = probe.sameWorld + 1 end
        local id = obj:GetAddress()
        if source == "owned" then owned[id] = true end
        local role
        if is_a(obj, NET) or is_a(obj, STOCK_NET) then role = "winch"
        elseif is_a(obj, BOX) then role = "container"
        else return end
        probe.matched = probe.matched + 1
        if not by_id[id] then
            local level = opt(function() return obj:GetLevel() end)
            by_id[id] = {role = role, object = name(obj), actorName = short(obj), actorWorld = name(ow),
                actorLevel = name(level), sameWorld = in_world, inLoadedLevel = same(level, loaded), sources = {}}
            handles[id] = obj
            if role == "container" then containers[#containers + 1] = obj end
            result.candidates[#result.candidates + 1] = by_id[id]
        end
        by_id[id].sources[#by_id[id].sources + 1] = source
    end

    query(result, "owned", function(probe)
        assert(component_owned, "Selected ship level-instance component unavailable or owner mismatch")
        local actors = li.OwnedActors
        local count = actors:GetArrayNum()
        assert(math.type(count) == "integer" and count >= 0, "Invalid weak actor array size")
        probe.raw, probe.truncated = count, count > LIMIT
        -- This loader's weak-property GetParam is unsupported. Indexed Get
        -- returns FWeakObjectPtr. Out-of-bounds indexing can grow a TArray.
        for i = 1, math.min(count, LIMIT) do
            local object = opt(function() return actors[i]:Get() end)
            if object then add(object, "owned", probe) end
        end
    end)
    query(result, "savedNames", function(probe)
        assert(component_owned, "Selected ship level-instance component unavailable or owner mismatch")
        probe.names = {}
        li.SpawnedPersistentRuntimeActors:ForEach(function(param)
            probe.raw = probe.raw + 1
            if probe.raw > LIMIT then probe.truncated = true; return true end
            local n = opt(function() return param:get():ToString() end)
            if n and n:find("BP_Module_Fishing_C", 1, true) then
                saved[n] = true
                probe.matched = probe.matched + 1
                if #probe.names < 16 then probe.names[#probe.names + 1] = n end
            end
        end)
    end)
    for _, entry in ipairs({{"native", "VoyageModuleFishingActor"}, {"blueprint", "BP_Module_Fishing_C"},
            {"container", "BP_Inventory_Container_Fishing_C"}}) do
        query(result, entry[1], function(probe)
            local objects = FindAllOf(entry[2]) or {}
            probe.raw, probe.truncated = #objects, #objects > LIMIT
            for i = 1, math.min(#objects, LIMIT) do add(objects[i], entry[1], probe) end
        end)
    end

    query(result, "instanceName", function(probe)
        local ship_name = assert(short(ship), "Missing ship name")
        local n = ship_name .. "LevelInstanceBP_Module_Fishing_C_0"
        probe.lookup = n
        local obj = FindObject("BP_Module_Fishing_C", n)
        if valid(obj) then probe.raw = 1; add(obj, "instanceName", probe) end
    end)
    -- The container's actual child/attachment parent is another route to the
    -- winch when it is absent from a native-class global query.
    query(result, "containerParent", function(probe)
        for _, container in ipairs(containers) do
            for _, method in ipairs({"GetParentActor", "GetAttachParentActor", "GetOwner"}) do
                local parent = opt(function() return container[method](container) end)
                if is_a(parent, NET) or is_a(parent, STOCK_NET) then
                    probe.raw = probe.raw + 1
                    add(parent, "containerParent", probe)
                    break
                end
            end
        end
    end)
    local matches, pending, chosen, chosen_row = 0, 0, nil, nil
    for id, row in pairs(by_id) do
        local obj = handles[id]
        local parent_boat = opt(function() return observer.boat_ancestor(obj) end)
        local other_ship = valid(parent_boat) and not same(parent_boat, ship)
        row.ownedByShip = owned[id] == true
        row.shipSavedName = saved[row.actorName] == true
        row.parentBoat = name(parent_boat)
        local conflicting_level = not row.sameWorld and result.loadedLevel and row.actorLevel and not row.inLoadedLevel
        if not other_ship and not conflicting_level and (row.ownedByShip or row.sameWorld or row.inLoadedLevel) then
            if row.ownedByShip then row.association = "level_instance_owned"
            elseif same(parent_boat, ship) then row.association = "ship_ancestry"
            elseif row.inLoadedLevel then row.association = "ship_loaded_level"
            elseif saved[row.actorName] then row.association = "ship_saved_actor_name" end
        end
        if row.role == "winch" then
            if row.association then matches, chosen, chosen_row = matches + 1, obj, row
            elseif not other_ship then pending = pending + 1 end
        end
    end
    table.sort(result.candidates, function(a,b) return (a.object or "") < (b.object or "") end)
    if matches ~= 1 then
        if matches > 1 then result.status = "ambiguous_net"
        elseif pending > 0 then result.status = "unverified_net"
        else result.status = "no_net" end
        return result
    end
    result.net = name(chosen)
    result.coordinateFrame = chosen_row.sameWorld and "same_world"
        or chosen_row.inLoadedLevel and "ship_loaded_level" or "ship_owned_world_unverified"
    local winch = anchor(result, "winch", chosen, false, transform, mathlib)
    for _, entry in ipairs({{"root", "RootScene"}, {"roller", "RollerComp"}, {"container_location", "ContainerLocation"},
            {"switch", "SwitchChildActor"}, {"cable_snap", "CableSnapPoint"}}) do
        local component = opt(function() return chosen[entry[2]] end)
        if valid(component) and same(opt(function() return component:GetOwner() end), chosen) then
            anchor(result, entry[1], component, true, transform, mathlib)
        end
    end
    if not winch.shipLocalCm or not winch.shipLocalRotationDeg then result.status = "transform_unavailable"
    elseif result.coordinateFrame == "ship_owned_world_unverified" then result.status = "frame_unverified"
    else result.status = "measured" end
    return result
end

function M.capture()
    local ok, result = xpcall(capture, debug.traceback)
    if ok then return result end
    return {status = "error", detail = tostring(result), candidates = {}, anchors = {}, probes = {}}
end
return M
