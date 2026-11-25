-- Observe one local build action at a time. Keep only Lua values across callbacks.
local valid=require("shipnet.observer").valid
local variants=require("shipnet.variants")
local Trace={}
Trace.__index=Trace

function Trace.name(object)
    if type(object)=="string" then return object end
    if not valid(object) then return "<none>" end
    return object:GetFullName()
end

function Trace.text(value)
    if type(value)=="string" then return value end
    return value and value:ToString() or ""
end

local function write(self,attempt,message)
    self.log(string.format("Build #%d [%s] %s",attempt.id,attempt.title,message))
end

function Trace:reset()
    local a=self.attempt
    if a and not a.dispatched then
        write(self,a,"no Fabricate action observed after input")
    end
    self.attempt=nil
end

function Trace:tick()
    if self.attempt and os.time()>=self.attempt.expires then self:reset() end
end

function Trace:start(title)
    self:reset()
    self.serial=self.serial+1
    self.attempt={id=self.serial,title=title,expires=os.time()+3}
    return self.attempt
end

local function disabledReason(builder)
    local reason=Trace.text(builder.FailureReason)
    return reason~="" and reason or "game supplied no placement failure text"
end

function Trace:pressed(controls,builderClass,describeMount)
    local pc=FindFirstOf("VoyagePlayerController")
    if not valid(pc) or not pc:IsLocalController() or not valid(pc.Pawn) then return end
    local owner=controls:GetOwner()
    if not valid(owner) or (owner:GetAddress()~=pc.Pawn:GetAddress() and owner:GetAddress()~=pc:GetAddress()) then return end
    local builder=pc.Pawn:GetComponentByClass(StaticFindObject(builderClass))
    local kind=valid(builder) and variants.forItem(builder.CurrentItem)
    if not kind then return end
    local a=self:start(kind.title)
    a.builder=builder:GetAddress()
    a.source=valid(builder.SourceActor)
    write(self,a,string.format("input pressed: CanPlace=%s WaitingForConfirmation=%s source=%s factory=%s",
        tostring(builder.CanPlace),tostring(builder.WaitingForConfirmation),Trace.name(builder.SourceActor),
        Trace.name(builder["Fabricator Factory"])))
    if builder.CanPlace==false then
        write(self,a,"Build action disabled: "..disabledReason(builder))
        local detail=describeMount(builder,pc)
        if detail then write(self,a,"mount recheck: "..detail) end
    end
end

function Trace:validation(item,allowed,reason)
    local kind=variants.forItem(item)
    local a=self.attempt
    if not kind and not a and allowed then return end
    if not a or (kind and a.title~=kind.title) then a=self:start(kind and kind.title or Trace.name(item)) end
    a.dispatched=true
    a.allowed=allowed
    write(self,a,allowed and "winch validation passed" or ("winch validation rejected: "..tostring(reason)))
end

function Trace:site(generator,site,genClass)
    if not generator:IsA(genClass) then return end
    local a=self.attempt
    if not a then
        local builder=generator.PlacementComponent
        local kind=valid(builder) and variants.forItem(builder.CurrentItem)
        if not kind then return end
        a=self:start(kind.title)
    end
    a.dispatched=true
    a.reportedSite=true
    if valid(site) then write(self,a,"game returned construction site: "..Trace.name(site))
    else write(self,a,"game returned no construction site") end
end

-- Blueprint hooks in the pinned UE4SS build run after the Blueprint body. Its
-- validator and OnFabricate have therefore already reported on this same action.
function Trace:action(builder)
    local a=self.attempt
    local kind=variants.forItem(builder.CurrentItem)
    if a and a.builder and a.builder~=builder:GetAddress() then return end
    if not kind and not (a and a.builder==builder:GetAddress()) then return end
    if not a or (kind and kind.title~=a.title) then a=self:start(kind.title) end
    a.dispatched=true
    local result="Fabricate action handled"
    if not a.reportedSite and a.allowed==nil then
        if builder.WaitingForConfirmation then result="Fabricate: waiting for another confirmation"
        elseif builder.CanPlace==false and valid(builder.CurrentItem) then result="Fabricate: placement disabled: "..disabledReason(builder)
        elseif a.source and not valid(builder.CurrentItem) then result="Fabricate: existing source actor placement ended"
        else result="Fabricate: no validator or construction-site callback observed" end
    end
    write(self,a,result)
    self.attempt=nil
end

function Trace:register(hook,builderClass,genClass,socketClass,describeMount)
    -- Diagnostics must not prevent registration of the actual placement hooks.
    local function observe(path,callback,post)
        local function read(...)
            local ok,err=pcall(callback,...)
            if not ok then self.log("Build trace "..path..": "..tostring(err)) end
        end
        local ok,err
        if post then ok,err=pcall(hook,path,function() end,read)
        else ok,err=pcall(hook,path,read) end
        if not ok then self.log("Build trace hook unavailable: "..path.." "..tostring(err)) end
    end
    -- FabricatePlacement binds IAV_Interact.OnStarted. The primary mouse action rotates.
    observe("/Script/Voyage.VoyageCharacterInputControlsComponent:OnInteractOneStarted",function(ctx)
        self:pressed(ctx:get(),builderClass,describeMount)
    end)
    observe("/Script/Voyage.VoyagePlayerController:OnPlayerInteraction",function(ctx,target,part)
        local a=self.attempt
        if a and not a.dispatched and ctx:get():IsLocalController() then
            write(self,a,"game routed interaction to "..Trace.name(target:get()).." component="..Trace.name(part:get()))
        end
    end)
    observe(builderClass..":Fabricate",function(ctx) self:action(ctx:get()) end)
    observe(socketClass..":OnFabricate",function(ctx,site) self:site(ctx:get(),site:get(),genClass) end)
    -- Native post-hook arguments on 527a483b are (context, return value, inputs...).
    observe("/Script/Voyage.VoyageFabricatorComponent:CanFabricateItem",function(ctx,result,item)
        local a=self.attempt
        if not a or not a.allowed or a.reportedSite then return end
        local kind=variants.forItem(item:get())
        local component=ctx:get()
        if kind and kind.title==a.title and valid(component) then
            local owner=component:GetOwner()
            if valid(owner) and owner:IsA("/Game/Blueprints/Fabrication/BP_Location_Fabricator.BP_Location_Fabricator_C") then
                write(self,a,"stock material check CanFabricateItem="..tostring(result:get()).." on "..Trace.name(owner))
            end
        end
    end,true)
end

return {name=Trace.name,text=Trace.text,new=function(log) return setmetatable({log=log,serial=0},Trace) end}
