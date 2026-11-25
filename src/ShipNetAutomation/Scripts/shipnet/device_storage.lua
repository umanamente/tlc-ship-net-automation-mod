-- Contents and attachment live in the current Voyage save. The visual controller
-- can be unloaded and rebuilt without owning or destroying the backing box.
local valid = require("shipnet.observer").valid
local Store = {}
Store.__index = Store
local BOX = "/Game/Blueprints/Interactives/Containers/BP_Inventory_PlayerBox_Small.BP_Inventory_PlayerBox_Small_C"
local BARGE = "/Game/Blueprints/Vehicles/BP_Boat_Barge.BP_Boat_Barge_C"
local PERSIST = "/Script/Voyage.Default__VoyagePersistentSubsystem"
local MISC = "/Script/Voyage.Default__VoyageMiscBlueprintFunctionLibrary"
local WEIGHT = "/Script/Voyage.VoyageInventoryWeightLimitedComponent"
local ACCESS_READ = 0 -- EVoyageInventoryAccessType::Read
local SHIP_LINK = "ShipNet_DeviceStoreRef_"
local BOX_MARK = "ShipNet_DeviceStore_"

local function same(a,b)
    return valid(a) and valid(b) and a:GetAddress()==b:GetAddress()
end

local function path(o)
    return assert(o:GetFullName():match("^[^ ]+ (/.+)$"))
end

local function hex_id(sub,actor)
    local id = sub:GetPersistentActorComponent(actor).PersistentUniqueIdRuntime
    assert(math.type(id)=="integer" and id~=0,"Missing native runtime identity")
    return string.format("%016x",id)
end

local function trace_ship(actor,ship)
    for _=1,4 do
        if not valid(actor) then return false end
        if same(actor,ship) then return true end
        actor=actor:GetAttachParentActor()
    end
    return false
end

local function tag_actor(actor,tag)
    if not actor:ActorHasTag(tag) then actor.Tags[actor.Tags:GetArrayNum()+1]=tag end
    assert(actor:ActorHasTag(tag),"Could not record the device inventory identity")
end

