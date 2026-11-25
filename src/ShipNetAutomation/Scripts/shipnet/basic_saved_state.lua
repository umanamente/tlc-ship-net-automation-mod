-- Voyage keys each saved component by its object name and outer chain. Basic
-- kept its actor identity and socket when its two component names changed.
local valid=require("shipnet.observer").valid
local HASH_OBJECT="/Script/Engine.CurveFloat"
local TRANSIENT=0x40
local function unwrap(value)
    return type(value.get)=="function" and value:get() or value
end

local function record_in(list,id)
    local actors=list.actors
    if actors:Contains(id) then
        local record=unwrap(actors:Find(id))
        assert(record.persistentId==id,"Basic saved actor identity mismatch")
        return record
    end
end

local function saved_actor(sub,persist)
    local worlds,id=sub.PersistentActors,persist.PersistentUniqueIdRuntime
    assert(math.type(id)=="integer" and id~=0,"Waiting for Basic persistent ID")
    local function at(zone)
        if worlds:Contains(zone) then return record_in(unwrap(worlds:Find(zone)),id) end
    end
    local stored,current=persist.LastStoredZoneId,persist.CurrentRuntimeZoneId
    local record=at(stored) or (current~=stored and at(current))
    if record then return record end
    -- A new fabrication has no saved row. Only search other zones if Voyage
    -- says it previously stored this actor, e.g. before moving the barge.
    if stored:ToString()~="None" then
        worlds:ForEach(function(_,list)
            record=record_in(unwrap(list),id)
            return record~=nil
        end)
    end
    return record
end

local function old_hash(sub,actor,name)
    -- GetComponentHash accepts any UObject. This transient, unregistered
    -- object gives Voyage the original name and owner without adding a module.
    local ownerPath=assert(actor:GetFullName():match("^[^ ]+ (/.+)$"))
    local token=StaticFindObject(ownerPath.."."..name)
    if not valid(token) then
        token=StaticConstructObject(StaticFindObject(HASH_OBJECT),actor,FName(name),TRANSIENT)
    end
    assert(valid(token) and token:IsA(HASH_OBJECT) and token:HasAnyFlags(TRANSIENT)
        and token:GetOuter():GetAddress()==actor:GetAddress() and token:GetFName():ToString()==name,
        "Cannot resolve legacy Basic component name "..name)
    return sub:GetComponentHash(token,false)
end

local function restore_component(sub,actor,data,target,oldName,marker)
    assert(valid(target) and target:GetOwner():GetAddress()==actor:GetAddress(),"Waiting for Basic component "..oldName)
    if data:Contains(sub:GetComponentHash(target,false)) then return end
    local tag=FName(marker)
    if actor:ActorHasTag(tag) then return end
    local key=old_hash(sub,actor,oldName)
    if not data:Contains(key) then return end
    local bytes=unwrap(data:Find(key)).ByteData
    assert(bytes:GetArrayNum()>0 and sub:DeserializeSaveGameProperties(target,bytes),"Cannot restore Basic component "..oldName)
    -- A rebind can happen before the next save replaces the old row. Mark each
    -- successful import separately so it cannot overwrite later power use or damage.
    local tags=actor.Tags
    tags[tags:GetArrayNum()+1]=tag
end

local function restore(actor,sub)
    local persist=actor.PersistentComponent
    assert(valid(persist) and persist:GetOwner():GetAddress()==actor:GetAddress(),"Waiting for Basic persistence")
    local record=saved_actor(sub,persist)
    if not record then return end
    local module=actor.ModuleComponent
    assert(valid(module) and module.bHasInitialized,"Waiting for Basic receiver initialization")
    restore_component(sub,actor,record.ComponentData,module,"VoyageModule","ShipNet_BasicReceiverRestored")
    restore_component(sub,actor,record.ComponentData,actor.DestructibleObjectComponent,
        "VoyageDestructibleObject","ShipNet_BasicHealthRestored")
end

return {restore=restore}
