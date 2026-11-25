-- Fishing catches live in the stock drawer. A transfer always originates in
-- one of its live slots, including when resuming an interrupted unloading.
local observer = require("shipnet.observer")
local valid = observer.valid
local M = {}
local NET = "/Script/Voyage.VoyageModuleFishingActor"
local DRAWER = "/Game/Blueprints/Interactives/Containers/BP_Inventory_Container_Fishing.BP_Inventory_Container_Fishing_C"
local CABINET = "/Game/Mods/ShipNetAutomation/BP_Module_WinchAutomator.BP_Module_WinchAutomator_C"
local BARGE = "/Game/Blueprints/Vehicles/BP_Boat_Barge.BP_Boat_Barge_C"
local WEIGHT = "/Script/Voyage.VoyageInventoryWeightLimitedComponent"
local SYSTEM = "/Script/Engine.Default__KismetSystemLibrary"
local busy = {}

local function same(a, b)
    return valid(a) and valid(b) and a:GetAddress() == b:GetAddress()
end

local function unwrap(x)
    if type(x) ~= "table" and type(x) ~= "userdata" then return x end
    local ok, getter = pcall(function() return x.get end)
    if ok and type(getter) == "function" then return getter(x) end
    return x
end

local function live(a, class)
    return valid(a) and a:IsA(class) and not a:IsActorBeingDestroyed()
end

local function source(net)
    assert(live(net, NET), "Fishing winch unavailable")
    local child = net.ContainerChildActor
    if not valid(child) then child = net.Container end
    assert(valid(child) and same(child:GetOwner(), net), "Fishing drawer is loading")
    local drawer, inventory = child.ChildActor, net.InventoryComponent
    assert(live(drawer, DRAWER) and valid(inventory) and inventory:IsA(WEIGHT)
        and same(inventory:GetOwner(), drawer) and same(drawer:GetWorld(), net:GetWorld()),
        "Fishing drawer inventory unavailable")
    return inventory, drawer
end

local function storage(net, cabinet)
    assert(live(cabinet, CABINET) and not cabinet:ActorHasTag(FName("Recycling")), "Mounted cabinet unavailable")
    -- A barge's streamed winch can have a different UWorld from the built
    -- cabinet. Establish their relationship through actual mount or level ownership.
    local mount = cabinet:GetAttachParentActor()
    if not same(mount, net) then
        assert(valid(mount) and mount:IsA(BARGE), "Cabinet detached")
        if not same(net:GetAttachParentActor(), mount) then
            local li = mount.LevelInstanceComponent
            assert(valid(li) and same(li:GetOwner(), mount) and valid(li.LoadingLevel)
                and same(li.LoadingLevel:GetLoadedLevel(), net:GetLevel()), "Cabinet belongs to a different winch")
        end
    end
    local inventory = cabinet.VoyageInventoryWeightLimited
    assert(valid(inventory) and inventory:IsA(WEIGHT) and same(inventory:GetOwner(), cabinet),
        "Cabinet inventory unavailable")
    return inventory
end