local function link_id(ship)
    local id
    for i=1,ship.Tags:GetArrayNum() do
        local value=ship.Tags[i]:ToString():match("^"..SHIP_LINK.."(%x+)$")
        if value then
            value=value:lower()
            assert(#value==16 and (not id or value==id),"Conflicting saved device inventory identities")
            id=value
        end
    end
    return id
end

local function context(preview,ship)
    assert(valid(preview) and valid(ship) and ship:IsA(BARGE) and not ship:HasAnyFlags(0x30)
        and trace_ship(preview,ship),"Mounted device or selected barge unavailable")
    local world=ship:GetWorld()
    local sub=StaticFindObject(PERSIST):GetPersistentSubsystem(world)
    assert(valid(sub),"Save subsystem unavailable")
    return {world=world,sub=sub,ship=ship,mark=FName(BOX_MARK..hex_id(sub,ship)),link=link_id(ship)}
end

local function owned_inventory(box)
    local inv=box.VoyageInventoryWeightLimited
    assert(valid(inv) and inv:IsA(WEIGHT) and same(inv:GetOwner(),box),"Device inventory owner changed")
    return inv
end

local function live_inventory(box,allowRead)
    local inv=owned_inventory(box)
    local access=inv.Access
    assert(box.IsLocked==false and (access==1 or access==2 or (allowRead and access==ACCESS_READ)),
        "Device inventory is locked")
    return inv
end

local function eligible(ctx,box)
    return valid(box) and not box:HasAnyFlags(0x30) and box:IsA(BOX) and same(box:GetWorld(),ctx.world)
end

local function verify(ctx,box)
    assert(eligible(ctx,box) and same(box:GetAttachParentActor(),ctx.ship),"Device inventory attachment unavailable")
    assert(ctx.sub:IsPersistentActor(box),"Device inventory is not save-owned")
    local id=hex_id(ctx.sub,box)
    assert((not ctx.link or ctx.link==id) and (ctx.link==id or box:ActorHasTag(ctx.mark)),
        "Saved device inventory identity changed")
    return live_inventory(box),id
end

local function remember(self,ctx,box)
    local inv,id=verify(ctx,box)
    if not self.ref or self.ref.address~=box:GetAddress() or self.ref.path~=path(box) then
        -- Keep the stock collision/graphics out of the casing and drawer. The
        -- traced casing invokes the stock controller action with this exact box.
        box:SetActorHiddenInGame(true)
        box:SetActorEnableCollision(false)
    end
    self.ref={path=path(box),address=box:GetAddress(),id=id,ship=ctx.ship:GetAddress(),world=ctx.world:GetAddress()}
    return inv
end

local function discover(ctx)
    local match
    for _,box in ipairs(FindAllOf("BP_Inventory_PlayerBox_Small_C") or {}) do
        if eligible(ctx,box) and (box:ActorHasTag(ctx.mark)
            or (ctx.link and same(box:GetAttachParentActor(),ctx.ship) and hex_id(ctx.sub,box)==ctx.link)) then
            assert(not match or same(match,box),"Multiple inventories claim this device")
            match=box
        end
    end
    return match
end

local function finish_new(self,ctx,box)
    tag_actor(box,ctx.mark)
    local id=hex_id(ctx.sub,box)
    assert(not ctx.link or ctx.link==id,"A different saved inventory is already linked")
    tag_actor(ctx.ship,FName(SHIP_LINK..id))
    ctx.link=id
    if not same(box:GetAttachParentActor(),ctx.ship) then
        assert(not valid(box:GetAttachParentActor()) and ctx.sub:AttachActor(box,ctx.ship:K2_GetRootComponent(),false)
            and same(box:GetAttachParentActor(),ctx.ship),"Game could not attach storage to the barge")
    end
    local inv=live_inventory(box)
    inv:SetInventoryName(FText("Net controller"))
    assert(ctx.sub:SerializeActor(box) and ctx.sub:SerializeActor(ctx.ship),"Game could not serialize the device inventory link")
    self.pending=nil
    return remember(self,ctx,box)
end

local function spawn(self,ctx,preview)
    local cls=StaticFindObject(BOX)
    if not valid(cls) then cls=LoadAsset(BOX) end
    assert(valid(cls),"Stock storage box class unavailable")
    local box=StaticFindObject(MISC):SpawnRuntimeActorFromClass(ctx.world,cls,preview:GetTransform(),{Value=0},nil,ctx.ship)
    assert(eligible(ctx,box),"Game could not create the stock storage box")
    -- Retry initialization only on this exact actor; never adopt or reattach a
    -- player box which was independently detached after successful commissioning.
    self.pending={path=path(box),address=box:GetAddress(),ship=ctx.ship:GetAddress(),world=ctx.world:GetAddress()}
    return finish_new(self,ctx,box)
end

local function inventory(self,preview,ship,create)
    local ctx=context(preview,ship)
    local pending=self.pending
    if pending and pending.ship==ship:GetAddress() and pending.world==ctx.world:GetAddress() then
        local box=StaticFindObject(pending.path)
        assert(create and eligible(ctx,box) and box:GetAddress()==pending.address,"Waiting for device inventory initialization")
        return finish_new(self,ctx,box)
    end
    local ref=self.ref
    if ref and ref.ship==ship:GetAddress() and ref.world==ctx.world:GetAddress() then
        local cached=StaticFindObject(ref.path)
        if valid(cached) and cached:GetAddress()==ref.address then
            local inv=verify(ctx,cached)
            return inv
        end
    end
    -- Poll restoration when needed without enumerating all small boxes on
    -- every display refresh. An interaction always rechecks the live world.
    local last=self.empty
    if not create and not ctx.link and last and last.ship==ship:GetAddress() and last.world==ctx.world:GetAddress()
        and os.time()<last.retry then return nil,"uncreated" end
    local box=discover(ctx)
    if box then return remember(self,ctx,box) end
    assert(not ctx.link,"Waiting for the saved device inventory to load")
    if create then return spawn(self,ctx,preview) end
    self.empty={ship=ship:GetAddress(),world=ctx.world:GetAddress(),retry=os.time()+2}
    return nil,"uncreated"
end

function Store:inventory(preview,ship,create)
    if self.carrier then
        local ok,inv=pcall(function()
            assert(valid(preview) and same(preview,self.carrier),"Built controller unavailable")
            return live_inventory(preview,true)
        end)
        if ok then return inv end
        return nil,tostring(inv)
    end
    local ok,inv,detail=pcall(inventory,self,preview,ship,create==true)
    if not ok then return nil,tostring(inv) end
    return inv,detail
end

function Store:inspect(preview,ship)
    local inv,why=self:inventory(preview,ship,false)
    if not inv then
        if why=="uncreated" then return {status="uncreated",fillRatio=0,weightKg=0,itemCount=0} end
        return {status="unavailable",detail=why}
    end
    local ok,report=pcall(function()
        local weight,capacity=inv:GetTotalWeight(),inv:GetCurrentMaxWeightLimit()
        return {status="ready",actor=path(inv:GetOwner()),inventory=path(inv),nativeId=self.ref.id,
            weightKg=weight,capacityKg=capacity,fillRatio=capacity>0 and weight/capacity or nil,
            itemCount=inv:GetTotalNumItems()}
    end)
    if ok then return report end
    return {status="unavailable",detail=tostring(report)}
end

function Store:open(pc,preview,ship,allowCreate)
    if not valid(pc) or not pc:IsLocalController() or not valid(ship) or not same(pc:GetWorld(),ship:GetWorld()) then
        return false,"Local barge or controller unavailable"
    end
    local inv,why=self:inventory(preview,ship,allowCreate~=false)
    if not inv then return false,why end
    local ok,detail=pcall(function()
        local box=inv:GetOwner()
        assert(valid(box.InteractiveObject) and same(box.InteractiveObject:GetOwner(),box),"Stock container interaction unavailable")
        -- Identical to BP_Container_Base.Interact_OpenTriggered. The stock menu
        -- binds the local backpack and the selected box and owns all transfers.
        pc:OnPlayerInteraction(box,box.InteractiveObject)
    end)
    if not ok then return false,tostring(detail) end
    return true,self:inspect(preview,ship)
end

return {
    new=function() return setmetatable({},Store) end,
    forCarrier=function(carrier,subsystem)
        local id=hex_id(subsystem,carrier)
        local inv=owned_inventory(carrier)
        -- Voyage hides and disables both deposit buttons in its stock menu.
        inv.Access=ACCESS_READ
        return setmetatable({carrier=carrier,ref={id=id}},Store)
    end,
}
