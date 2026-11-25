-- The player-box LED material draws the weight meter. A stock buoy shader pulses the red alarm.
local M = {}
local valid = require("shipnet.observer").valid
local modules = "/Game/Materials/Modules/"
local buoy_material = "/Game/AssetSets/Launch_site/Materials/M_Master_Emissive_Buoy"
local sweep_material = "/Game/AssetSets/Sockets/M_SocketInteractionVis"
local sweep_texture = "/Game/Mods/ShipNetAutomation/T_WinchCargoSweep"
local green = {R=0.052, G=0.72, B=0.181, A=1}
local yellow = {R=0.84, G=0.59, B=0.035, A=1}
local red = {R=0.78, G=0.012, B=0.008, A=1}
local black = {R=0, G=0, B=0, A=1}
local columns = 42
local tileCount, firstTile = 90, 44
local steadyGlow = 0.02
local sweepSection = 1
local normal = {X=0,Y=1,Z=0}

local function asset(package)
    local path = package .. "." .. package:match("([^/]+)$")
    local object = StaticFindObject(path)
    if not valid(object) then object = LoadAsset(path) end
    assert(valid(object), "Cargo meter asset unavailable: " .. path)
    return object
end

local function parameter(name)
    return FName(name, EFindName.FNAME_Find)
end

local function meter_color(material, color)
    -- The stock shader modulates ColorLow with game time. Only the alarm should pulse.
    material:SetVectorParameterValue(parameter("ColorLow"), black)
    material:SetVectorParameterValue(parameter("ColorFull"), color)
end

local function write_level(component, material, lit)
    -- Stock lights floor(U*ScaleX) <= ProgressLevel*ScaleX and scales ColorFull by level squared.
    -- The upper half of its UV grid keeps the brightness correction small, even at one lit cell.
    -- Choose a cutoff halfway between tile indices so GPU rounding cannot flip the last LED.
    local level = (firstTile - 0.5 + lit) / tileCount
    material:SetScalarParameterValue(parameter("Glow"), steadyGlow / (level * level))
    component:SetScalarParameterValueOnMaterials(parameter("ProgressLevel"), level)
end

