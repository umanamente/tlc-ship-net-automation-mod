-- Read-only snapshots. Call sample() on the game thread. Between samples
-- retain only names/addresses and ordinary Lua values, never engine handles.
local Observer = {}
Observer.__index = Observer

local BOAT = "/Script/Voyage.VoyageBoatPawn"
local BARGE = "/Game/Blueprints/Vehicles/BP_Boat_Barge.BP_Boat_Barge_C"
local FISHING = "/Script/Voyage.VoyageModuleFishingActor"
local STOCK_NET = "/Game/Blueprints/Modules/Utility/Boat/BP_Module_Fishing.BP_Module_Fishing_C"
local INVENTORY = "/Script/Voyage.VoyageBaseInventoryComponent"
local WEIGHT_LIMITED = "/Script/Voyage.VoyageInventoryWeightLimitedComponent"
local CONTAINER = "/Game/Blueprints/Interactives/Containers/BP_Container_Base.BP_Container_Base_C"

local function valid(object)
    if type(object) ~= "userdata" and type(object) ~= "table" then return false end
    local ok, is_valid = pcall(function() return object:IsValid() end)
    return ok and is_valid == true
end

-- The pinned loader returns RemoteUnrealParam for each element of reflected
-- array out-parameters (also for TMap iterator keys and values). Those
-- wrappers expose get(), but do not implement UObject:IsValid/GetAddress.
local function unwrap(value)
    for _ = 1, 4 do
        if type(value) ~= "userdata" and type(value) ~= "table" then break end
        local ok, getter = pcall(function() return value.get end)
        if not ok or type(getter) ~= "function" then break end
        local read, direct = pcall(getter, value)
        if not read or rawequal(direct, value) then break end
        value = direct
    end
    return value
end

local function live(object)
    return valid(object) and not object:HasAnyFlags(0x30) -- CDO or archetype
end

local function same(a, b)
    return valid(a) and valid(b) and a:GetAddress() == b:GetAddress()
end

local function descriptor(object)
    local name = object:GetFullName()
    return {path = assert(name:match("^[^ ]+ (/.+)$")), id = name .. "@" .. tostring(object:GetAddress())}
end

local function resolve(ref)
    if not ref then return nil end
    local object = StaticFindObject(ref.path)
    if live(object) and descriptor(object).id == ref.id then return object end
end

local function optional(read)
    local ok, value = pcall(read)
    if ok then return value end
end

local function number(value)
    if type(value) == "number" and value == value and math.abs(value) < math.huge then return value end
end

local function boolean(value)
    if type(value) == "boolean" then return value end
end

local function field(object, key, convert)
    return convert(optional(function() return object[key] end))
end

local function persistent_id(actor)
    return optional(function()
        local library = StaticFindObject("/Script/Voyage.Default__VoyagePersistentSubsystem")
        local component = library:GetPersistentActorComponent(actor)
        if valid(component) and same(component:GetOwner(), actor) then
            local id = component.PersistentUniqueIdRuntime
            if math.type(id) == "integer" and id ~= 0 then return string.format("%016x", id) end
        end
    end)
end

