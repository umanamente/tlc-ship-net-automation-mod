"""Verify native skill ownership and migration of dev.7–11 Vault recipes."""
import unittest

from lupa.lua54 import LuaRuntime
from test_observer import SCRIPTS


WORLD = """
local serial=0
function object(class)
    serial=serial+1
    local o={address=serial, class=class}
    function o:GetAddress() return self.address end
    function o:IsValid() return not self.invalid end
    function o:IsA(kind) return kind==self.class end
    function o:GetWorld() return self.world or world end
    return o
end
itemName="DA_Item_Module_WinchAutomator"
skillName="DA_Skill_Engineering_Winch_Automator"
itemPath="/Game/Data/Assets/Modules/"..itemName.."."..itemName
skillPath="/Game/Data/Assets/Skill/Modules/"..skillName.."."..skillName
world=object("World"); pc=object("Controller"); state=object("/Script/Voyage.VoyagePlayerState")
vault=object("Vault"); pc.PlayerState=state; pc.Pawn=object("Character")
function pc:IsLocalController() return true end
function state:GetInventory(kind) assert(kind==2); return vault end
known=false; present=false; adds=0; removes=0; playing=true
recipe=object("/Script/Voyage.VoyageItem"); skill=object("/Script/Voyage.VoyageSkill")
function state:HasSkill(s) assert(s==skill);return known end
function vault:HasItem(i) assert(i==recipe);return present end
function vault:RemoveItem(i,n,slot,notify)
    assert(i==recipe and n==1 and slot==-1 and notify and not known and present)
    removes=removes+1;present=false;return 1
end
function vault:AddItem(i,data,stack,notify)
    assert(i==recipe and data.ItemCount==1 and stack and notify and known and not present)
    adds=adds+1;present=true
end
function FindFirstOf(class) assert(class=="VoyagePlayerController");return pc end
function FName(txt) return txt end
local system=object("System")
function system:GetObjectFromPrimaryAssetId(id)
    if id.PrimaryAssetName==itemName and id.PrimaryAssetType.Name=="Item" then return recipe end
    if id.PrimaryAssetName==skillName and id.PrimaryAssetType.Name=="Skill" and not missing then return skill end
end
local subsystems=object("Subsystems")
local stateClass=object("GameStateClass")
local game=object("GameState")
function subsystems:GetGameInstanceSubsystem(player,cls) assert(player==pc and cls==stateClass);return game end
function game:IsPlaying() return playing end
objects={[itemPath]=recipe,[skillPath]=skill,
    ["/Script/Engine.Default__KismetSystemLibrary"]=system,
    ["/Script/Engine.Default__SubsystemBlueprintLibrary"]=subsystems,
    ["/Script/Voyage.VoyageGameStateSubsystem"]=stateClass}
function StaticFindObject(path) return objects[path] end
function LoadAsset(path) return objects[path] end
now=200;os.time=function()return now end
api=require("shipnet.build_catalog");catalog=api.new({log=function()end})
function check() now=now+11;return catalog:tick() end
"""


class BuildCatalogTest(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts=SCRIPTS.as_posix()
        self.lua.execute('package.path=scripts.."/?.lua;"..package.path')
        self.lua.execute(WORLD)

    def test_fresh_player_only_gets_recipe_from_learning_the_stock_skill(self):
        self.lua.execute("""
            assert(check()=="locked" and not api.learned(pc))
            known=true;present=true
            assert(check()=="learned" and api.learned(pc))
            assert(present and adds==0 and removes==0)
        """)

    def test_old_character_then_disk_reload_in_either_order(self):
        self.lua.execute("""
            present=true;playing=false
            assert(check()=="waiting_for_player" and present)
            playing=true;assert(check()=="legacy_removed" and not present)
            assert(check()=="locked" and removes==1 and adds==0)
            known=true;present=true
            catalog:reset();assert(check()=="learned" and present)
            -- A delayed Vault restore is repaired only for verified ownership.
            present=false;assert(check()=="learned" and present and adds==1)
            assert(check()=="learned" and removes==1 and adds==1)
        """)

    def test_late_vault_restore_while_unresearched_is_not_grandfathered(self):
        self.lua.execute("""
            assert(check()=="locked")
            present=true;assert(not api.learned(pc));assert(check()=="legacy_removed")
            assert(not present and removes==1 and adds==0)
        """)

    def test_wrong_world_unavailable_vault_or_missing_skill_does_not_remove(self):
        self.lua.execute("""
            present=true;state.world=object("OtherWorld");assert(check()=="waiting_for_player")
            state.world=nil;missing=true;assert(check()=="unregistered")
            missing=false;function state:GetInventory() return nil end
            assert(check()=="waiting_for_player" and present and removes==0)
        """)

    def test_travel_during_asset_resolution_defers_migration(self):
        self.lua.execute("""
            present=true;objects[skillPath]=nil
            function LoadAsset(path)
                assert(path==skillPath);pc.PlayerState=object("/Script/Voyage.VoyagePlayerState")
                return skill
            end
            assert(check()=="waiting_for_player" and present and removes==0)
        """)
