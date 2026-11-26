-- Run only for a completed cabinet bound to the stock winch on this barge.
local cargo = require("shipnet.automation_cargo")
local electric = require("shipnet.automation_power")
local Cycle = {}
Cycle.__index = Cycle
local SWITCH_ACK_SECONDS = 4
local HAUL_MARGIN_KG = 1
local HAUL_DELAY_SECONDS = 10
local BEFORE_UNLOAD_SECONDS = 1
local BEFORE_LOWER_SECONDS = 1
local BASIC_POWER_WATTS = 500
local UNLOAD_KG_PER_SECOND = 5
local UNLOAD_INTERVAL = .25
local MAX_TRANSFERS_PER_POLL = 8

local powerMessage = {
    disconnected = "Waiting for cable connection",
    rechecking = "Rechecking electrical connection",
    no_power = "Waiting for external power",
    not_ready = "Waiting for the electrical inlet",
    no_elapsed = "Waiting for power",
}

local function stopDraw(self, cabinet, elapsed)
    self.power:consume(cabinet, elapsed or 0, "off")
    self.drawKW = 0
end

function Cycle:stopUnloading()
    self.unloading, self.unloadBudgetKg = false, nil
    self.unloadElapsed = 0
    self.drawerWaitingSince = nil
end

function Cycle:interruptObservation()
    self.haulCheck = nil
    self.unloadAt, self.lowerAt = nil, nil
    self:stopUnloading()
end

function Cycle:setEnabled(cabinet, enabled)
    cabinet.WinchAutomationEnabled = enabled
    self.request = nil
    self.lastLength, self.loweringUntil = nil, nil
    self.lastTime, self.drawKW = nil, 0
    self:interruptObservation()
    if enabled then
        self.transferUnconfirmed = false
        self.status = "Starting automation"
    else
        self.manualRaise = false
        if not self.transferUnconfirmed then self.status = "Automation off" end
        stopDraw(self, cabinet)
    end
end

function Cycle:reset()
    self:interruptObservation()
    self.power:reset()
end

function Cycle:adoptPanelRaise(leverOn, now, enabled)
    self.request = {on=false, retryAt=now + SWITCH_ACK_SECONDS}
    self.lastLever = leverOn
    self.manualRaise = false
    self.loweringUntil = nil
    self:interruptObservation()
    if not self.transferUnconfirmed then self.status = enabled and "Raising net" or "Automation off" end
end

local function haulThreshold(capacity)
    return math.max(0, capacity - HAUL_MARGIN_KG)
end

local function storageHaul(info)
    if info.status == "unavailable" or info.space == nil then return "Waiting for storage", "standby" end
    if info.space then return "Raising net", "active", "raise" end
    return "Empty the cabinet", "standby"
end

local function fishingAction(self, net, cabinet, now, lowering)
    -- Recheck the live weight on every poll, including during near-full confirmation.
    local weight, capacity = cargo.weight(net)
    if not weight or not capacity or capacity <= 0 then
        self.haulCheck = nil
        return "Waiting for fishing net", "standby"
    end
    if weight >= capacity then
        self.haulCheck = nil
        return "Raising net", "active", "raise"
    end

    local storage
    if not self.basic and not lowering and weight > 0 then
        local freeKg = cargo.storageFreeWeight(net, cabinet)
        if freeKg and freeKg > 0 and weight >= freeKg then
            storage = cargo.inspect(net, cabinet)
            if storage.status ~= "unavailable" and storage.space then return storageHaul(storage) end
        end
    end

    local threshold = haulThreshold(capacity)
    if weight == 0 or weight < threshold then
        self.haulCheck = nil
        if lowering then return "Lowering net", "active" end
        if storage then return storageHaul(storage) end
        if threshold == 0 then return "Waiting for catch", "standby" end
        return ("Waiting for %g kg"):format(threshold), "standby"
    end

    local check = self.haulCheck
    if not check or weight > check.lastWeight then
        check = {dueAt=now + HAUL_DELAY_SECONDS}
        self.haulCheck = check
    end
    check.lastWeight = weight
    if now < check.dueAt then
        if lowering then return "Lowering net", "active" end
        return "Confirming catch weight", "standby"
    end
    if lowering and not self.basic then return "Lowering net", "active" end
    return "Raising net", "active", "raise"