local function bytes(array)
    local count, parts = #array, {}
    if count > 0 then
        array:ForEach(function(_, value)
            parts[#parts + 1] = string.char(unwrap(value))
        end)
    end
    assert(#parts == count, "Incomplete cargo instance data")
    return table.concat(parts)
end

local function name(value)
    return type(value) == "string" and value or value:ToString()
end

local function payload(data)
    local fields, map = {}, data.ItemDataMap
    if #map > 0 then
        map:ForEach(function(key, value)
            local field = name(unwrap(key))
            local contents = bytes(unwrap(value).Data)
            fields[#fields + 1] = string.pack("s4s4", field, contents)
        end)
        assert(#fields == #map, "Incomplete cargo instance fields")
        table.sort(fields)
    end
    return string.pack("s4", bytes(data.ItemData)) .. table.concat(fields)
end

local function read_slot(key, value, exact)
    local entry = unwrap(value)
    local slot, count = math.tointeger(unwrap(key)), math.tointeger(entry.Data.ItemCount)
    assert(slot and slot >= 0 and count and count >= 0, "Invalid cargo slot")
    if count == 0 then return nil end
    local item = unwrap(entry.Item)
    if not valid(item) then
        item = StaticFindObject(SYSTEM):GetObjectFromPrimaryAssetId({
            PrimaryAssetType={Name=entry.AssetType.Name}, PrimaryAssetName=entry.AssetName})
    end
    local data = entry.Data
    local row = {slot=slot, count=count, item=item, flags=data.Flags, timestamp=data.Timestamp,
        plain=#data.ItemData == 0 and #data.ItemDataMap == 0}
    if exact then
        row.assetType = name(entry.AssetType.Name)
        row.assetName = name(entry.AssetName)
        row.payload = payload(data)
        row.version = data.Version
    end
    return row
end

local function slots(inventory, exact)
    local rows, total, err = {bySlot={}}, 0, nil
    inventory.Items:ForEach(function(key, value)
        local ok, row = pcall(read_slot,key,value,exact)
        if not ok then
            err = row
            return true
        end
        if row then
            rows[#rows+1] = row
            rows.bySlot[row.slot] = row
            total = total + row.count
        end
    end)
    assert(not err,err)
    table.sort(rows, function(a,b) return a.slot < b.slot end)
    return rows, total
end

local function plain_match(a, b, paced)
    return a.plain and b.plain and same(a.item,b.item) and a.flags == b.flags
        and (a.timestamp == b.timestamp or (paced and a.flags & 1 == 0))
end

local function slot_capacity(dest, item, index, occupied, requested)
    -- Voyage's slot estimate can return the requested count even for a full stack.
    local limit = item.MaxStackCount
    if limit > 0 then requested = math.min(requested, limit - occupied) end
    if requested <= 0 or not dest:IsValidSlotIndex(index) or not dest:CanAddToSlot(index,item) then return 0 end
    local room = dest:EstimateAddAmountToSlot(index,item,requested)
    assert(math.tointeger(room) and room >= 0, "Unreadable destination slot capacity")
    return math.min(requested,room)
end

local function allowed(sourceInv, dest, row, index, occupied, requested)
    local count = slot_capacity(dest,row.item,index,occupied,requested)
    if count < row.count and (not row.plain or not sourceInv:CanSplitSlot(row.slot)) then return 0 end
    return count
end

local function compatible_stack(src, dst, row, targetRows, requested, paced)
    for _,other in ipairs(targetRows) do
        if plain_match(row,other,paced) then
            local count = allowed(src,dst,row,other.slot,other.count,requested)
            if count > 0 then return {row=row, target=other.slot, count=count, targetCount=other.count} end
        end
    end
end

local function count_within_weight(count, unitWeight, availableKg)
    assert(type(unitWeight) == "number" and unitWeight >= 0 and unitWeight < math.huge, "Unreadable cargo item weight")
    if unitWeight == 0 then return count end
    return math.min(count, math.floor((availableKg + 1e-6) / unitWeight))
end

local function choose(src, dst, rows, targetRows, empty, paced)
    local unresolved
    local freeKg = math.max(0, dst:GetRemainingWeightSpace())
    for _,row in ipairs(rows) do
        if not valid(row.item) or not src:IsValidSlotIndex(row.slot) or not src:CanRemoveSlot(row.slot) then
            unresolved = true
        elseif dst:CanAddItem(row.item) then
            local estimate = dst:EstimateAddAmount(row.item,row.count)
            assert(math.tointeger(estimate) and estimate >= 0, "Unreadable cabinet capacity")
            local requested = count_within_weight(math.min(row.count, estimate), row.item.Weight, freeKg)
            if requested > 0 then
                -- Stack ordinary portions even when the native add refreshed their timestamps.
                if paced then
                    local move = compatible_stack(src,dst,row,targetRows,requested,true)
                    if move then return move end
                end
                if empty >= 0 then
                    local count = allowed(src,dst,row,empty,0,requested)
                    if count > 0 then return {row=row, target=empty, count=count} end
                end
                if not paced then
                    local move = compatible_stack(src,dst,row,targetRows,requested)
                    if move then return move end
                end
            end
        end
    end
    if unresolved then return nil, "Cargo item is unavailable or locked" end
end

local function finite(x)
    return type(x) == "number" and x >= 0 and x < math.huge
end

local function weights(src)
    local weight, capacity = src:GetTotalWeight(), src:GetCurrentMaxWeightLimit()
    assert(finite(weight) and finite(capacity), "Fishing drawer weight unavailable")
    return weight, capacity
end

function M.weight(net)
    local ok, weight, capacity = pcall(function() return weights(source(net)) end)
    if ok then return weight, capacity end
    return nil
end

local function inspect(net,cabinet,exact,paced)
    local src, drawer = source(net)
    local dst = storage(net,cabinet)
    local rows, remaining = slots(src,exact)
    local targetRows, targetTotal = slots(dst,exact)
    local weight, capacity = weights(src)
    local ready = net.FullyRaised == true and drawer.InteractEnabled == true and drawer.IsLocked == false
    local empty = math.tointeger(dst:GetNextEmptySlot())
    assert(empty, "Cabinet slot capacity unavailable")
    if empty >= 0 and (not dst:IsValidSlotIndex(empty) or dst:IsSlotOccupied(empty)) then empty = -1 end
    local move, why = choose(src,dst,rows,targetRows,empty,paced)
    local space = move ~= nil
    if remaining == 0 and dst:GetRemainingWeightSpace() > 0 then
        space = empty >= 0
        for _,row in ipairs(targetRows) do
            if space then break end
            space = row.plain and valid(row.item) and dst:CanAddItem(row.item)
                and slot_capacity(dst,row.item,row.slot,row.count,1) > 0
        end
    end
    local status = "available"
    if why then status = "unavailable"
    elseif remaining == 0 then status = "empty"
    elseif not space then status = "full" end
    return {status=status, remaining=remaining, moved=0, ready=ready, space=space,
        weight=weight, capacity=capacity, detail=why}, move, src, dst, targetTotal, rows, targetRows
end

local function failure(detail)
    return {status="unavailable", ready=false, space=false, moved=0, detail=tostring(detail)}
end

function M.inspect(net,cabinet)
    local ok, result = pcall(inspect,net,cabinet,false,true)
    return ok and result or failure(result)
end

function M.count(net)
    local ok, count = pcall(function()
        local src = source(net)
        local _, total = slots(src)
        return total
    end)
    if ok then return count end
    return nil,tostring(count)
end

function M.drawerContents(net)
    local ok, count = pcall(function()
        local inventory, drawer = source(net)
        if net.FullyRaised ~= true or drawer.InteractEnabled ~= true or drawer.IsLocked ~= false then return end
        local _, total = slots(inventory)
        return total
    end)
    if ok then return count end
end

local function same_data(before, after, moved)
    if not before or not after or before.assetType ~= after.assetType or before.assetName ~= after.assetName
        or before.payload ~= after.payload or before.flags ~= after.flags then return false end
    if valid(before.item) or valid(after.item) then
        if not same(before.item,after.item) then return false end
    end
    -- AddToSlot may refresh the destination time when the item has no
    -- keep-time flag. The native copier also updates its serialization version.
    return before.timestamp == after.timestamp or (moved and after.timestamp ~= 0
        and (before.timestamp == 0 or before.flags & 1 == 0))
end

local function same_except(before, after, skip)
    for _,row in ipairs(before) do
        if row.slot ~= skip then
            local other = after.bySlot[row.slot]
            if not same_data(row,other) or row.count ~= other.count or row.version ~= other.version then return false end
        end
    end
    for _,row in ipairs(after) do
        if row.slot ~= skip and not before.bySlot[row.slot] then return false end
    end
    return true
end

local function check_transfer(info, move, src, dst, oldTarget, oldSourceRows, oldTargetRows, called, native)
    local sourceRows, remaining = slots(src,true)
    local targetRows, nowTarget = slots(dst,true)
    local removed, arrived = info.remaining-remaining, nowTarget-oldTarget
    local before = move.row
    local from, to = sourceRows.bySlot[before.slot], targetRows.bySlot[move.target]
    if (not called or native == 0) and removed == 0 and arrived == 0
        and same_except(oldSourceRows,sourceRows) and same_except(oldTargetRows,targetRows) then
        return failure(called and "Native transfer declined" or native)
    end
    assert(removed > 0 and removed == arrived and removed <= move.count and (not called or native == removed)
        and same_data(before,to,true) and to.count - (move.targetCount or 0) == removed
        and (not from or same_data(before,from)) and (from and from.count or 0) == before.count - removed
        and same_except(oldSourceRows,sourceRows,before.slot) and same_except(oldTargetRows,targetRows,move.target),
        "Native transfer changed the inventories unexpectedly")
    info.status,info.moved,info.remaining = "moved",removed,remaining
    if move.unitWeight then info.movedKg = removed * move.unitWeight end
    info.weight,info.capacity = weights(src)
    return info
end

local function unload(net,cabinet,budgetKg)
    local info, move, src, dst, targetTotal, sourceRows, targetRows = inspect(net,cabinet,true,budgetKg~=nil)
    if not info.ready then
        info.status = "not_ready"
        return info
    end
    if not move then return info end
    if budgetKg ~= nil then
        local unitWeight = move.row.item.Weight
        local count = count_within_weight(move.count, unitWeight, budgetKg)
        if count == 0 or (count < move.count and (not move.row.plain or not src:CanSplitSlot(move.row.slot))) then
            info.status = "accruing"
            return info
        end
        move.count, move.unitWeight = count, unitWeight
    end
    local called, native = pcall(function()
        return dst:TransferSlot(src,move.row.slot,move.target,move.count)
    end)
    -- After the mutating call, a failed read is an unknown result. Only an
    -- observed full commit or an unchanged pair permits another automatic step.
    local verified, result = pcall(check_transfer,info,move,src,dst,targetTotal,sourceRows,targetRows,called,native)
    if verified then return result end
    return {status="unconfirmed", ready=false, space=false, detail=tostring(result)}
end

function M.unload(net,cabinet,budgetKg)
    if budgetKg ~= nil and not finite(budgetKg) then return failure("Invalid cargo weight budget") end
    if not valid(cabinet) then return failure("Mounted cabinet unavailable") end
    local id = cabinet:GetAddress()
    if busy[id] then return failure("Cargo transfer in progress") end
    busy[id] = true
    local ok, result = pcall(unload,net,cabinet,budgetKg)
    busy[id] = nil
    return ok and result or failure(result)
end

return M
