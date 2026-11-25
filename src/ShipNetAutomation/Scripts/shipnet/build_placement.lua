-- The ordinary fabrication component owns the ghost, materials, progress and payment.
-- Supply the generator result only for this recipe on its measured winch.
local fit = require("shipnet.fit")
local catalog = require("shipnet.build_catalog")
local observer = require("shipnet.observer")
local survey = require("shipnet.survey")
local variants = require("shipnet.variants")
local buildTrace = require("shipnet.build_trace")
local valid = observer.valid
local Placement = {}
Placement.__index = Placement

local GEN = "/Game/Mods/ShipNetAutomation/BP_WinchMountGenerator.BP_WinchMountGenerator_C"
local NET = "/Game/Blueprints/Modules/Utility/Boat/BP_Module_Fishing.BP_Module_Fishing_C"
local SOCKET = "/Game/Blueprints/Fabrication/BP_CraftingLocationGenerator_SocketMatch.BP_CraftingLocationGenerator_SocketMatch_C"
local SITE = "/Game/Blueprints/Fabrication/BP_Location_Fabricator.BP_Location_Fabricator_C"
local BUILDER = "/Game/Blueprints/Fabrication/BP_FabricationPlacementComponent.BP_FabricationPlacementComponent_C"
local FACTORY = "/Game/Mods/ShipNetAutomation/BP_WinchBuildFactory.BP_WinchBuildFactory_C"
local MATH = "/Script/Engine.Default__KismetMathLibrary"
local SYSTEM = "/Script/Engine.Default__KismetSystemLibrary"
local ONE = {X=1,Y=1,Z=1}
local ZERO = {R=0,G=0,B=0,A=0}

local function same(a,b)
    return valid(a) and valid(b) and a:GetAddress()==b:GetAddress()
end

local function stock_pose(gen, maths)
    return maths:MakeTransform(gen.PlacementLocation,gen.PlacementRotation,ONE)
end

local function rejected(reason, pose)
    return {bSuccess=false, Location=pose, FailureReason=FText(reason)}
end

local function winch_of(actor)
    for _=1,3 do
        if not valid(actor) then return end
        if actor:IsA(NET) then return actor end
        local parent=actor:GetParentActor()
        actor=valid(parent) and parent or actor:GetAttachParentActor()
    end
end

-- The barge owns a streamed level. Its winch need not have a direct Actor owner.
local function barge_for(self,pc,net)
    local ctx=observer.survey_context()
    if not ctx or not valid(ctx.ship) or not same(ctx.pawn,pc.Pawn) then return end
    local ship=ctx.ship
    if self.ship~=ship:GetAddress() or self.net~=net:GetAddress() then
        local current=survey.capture()
        if (current.coordinateFrame~="same_world" and current.coordinateFrame~="ship_loaded_level")
            or current.ship~=ship:GetFullName() or current.net~=net:GetFullName() then return end
        self.ship,self.net=ship:GetAddress(),net:GetAddress()
    end
    return ship
end

local function occupies(actor, ship, net, pos, constructionSite)
    if not valid(actor) or actor:HasAnyFlags(0x30) or actor:IsActorBeingDestroyed() then return false end
    if constructionSite then
        -- The fabrication site can exist before the game attaches it to the ship.
        if not same(actor:GetWorld(),ship:GetWorld()) then return false end
    else
        -- The stock builder also instantiates our cabinet for its unattached preview.
        local parent=actor:GetAttachParentActor()
        if same(parent,net) then return true end
        if not same(parent,ship) then return false end
    end
    local p=actor:K2_GetActorLocation()
    return (p.X-pos.X)^2+(p.Y-pos.Y)^2+(p.Z-pos.Z)^2<55^2
end

local function taken(ship, net, pos)
    for _,kind in ipairs(variants.all) do
        for _,actor in ipairs(FindAllOf(kind.carrierName) or {}) do
            if occupies(actor,ship,net,pos,false) and actor:IsA(kind.carrier) then return actor end
        end
    end
    for _,site in ipairs(FindAllOf("BP_Location_Fabricator_C") or {}) do
        if occupies(site,ship,net,pos,true) and variants.forItem(site.FabricationItemOrPattern) then return site end
    end
    return false
end

