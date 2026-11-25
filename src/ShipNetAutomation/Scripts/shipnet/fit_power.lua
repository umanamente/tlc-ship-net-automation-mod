-- The preview owns its temporary components. Finished cabinets use the named
-- stock components on their Blueprint so Voyage can restore connected cables.
local M = {}
local Power = {}
Power.__index = Power
local valid = require("shipnet.observer").valid
local variants = require("shipnet.variants")
local VIEW = "/Script/Voyage.VoyageModuleSocketViewComponent"
local MODULE = "/Script/Voyage.VoyageModuleComponent"
local DATA = "/Game/Data/Assets/ModuleSockets/DA_Socket_ElectricData.DA_Socket_ElectricData"
local MESH = "/Game/AssetSets/Sockets/SM_Socket_Electrical_Output.SM_Socket_Electrical_Output"
local MATH = "/Script/Engine.Default__KismetMathLibrary"
local SYSTEM = "/Script/Engine.Default__KismetSystemLibrary"
local INPUT, ELECTRICITY = 1, 0
local ORIGIN = {X=-68.4, Y=-0.5, Z=29.8}
-- Stock electrical inputs expose mesh +Y on the module exterior. The data
-- asset maps that face to socket -Z. Keep the native cable frame and the
-- render mesh together at the adapter. Its local +Z points toward the tip
-- of the lightning symbol and the top vertex of the upright triangle.
local ROTATION = {Pitch=0, Yaw=90, Roll=-90}
local SCALE = {X=1, Y=1, Z=1}

-- Rotator.pitch in the shipping reflection map is lowercase. Passing a Lua
-- table with Pitch loses that field; MakeRotator returns a native FRotator.
local function native_rotation(maths, rot)
    return maths:MakeRotator(rot.Roll, rot.Pitch, rot.Yaw)
end

local function read(fn)
    local ok, value = pcall(fn)
    if ok then return value end
end

local function same(a, b)
    return valid(a) and valid(b) and a:GetAddress() == b:GetAddress()
end

local function path(obj)
    if valid(obj) then return obj:GetFullName():match("^[^ ]+ (/.+)$") end
end

local function ref(obj)
    return {path=assert(path(obj), "missing object path"), address=obj:GetAddress()}
end

local function resolve(id)
    if id then
        local obj = StaticFindObject(id.path)
        if valid(obj) and obj:GetAddress() == id.address then return obj end
    end
end

local function owned(actor, id)
    local obj = resolve(id)
    if obj and same(obj:GetOwner(), actor) then return obj end
end

local function asset(name)
    local obj = StaticFindObject(name)
    if not valid(obj) then obj = LoadAsset(name) end
    assert(valid(obj) and path(obj) == name, "asset unavailable: " .. name)
    return obj
end

local function found(name)
    local obj = StaticFindObject(name)
    assert(valid(obj), "reflection unavailable: " .. name)
    return obj
end

local function begin(self, actor, key, cls, transform)
    local obj = actor:AddComponentByClass(found(cls), false, transform, true)
    assert(valid(obj) and same(obj:GetOwner(), actor), "could not add " .. cls)
    self[key] = ref(obj)
    return obj
end

-- This is the actual module socket array (TObjectPtr); checking membership
-- distinguishes a socket with an owner pointer from a registered socket.
local function listed(module, socket)
    return read(function()
        local matched = false
        module.Sockets:ForEach(function(_, wrapped)
            local object = valid(wrapped) and wrapped or wrapped:get()
            if same(object, socket) then matched=true; return true end
        end)
        return matched
    end)
end

local function known_mesh(component)
    if valid(component) then return path(read(function() return component.StaticMesh end)) end
end

local function finite_vector(v)
    local p = {X=v.X,Y=v.Y,Z=v.Z}
    for _,axis in ipairs({"X","Y","Z"}) do
        local n = p[axis]
        assert(type(n) == "number" and n == n and math.abs(n) < math.huge, "invalid mesh vector")
    end
    return p
end

local function measured_axis(maths, component, actorFrame, axis)
    local frame = component:K2_GetComponentToWorld()
    local function point(p)
        return finite_vector(maths:InverseTransformLocation(actorFrame,maths:TransformLocation(frame,p)))
    end
    local origin, tip = point({X=0,Y=0,Z=0}), point(axis)
    local x,y,z = tip.X-origin.X,tip.Y-origin.Y,tip.Z-origin.Z
    local len = math.sqrt(x*x+y*y+z*z)
    assert(len > 1e-8, "zero-length component axis")
    return {X=x/len,Y=y/len,Z=z/len}, origin, point
end