function M.mount(result, actor, rootComponent, maths, bar)
    local material = asset(modules .. "MI_PogressBar_PlayerBox_LED")
    local class = StaticFindObject("/Script/ProceduralMeshComponent.ProceduralMeshComponent")
    assert(valid(class), "Cargo meter component class unavailable")
    -- This material tiles according to component scale, and reserves two tiles at each edge.
    -- Keep scale at 1. Crop UVs to one row of 42 visible cells within the actual 2.9 cm recess.
    local front = {X=(bar.minX + bar.maxX) / 2, Y=bar.Y, Z=bar.Z}
    local transform = maths:MakeTransform(front, maths:MakeRotator(0, 0, 0), {X=1, Y=1, Z=1})
    local halfWidth = (bar.maxX - bar.minX) / 2
    local halfHeight = bar.height / 2
    local vertices = {{X=-halfWidth,Y=0,Z=-halfHeight}, {X=halfWidth,Y=0,Z=-halfHeight},
                      {X=halfWidth,Y=0,Z=halfHeight}, {X=-halfWidth,Y=0,Z=halfHeight}}
    local left, right = firstTile / tileCount, (firstTile + columns) / tileCount
    local top, bottom = 44 / tileCount, 45 / tileCount
    local uv = {{X=left,Y=bottom}, {X=right,Y=bottom}, {X=right,Y=top}, {X=left,Y=top}}
    local component = actor:AddComponentByClass(class, false, transform, true)
    assert(valid(component), "Could not create cargo meter")
    local ok, instance = pcall(function()
        component:SetMobility(2)
        component:SetCollisionEnabled(0)
        component:SetGenerateOverlapEvents(false)
        actor:FinishAddComponent(component, false, transform)
        local parent = component:GetAttachParent()
        assert(valid(parent) and parent:GetAddress() == rootComponent:GetAddress(), "Unexpected cargo meter parent")
        component:CreateMeshSection_LinearColor(0, vertices, {0,1,2,0,2,3}, {normal,normal,normal,normal},
            uv, {}, {}, {}, {}, {}, false, false)
        assert(component:GetNumSections() == 1, "Could not create cargo meter face")
        local mid = component:CreateDynamicMaterialInstance(0, material, parameter("None"))
        assert(valid(mid), "Could not create cargo LED material")
        meter_color(mid, green)
        mid:SetScalarParameterValue(parameter("ScaleX"), tileCount)
        write_level(component, mid, 0)
        return mid
    end)
    if not ok then
        component:K2_DestroyComponent(actor)
        error(instance)
    end
    result.components[#result.components + 1] = component
    result.fill = component
    result.meterMaterial = instance
    result.meterColor = green
    result.meterHalfWidth, result.meterHalfHeight = halfWidth, halfHeight
    result.sweepColumns = 0
    result.fillFraction = 0
    result.meterAlarmActive = false
    result.meterUnloading = false
end

local function write_sweep(result, lit)
    local component = result.fill
    if lit == 0 then
        component:SetMeshSectionVisible(sweepSection, false)
        return
    end

    -- Each overlay quad sits inside a lit LED. The atlas row leaves room for
    -- the tail to exit on the right before another sweep enters on the left.
    local vertices, indices, normals, uv = {}, {}, {}, {}
    local width = 2 * result.meterHalfWidth / columns
    local height = result.meterHalfHeight * .60
    local period = lit + 6
    local v = ((lit - 1) * 4 + 2) / 256
    for i = 0, lit - 1 do
        local left = -result.meterHalfWidth + width * (i + .16)
        local right = -result.meterHalfWidth + width * (i + .84)
        local u0, u1 = (i + .16) / period, (i + .84) / period
        local n = #vertices
        vertices[n+1], vertices[n+2] = {X=left,Y=.035,Z=-height}, {X=right,Y=.035,Z=-height}
        vertices[n+3], vertices[n+4] = {X=right,Y=.035,Z=height}, {X=left,Y=.035,Z=height}
        uv[n+1], uv[n+2], uv[n+3], uv[n+4] = {X=u0,Y=v}, {X=u1,Y=v}, {X=u1,Y=v}, {X=u0,Y=v}
        for j = n + 1, n + 4 do normals[j] = normal end
        local k = #indices
        indices[k+1], indices[k+2], indices[k+3] = n, n+1, n+2
        indices[k+4], indices[k+5], indices[k+6] = n, n+2, n+3
    end
    component:CreateMeshSection_LinearColor(sweepSection, vertices, indices, normals, uv, {}, {}, {}, {}, {}, false, false)
    if not valid(result.sweepMaterial) then
        local mid = component:CreateDynamicMaterialInstance(sweepSection, asset(sweep_material), parameter("None"))
        assert(valid(mid), "Could not create cargo sweep material")
        local texture, input = asset(sweep_texture), parameter("Texture")
        mid:SetTextureParameterValue(input, texture)
        local bound = mid:K2_GetTextureParameterValue(input)
        assert(valid(bound) and bound:GetAddress() == texture:GetAddress(), "Cargo sweep texture did not bind")
        mid:SetVectorParameterValue(parameter("Color"), {R=.98,G=.76,B=.18,A=1})
        mid:SetScalarParameterValue(parameter("Emissive"), 10)
        mid:SetScalarParameterValue(parameter("Panning"), 1)
        mid:SetScalarParameterValue(parameter("USpeed"), -.9)
        result.sweepMaterial = mid
    end
    component:SetMeshSectionVisible(sweepSection, true)
end

local function set_sweep(result, lit)
    if result.sweepColumns == lit or result.meterSweepError then return end
    local ok, reason = pcall(write_sweep, result, lit)
    if not ok then
        pcall(function() result.fill:SetMeshSectionVisible(sweepSection, false) end)
        result.meterSweepError = tostring(reason)
        return
    end
    result.sweepColumns = lit
end

function M.blinkMaterial(component, tint, minimum, maximum)
    local mid = component:CreateDynamicMaterialInstance(0, asset(buoy_material), parameter("None"))
    assert(valid(mid), "Could not create alarm material")
    mid:SetVectorParameterValue(parameter("Emissive Color"), tint or red)
    mid:SetVectorParameterValue(parameter("Emissive Color Empty"), tint or red)
    mid:SetScalarParameterValue(parameter("IsEmpty"), 0)
    mid:SetScalarParameterValue(parameter("EmissivePowerMin"), minimum or 0.08)
    mid:SetScalarParameterValue(parameter("EmissivePowerMax"), maximum or 2)
    -- This stock shader applies sin(2*pi*Time*BlinkingSpeed) on the GPU.
    mid:SetScalarParameterValue(parameter("BlinkingSpeed"), 1 / 1.3)
    return mid
end

local function show_alarm(result)
    local cells = result.alarmCells
    assert(valid(cells), "Cargo alarm cells unavailable")
    if not valid(result.meterAlarmMaterial) then
        result.meterAlarmMaterial = M.blinkMaterial(cells)
    end
    cells:SetVisibility(true, false)
    result.fill:SetVisibility(false, false)
end

function M.setFill(result, fraction, alarm, unloading)
    return pcall(function()
        assert(result and result.ok and valid(result.fill), "Cargo meter unavailable")
        assert(type(fraction) == "number" and math.abs(fraction) < math.huge, "Expected a finite weight fraction")
        local clamped = math.max(0, math.min(1, fraction))
        local alarmActive = alarm == true or clamped == 1
        local loadingActive = unloading == true and not alarmActive
        if result.fillFraction == clamped and result.meterAlarmActive == alarmActive
            and result.meterUnloading == loadingActive then return end
        local alarmError = result.meterAlarmError
        if alarmActive and not result.meterAlarmActive then
            local ok, reason = pcall(show_alarm, result)
            if not ok then
                -- Use steady red if the pulsing material is unavailable.
                if valid(result.alarmCells) then result.alarmCells:SetVisibility(false, false) end
                result.fill:SetVisibility(true, false)
                alarmError = tostring(reason)
            end
        elseif not alarmActive and result.meterAlarmActive then
            if valid(result.alarmCells) then result.alarmCells:SetVisibility(false, false) end
            result.fill:SetVisibility(true, false)
            alarmError = nil
        end
        local lit = alarmError and columns or math.floor(columns * clamped)
        local lastLit = result.meterAlarmError and columns or math.floor(columns * result.fillFraction)
        if lit ~= lastLit then write_level(result.fill, result.meterMaterial, lit) end
        local color = alarmError and red or loadingActive and yellow or green
        if result.meterColor ~= color then
            meter_color(result.meterMaterial, color)
            result.meterColor = color
        end
        result.fillFraction, result.meterAlarmActive, result.meterAlarmError = clamped, alarmActive, alarmError
        result.meterUnloading = loadingActive
        set_sweep(result, loadingActive and lit or 0)
    end)
end

return M