end

local function lowerWhenReady(self, now)
    self.lowerAt = self.lowerAt or now + BEFORE_LOWER_SECONDS
    if now < self.lowerAt then return "Waiting to lower net", "standby" end
    return "Lowering net", "active", "lower"
end

local function nextAction(self, net, cabinet, now, lowering, enabled)
    if not self.manualRaise and not net.FullyRaised and net.NetDropped then
        return fishingAction(self, net, cabinet, now, lowering)
    end
    self.haulCheck = nil
    if not net.FullyRaised then return "Raising net", enabled and "active" or "off" end
    if self.basic then
        local count = cargo.drawerContents(net)
        if count ~= 0 then self.lowerAt = nil end
        if count == nil then return "Waiting for the catch drawer", "standby" end
        if count > 0 then return "Unload the catch drawer", "standby", "wait_for_player" end
        return lowerWhenReady(self, now)
    end

    local idle = enabled and "standby" or "off"
    local info = cargo.inspect(net, cabinet)
    local storageUnavailable = info.status == "unavailable" or info.space == nil
    if storageUnavailable or not info.ready then
        self.unloadAt, self.lowerAt = nil, nil
        if storageUnavailable then return "Waiting for storage", idle end
        return "Waiting for the catch drawer", idle
    end
    self.unloadAt = self.unloadAt or now + BEFORE_UNLOAD_SECONDS
    if info.remaining > 0 and info.space then
        self.lowerAt = nil
        if now < self.unloadAt then return "Waiting to unload catch", idle end
        return "Unloading catch", "active", "unload"
    end
    if not enabled then
        self.manualRaise = false
        return "Automation off", "off"
    end
    if info.remaining > 0 then
        if info.capacity <= 0 then
            self.lowerAt = nil
            return "Waiting for fishing net", idle
        end
        if info.weight > 0 and info.weight >= haulThreshold(info.capacity) then
            self.lowerAt = nil
            return "Empty the cabinet", idle
        end
    end
    return lowerWhenReady(self, now)
end

function Cycle:unload(cabinet, net, elapsed)
    self.unloading = true
    local total = (self.unloadElapsed or 0) + elapsed
    local intervals = math.floor((total + 1e-6) / UNLOAD_INTERVAL)
    self.unloadElapsed = math.max(0, total - intervals * UNLOAD_INTERVAL)
    if intervals == 0 then return false end
    -- One batch per due poll. A late callback must not replay missed batches.
    self.unloadBudgetKg = (self.unloadBudgetKg or 0) + UNLOAD_INTERVAL * UNLOAD_KG_PER_SECOND
    local changed = false
    for _ = 1, MAX_TRANSFERS_PER_POLL do
        local result = cargo.unload(net, cabinet, self.unloadBudgetKg)
        if result.status == "accruing" then return changed end
        if result.status == "moved" then
            changed = true
            self.unloadBudgetKg = math.max(0, self.unloadBudgetKg - result.movedKg)
            if result.remaining == 0 then
                self:stopUnloading()
                return changed, true
            end
            if self.unloadBudgetKg == 0 then return changed end
        else
            self:stopUnloading()
            if result.status == "unconfirmed" then
                self.transferUnconfirmed = true
                self:setEnabled(cabinet, false)
                self.status = "Check both inventories before restarting"
            elseif result.status == "full" then self.status = "Empty the cabinet"
            elseif result.status ~= "empty" then self.status = "Waiting for the catch drawer" end
            return changed or result.status == "unconfirmed"
        end
    end
    -- A drawer fragmented across many slots should not bank unused batches.
    self.unloadBudgetKg = 0
    return changed
end

