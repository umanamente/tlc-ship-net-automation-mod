-- Owned runtime widgets. Only the navigation button's bound click event is
-- observed. No game, inventory or net interaction is issued by this module.
local Panel = {}
Panel.__index = Panel

local HUD = "/Game/UI/Game/HUD/"
local HOST = "BP_VoyageIngameEmpty"
local BUTTON = "BP_VoyageCheat_MenuButton_Widget"
local CLICK = HUD .. BUTTON .. "." .. BUTTON .. "_C:BndEvt__" .. BUTTON ..
    "_Button_K2Node_ComponentBoundEvent_0_OnButtonClickedEvent__DelegateSignature"
local WHITE = { R = 0.91, G = 0.95, B = 0.98, A = 1 }
local ACCENT = { R = 0.36, G = 0.83, B = 0.84, A = 1 }
local SURFACE = { R = 0.018, G = 0.031, B = 0.040, A = 0.99 }
local BUTTON_COLOR = { R = 0.09, G = 0.18, B = 0.23, A = 1 }
local SELECTED = { R = 0.045, G = 0.30, B = 0.32, A = 1 }
local GREEN = { R = 0.32, G = 0.83, B = 0.47, A = 1 }

local function valid(object)
    local ok, yes = pcall(function() return object ~= nil and object:IsValid() end)
    return ok and yes == true
end

local function scope()
    local pc = FindFirstOf("VoyagePlayerController")
    if not valid(pc) or not pc:IsLocalController() then return end
    local world = pc:GetWorld()
    if not valid(world) then return end
    local pawn = pc.Pawn
    return pc, tostring(pc:GetAddress()) .. "/" .. tostring(world:GetAddress()),
        valid(pawn) and tostring(pawn:GetAddress()) or nil
end

local function widget_class(name)
    local asset = name .. "_C"
    local path = HUD .. name .. "." .. asset
    local class = StaticFindObject(path)
    if not valid(class) then
        local registry = StaticFindObject("/Script/AssetRegistry.Default__AssetRegistryHelpers")
        assert(valid(registry), "Asset registry unavailable")
        class = registry:GetAsset({ PackageName = FName(HUD .. name, EFindName.FNAME_Add),
            AssetName = FName(asset, EFindName.FNAME_Add) })
    end
    assert(valid(class) and class:IsA("/Script/CoreUObject.Class") and
        class:GetFullName():match("^[^ ]+ (.+)$") == path, "Missing widget class " .. name)
    local parent = class
    for _ = 1, 16 do
        if not valid(parent) then break end
        if parent:GetFullName():match("^[^ ]+ (.+)$") == "/Script/UMG.UserWidget" then return class end
        parent = parent:GetSuperStruct()
    end
    error("Invalid widget class " .. name)
end

local function pad(x, y)
    return { Left = x, Right = x, Top = y, Bottom = y }
end

-- World glass and its focus-only input target use these same stock widget classes.
function Panel.host(pc)
    local input=StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
    local host=input:Create(pc,widget_class(HOST),pc)
    assert(valid(host) and valid(host.WidgetTree.RootWidget),"Missing screen canvas")
    return host,input
end

function Panel.inputButton(pc,input)
    return input:Create(pc,widget_class(BUTTON),pc)
end
Panel.clickEvent=CLICK

local function add(parent, child, fill)
    local slot = parent:AddChild(child)
    slot:SetPadding(pad(4, 4))
    if fill then slot:SetSize({ Value = 1, SizeRule = 1 }) end
    return slot
end

function Panel.new(callbacks)
    return setmetatable({ callbacks = callbacks, tab = "settings", serial = 0 }, Panel)
end

function Panel:_log(message)
    if self.callbacks.log then pcall(self.callbacks.log, tostring(message)) end
end

function Panel:is_open()
    return self.view ~= nil and self.view.open == true
end

function Panel:is_device_open()
    return self:is_open() and self.view.device == true
end

function Panel:_make(name, tree)
    local class = StaticFindObject("/Script/UMG." .. name)
    assert(valid(class), "Missing UMG class " .. name)
    self.serial = self.serial + 1
    local obj = StaticConstructObject(class, tree or self.view.tree,
        FName("ShipNetAutomation_" .. name .. "_" .. self.serial), EObjectFlags.RF_Transient)
    assert(valid(obj), "Failed to construct " .. name)
    return obj
