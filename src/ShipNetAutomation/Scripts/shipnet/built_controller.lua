-- Rebind the saved cabinet after fabrication, level streaming or a world reload.
local fit=require("shipnet.fit")
local survey=require("shipnet.survey")
local observer=require("shipnet.observer")
local variants=require("shipnet.variants")
local valid=observer.valid
local Built={}
Built.__index=Built

local function same(a,b)
    return valid(a) and valid(b) and a:GetAddress()==b:GetAddress()
end

local function object(name)
    local path=name and name:match("^[^ ]+ (/.+)$")
    return path and StaticFindObject(path)
end

function Built:isBound()
    return self.runtime.built==true
end

function Built:runtimeForInteraction()
    if self:isBound() then return self.runtime end
end

local function resolved(entry)
    if not entry then return end
    local obj=StaticFindObject(entry.path)
    if valid(obj) and obj:GetAddress()==entry.address then return obj end
end

local function legacy_store(self)
    if not self:isBound() or self.runtime.variant==variants.basic then return end
    local device=self.runtime
    local actor,ship,mount=resolved(device.actorRef),resolved(device.shipRef),resolved(device.mountRef)
    if not valid(actor) or not valid(ship) or not same(actor:GetAttachParentActor(),mount) then return end
    self.legacy=self.legacy or require("shipnet.device_storage").new()
    return self.legacy,ship
end

function Built:hasLegacyStorage()
    local store,ship=legacy_store(self)
    -- Legacy lookup needs only the owning barge; creating an inventory requires
    -- an explicit request on a dev.6 preview and is never part of this route.
    return store~=nil and store:inventory(ship,ship,false)~=nil
end

function Built:openLegacyStorage(pc)
    local store,ship=legacy_store(self)
    if not store then return false,"Built controller unavailable" end
    return store:open(pc or FindFirstOf("VoyagePlayerController"),ship,ship,false)
end

function Built:reset()
    if self:isBound() then self.runtime:hide("map_change") end
    self.nextScan,self.lastError,self.legacy=0,nil,nil
end

local function discover(self)
    -- Do not survey the ship when the mod's class or a built instance is absent.
    local candidates={}
    for _,kind in ipairs(variants.all) do
        if valid(StaticFindObject(kind.carrier)) then
            for _,actor in ipairs(FindAllOf(kind.carrierName) or {}) do
                if valid(actor) and not actor:HasAnyFlags(0x30) and actor:IsA(kind.carrier) then
                    candidates[#candidates+1]=actor
                end
            end
        end
    end
    if #candidates==0 then return end
    local measured=survey.capture()
    if measured.coordinateFrame~="same_world" and measured.coordinateFrame~="ship_loaded_level" then return end
    local ship,net=object(measured.ship),object(measured.net)
    if not fit.builtMount(ship,net) then return end
    local sub=StaticFindObject("/Script/Voyage.Default__VoyagePersistentSubsystem"):GetPersistentSubsystem(ship:GetWorld())
    if not valid(sub) then return end
    local match
    for _,actor in ipairs(candidates) do
        local parent=actor:GetAttachParentActor()
        if (same(parent,net) or same(parent,ship)) and sub:IsPersistentActor(actor) then
            if match then return end
            match=actor
        end
    end
    if match then
        local report=self.runtime:bindBuilt(match,ship,net)
        if not report.visible then error(report.detail or "Could not initialize built controller",0) end
    end
end

function Built:tick()
    if self:isBound() then self.runtime:tick() end
    local now=os.time()
    if now<self.nextScan then return end
    self.nextScan=now+2
    if self:isBound() then
        local ok,ctx=pcall(observer.survey_context)
        local bound=self.runtime.shipRef
        if not ok or not ctx or not valid(ctx.ship) or (bound and ctx.ship:GetAddress()==bound.address) then return end
        self.runtime:hide("map_change")
    end
    local ok,why=pcall(discover,self)
    if not ok and why~=self.lastError and self.handlers.log then self.handlers.log("Built controller: "..tostring(why)) end
    self.lastError=not ok and why or nil
end

local function new(options)
    local self=setmetatable({runtime=fit.new(),handlers=options.handlers,nextScan=0},Built)
    self.runtime:setInteractionHandlers(self.handlers)
    return self
end

return {new=new}
