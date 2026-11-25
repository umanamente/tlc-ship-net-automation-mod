-- Voyage stores electricity in kJ. The stock cable and module subsystem supply
-- the receiver. Each successful game-thread call pays for that interval only.
local valid = require("shipnet.observer").valid
local Power = {}
Power.__index = Power

local ELECTRICITY, INPUT, CONSUMPTION_AFTER_MODIFIERS = 0, 1, 1
local KILOWATTS = {active = 4, standby = 0.5}
local EPSILON = 1e-8
local CONNECTION_RECHECK_SECONDS = 0.5
local powerEvents = {
    disconnected = "Winch is waiting for both cable ends to connect",
    rechecking = "Winch requested a grid update at both ends of the connected cable after receiving no power",
    powered = "Winch external supply confirmed",
}

local function finite(n)
    return type(n) == "number" and n == n and math.abs(n) < math.huge
end

local function same(a, b)
    return valid(a) and valid(b) and a:GetAddress() == b:GetAddress()
end

local function receive(module, enabled)
    local config = module.ConfigData
    if config.bAcceptResourceOffer == enabled and config.bAcceptResourceOfferOff == enabled
        and config.bAcceptResourceOfferProduction == enabled then return end
    module:SetReceiveResourcesState(enabled)
    -- Inventory modules can be in either native switch state. Both offer
    -- permissions must agree for the native cable to charge the receiver.
    config.bAcceptResourceOffer = enabled
    config.bAcceptResourceOfferOff = enabled
    config.bAcceptResourceOfferProduction = enabled
end

local function debit(module, route, before, quantity)
    local removed = module:RemoveResource(ELECTRICITY, quantity, CONSUMPTION_AFTER_MODIFIERS)
    local after = module:GetResourceAmount(ELECTRICITY)
    if not finite(after) then error("Invalid electricity reading") end
    route.balance = after
    route.credit = math.max(0, route.credit - math.max(0, before - after))
    return removed == true and math.abs((before - after) - quantity) <= EPSILON
end

local function recheck_connection(route, module, peer, seconds)
    if not route.stalledSeconds or seconds <= 0 then return end
    route.stalledSeconds = route.stalledSeconds + seconds
    if route.stalledSeconds < CONNECTION_RECHECK_SECONDS then return end
    local upstream = peer:GetModule()
    if not valid(upstream) or not upstream.bHasInitialized then return end
    -- Voyage uses this notification to invalidate each module's socket caches
    -- and queue the module for a grid update. Leave both physical plugs in place.
    route.stalledSeconds = nil
    module:ConnectionsChanged()
    upstream:ConnectionsChanged()
    return true
end

local function consume(self, cabinet, seconds, mode, id)
    local inlet = cabinet.WinchPowerInlet
    if not valid(inlet) or not same(inlet:GetOwner(), cabinet) then return false, "not_ready" end
    local module = inlet:GetModule()
    if not valid(module) or not same(module:GetOwner(), cabinet) or not module.bHasInitialized
        or inlet.Port.Type ~= INPUT or inlet.Port.ResourceType ~= ELECTRICITY then return false, "not_ready" end
    local displayOnly = mode == "off"
    local amount = module:GetResourceAmount(ELECTRICITY)
    if displayOnly and amount ~= 0 then
        receive(module, false)
        return false, "off"
    end

    local peer = inlet:GetConnectedSocket()
    if not inlet:IsSocketConnected() or not valid(peer) or same(peer:GetOwner(), cabinet)
        or not same(peer:GetConnectedSocket(), inlet) then
        receive(module, not displayOnly)
        return false, displayOnly and "off" or "disconnected"
    end
    receive(module, true)
    local capacity = module:GetMaxResourceAmount(ELECTRICITY)
    if not finite(amount) or not finite(capacity) or capacity <= 0 then return false, "not_ready" end
    local route = self.routes[id]
    local moduleId, peerId = module:GetAddress(), peer:GetAddress()
    local newRoute = not route or route.module ~= moduleId or route.peer ~= peerId or route.displayOnly ~= displayOnly
    if newRoute then
        route = {module = moduleId, peer = peerId, displayOnly = displayOnly, credit = 0, balance = amount, stalledSeconds = 0}
        self.routes[id] = route
    end
    local stalledStep = newRoute and 0 or seconds
    if displayOnly then
        -- The grid supplies the first charge. Never debit the receiver or
        -- authorize a winch command while waking an unpowered display.
        if finite(stalledStep) then recheck_connection(route, module, peer, stalledStep) end
        return false, "charging_display"
    end

    -- Only energy newly received on this connection can authorize work. This
    -- also works through splitters where the direct neighbour is a passive
    -- junction. A loose cable or a dead source plus an old charge cannot run it.
    local received = amount - route.balance
    route.credit = math.max(0, math.min(amount, route.credit + received))
    route.balance = amount
    if not finite(seconds) or seconds <= 0 then return false, "no_elapsed" end
    local cost = seconds * self:kilowatts(mode)
    if cost > capacity or cost <= EPSILON then return false, "no_power" end
    if received > EPSILON and route.stalledSeconds then route.stalledSeconds = 0 end
    if route.credit + EPSILON < cost then
        -- A full receiver offers no headroom for a new source to demonstrate
        -- delivery. Place a bounded startup load, once, for the missing space.
        local missing = cost - route.credit - (capacity - amount)
        if missing > EPSILON then
            -- This spends the unverified part of the old reservoir first.
            local earned = route.credit
            debit(module, route, amount, math.min(amount, missing))
            route.credit = math.min(earned, route.balance)
        end
        if received <= EPSILON and recheck_connection(route, module, peer, stalledStep) then return false, "rechecking" end
        return false, "no_power"
    end
    if not debit(module, route, amount, cost) then return false, "no_power" end
    return true, "powered"
end

function Power:consume(cabinet, seconds, mode)
    if not valid(cabinet) or (mode ~= "off" and not KILOWATTS[mode]) then return false, "not_ready" end
    local id = cabinet:GetAddress()
    local ok, paid, reason = pcall(consume, self, cabinet, seconds, mode, id)
    if not ok or reason == "not_ready" or reason == "disconnected" or reason == "off" then self.routes[id] = nil end
    if not ok then return false, "not_ready" end
    if self.log then
        local event = powerEvents[reason]
        if mode == "off" then self.lastEvent[id] = nil
        elseif event and self.lastEvent[id] ~= event then
            self.lastEvent[id] = event
            self.log(event)
        end
    end
    return paid, reason
end

function Power:reset()
    self.routes = {}
    self.lastEvent = {}
end

function Power:kilowatts(mode)
    return self.fixedKW or KILOWATTS[mode]
end

return {new = function(log, fixedKW)
    return setmetatable({routes = {}, lastEvent = {}, log = log, fixedKW = fixedKW}, Power)
end}
