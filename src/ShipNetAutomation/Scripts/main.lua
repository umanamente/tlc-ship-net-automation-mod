local storage = require("shipnet.storage")
local game_version = require("shipnet.game_version")
local observer = require("shipnet.observer").new()
local survey = require("shipnet.survey")
local panel_module = require("shipnet.panel")
local fit_module = require("shipnet.fit")
local fit_session = require("shipnet.fit_session")
local build_catalog = require("shipnet.build_catalog")
local variants = require("shipnet.variants")
local build_placement = require("shipnet.build_placement")
local built_controller = require("shipnet.built_controller")

local source = debug.getinfo(1, "S").source:gsub("\\", "/")
local dir = assert(source:match("^@(.*)/Scripts/main%.lua$"), "ShipNetAutomation must run under Scripts/")
local poll_ms = 250
local version = "0.1.0"
local build = game_version.steam_build(dir)
local installed_game_version
local version_attempts = 0
local state = {debugEnabled = storage.load_debug(dir), recording = false, message = "", summary = ""}
local writer, previous, quiet_samples, polls = nil, nil, 0, 0
local weight_polls, last_signal = 0, nil
local panel, active, loading, in_pump = nil, true, false, false
local key_toggle, key_close = false, false

local function log(message) print("[ShipNetAutomation] " .. tostring(message) .. "\n") end

local function message(text)
    state.message = text
    log(text)
end

local runtime = fit_module.new()
local built, device_runtime
local catalog = build_catalog.new({log=log})
local basicCatalog = build_catalog.new({log=log, variant=variants.basic})
local placement = build_placement.new({log=log,onCompleted=function() built.nextScan=0 end})
local fit = fit_session.new({runtime=runtime, state=state, storage=storage, dir=dir, message=message,
    version=version, build=build, survey=survey, observer=require("shipnet.observer").new()})

local function close_writer()
    local file = writer
    writer, previous, state.recording = nil, nil, false
    if file then
        local ok, err = file:close()
        if not ok then message("Could not close trace: " .. tostring(err)) end
        return ok
    end
    return true
end

local function append(row)
    if writer.seq == 0 then
        row.schema, row.modVersion, row.steamBuild, row.referenceBuild = 1, version, build, "25982825"
        row.gameVersion = installed_game_version
    end
    local ok, reason = writer:append(row)
    if not ok then
        close_writer()
        message("Trace write failed: " .. tostring(reason))
        return false
    end
    return true
end

local function open_trace()
    local reason
    writer, reason = storage.open(dir)
    if not writer then message("Cannot create a trace in Logs: " .. tostring(reason)); return false end
    state.logName = writer.name
    previous, polls, quiet_samples = nil, 0, 0
    weight_polls, last_signal = 0, nil
    state.signal = nil
    observer:reset()
    return true
end

local function shown(value)
    if value == nil then return "?" end
    return tostring(value)
end

local function summary(sample)
    if sample.netWeight == nil and sample.fullyRaised == nil then
        return tostring(sample.status) .. (sample.detail and ("  " .. sample.detail:match("^[^\n]*")) or "")
    end
    return string.format("Weight %s / %s kg   |   Raised %s   |   Interact %s   |   Items %s",
        shown(sample.netWeight), shown(sample.inventoryMaxWeight), shown(sample.fullyRaised),
        shown(sample.interactionEnabled), shown(sample.inventoryTotalCount))
end

-- Keep continuously moving counters in the full readings without emitting
-- four identical-in-practice records per second while the net is trawling.
local function comparison(sample)
    local result = {}
    for key, value in pairs(sample) do
        if key ~= "currentLength" and key ~= "fishingCounter" and key ~= "shipSpeedCmS" then
            result[key] = storage.encode(value, key)
        end
    end
    return result
end

