-- Construction knowledge belongs to the player's native research skill.
local valid = require("shipnet.observer").valid
local Catalog = {}
Catalog.__index = Catalog

local variants = require("shipnet.variants")
local SYSTEM = "/Script/Engine.Default__KismetSystemLibrary"
local SUBSYSTEMS = "/Script/Engine.Default__SubsystemBlueprintLibrary"
local GAME_STATE = "/Script/Voyage.VoyageGameStateSubsystem"
local PLAYER_STATE = "/Script/Voyage.VoyagePlayerState"
local PLAYER_VAULT = 2

local function same(a, b)
    return valid(a) and valid(b) and a:GetAddress() == b:GetAddress()
end

local function player_state(pc)
    if not valid(pc) or not pc:IsLocalController() or not valid(pc.Pawn) then return end
    local world, state = pc:GetWorld(), pc.PlayerState
    if same(world, pc.Pawn:GetWorld()) and valid(state) and state:IsA(PLAYER_STATE)
        and same(world, state:GetWorld()) then return state end
end

-- Also used by the placement/commit hook. Never load a package from a Blueprint callback.
local function learned(pc, variant)
    variant = variant or variants.advanced
    local state = player_state(pc)
    local skill = StaticFindObject(variant.skill)
    return state ~= nil and valid(skill) and state:HasSkill(skill) == true
end

local function registered(kind, name, path)
    local asset = StaticFindObject(path)
    if not valid(asset) then asset = LoadAsset(path) end
    if not valid(asset) or not asset:IsA("/Script/Voyage.Voyage" .. kind) then return end
    local id = {PrimaryAssetType={Name=FName(kind)}, PrimaryAssetName=FName(name)}
    if same(asset, StaticFindObject(SYSTEM):GetObjectFromPrimaryAssetId(id)) then return asset end
end

local function reconcile(variant)
    local pc = FindFirstOf("VoyagePlayerController")
    local state = player_state(pc)
    if not state then return "waiting_for_player" end
    local game = StaticFindObject(SUBSYSTEMS):GetGameInstanceSubsystem(pc, StaticFindObject(GAME_STATE))
    if not valid(game) or game:IsPlaying() ~= true then return "waiting_for_player" end
    local item = registered("Item", variant.itemName, variant.item)
    local skill = registered("Skill", variant.skillName, variant.skill)
    if not item or not skill then return "unregistered" end
    -- Asset loading can dispatch callbacks or change the active world.
    if not same(pc, FindFirstOf("VoyagePlayerController")) or not same(state, player_state(pc)) then
        return "waiting_for_player"
    end
    -- The native player state resolves the character's Vault even while they drive.
    local vault = state:GetInventory(PLAYER_VAULT)
    if not valid(vault) then return "waiting_for_player" end
    local known, present = state:HasSkill(skill), vault:HasItem(item)
    if type(known) ~= "boolean" or type(present) ~= "boolean" then return "waiting_for_player" end
    if present and not known then
        -- dev.7–11 put exactly one copy of this recipe in the Vault, without a skill.
        vault:RemoveItem(item, 1, -1, true)
        assert(vault:HasItem(item) == false, "Could not confirm removal of the old Winch Automator recipe")
        return "legacy_removed"
    elseif known and not present then
        -- Research normally awards the item itself. Repair only a restored Vault
        -- that disagrees with a genuinely learned skill on the current player.
        vault:AddItem(item, {ItemCount=1, Timestamp=0, Flags=0}, true, true)
        assert(vault:HasItem(item) == true, "Learned Winch Automator recipe missing from the Vault")
    end
    return known and "learned" or "locked"
end

function Catalog:reset()
    self.nextCheck, self.lastMessage = 0, nil
end

function Catalog:tick()
    local now = os.time()
    if now < self.nextCheck then return end
    self.nextCheck = now + 2
    local ok, status = pcall(reconcile, self.variant)
    if self.nextCheck == 0 then return end
    if ok and status ~= "waiting_for_player" then self.nextCheck = now + 10 end
    local message
    if not ok then message = "Recipe catalogue check failed: " .. tostring(status)
    elseif status == "unregistered" then message = self.variant.title .. " research or item is missing from the game asset registry."
    elseif status == "legacy_removed" then message = "Winch Automator now requires research on this character." end
    if message and message ~= self.lastMessage and self.log then self.log(message) end
    self.lastMessage = message
    return status
end

return {learned=learned, new=function(options)
    local self = setmetatable({log=options.log, variant=options.variant or variants.advanced}, Catalog)
    self:reset()
    return self
end}
