-- Fit controls and local reports. All Unreal object references stay in the fit runtime.
local Session = {}
Session.__index = Session
local model = require("shipnet.model")
local steps = {5, 20, 1}
local moves = {fit_x_minus={"X",-1}, fit_x_plus={"X",1}, fit_y_minus={"Y",-1}, fit_y_plus={"Y",1},
    fit_z_minus={"Z",-1}, fit_z_plus={"Z",1}, fit_yaw_minus={"Yaw",-1}, fit_yaw_plus={"Yaw",1}}

local function label(value)
    if value == nil then return "unknown" end
    if value == true then return "yes" elseif value == false then return "no" end
    return tostring(value)
end

function Session.new(opts)
    local self = setmetatable(opts, Session)
    self.step_index, self.hatch, self.drive, self.polls = 1, 0, 0, 0
    self.offset = self.storage.load_fit(self.dir) or {}
    self:update_coordinates()
    return self
end

function Session:update_coordinates()
    local p = self.offset
    self.state.fitCoordinates = string.format("Winch-local   X %.1f   Y %.1f   Z %.1f cm   |   Yaw %.1f°   |   Step %d cm / °",
        p.X or 0, p.Y or 0, p.Z or 0, p.Yaw or 0, steps[self.step_index])
end

function Session:apply(report)
    self.state.fitVisible = report.visible == true
    self.state.fitStatus = (self.state.fitVisible and "Controller visible" or "Controller hidden") ..
        "  |  " .. tostring(report.status or "unknown")
    if report.visible and report.placementMode then
        self.state.fitStatus = self.state.fitStatus .. "  |  " .. report.placementMode:gsub("_"," ")
    end
    if report.visible and type(report.hatchDegrees) == "number" then
        local lid = report.hatchDegrees > 0 and ("Top lid open %g°"):format(report.hatchDegrees) or "Top lid closed"
        self.state.fitStatus = self.state.fitStatus .. "  |  " .. lid
    end
    if report.detail and report.detail ~= "" then
        self.state.fitStatus = self.state.fitStatus .. "  |  " .. tostring(report.detail):match("^[^\n]*"):sub(1,230)
    end
    local p = report.power
    self.state.fitPower = p and string.format("Inlet %s   |   Stock mesh %s   |   Registered %s\nCable present %s   |   Connected %s   |   Has power %s",
        label(p.status), label(p.visual), label(p.registered), label(p.cablePresent), label(p.connected), label(p.hasPower)) or ""
    if self.state.fitVisible and report.offset then self.offset = report.offset end
    self:update_coordinates()
end

function Session:call(method, ...)
    local ok, value = pcall(self.runtime[method], self.runtime, ...)
    if ok and type(value) == "table" then return value end
    return {status="runtime_error", visible=self.state.fitVisible == true,
        detail=ok and ("No report from " .. method) or tostring(value)}
end

function Session:write(action, report, inspect)
    if not self.writer then
        local reason
        self.writer, reason = self.storage.open(self.dir, "fit-check")
        if not self.writer then self.message("Could not create fit report: " .. tostring(reason)); return end
        self.state.fitFile = self.writer.name
    end
    local row = {kind="fit_check", schema=1, modVersion=self.version, steamBuild=self.build,
        action=action, fit=report, hatchDegrees=self.hatch, driveDegrees=self.drive}
    if inspect then
        local ok, survey = pcall(self.survey.capture)
        row.survey = ok and survey or {status="error",detail=tostring(survey)}
        local read, sample = pcall(self.observer.sample, self.observer)
        row.stock = read and sample or {status="error",detail=tostring(sample)}
    end
    local wrote, reason = self.writer:append(row)
    if not wrote then self:close_log(); self.message("Could not write fit report: " .. tostring(reason)) end
end

function Session:close_log()
    if self.writer then
        local ok, reason = self.writer:close()
        self.writer = nil
        if not ok then self.message("Could not close fit report: " .. tostring(reason)) end
    end
end

function Session:stop(reason)
    if not self.state.fitVisible and not self.writer then return true end
    local result = self:call("hide", reason)
    self:apply(result)
    if self.writer then self:write(reason, result) end
    if not result.visible or reason=="map_change" or reason=="mod_unload" then
        self:close_log()
        self.last_power, self.last_raised = nil, nil
        self.hatch, self.drive = 0, 0
        return true
    end
    self.message(result.detail or "Unplug the preview cable and retry.")
    return false
end

function Session:action(id)
    if id == "fit_step" then
        self.step_index = self.step_index % #steps + 1
        self:update_coordinates()
        return
    end
    if id == "fit_hide" then self:stop("user"); return end
    if id == "fit_show" and self.state.fitVisible then return end
    if id ~= "fit_show" and id ~= "fit_capture" and not self.state.fitVisible then return end
    local result
    if id == "fit_show" then
        result = self:call("show", self.storage.load_fit(self.dir))
        self.hatch, self.drive = 0, 0
        self.last_raised = result.stockFullyRaised
    elseif id == "fit_capture" then
        result = self:call("report")
    elseif moves[id] then
        local move = moves[id]
        result = self:call("move", move[1], move[2] * steps[self.step_index])
    elseif id == "fit_reset" then
        result = self:call("reset")
    elseif id == "fit_save" then
        result = self:call("report")
        if result.visible and result.offset then
            local ok, reason = self.storage.save_fit(self.dir, result.offset)
            self.message(ok and "Preview position saved." or ("Could not save position: " .. tostring(reason)))
        end
    elseif id == "fit_hatch" or id == "fit_drive" then
        local hatch = id == "fit_hatch" and (self.hatch == 0 and model.maxHatchDegrees or 0) or self.hatch
        local drive = id == "fit_drive" and ((self.drive + 90 + 180) % 360 - 180) or self.drive
        result = self:call("pose", hatch, drive)
        if result.visible and result.status=="shown" then self.hatch, self.drive = hatch, drive end
    else
        return
    end
    self:apply(result)
    self:write(id, result, id=="fit_capture" or id=="fit_show")
    if not result.visible then self:close_log() end
end

function Session:tick()
    if not self.state.fitVisible then return false end
    local ok, event = pcall(self.runtime.tick, self.runtime)
    if not ok then event={status="runtime_error",visible=true,detail=tostring(event)} end
    self.polls = self.polls + 1
    if not event and self.polls % 8 ~= 0 then return false end
    local r = event or self:call("status")
    self:apply(r)
    if type(r.stockFullyRaised) == "boolean" then
        if self.last_raised ~= nil and self.last_raised ~= r.stockFullyRaised then
            self:write(r.stockFullyRaised and "winch_fully_raised" or "winch_left_raised_position",
                self:call("report"), true)
        end
        self.last_raised = r.stockFullyRaised
    end
    local power_key = self.storage.encode({status=r.status,visible=r.visible,power=self.state.fitPower})
    if self.last_power ~= power_key then
        self:write("status_change", r)
        self.last_power = power_key
    end
    if not r.visible then self:close_log(); self.last_power, self.last_raised = nil, nil end
    return true
end

return Session