-- Use the rendered child, not the socket collision box: ReloadMesh may apply
-- its own rotation/translation. The native electrical mesh is thin on Y.
local function mesh_fit(actor, mesh, basic)
    local result = {status="unavailable"}
    local ok, err = pcall(function()
        local maths = found(MATH)
        local actorFrame = actor:GetTransform()
        local axis, origin, local_point = measured_axis(maths, mesh, actorFrame, {X=0,Y=1,Z=0})
        result.originLocalCm = origin
        result.shortAxisLocal = axis
        local mark = measured_axis(maths, mesh, actorFrame, {X=0,Y=0,Z=1})
        result.markUpLocal = mark
        result.markUpErrorDeg = math.deg(math.acos(math.max(-1,math.min(1,mark.Z))))
        -- abs(dot(axis, cabinet's -X face normal)); zero means parallel faces.
        local face = basic and axis.Y or -axis.X
        result.planeErrorDeg = math.deg(math.acos(math.min(1,math.abs(face))))
        -- The plug receptacle is on mesh +Y, the blank blue cap on -Y.
        -- Report the signed face separately: both sides give zero plane error.
        result.matingFaceErrorDeg = math.deg(math.acos(math.max(-1,math.min(1,face))))
        result.status = "axis_only"
        local bounds = mesh.StaticMesh:GetBounds()
        local center = finite_vector(bounds.Origin)
        result.centerLocalCm = local_point(center)
        local halfDepth = finite_vector(bounds.BoxExtent).Y
        result.matingSideBoundLocalCm = local_point({X=center.X,Y=center.Y+halfDepth,Z=center.Z})
        result.backSideBoundLocalCm = local_point({X=center.X,Y=center.Y-halfDepth,Z=center.Z})
        local function depth(p)
            return basic and p.Y-origin.Y or origin.X-p.X
        end
        result.matingSideBeyondPivotCm = depth(result.matingSideBoundLocalCm)
        result.backSideBeyondPivotCm = depth(result.backSideBoundLocalCm)
        result.status = "measured"
    end)
    if not ok then result.detail = tostring(err) end
    return result
end

local function inspect(self, actor)
    local row = {status="no_preview", socketData=DATA, expectedMesh=MESH}
    if not valid(actor) or not self.actor or actor:GetAddress() ~= self.actor.address
        or path(actor) ~= self.actor.path then return row end
    row.localCm, row.localRotationDeg = self.location, self.rotation
    row.detail = self.failure
    local module, socket = owned(actor, self.module), owned(actor, self.socket)
    if module then
        row.module = path(module)
        row.moduleInitialized = read(function() return module.bHasInitialized end)
        row.moduleSubsystem = path(read(function() return module.ModuleSubsystem end))
        row.hasPower = read(function() return module:HasPower() end)
        row.electricity = read(function() return module:GetResourceAmount(ELECTRICITY) end)
    end
    if socket then
        row.socket = path(socket)
        local native = read(function() return socket.mesh end)
        row.socketMesh = known_mesh(native)
        if row.socketMesh == MESH then row.renderedMeshFit = mesh_fit(actor, native, self.basic) end
        row.socketDataApplied = self.dataApplied == true
        row.portDirection = read(function() return socket.Port.Type end)
        row.resourceType = read(function() return socket.Port.ResourceType end)
        row.socketCollision = read(function() return socket:GetCollisionEnabled() end)
        row.socketFrameUpLocal = read(function()
            return measured_axis(found(MATH), socket, actor:GetTransform(), {X=0,Y=0,Z=1})
        end)
        local up = row.socketFrameUpLocal
        if up then
            row.cableFaceLocal = {X=-up.X,Y=-up.Y,Z=-up.Z}
            row.cableFaceErrorDeg = math.deg(math.acos(math.max(-1,math.min(1,self.basic and -up.Y or up.X))))
        end
        local collision = read(function() return socket.SocketCollisionBox end)
        if valid(collision) then
            row.hitBox = path(collision)
            row.hitBoxUpLocal = read(function()
                return measured_axis(found(MATH), collision, actor:GetTransform(), {X=0,Y=0,Z=1})
            end)
        end
        row.socketAvailable = read(function() return socket:IsSocketAvailable() end)
        row.transferPerSecond = read(function() return socket.ResourceTransferPerSecond end)
        row.worldCm = read(function()
            local v = socket:K2_GetComponentLocation()
            return {X=v.X, Y=v.Y, Z=v.Z}
        end)
        row.socketOwner = path(read(function() return socket:GetModule() end))
        row.registered = false
        if module and row.socketOwner == row.module then row.registered = listed(module, socket) end
        row.connected = read(function() return socket:IsSocketConnected() end)
        row.cablePresent = read(function() return socket:IsSocketConnectedOrHasCable() end)
        row.hasInputConnection = read(function() return socket:HasInputConnection() end)
        row.connectedSocket = path(read(function() return socket:GetConnectedSocket() end))
    else
        row.registered = false
    end
    local fallback = owned(actor, self.fallback)
    if fallback then
        row.visualFallbackMesh = known_mesh(fallback)
        if row.visualFallbackMesh == MESH and not row.renderedMeshFit then
            row.renderedMeshFit = mesh_fit(actor, fallback)
        end
    end
    row.visual = row.socketMesh == MESH or row.visualFallbackMesh == MESH
    if row.registered and row.socketDataApplied and row.portDirection == INPUT
        and row.resourceType == ELECTRICITY and row.socketMesh == MESH then
        row.status = "native_input"
    elseif row.visualFallbackMesh == MESH then row.status = "visual_only"
    elseif socket then row.status = self.failure and "socket_setup_incomplete" or "waiting_for_socket"
    else row.status = "socket_unavailable" end
    return row
end

function Power:inspect(actor)
    local ok, row = pcall(inspect, self, actor)
    if ok then return row end
    return {status="socket_read_error", detail=tostring(row)}
end

local function named_component(actor, name, class)
    local component=read(function() return actor[name] end)
    if not valid(component) then component=StaticFindObject(path(actor).."."..name) end
    if valid(component) and same(component:GetOwner(),actor) and component:IsA(class) then
        return component
    end
end

-- The initial cabinets saved Health=0 while indestructible. Voyage checks
-- this saved current value independently of the item's authored maximum.
local function restore_receiver_health(actor, module, basic)
    local component = actor[basic and "DestructibleObjectComponent" or "VoyageDestructibleObject"]
    if not valid(component) or component.bIsDestructible ~= false then return end
    local currentMaximum = module:GetMaxDurability()
    if currentMaximum > 0 and component.Health ~= 0 then return end
    local item
    if basic then item=module.ItemAsset else item=actor.ContainerItem end
    if not same(component:GetOwner(), actor) or not same(module.DestructibleObjectReference, component)
        or not valid(item) or path(item) ~= (basic and variants.basic.item or variants.advanced.item)
        or item.bIsDestructible ~= false or actor:ActorHasTag(FName("Recycling")) then return end
    local settings = item.DestructibleObjectProperties
    local maximum = settings.Health
    if type(maximum) ~= "number" or maximum <= 0 then return end
    if currentMaximum == 0 then component.DestructibleObjectProperties.Health = maximum end
    if module:GetMaxDurability() == maximum and module:GetDurability() == 0 then
        component:OverrideHealth(maximum)
    end
end

-- An existing save constructs the new SCS socket with the same name as a new
-- cabinet. Wait for native initialization and preserve the restored endpoint.
function Power:bindBuilt(actor, variant)
    if not valid(actor) then return {status="no_input"} end
    local basic=variant==variants.basic
    local module=named_component(actor,basic and "ModuleComponent" or "VoyageModule",MODULE)
    local socket=named_component(actor,"WinchPowerInlet",VIEW)
    if not module or not socket or not module.bHasInitialized then return {status="waiting_for_socket"} end
    self.actor,self.module,self.socket=ref(actor),ref(module),ref(socket)
    self.basic=basic
    self.location,self.rotation=ORIGIN,ROTATION
    if self.basic then
        self.location=variant.geometry.anchors.inlet
        self.rotation={Pitch=0,Yaw=0,Roll=-90}
    end
    local ok,err=pcall(function()
        restore_receiver_health(actor,module,self.basic)
        local system=found(SYSTEM)
        local data=system:Conv_SoftObjectReferenceToObject(socket.DataAsset)
        if not valid(data) then
            asset(DATA)
            data=system:Conv_SoftObjectReferenceToObject(socket.DataAsset)
        end
        self.dataApplied=path(data)==DATA
        if not self.dataApplied then return end
        local owner=socket:GetModule()
        if valid(owner) and not same(owner,module) then error("Native socket belongs to another module") end
        if not valid(owner) then
            if socket:IsSocketConnectedOrHasCable() then return end
            socket:InitializeSockets(module)
        end
        if same(socket:GetModule(),module) and listed(module,socket)==false then module:AddExternalSocket(socket) end
        if not known_mesh(socket.mesh) and not socket:IsSocketConnectedOrHasCable() then
            asset(MESH)
            socket:ReloadMesh()
        end
    end)
    self.failure=not ok and tostring(err) or nil
    local row=self:inspect(actor)
    self.nativeReady=row.status=="native_input"
    return row
end

function Power:builtStatus(actor)
    local module,socket=owned(actor,self.module),owned(actor,self.socket)
    if not self.nativeReady or not module or not socket or not same(socket:GetModule(),module)
        or not listed(module,socket) then
        return {status="waiting_for_socket"}
    end
    restore_receiver_health(actor,module,self.basic)
    return {status="native_input",socket=self.socket.path,connected=socket:IsSocketConnected(),
        cablePresent=socket:IsSocketConnectedOrHasCable(),hasPower=module:HasPower(),
        electricity=module:GetResourceAmount(ELECTRICITY)}
end

local function install(self, actor)
    local mathlib = found(MATH)
    local identity = mathlib:MakeTransform({X=0,Y=0,Z=0}, {Pitch=0,Yaw=0,Roll=0}, SCALE)
    local transform = mathlib:MakeTransform(self.location, native_rotation(mathlib, self.rotation), SCALE)
    local data = asset(DATA)
    asset(MESH) -- Preload before native ReloadMesh; also verifies the installed asset name.
    local system = found(SYSTEM)
    local soft = system:Conv_ObjectToSoftObjectReference(data)
    local module = begin(self, actor, "module", MODULE, identity)
    module.bIsMasterModule = true
    module.bRegisterModule = true
    module.bExcludeFromSharedGroups = true
    local config = module.ConfigData
    config.bShareResources, config.bShareResourcesOff = false, false
    config.bAcceptResourceOffer, config.bAcceptResourceOfferOff = true, true
    config.ModuleResourceType = ELECTRICITY
    config.MaxResourceAmount, config.DefaultResourceAmount = 1.0, 0.0
    config.ResourceBandwidthInput, config.ResourceBandwidthOutput = 1.0, 0.0
    actor:FinishAddComponent(module, false, identity)
    -- A finite isolated receiver lets a tester observe transfer with no
    -- automatic switching of the winch and no perpetual test load.
    module:SetupNewResource(ELECTRICITY, 1.0, 1.0, 0.0, INPUT, false)
    local socket = begin(self, actor, "socket", VIEW, transform)
    socket.bAutoInitialize = false
    socket.DataAsset = soft
    assert(same(system:Conv_SoftObjectReferenceToObject(socket.DataAsset), data),
        "native electrical data reference did not round-trip")
    self.dataApplied = true
    socket.Port.DefaultDirection, socket.Port.Type, socket.Port.ResourceType = INPUT, INPUT, ELECTRICITY
    socket.Port.Bandwidth.Input, socket.Port.Bandwidth.Output = 1.0, 0.0
    socket:SetMobility(2)
    self.registrationAttempted = true
    actor:FinishAddComponent(socket, false, transform)
    socket:InitializeSockets(module)
    if listed(module, socket) == false then module:AddExternalSocket(socket) end
    socket:ReloadMesh()
end

local function visual_only(self, actor)
    local mathlib = found(MATH)
    local mesh = asset(MESH)
    local orient = mathlib:ComposeRotators(mathlib:MakeRotator(90,0,0), native_rotation(mathlib, self.rotation))
    local transform = mathlib:MakeTransform(self.location, orient, SCALE)
    local component = begin(self, actor, "fallback", "/Script/Engine.StaticMeshComponent", transform)
    component:SetMobility(2)
    component:SetCollisionEnabled(0)
    assert(component:SetStaticMesh(mesh) ~= false, "could not set fallback stock mesh")
    actor:FinishAddComponent(component, false, transform)
end

function Power:mount(actor, location, rotation)
    if not valid(actor) then return {status="no_preview"} end
    if self.actor then return self:inspect(actor) end
    self.actor = ref(actor)
    self.location, self.rotation = location or ORIGIN, rotation or ROTATION
    local ok, detail = pcall(install, self, actor)
    if not ok then
        self.failure = tostring(detail)
        -- No second visual is added alongside a registered or asynchronously
        -- loading view. An unregistered, unfinished component is actor-owned.
        if not self.registrationAttempted then
            local shown, err = pcall(visual_only, self, actor)
            if not shown then self.failure = self.failure .. " | visual: " .. tostring(err) end
        end
    end
    return self:inspect(actor)
end

function Power:before_remove(actor)
    if not self.registrationAttempted then return {allowed=true, status="clear"} end
    local row = self:inspect(actor)
    if row.cablePresent == true or row.connected == true or row.hasInputConnection == true
        or row.connectedSocket then return {allowed=false, status="detach_cable_first"} end
    if row.cablePresent ~= false then return {allowed=false, status="connection_unknown"} end
    return {allowed=true, status="clear"}
end

function Power:reset()
    self.basic=nil
    self.actor, self.module, self.socket, self.fallback = nil, nil, nil, nil
    self.location, self.rotation, self.dataApplied, self.failure, self.registrationAttempted, self.nativeReady = nil, nil, nil, nil, nil, nil
end

function M.new() return setmetatable({}, Power) end
return M