end

function Panel:_label(value, size, color)
    local label = self:_make("TextBlock")
    label:SetText(FText(value))
    label:SetAutoWrapText(true)
    local font = label.Font
    font.Size = size
    label:SetFont(font)
    label:SetColorAndOpacity({ SpecifiedColor = color or WHITE, ColorUseRule = 0 })
    return label
end

function Panel:_ensure_hook()
    if self.hooked then return end
    self.hook_pre, self.hook_post = RegisterHook(CLICK, function(context)
        local v = self.view
        if not v or not v.open or #v.pending >= 12 then return end
        -- Unrelated game and mod buttons can execute the same Blueprint. An
        -- instance in our current host must match before queueing anything.
        local ok, id = pcall(function()
            local obj = context:get()
            if valid(obj) then return obj:GetAddress() end
        end)
        local record = ok and v.by_address[id]
        if record and record.active then v.pending[#v.pending + 1] = record end
    end)
    self.hooked = true
end

function Panel:_button(parent, id, title, page, argument)
    local v = self.view
    local button = v.input:Create(v.pc, v.button_class, v.pc)
    assert(valid(button) and valid(button.Button) and valid(button.ButtonText), "Missing navigation button controls")
    button.Text = title
    button.ButtonText:SetText(FText(title))
    button.ButtonText:SetAutoWrapText(true)
    button.Button:SetBackgroundColor(BUTTON_COLOR)
    add(parent, button, page == "debug" or page == "fit" or id == "settings" or id == "debug" or id == "fit")
    local record = { id = id, widget = button, page = page, argument = argument }
    v.controls[id] = record
    v.by_address[button:GetAddress()] = record
    return button.Button
end

function Panel:_build()
    local v = self.view
    local body = self:_make("VerticalBox")
    local frame = self:_make("Border")
    frame:SetBrushColor(SURFACE)
    frame:SetPadding(pad(16, 12))
    frame:SetContent(body)
    v.slot = v.root:AddChildToCanvas(frame)
    v.slot:SetAutoSize(false)
    v.slot:SetAnchors({ Minimum = { X = 0.5, Y = 0.5 }, Maximum = { X = 0.5, Y = 0.5 } })
    v.slot:SetAlignment({ X = 0.5, Y = 0.5 })
    v.slot:SetPosition({ X = 0, Y = 0 })

    local header = self:_make("HorizontalBox")
    add(body, header)
    add(header, self:_label(v.device and "Winch settings" or "Ship Net Automation", 23, ACCENT), true)
    v.focus = self:_button(header, "close", "Close")
    if v.device then
        add(body, self:_label("Fishing net", 18))
        v.net_reading = self:_label("", 16)
        add(body, v.net_reading)
        local commands = self:_make("HorizontalBox")
        add(body, commands)
        self:_button(commands, "device_raise", "Raise net")
        self:_button(commands, "device_lower", "Lower net")
        v.automationRow = self:_make("HorizontalBox")
        add(body, v.automationRow)
        self:_button(v.automationRow, "device_auto", "Start automation")
        v.automationReading = self:_label("", 15)
        add(v.automationRow, v.automationReading, true)
        v.storageLabel = self:_label("Internal storage", 18)
        v.storageRow = self:_make("HorizontalBox")
        add(body, v.storageLabel)
        local storage_row = v.storageRow
        add(body, storage_row)
        v.storage_reading = self:_label("", 16, GREEN)
        add(storage_row, v.storage_reading, true)
        self:_button(storage_row, "device_legacy", "Open dev.6 preview storage")
        v.power_reading = self:_label("", 15)
        add(body, v.power_reading)
        v.feedback = self:_label("", 14, ACCENT)
        add(body, v.feedback)
        return
    end
    local tabs = self:_make("HorizontalBox")
    add(body, tabs)
    self:_button(tabs, "settings", "Settings")
    self:_button(tabs, "debug", "Debug")
    self:_button(tabs, "fit", "Fit test")

    local scroll = self:_make("ScrollBox")
    add(body, scroll, true)
    v.pages = {}
    for _, name in ipairs({ "settings", "debug", "fit" }) do
        local box = self:_make("VerticalBox")
        scroll:AddChild(box)
        v.pages[name] = box
    end
    local settings = v.pages.settings
    add(settings, self:_label("Developer tools", 18, WHITE))
    add(settings, self:_label("Enable Debug and Fit test to record the stock net and place the rail controller.", 15, WHITE))
    self:_button(settings, "set_debug", "Enable Debug tab", "settings")
    if self.callbacks.legacyAvailable and self.callbacks.legacyAvailable() then
        self:_button(settings,"device_legacy","Open dev.6 preview storage","settings")
    end

    local debug = v.pages.debug
    local tools_row = self:_make("HorizontalBox")
    add(debug, tools_row)
    self:_button(tools_row, "survey", "Survey mounting point", "debug")
    add(debug, self:_label("Stand on the proposed deck spot facing the service aisle, then take one survey.", 15))
    v.recording = self:_label("", 18, ACCENT)
    add(debug, v.recording)
    add(debug, self:_label("Start recording and check the net weight here before lowering the net. Close the panel to operate the winch. Reopen to mark a step or stop recording.", 15))
    local actions = self:_make("HorizontalBox")
    add(debug, actions)
    self:_button(actions, "start", "Start recording", "debug")
    self:_button(actions, "stop", "Stop recording", "debug")
    self:_button(actions, "snapshot", "Take snapshot", "debug")
    add(debug, self:_label("Manual markers", 17))
    local before = self:_make("HorizontalBox")
    add(debug, before)
    self:_button(before, "mark_lower", "Before lowering", "debug", "about_to_lower")
    self:_button(before, "mark_raise", "Before raising", "debug", "about_to_raise")
    local loot = self:_make("HorizontalBox")
    add(debug, loot)
    self:_button(loot, "mark_collect", "Before collecting", "debug", "about_to_collect")
    self:_button(loot, "mark_collected", "After collecting", "debug", "collected")
    v.summary = self:_label("", 14)
    v.log_name = self:_label("", 14)
    add(debug, v.summary)
    add(debug, v.log_name)
    local fit = v.pages.fit
    local function row(...)
        local line = self:_make("HorizontalBox")
        add(fit, line)
        local buttons = {...}
        for i = 1, #buttons, 2 do self:_button(line, buttons[i], buttons[i+1], "fit") end
    end
    v.fit_status = self:_label("", 16, ACCENT)
    add(fit, v.fit_status)
    row("fit_show", "Show controller", "fit_hide", "Remove preview", "fit_capture", "Capture report")
    v.fit_power = self:_label("", 14)
    add(fit, v.fit_power)
    row("fit_hatch", "Open / close top lid", "fit_drive", "Turn shaft 90°")
    v.fit_coordinates = self:_label("", 15)
    add(fit, v.fit_coordinates)
    row("fit_x_minus", "X −", "fit_x_plus", "X +", "fit_y_minus", "Y −", "fit_y_plus", "Y +")
    row("fit_z_minus", "Z −", "fit_z_plus", "Z +", "fit_yaw_minus", "Yaw −", "fit_yaw_plus", "Yaw +")
    row("fit_step", "Change step", "fit_save", "Save position", "fit_reset", "Reset position")
    v.fit_file = self:_label("", 14)
    add(fit, v.fit_file)
    v.message = self:_label("", 14, ACCENT)
    add(body, v.message)
end

function Panel:_fit()
    local v = self.view
    local size = v.layout:GetViewportSize(v.pc)
    local dpi = v.layout:GetViewportScale(v.pc)
    assert(type(dpi) == "number" and dpi > 0 and size.X > 0 and size.Y > 0, "Viewport unavailable")
    local width = math.max(1, math.min(v.device and 490 or 710, size.X / dpi - 16))
    local height = math.max(1, math.min(v.device and 425 or 570, size.Y / dpi - 16))
    if width ~= v.width or height ~= v.height then
        v.slot:SetSize({ X = width, Y = height })
        v.width, v.height = width, height
    end
end

function Panel:_refresh()
    local v = self.view
    local function update(key, value)
        if v.text_cache[key] ~= value then
            v[key]:SetText(FText(value))
            v.text_cache[key] = value
        end
    end
    if v.device then
        local d = self.callbacks.device()
        local position = "Unavailable"
        if d.netAvailable then
            if d.fullyRaised then position = "On deck"
            elseif d.netDropped then position = "Deployed"
            else position = "Hauling" end
        end
        if type(d.netWeightKg) == "number" then position = ("%s   |   Catch %.1f kg"):format(position, d.netWeightKg) end
        update("net_reading", position)
        local storageVisibility = d.basic and 1 or 0
        v.storageLabel:SetVisibility(storageVisibility)
        v.storageRow:SetVisibility(storageVisibility)
        local ratio = d.storage and d.storage.fillRatio
        update("storage_reading", type(ratio) == "number" and ("%d%% full"):format(math.floor(ratio * 100 + .5)) or "Unavailable")
        local power = d.power or {}
        local supply = "Unknown"
        local automatic = d.automationEnabled
        if automatic and power.connected == false then supply = "Waiting for connection"
        elseif (d.automationDrawKW or 0) > 0 or (not automatic and power.hasPower == true) then supply = "Powered"
        elseif power.connected == true then supply = "Cable connected"
        elseif power.connected == false then supply = "No cable" end
        local draw = d.automationDrawKW and ("   |   %g kW"):format(d.automationDrawKW) or ""
        update("power_reading", "Electrical inlet   |   " .. supply .. draw)
        v.automationRow:SetVisibility(automatic == nil and 1 or 0)
        if automatic ~= nil then
            update("automationReading", d.automationStatus or "")
            local title = automatic and "Stop automation" or "Start automation"
            if v.text_cache.autoButton ~= title then
                local button = v.controls.device_auto.widget
                button.Text = title
                button.ButtonText:SetText(FText(title))
                v.text_cache.autoButton = title
            end
        end
        update("feedback", v.commandFeedback or "")
        local legacy = self.callbacks.openLegacy and self.callbacks.legacyAvailable and self.callbacks.legacyAvailable() == true
        for id, record in pairs(v.controls) do
            local enabled = id == "close" or (id == "device_auto" and automatic ~= nil) or (id == "device_legacy" and legacy) or (d.netAvailable and
                ((id == "device_raise" and not d.fullyRaised) or (id == "device_lower" and not d.netDropped)))
            record.active = enabled == true
            record.widget:SetIsEnabled(record.active)
            if id == "device_legacy" then record.widget:SetVisibility(legacy and 0 or 1) end
        end
        return
    end
    local state = self.callbacks.state()
    local enabled, recording = state.debugEnabled == true, state.recording == true
    if not enabled then self.tab = "settings" end
    local shown = state.fitVisible == true
    if v.last_tab ~= self.tab or v.last_enabled ~= enabled or v.last_recording ~= recording or v.last_fit ~= shown then
        for page, box in pairs(v.pages) do box:SetVisibility(page == self.tab and 0 or 1) end
        for id, item in pairs(v.controls) do
            local visible = (id ~= "debug" and id ~= "fit") or enabled
            local available = (id ~= "start" or not recording) and
                ((id ~= "stop" and not item.argument) or recording)
            if item.page == "fit" then
                available = (id == "fit_show" and not shown) or id == "fit_capture" or id == "fit_step" or
                    (id ~= "fit_show" and shown)
            end
            item.active = visible and available and (not item.page or item.page == self.tab)
            item.widget:SetVisibility(visible and 0 or 1)
            item.widget:SetIsEnabled(available)
            if id == "debug" or id == "settings" or id == "fit" then
                item.widget.Button:SetBackgroundColor(id == self.tab and SELECTED or BUTTON_COLOR)
            end
        end
        local toggle = v.controls.set_debug.widget
        local caption = enabled and "Disable Debug tab" or "Enable Debug tab"
        toggle.Text = caption
        toggle.ButtonText:SetText(FText(caption))
        v.last_tab, v.last_enabled, v.last_recording, v.last_fit = self.tab, enabled, recording, shown
    end
    update("recording", recording and ("Recording - " .. (state.signal or "Checking net")) or "Recorder idle")
    update("message", tostring(state.message or ""))
    update("summary", tostring(state.summary or ""))
    update("log_name", state.logName and ("Log file: " .. state.logName) or "")
    update("fit_status", state.fitStatus or "Board the barge, then show the controller.")
    update("fit_power", state.fitPower or "")
    update("fit_coordinates", state.fitCoordinates or "")
    update("fit_file", state.fitFile and ("Report: " .. state.fitFile) or "")
end

function Panel:refresh()
    if not self:is_open() then return end
    local ok, err = pcall(self._refresh, self)
    if not ok then self:_log(err) end
end

function Panel:clear_prompt()
    local hint = self.prompt
    self.prompt = nil
    if hint and valid(hint.host) then hint.host:RemoveFromParent() end
end

function Panel:update_prompt(hint)
    if not hint or self:is_open() then
        if self.prompt and self.prompt.visible then
            if valid(self.prompt.host) then self.prompt.host:SetVisibility(1) end
            self.prompt.visible = false
        end
        return
    end
    local pc, key = scope()
    if not pc then return end
    if self.prompt and (self.prompt.key ~= key or not valid(self.prompt.host)) then self:clear_prompt() end
    if not self.prompt then
        local input = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
        local host = input:Create(pc, widget_class(HOST), pc)
        local tree = host.WidgetTree
        local frame = self:_make("Border", tree)
        local label = self:_make("TextBlock", tree)
        frame:SetBrushColor(SURFACE)
        frame:SetPadding(pad(14, 6))
        local font = label.Font
        font.Size = 16
        label:SetFont(font)
        label:SetColorAndOpacity({SpecifiedColor=WHITE, ColorUseRule=0})
        frame:SetContent(label)
        local slot = tree.RootWidget:AddChildToCanvas(frame)
        slot:SetAutoSize(true)
        slot:SetAnchors({Minimum={X=.5,Y=.79},Maximum={X=.5,Y=.79}})
        slot:SetAlignment({X=.5,Y=1})
        slot:SetPosition({X=0,Y=0})
        host:SetVisibility(3) -- HitTestInvisible, including the label.
        host:AddToViewport(9650)
        self.prompt = {host=host, key=key, label=label, visible=true}
    end
    local text = (hint.key and hint.key ~= "" and (hint.key .. "    ") or "") .. hint.label
    if text ~= self.prompt.text then self.prompt.label:SetText(FText(text)); self.prompt.text = text end
    if not self.prompt.visible then self.prompt.host:SetVisibility(3); self.prompt.visible = true end
end

-- Called during travel after UE releases the old world. This path deliberately
-- touches only Lua state. A queued click cannot be replayed in the new world.
function Panel:discard()
    self.view = nil
    self.prompt = nil
    self.tab = "settings"
end

function Panel:close(reason)
    local v = self.view
    if not v then return true end
    v.open = false
    v.pending = {}
    local ok, pc, key = pcall(scope)
    if not ok or not pc then return false end -- Retry after a transient loading gap.
    if key ~= v.key then self:discard(); return true end
    local errors = {}
    local function release(field, fn)
        if not v[field] then return end
        local success, err = pcall(fn)
        if success then v[field] = nil else errors[#errors + 1] = tostring(err) end
    end
    release("move", function() pc:SetIgnoreMoveInput(false) end)
    release("look", function() pc:SetIgnoreLookInput(false) end)
    release("mode", function() v.input:SetInputMode_GameOnly(pc, true) end)
    release("cursor", function() pc.bShowMouseCursor = v.previous_cursor end)
    if not v.mode then release("focus_claim", function() v.input:SetFocusToGameViewport() end) end
    if #errors == 0 then
        release("host", function()
            if valid(v.host) then
                v.host:RemoveFromParent()
                assert(not v.host:IsInViewport(), "Window still in viewport")
            end
        end)
    end
    if #errors == 0 then self.view = nil; return true end
    local detail = table.concat(errors, " / ")
    if v.last_error ~= detail then self:_log("Closing window (" .. tostring(reason) .. "): " .. detail) end
    v.last_error = detail
    return false, detail
end

function Panel:toggle()
    if self:is_open() then return self:close("user") end
    return self:_open(false)
end

function Panel:open_device(pc)
    if self:is_device_open() then return true end
    if self:is_open() then return false, "Close the current window first." end
    return self:_open(true, pc)
end

function Panel:_open(device, sourcePc)
    if self.view and not self:close("retry") then return false end
    local ok, err = pcall(function()
        self:update_prompt(nil)
        local pc, key, pawn = scope()
        assert(pc and pawn, "Load a playable world before opening Ship Net Automation")
        assert(not sourcePc or (valid(sourcePc) and pc:GetAddress() == sourcePc:GetAddress()), "Player controller changed")
        local gameplay = StaticFindObject("/Script/Engine.Default__GameplayStatics")
        assert(not pc.bShowMouseCursor and valid(gameplay) and not gameplay:IsGamePaused(pc),
            "Close the current game menu before opening Ship Net Automation")
        local input = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
        local layout = StaticFindObject("/Script/UMG.Default__WidgetLayoutLibrary")
        assert(valid(input) and valid(layout), "UMG library unavailable")
        local v = { pc = pc, key = key, pawn = pawn, input = input, layout = layout, device = device,
            previous_cursor = pc.bShowMouseCursor == true, by_address = {}, controls = {}, pending = {}, text_cache = {} }
        self.view = v
        v.button_class = widget_class(BUTTON)
        self:_ensure_hook()
        v.host = input:Create(pc, widget_class(HOST), pc)
        assert(valid(v.host), "Window creation failed")
        v.tree = v.host.WidgetTree
        assert(valid(v.tree) and v.tree:GetOuter():GetAddress() == v.host:GetAddress(), "Unexpected widget tree owner")
        v.root = v.tree.RootWidget
        assert(valid(v.root) and v.root:IsA("/Script/UMG.CanvasPanel") and
            v.root:GetOuter():GetAddress() == v.tree:GetAddress(), "Missing native canvas")
        self:_build()
        v.host:SetVisibility(4)
        v.host:AddToViewport(9790)
        assert(v.host:IsInViewport(), "Window failed to enter the viewport")
        self:_fit()
        self:_refresh()
        pc:SetIgnoreMoveInput(true)
        v.move = true
        pc:SetIgnoreLookInput(true)
        v.look = true
        v.cursor = true
        pc.bShowMouseCursor = true
        v.mode, v.focus_claim = true, true
        input:SetInputMode_UIOnlyEx(pc, v.focus, 0, true)
        v.focus:SetKeyboardFocus()
        v.open = true
    end)
    if not ok then
        self:close("open failure")
        self:_log(err)
        return false, tostring(err)
    end
    return true
end

function Panel:_click(record)
    if not record.active then return end
    local id = record.id
    if id == "close" then self:close("user"); return end
    if id == "device_legacy" then
        if not self.callbacks.legacyAvailable() then
            self.view.commandFeedback = "Preview storage is unavailable."
            self:refresh()
            return
        end
        local pc = self.view.pc
        if self:close("open preview storage") then
            local opened, why = self.callbacks.openLegacy(pc)
            if not opened then
                local detail = why == "uncreated" and "Preview storage is unavailable." or tostring(why or "Unable to open preview storage.")
                if self:open_device(pc) then self.view.commandFeedback = detail; self:refresh() else self:_log(detail) end
            end
        end
        return
    end
    if id == "device_auto" then
        local ok, feedback = self.callbacks.automation(not self.callbacks.device().automationEnabled)
        self.view.commandFeedback = not ok and feedback or nil
    elseif id == "device_raise" or id == "device_lower" then
        local _, feedback = self.callbacks.command(id == "device_raise" and "raise" or "lower")
        self.view.commandFeedback = feedback
    elseif id == "settings" or id == "debug" or id == "fit" then
        self.tab = id
    elseif id == "set_debug" then
        self.callbacks.action(id, not self.callbacks.state().debugEnabled)
    else
        self.callbacks.action(record.argument and "mark" or id, record.argument)
    end
    self:refresh()
end

function Panel:tick()
    local v = self.view
    if not v then return end
    if not v.open then self:close("retry"); return end
    local ok, err = pcall(function()
        local pc, key, pawn = scope()
        if not pc then self:close("controller unavailable"); return end
        if key ~= v.key then self:discard(); return end
        if pawn ~= v.pawn or not valid(v.host) or not v.host:IsInViewport() or not pc.bShowMouseCursor then
            self:close("game context changed")
            return
        end
        self:_fit()
        local pending = v.pending
        v.pending = {}
        for _, record in ipairs(pending) do
            if self.view ~= v or not v.open then break end
            self:_click(record)
        end
    end)
    if not ok then
        self:_log(err)
        self:close("window error")
    end
end

function Panel:shutdown()
    self:clear_prompt()
    self:close("unload")
    if self.hooked and type(UnregisterHook) == "function" and self.hook_pre and self.hook_post then
        local ok = pcall(UnregisterHook, CLICK, self.hook_pre, self.hook_post)
        if ok then self.hooked = false end
    end
end

return Panel