local function changes(current)
    local names = {}
    for key, value in pairs(current) do
        if not previous or previous[key] ~= value then names[#names + 1] = key end
    end
    for key in pairs(previous or {}) do
        if current[key] == nil then names[#names + 1] = key end
    end
    table.sort(names)
    return names
end

local function record(kind, reason, marker)
    if not writer or loading then return false end
    local ok, sample = pcall(observer.sample, observer)
    if not ok then sample = {status = "observer_error", detail = tostring(sample)} end
    polls = polls + 1
    local has_weight = type(sample.netWeight) == "number"
    if has_weight then weight_polls = weight_polls + 1 end
    if last_signal ~= has_weight then
        last_signal = has_weight
        state.signal = has_weight and "Receiving net weight" or "Waiting for net weight"
        log(state.signal .. " (" .. tostring(sample.status) .. ")")
    end
    local current = comparison(sample)
    local changed = changes(current)
    local heartbeat = quiet_samples >= 59
    if not reason and #changed == 0 and not heartbeat then
        quiet_samples = quiet_samples + 1
        return false
    end
    local row = {kind = kind, reason = reason or (#changed > 0 and "change" or "heartbeat"),
        marker = marker, poll = polls, changed = changed, state = sample}
    if not append(row) then return true end
    previous, quiet_samples = current, 0
    state.summary = summary(sample)
    return true
end

local function stop(reason, final_sample)
    if not writer then return end
    if final_sample then record("sample", "final") end
    if not writer or not append({kind = "stop", reason = reason, polls = polls, weightPolls = weight_polls}) then return end
    if close_writer() then
        message((weight_polls > 0 and "Recording stopped. " or "Recording stopped with no net weight readings. ") .. state.logName)
    end
end

local markers = {about_to_lower = true, about_to_raise = true, about_to_collect = true, collected = true}

local function capture_mount()
    local result_ok, result = xpcall(survey.capture, debug.traceback)
    if not result_ok then result = {status = "error", detail = tostring(result)} end
    local report, reason = storage.open(dir, "mount-survey")
    if not report then message("Cannot create mount survey: " .. tostring(reason)); return end
    local wrote, write_error = report:append({kind = "mount_survey", schema = 1, modVersion = version,
        steamBuild = build, referenceBuild = "25982825", survey = result})
    local closed, close_error = report:close()
    if not wrote or not closed then message("Could not save mount survey: " .. tostring(write_error or close_error)); return end
    if not state.recording then state.logName = report.name end
    local outcome = result.status == "measured" and "Winch position measured" or ("Survey: " .. tostring(result.status))
    message(outcome .. ". " .. report.name)
end

local function action(name, arg)
    if not active or loading then return end
    if name == "set_debug" and type(arg) == "boolean" then
        if arg == state.debugEnabled then return end
        if not arg and not fit:stop("debug_disabled") then return end
        local saved, reason = storage.save_debug(dir, arg)
        if saved then
            state.debugEnabled = arg
            if not arg then stop("debug_disabled", false); state.summary = "" end
            message(arg and "Debug tools enabled." or "Debug tools disabled.")
        else
            message("Cannot save the Debug setting: " .. tostring(reason))
        end
    elseif not state.debugEnabled then
        return
    elseif name:sub(1,4) == "fit_" then
        if name=="fit_show" and built:isBound() then
            message("A built controller already occupies this winch.")
        else
            fit:action(name)
        end
    elseif name == "survey" then
        capture_mount()
    elseif name == "start" and not writer then
        if open_trace() and append({kind = "start", pollIntervalMs = poll_ms}) then
            state.recording = true
            message("Recording. " .. state.logName)
            record("sample", "initial")
        end
    elseif name == "stop" and state.recording then
        stop("user", true)
    elseif name == "snapshot" then
        local single = not writer
        if not single or open_trace() then
            record("snapshot", "requested")
            if writer and (not single or close_writer()) then message("Snapshot saved. " .. state.logName) end
        end
    elseif name == "mark" and state.recording and markers[arg] then
        record("mark", "player", arg)
        if writer then message("Marked " .. arg:gsub("_", " ") .. ".") end
    end
end

panel = panel_module.new({
    state = function() return state end, action = action, log = log,
    device = function() return (device_runtime or runtime):deviceStatus() end,
    command = function(which) return (device_runtime or runtime):controlNet(which) end,
    automation = function(enabled)
        if device_runtime and device_runtime==built:runtimeForInteraction() then return device_runtime:setAutomation(enabled) end
        return false,"Device unavailable"
    end,
    legacyAvailable = function()
        return built and built:hasLegacyStorage()
    end,
    openLegacy = function(pc)
        if not built or not built:isBound() then return false,"Device unavailable." end
        return built:openLegacyStorage(pc)
    end,
})
local function open_device(caller, pc)
    if not active or loading or not caller then return false, "Device unavailable." end
    device_runtime = caller
    if caller.built then
        if panel:is_open() then return false,"Close the current window first." end
        return caller:openScreen(pc)
    end
    return panel:open_device(pc)
end
runtime:setInteractionHandlers({screen=function(pc) return open_device(runtime,pc) end, log=log})
built = built_controller.new({handlers={
    screen=function(pc) return open_device(built:runtimeForInteraction(),pc) end, log=log,
}})
local next_device_refresh = 0
local function pump()
    if active and not loading and not installed_game_version and version_attempts < 20 then
        version_attempts = version_attempts + 1
        local reason
        installed_game_version, reason = game_version.capture(dir, build, version, version_attempts == 20)
        if installed_game_version then
            log("Game version " .. installed_game_version .. "; Steam build " .. (build or "unknown"))
        elseif version_attempts == 20 then
            log("Could not record game version: " .. tostring(reason))
        end
    end
    if not active or loading or in_pump then return end
    in_pump = true
    local ok, err = pcall(function()
        catalog:tick()
        basicCatalog:tick()
        placement:tick()
        built:tick()
        local glass=device_runtime and device_runtime.screen
        if (key_close or key_toggle) and glass and glass.focus then glass:close()
        elseif key_close then panel:close("escape")
        elseif key_toggle then panel:toggle() end
        key_close, key_toggle = false, false
        panel:tick()
        if fit:tick() then panel:refresh() end
        if panel.update_prompt then
            local hint
            if not panel:is_open() then
                local installed = built:runtimeForInteraction()
                if installed then hint = installed:interactionHint() end
                if not hint and state.fitVisible then hint = runtime:interactionHint() end
            end
            panel:update_prompt(hint)
        end
        if panel.is_device_open and panel:is_device_open() and os.time() >= next_device_refresh then
            next_device_refresh = os.time() + 1
            local available=device_runtime and (device_runtime==built:runtimeForInteraction()
                or (device_runtime==runtime and state.fitVisible))
            if available then
                panel:refresh()
            else
                panel:close("device removed")
            end
        end
        if state.recording and record("sample") then panel:refresh() end
    end)
    in_pump = false
    if not ok then
        key_toggle, key_close = false, false
        if writer then stop("runtime_error", false) end
        message("Diagnostic update failed: " .. tostring(err))
        pcall(panel.close, panel, "update failed")
    end
end

local ok, loop = pcall(LoopInGameThreadWithDelay, poll_ms, pump)
if not ok or type(loop) ~= "number" then
    log("Game-thread scheduler unavailable: " .. tostring(loop))
    return
end

local function bind_toggle(modifiers)
    if type(IsKeyBindRegistered) == "function" then
        local checked, occupied = pcall(IsKeyBindRegistered, Key.F4, modifiers)
        if not checked or occupied then return false end
    end
    return pcall(RegisterKeyBind, Key.F4, modifiers, function() if active and not loading then key_toggle = true end end)
end
local binding = "F4"
if not bind_toggle({}) then
    binding = "Ctrl+Shift+F4"
    if not ModifierKey or not bind_toggle({ModifierKey.CONTROL, ModifierKey.SHIFT}) then
        binding = "unavailable (key binding conflict)"
    end
end
if Key.ESCAPE then
    pcall(RegisterKeyBind, Key.ESCAPE, {}, function()
        if active and not loading and ((panel.is_open and panel:is_open())
            or (device_runtime and device_runtime.screen and device_runtime.screen.focus)) then key_close = true end
    end)
end

if type(RegisterLoadMapPreHook) == "function" and type(RegisterLoadMapPostHook) == "function" then
    RegisterLoadMapPreHook(function()
        loading, key_toggle, key_close = true, false, false
        device_runtime = nil
        placement:shutdown()
        catalog:reset()
        basicCatalog:reset()
        built:reset()
        if writer then stop("map_change", false) end
        fit:stop("map_change")
        if panel.clear_prompt then pcall(panel.clear_prompt, panel) end
        pcall(panel.close, panel, "travel")
        if panel.discard then panel:discard() end
        observer:reset()
        state.summary = ""
    end)
    RegisterLoadMapPostHook(function() loading = false end)
end

if ModRef then
    ModRef.OnUnload = function()
        active = false
        placement:shutdown()
        built:reset()
        if writer then stop("mod_unload", false) end
        fit:stop("mod_unload")
        if CancelDelayedAction then pcall(CancelDelayedAction, loop) end
        if panel.shutdown then pcall(panel.shutdown, panel) else pcall(panel.close, panel, "unload") end
        observer:reset()
    end
end
log(version .. " loaded. Panel: " .. binding .. ". Traces: " .. dir .. "/Logs")