-- ParentActor covers a child-actor component. AttachParent covers deck
-- attachments. Owner covers stock actors that occur in neither hierarchy.
local function boat_ancestor(actor)
    local queue, seen = {}, {}
    local function enqueue(candidate)
        candidate = unwrap(candidate)
        if valid(candidate) then
            local key = candidate:GetAddress()
            if not seen[key] then
                seen[key] = true
                queue[#queue + 1] = candidate
            end
        end
    end
    enqueue(actor)
    local index = 1
    while index <= #queue and index <= 24 do
        local current = queue[index]
        index = index + 1
        if current:IsA(BOAT) then return current end
        enqueue(optional(function() return current:GetParentActor() end))
        enqueue(optional(function() return current:GetAttachParentActor() end))
        enqueue(optional(function() return current:GetOwner() end))
    end
end

local function player_boat(pawn)
    if pawn:IsA(BOAT) then return pawn end
    return optional(function() return boat_ancestor(pawn:GetMovementBaseActor(pawn)) end)
end

local function select_ship(pawn_boat, world)
    if valid(pawn_boat) and same(pawn_boat:GetWorld(), world) then
        return pawn_boat, "player_boat"
    end
    local selected
    for _, boat in ipairs(FindAllOf("VoyageBoatPawn") or {}) do
        if live(boat) and boat:IsA(BARGE) and same(boat:GetWorld(), world) then
            if selected and not same(boat, selected) then return nil, "ambiguous_ship" end
            selected = boat
        end
    end
    return selected, selected and "only_loaded_barge" or "no_ship"
end

local function select_net(ship, world, ship_selection)
    local selected, source
    local function consider(actor, via)
        if selected and not same(actor, selected) then return false end
        selected, source = actor, source or via
        return true
    end

    local ambiguous = false
    local function visit(_, wrapped)
        local component = unwrap(wrapped)
        if valid(component) then
            local owner = unwrap(component:GetOwner())
            if live(owner) and owner:IsA(FISHING) and same(owner:GetWorld(), world) then
                local parent = boat_ancestor(owner)
                if (not parent or same(parent, ship)) and not consider(owner, "ship_module") then
                    ambiguous = true
                    return true
                end
            end
        end
    end
    local read_modules = pcall(function()
        local out = {}
        ship:GetAllModules(out)
        local array = unwrap(out.Modules or out)
        if type(array.ForEach) == "function" then
            array:ForEach(visit)
        else
            for index, entry in ipairs(array) do if visit(index, entry) then break end end
        end
    end)
    if ambiguous then return nil, "ambiguous_net" end
    if not read_modules then
        -- A partially read list cannot prove uniqueness. Use world actors
        -- and their attachment chains as an independent discovery route.
        selected, source = nil, nil
    end
    local count, orphan, seen = 0, nil, {}
    for _, net in ipairs(FindAllOf("VoyageModuleFishingActor") or {}) do
        if live(net) and same(net:GetWorld(), world) and not seen[net:GetAddress()] then
            seen[net:GetAddress()] = true
            count = count + 1
            local parent = boat_ancestor(net)
            if same(parent, ship) then
                if not consider(net, "ship_ancestry") then return nil, "ambiguous_net" end
            elseif not parent and net:IsA(STOCK_NET) then
                orphan = net
            end
        end
    end
    if selected then return selected, "ready", source, count end
    if orphan and count > 1 then return nil, "ambiguous_net", nil, count end
    -- Diagnostics may observe an otherwise unidentified winch in a world
    -- containing precisely one Barge and one stock net. This does not prove
    -- mounting or ownership and must never authorize automatic operation.
    if orphan and count == 1 and ship:IsA(BARGE) then
        local sole, reason = ship, ship_selection
        if ship_selection ~= "only_loaded_barge" then sole, reason = select_ship(nil, world) end
        if same(sole, ship) then return orphan, "ready", "only_world_net_unverified", count end
        if reason == "ambiguous_ship" then return nil, reason, nil, count end
    end
    return nil, "no_net", nil, count
end

local function fname(value)
    if value == nil then return nil end
    local name = type(value) == "string" and value or value:ToString()
    if type(name) == "string" and name ~= "" and name ~= "None" then return name end
end

local function read_items(inventory)
    local rows, slots, total, visited = {}, {}, 0, 0
    local failure
    inventory.Items:ForEach(function(key, value)
        visited = visited + 1
        if visited > 512 then failure = "inventory_row_limit"; return true end
        local ok, err = pcall(function()
            local slot = math.tointeger(unwrap(key))
            local entry = unwrap(value)
            local count = math.tointeger(entry.Data.ItemCount)
            assert(slot and slot >= 0 and not slots[slot], "invalid inventory slot")
            assert(count and count >= 0, "invalid stack count")
            slots[slot] = true
            if count == 0 then return end
            local asset = fname(entry.AssetName)
            local kind = optional(function() return fname(entry.AssetType.Name) end)
            local item_id = asset and (kind and kind .. ":" .. asset or asset)
            if not item_id then
                local item = unwrap(entry.Item)
                assert(valid(item), "missing item identity")
                item_id = item:GetFullName()
            end
            rows[#rows + 1] = {slot = slot, itemId = item_id, count = count}
            total = total + count
        end)
        if not ok then failure = tostring(err); return true end
    end)
    assert(not failure, failure)
    table.sort(rows, function(a, b) return a.slot < b.slot end)
    return rows, total
end

local function inspect_inventory(net, result)
    local inventory = optional(function() return net.InventoryComponent end)
    local child = optional(function() return net.ContainerChildActor.ChildActor end)
    if not valid(child) then child = optional(function() return net.Container.ChildActor end) end
    local owner = valid(inventory) and optional(function() return inventory:GetOwner() end) or nil
    local container = valid(child) and child or owner
    if valid(container) and container:IsA(CONTAINER) then
        result.container = descriptor(container).id
        result.interactionEnabled = field(container, "InteractEnabled", boolean)
        result.containerClosed = field(container, "IsClosed", boolean)
        result.containerLocked = field(container, "IsLocked", boolean)
    end
    if not valid(inventory) or not inventory:IsA(INVENTORY) then
        result.inventoryError = "no_inventory"
        return
    end
    result.inventory = descriptor(inventory).id
    if not same(owner, net) and not same(owner, child) then
        result.inventoryError = "unverified_inventory_owner"
        return
    end
    result.inventoryWeight = optional(function()
        if inventory:IsA(WEIGHT_LIMITED) then return number(inventory:GetTotalWeight()) end
    end)
    local rows, total = read_items(inventory)
    result.inventoryReady, result.items, result.inventoryTotalCount = true, rows, total
end

local function inspect_net(net, result)
    result.netState = field(net, "NetState", number)
    result.netDropped = field(net, "NetDropped", boolean)
    result.fullyRaised = field(net, "FullyRaised", boolean)
    result.netWeight = field(net, "NetWeight", number)
    result.inventoryMaxWeight = field(net, "InventoryMaxWeight", number)
    result.currentLength = field(net, "CurrentLength", number)
    result.fishingCounter = field(net, "FishingCounter", number)
    result.isNetDropped = boolean(optional(function() return net:IsNetDropped() end))
    result.hasPower = optional(function()
        local module = net:GetMasterModuleComponent()
        if valid(module) and same(module:GetOwner(), net) then return boolean(module:HasPower()) end
    end)
    -- inventoryReady describes completeness of the slot read. Stock
    -- interactionEnabled independently reports whether the player can interact.
    result.inventoryReady = false
    local ok, err = pcall(inspect_inventory, net, result)
    if not ok then result.inventoryError = tostring(err) end
end

function Observer:reset()
    self.controller, self.binding, self.context = nil, nil, nil
    self.discovery, self.failure = nil, nil
    self.nextLookup, self.lastStatus = 0, "no_world"
end

local function sample(self)
    local now = os.time()
    local controller = resolve(self.controller)
    if not controller then
        if not self.controller and now < self.nextLookup then return {status = self.lastStatus} end
        self:reset()
        controller = FindFirstOf("VoyagePlayerController")
        if not live(controller) or controller:IsLocalController() ~= true then
            self.nextLookup = now + 2
            return {status = "no_world"}
        end
        self.controller = descriptor(controller)
    end
    local world, pawn = controller:GetWorld(), controller.Pawn
    if controller:IsLocalController() ~= true or not live(world) or not live(pawn) or not same(world, pawn:GetWorld()) then
        self:reset()
        self.nextLookup = now + 2
        return {status = "no_world"}
    end
    local result = {world = descriptor(world).id, player = self.controller.id}
    local pawn_boat = player_boat(pawn)
    local context = result.world .. "|" .. result.player .. "|" .. (valid(pawn_boat) and descriptor(pawn_boat).id or "")
    if context ~= self.context then
        self.context, self.binding, self.nextLookup = context, nil, 0
    end

    local binding = self.binding
    local ship = binding and resolve(binding.ship)
    local net = binding and resolve(binding.net)
    local stale = binding and (not ship or not net or not same(net:GetWorld(), world) or not same(ship:GetWorld(), world))
    if stale or now >= self.nextLookup then
        local selection, status, net_selection, count
        ship, selection = select_ship(pawn_boat, world)
        if ship then net, status, net_selection, count = select_net(ship, world, selection) else status = selection end
        self.lastStatus = status
        self.discovery = {worldNetCandidates = count, ship = ship and descriptor(ship).id,
            shipSelection = ship and selection}
        binding = nil
        if ship and net then
            binding = {ship = descriptor(ship), net = descriptor(net), netSelection = net_selection,
                shipPersistentId = persistent_id(ship), netPersistentId = persistent_id(net)}
        end
        self.binding = binding
        self.nextLookup = now + (binding and 30 or 3)
    end
    result.status = self.lastStatus
    for key, value in pairs(self.discovery or {}) do result[key] = value end
    if not binding then return result end
    result.ship, result.net = binding.ship.id, binding.net.id
    result.netSelection = binding.netSelection
    result.netAssociationVerified = binding.netSelection ~= "only_world_net_unverified"
    result.shipPersistentId, result.netPersistentId = binding.shipPersistentId, binding.netPersistentId
    result.identity = result.world .. "|" .. result.player .. "|" .. result.ship .. "|" .. result.net
    result.shipSpeedCmS = optional(function()
        local velocity = ship:GetVelocity()
        return number(math.sqrt(velocity.X ^ 2 + velocity.Y ^ 2 + velocity.Z ^ 2))
    end)
    inspect_net(net, result)
    if result.netState == nil or result.netDropped == nil or result.fullyRaised == nil then result.status = "waiting_state" end
    return result
end

function Observer:sample()
    local now, failure = os.time(), self.failure
    if failure and now < failure.retryAt then return {status = "error", detail = failure.detail} end
    local ok, result = xpcall(sample, debug.traceback, self)
    if ok then
        self.failure = nil
        return result
    end
    local delay = failure and math.min(failure.delay * 2, 30) or 3
    local detail = tostring(result)
    self.failure = {retryAt = now + delay, delay = delay, detail = detail}
    return {status = "error", detail = detail}
end

-- Immediate game-thread context for the separately requested mounting survey.
-- These live handles are consumed synchronously and never stored in a report.
local function survey_context()
    local controller = FindFirstOf("VoyagePlayerController")
    if not live(controller) or controller:IsLocalController() ~= true then return nil, "no_world" end
    local world, pawn = controller:GetWorld(), controller.Pawn
    if not live(world) or not live(pawn) or not same(world, pawn:GetWorld()) then return nil, "no_world" end
    local ship, selection = select_ship(player_boat(pawn), world)
    return {world = world, pawn = pawn, ship = ship, shipSelection = selection}, selection
end

return {survey_context = survey_context, boat_ancestor = boat_ancestor, valid = valid, new = function()
    local observer = setmetatable({}, Observer)
    observer:reset()
    return observer
end}