function Cycle:tick(cabinet, net, lever, now, command)
    local last = self.lastTime
    self.lastTime = now
    local powerStep = last and math.min(1, math.max(0, now-last)) or 0
    local enabled = cabinet.WinchAutomationEnabled == true
    local on = lever:IsOn()
    local changed = self.lastLever ~= nil and self.lastLever ~= on
    self.lastLever = on
    if self.transferUnconfirmed then
        self:stopUnloading()
        stopDraw(self, cabinet, powerStep)
        return
    end

    local pending = self.request
    if pending and not enabled and now >= pending.retryAt then
        self.request, pending = nil, nil
    end
    if changed and (not pending or pending.on ~= on) then
        if on then
            if enabled then
                self:setEnabled(cabinet, false)
                self.status = "Paused by manual control"
                return
            end
            if self.manualRaise then self.status = "Automation off" end
            self.manualRaise = false
        else
            -- The stock lever starts the haul. Wait for the drawer even if the
            -- game still reports the net as deployed during this poll.
            self:interruptObservation()
            self.manualRaise, self.loweringUntil = true, nil
        end
        self.request, pending = nil, nil
    end
    if pending and pending.on == on then
        local movingDown = net.NetDropped and not net.FullyRaised
        if (pending.on and movingDown) or (not pending.on and (not net.NetDropped or net.FullyRaised)) then
            self.request, pending = nil, nil
            if movingDown and on then self.manualRaise = false end
        end
    end
    if not enabled and (self.basic or not self.manualRaise) then
        self:interruptObservation()
        stopDraw(self, cabinet, powerStep)
        return
    end
    if last and now < last then
        self:interruptObservation()
    end
    if not last then
        self.power:consume(cabinet, 0, "standby")
        return
    end
    if now <= last then return end
    local elapsed = now - last
    -- NetDown can remain selected all the time the net is fishing. Follow
    -- physical cable travel to switch from motor load to standby.
    local length = net.CurrentLength
    local maximum = net.MaxLength
    if not net.FullyRaised then self.unloadAt, self.lowerAt = nil, nil end
    if net.FullyRaised or not net.NetDropped or (maximum and length and length >= maximum - .001) then
        self.loweringUntil = nil
    elseif self.lastLength and length and length > self.lastLength + .001 then
        self.loweringUntil = now + .75
    end
    self.lastLength = length
    local status, mode, action
    if pending and now < pending.retryAt then
        status, mode = pending.on and "Lowering net" or "Raising net", "active"
    else
        self.request = nil
        local lowering = self.loweringUntil and now < self.loweringUntil
        status, mode, action = nextAction(self, net, cabinet, now, lowering, enabled)
    end
    if action ~= "unload" and action ~= "wait_for_player" then self:stopUnloading() end
    if mode == "off" then
        self.status = status
        stopDraw(self, cabinet, powerStep)
        return
    end
    -- Do not replay elapsed time spent in map travel, pauses or an unloaded area.
    local paid, reason = self.power:consume(cabinet, powerStep, mode)
    self.drawKW = paid and (self.basic and BASIC_POWER_WATTS / 1000 or (mode == "active" and 4 or .5)) or 0
    self.status = paid and status or (powerMessage[reason] or "Waiting for external power")
    if not paid then self:stopUnloading() end
    if not paid or not action then return end
    if action == "wait_for_player" then
        self.drawerWaitingSince = self.drawerWaitingSince or now
        return
    end
    if action == "unload" then
        local moved, emptied = self:unload(cabinet, net, elapsed)
        if emptied then self.lowerAt = now + BEFORE_LOWER_SECONDS end
        return moved
    end
    self.haulCheck = nil
    self.request = {on = action == "lower", retryAt = now + SWITCH_ACK_SECONDS}
    local sent = command(action)
    if sent then
        self.lastLever = lever:IsOn()
        if action == "lower" then self.loweringUntil = now + .75 end
    else
        self.status = "Waiting for the winch"
    end
end

return {new=function(log, basic)
    return setmetatable({power=electric.new(log, basic and BASIC_POWER_WATTS / 1000 or nil),
        basic=basic, status="Automation off"}, Cycle)
end}