local function blocked_box(pc,center,orientation,extent,ignore,placement)
    local hits={}
    local found=StaticFindObject(SYSTEM):BoxTraceMultiForObjects(pc,center,center,extent,
        orientation,{0,1,2,3,4,5},false,ignore,0,hits,true,ZERO,ZERO,0)
    if not found then return false end
    local list=hits.OutHits or hits
    local seen,blocked=false,false
    local function inspect(hit)
        local result=hit.get and hit:get() or hit
        local c=result.Component:Get()
        seen=true
        if not valid(c) then blocked=blocked or "trace returned an invalid component"
        elseif not same(c:GetOwner(),placement:GetOwner()) then blocked=c end
    end
    if type(list.ForEach)=="function" then list:ForEach(function(_,hit) inspect(hit) end)
    else for _,hit in ipairs(list) do inspect(hit) end end
    return blocked or (not seen and "trace returned no readable hits")
end

local function obstructed(pc, ship, net, frame, maths, placement, kind)
    local ignore={pc.Pawn,ship,net}
    for _,key in ipairs({"SwitchChildActor","Container"}) do
        local part=net[key]
        if valid(part) and valid(part.ChildActor) then ignore[#ignore+1]=part.ChildActor end
    end
    if valid(placement.SourceActor) then ignore[#ignore+1]=placement.SourceActor end
    local orientation=maths:Quat_Rotator(frame.Rotation)
    if kind.manualUnload then
        local panel=maths:TransformLocation(frame,{X=133,Y=109,Z=-24})
        local sleeve=maths:TransformLocation(frame,{X=75,Y=105,Z=24})
        local drive=maths:TransformLocation(frame,{X=96,Y=101,Z=60})
        return blocked_box(pc,panel,orientation,{X=67,Y=12,Z=17},ignore,placement)
            or blocked_box(pc,sleeve,orientation,{X=9,Y=14,Z=32},ignore,placement)
            or blocked_box(pc,drive,orientation,{X=32,Y=9,Z=10},ignore,placement)
    end
    -- The cabinet and outboard drive have different envelopes around the stock drawer.
    local case=maths:TransformLocation(frame,{X=0,Y=0,Z=34.5})
    local drive=maths:TransformLocation(frame,{X=92,Y=82,Z=58})
    return blocked_box(pc,case,orientation,{X=69,Y=58,Z=34.5},ignore,placement)
        or blocked_box(pc,drive,orientation,{X=34,Y=28,Z=11},ignore,placement)
end

function Placement:location(gen,pc,diagnose,locked)
    local maths=StaticFindObject(MATH)
    local pose=stock_pose(gen,maths)
    local builder=gen.PlacementComponent
    local kind=valid(builder) and variants.forItem(builder.CurrentItem)
    if not valid(pc) or not pc:IsLocalController() or not kind then
        return rejected("Select the Winch Automator at its winch.",pose)
    end
    if not catalog.learned(pc,kind) then return rejected("Research " .. kind.title .. " before building it.",pose) end
    local aimMessage=kind.manualUnload and "Aim at the front of the fishing winch." or "Aim at the frame above the winch drawer."
    local net,hit
    if locked then
        net=StaticFindObject(locked.path)
        if not valid(net) or net:GetAddress()~=locked.net then return rejected("Selected winch is no longer available.",pose) end
    else
        hit=gen["Out Hit"]
        local part=hit.Component:Get()
        net=valid(part) and winch_of(part:GetOwner())
        -- The stock query reports an overlap hit for the winch shell on this build.
        if not valid(net) then return rejected(aimMessage,pose), diagnose and ("aim hit "..buildTrace.name(part)) end
    end
    local ship=barge_for(self,pc,net)
    if not ship or (locked and ship:GetAddress()~=locked.ship) then return rejected("This winch is not on the selected barge.",pose) end
    local xyz,rot=fit.builtMount(ship,net)
    if not xyz then return rejected("Winch mounting point is unavailable.",pose) end
    local mount=maths:ComposeTransforms(maths:MakeTransform(xyz,rot,ONE),net:GetTransform())
    if hit then
        local impact=hit.ImpactPoint
        local point=maths:InverseTransformLocation(mount,{X=impact.X,Y=impact.Y,Z=impact.Z})
        local inside
        if kind.manualUnload then
            inside=point.X>=49 and point.X<=246 and point.Y>=48 and point.Y<=125 and point.Z>=-80 and point.Z<=100
        else
            inside=math.abs(point.X)<=145 and math.abs(point.Y)<=125 and point.Z>=-80 and point.Z<=110
        end
        if not inside then
            return rejected(aimMessage,pose), diagnose and string.format("aim outside mount at (%.1f, %.1f, %.1f) cm",point.X,point.Y,point.Z)
        end
    end
    local occupant=taken(ship,net,mount.Translation)
    if occupant then return rejected("This winch already has an automator.",mount), diagnose and buildTrace.name(occupant) end
    local blocker=obstructed(pc,ship,net,mount,maths,builder,kind)
    if blocker then
        local detail
        if diagnose then
            detail=buildTrace.name(blocker)
            if valid(blocker) then detail=detail.." owner="..buildTrace.name(blocker:GetOwner()) end
        end
        return rejected("The winch mounting point is obstructed.",mount),detail
    end
    local root=ship:K2_GetRootComponent()
    if not valid(root) or not root:IsA("/Script/Engine.PrimitiveComponent") then
        return rejected("Barge attachment is unavailable.",mount)
    end
    return {bSuccess=true,AttachToComponent=root,Location=mount,FailureReason=FText("")},nil,net
end

local function evaluate(self,gen,pc,diagnose,locked)
    local ok,result,detail,net=pcall(self.location,self,gen,pc,diagnose,locked)
    if ok then return result,detail,net end
    detail=tostring(result)
    if self.lastError~=detail then self.lastError=detail; self.log("Winch mount check: "..detail) end
    return rejected("Winch mounting point is unavailable."),detail
end

local function path(obj)
    return obj:GetFullName():match("^[^ ]+ (/.+)$")
end

function Placement:restoreFactory()
    local entry=self.factory
    self.factory,self.preview=nil,nil
    if not entry then return end
    local builder=StaticFindObject(entry.builder)
    if valid(builder) and builder:GetAddress()==entry.address and same(builder["Fabricator Factory"],StaticFindObject(FACTORY)) then
        builder["Fabricator Factory"]=StaticFindObject(entry.original)
    end
end

function Placement:installFactory(builder,gen)
    -- The item's cooked generator owns a hard class reference through world travel.
    -- This callback runs inside the VM and must not synchronously load packages.
    local cls=valid(gen) and gen.BuildFactoryClass
    if not valid(cls) or not valid(builder) then return false end
    if self.factory and self.factory.address==builder:GetAddress() and same(builder["Fabricator Factory"],cls) then return true end
    self:restoreFactory()
    local original=builder["Fabricator Factory"]
    if not valid(original) or same(original,cls) then return false end
    self.factory={builder=path(builder),address=builder:GetAddress(),original=path(original)}
    builder["Fabricator Factory"]=cls
    return same(builder["Fabricator Factory"],cls)
end

-- The Blueprint calls the stock factory itself after this check succeeds.
-- Keep its returned construction site inside the game's Blueprint VM.
function Placement:canCommit(owner,item,requested,parent)
    local entry=self.factory
    if not entry then return false,"no winch construction factory installed on the builder" end
    local builder=StaticFindObject(entry.builder)
    if not valid(builder) then return false,"placement component no longer exists: "..entry.builder end
    if builder:GetAddress()~=entry.address then return false,"placement component replaced: "..entry.builder end
    if not same(builder.CurrentItem,item) then
        return false,"recipe mismatch: selected="..buildTrace.name(builder.CurrentItem).." requested="..buildTrace.name(item)
    end
    local pc=FindFirstOf("VoyagePlayerController")
    if not valid(pc) then return false,"player controller unavailable" end
    if not pc:IsLocalController() then return false,"controller is not local" end
    if not same(builder:GetOwner(),pc.Pawn) then return false,"placement component owner differs from local pawn" end
    if not (same(owner,pc.Pawn) or same(owner,builder.SourceActor)) then
        return false,"unexpected build owner="..buildTrace.name(owner).." pawn="..buildTrace.name(pc.Pawn).." source="..buildTrace.name(builder.SourceActor)
    end
    if not variants.forItem(item) then return true end
    local gen=builder.GeneratorCurrent
    if not valid(gen) or not gen:IsA(GEN) then return false,"winch location generator unavailable: "..buildTrace.name(gen) end
    -- Confirmation freezes the stock trace in world space while the green ghost
    -- follows the ship. Recheck the selected winch and mount in their current frame.
    local locked
    if builder.WaitingForConfirmation then
        locked=self.preview
        if not builder.CanPlace or not locked or locked.item~=item:GetAddress() or locked.gen~=gen:GetAddress() then
            return false,"no matching green preview for the selected recipe"
        end
    end
    local fresh,detail=evaluate(self,gen,pc,true,locked)
    if not fresh.bSuccess then
        return false,buildTrace.text(fresh.FailureReason)..(detail and (" "..detail) or "")
    end
    if not same(fresh.AttachToComponent,parent) then
        return false,"attachment mismatch: expected="..buildTrace.name(fresh.AttachToComponent).." requested="..buildTrace.name(parent)
    end
    local p,q=fresh.Location.Translation,requested.Translation
    local dx,dy,dz=p.X-q.X,p.Y-q.Y,p.Z-q.Z
    local distanceSquared=dx^2+dy^2+dz^2
    if distanceSquared<=5^2 then return true end
    return false,string.format("mount position mismatch: distance=%.2f cm limit=5 cm delta=(%.2f, %.2f, %.2f) cm",
        math.sqrt(distanceSquared),dx,dy,dz)
end

function Placement:reset()
    self:restoreFactory()
    self.trace:reset()
    self.ship,self.net,self.lastError=nil,nil,nil
    self.nextCheck=0
end

function Placement:tick()
    self.trace:tick()
    if self.ready or os.time()<self.nextCheck or type(RegisterHook)~="function" then return end
    self.nextCheck=os.time()+2
    local item=StaticFindObject(variants.advanced.item)
    if not valid(item) then item=StaticFindObject(variants.basic.item) end
    local pc=FindFirstOf("VoyagePlayerController")
    if not valid(pc) or not valid(pc.Pawn) or not valid(item) then return end
    local ok,err=pcall(function()
        assert(valid(item.CraftingLocationGenerator.BuildFactoryClass),"Winch construction factory unavailable")
        self.hooks={}
        local function hook(name,callback,post)
            assert(valid(StaticFindObject(name)),"Function unavailable: "..name)
            local a,b=RegisterHook(name,callback,post)
            self.hooks[#self.hooks+1]={name,a,b}
        end
        hook(FACTORY..":ValidateWinchBuild",function(context,owner,item,transform,attach)
            local requestedItem
            local success,allowed,reason=pcall(function()
                requestedItem=item:get()
                return self:canCommit(owner:get(),requestedItem,transform:get(),attach:get())
            end)
            local permit=success and allowed==true
            context:get().bCommitAllowed=permit
            if not success then reason=tostring(allowed) end
            self.trace:validation(requestedItem,permit,reason)
        end)
        hook(BUILDER..":SetCurrentItem",function(context,item)
            local builder=context:get()
            if self.factory and self.factory.address==builder:GetAddress() then self.preview=nil end
            if variants.forItem(item:get()) then
                self:installFactory(builder,item:get().CraftingLocationGenerator)
            elseif self.factory and self.factory.address==builder:GetAddress() then
                self:restoreFactory()
            end
        end)
        hook(SOCKET..":GenerateLocation",function(context,instigator)
            local gen=context:get()
            if valid(gen) and gen:IsA(GEN) then
                local result,_,net=evaluate(self,gen,instigator:get())
                local builder=gen.PlacementComponent
                if not self:installFactory(builder,gen) then
                    self.preview=nil
                    return rejected("Winch construction factory unavailable.",result.Location)
                end
                if result.bSuccess then
                    local saved=self.preview
                    local itemID,genID=builder.CurrentItem:GetAddress(),gen:GetAddress()
                    if not saved or saved.net~=self.net or saved.ship~=self.ship or saved.item~=itemID or saved.gen~=genID then
                        self.preview={net=self.net,path=path(net),ship=self.ship,item=itemID,gen=genID}
                    end
                else self.preview=nil end
                return result
            end
        end)
        -- The stock site calls this for the newly fabricated actor. Starting
        -- here preserves the saved switch when Voyage restores an existing actor.
        hook(SITE..":AttachSpawnedActor",function(context,child,attachment)
            local site,actor,parent=context:get(),child:get(),attachment:get()
            local kind=valid(site) and variants.forItem(site.FabricationItemOrPattern)
            if kind and valid(actor) and actor:IsA(kind.carrier) and valid(parent)
                and same(actor:GetAttachParentActor(),parent:GetOwner()) then
                actor.WinchAutomationEnabled=true
                if self.onCompleted then self.onCompleted() end
            end
        end)
        self.trace:register(hook,BUILDER,GEN,SOCKET,function(builder,pc)
            local gen=builder.GeneratorCurrent
            if valid(gen) and gen:IsA(GEN) then
                local _,detail=evaluate(self,gen,pc,true)
                return detail
            end
        end)
    end)
    if not ok then
        for _,h in ipairs(self.hooks or {}) do pcall(UnregisterHook,table.unpack(h)) end
        self.hooks=nil
        if self.lastError~=err then self.lastError=err; self.log("Winch placement hook: "..tostring(err)) end
        return
    end
    self.ready=true
end

function Placement:shutdown()
    for _,hook in ipairs(self.hooks or {}) do pcall(UnregisterHook,table.unpack(hook)) end
    self.hooks,self.ready=nil,false
    self:reset()
end

return {new=function(options)
    local self=setmetatable({log=options.log,onCompleted=options.onCompleted,trace=buildTrace.new(options.log)},Placement)
    self:reset()
    return self
end}
