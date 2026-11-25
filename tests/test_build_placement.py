"""Exercise the winch recipe's placement hook with a moving barge and stock hit types."""
import unittest

from lupa.lua54 import LuaRuntime
from test_observer import SCRIPTS, WORLD


PLACEMENT = r"""
local BUILT=require("shipnet.fit").builtClass
local BASIC=require("shipnet.variants").basic
local GEN="/Game/Mods/ShipNetAutomation/BP_WinchMountGenerator.BP_WinchMountGenerator_C"
local SOCKET="/Game/Blueprints/Fabrication/BP_CraftingLocationGenerator_SocketMatch.BP_CraftingLocationGenerator_SocketMatch_C"
local ITEM="/Game/Data/Assets/Modules/DA_Item_Module_WinchAutomator.DA_Item_Module_WinchAutomator"
local BLDR="/Game/Blueprints/Fabrication/BP_FabricationPlacementComponent.BP_FabricationPlacementComponent_C"
local FACTORY="/Game/Mods/ShipNetAutomation/BP_WinchBuildFactory.BP_WinchBuildFactory_C"
local function xyz(x,y,z) return {X=x,Y=y,Z=z} end
local function rotation(yaw) return {Pitch=0,Yaw=yaw,Roll=0} end
local function spin(p,deg)
    local a=math.rad(deg)
    return xyz(p.X*math.cos(a)-p.Y*math.sin(a),p.X*math.sin(a)+p.Y*math.cos(a),p.Z)
end
local function transform(t,p)
    local q=spin(p,t.Rotation.Yaw);local o=t.Translation
    return xyz(o.X+q.X,o.Y+q.Y,o.Z+q.Z)
end
local function frame(p,r) return {Translation=p,Rotation=r,Scale3D=xyz(1,1,1)} end
local function component(owner,name)
    local c=actor(name);data[c].owner=owner;return c
end
local function weak(obj) return {Get=function() return obj end} end
local winchFrame=frame(xyz(41000,27000,-100),rotation(90))
local fit=require("shipnet.fit")
local origin,rot=fit.builtMount(ship,net)
nominal=transform(winchFrame,origin)
data[net].GetTransform=function() return winchFrame end
root=actor("Hull",{["/Script/Engine.PrimitiveComponent"]=true})
data[root].owner=ship;data[ship].K2_GetRootComponent=function() return root end
drawer=actor("Drawer");data[drawer].parent=net
lever=actor("Switch");data[lever].attachment=net
local drawerChild=component(net,"Container");local switchChild=component(net,"SwitchChild")
data[drawerChild].ChildActor=drawer;data[switchChild].ChildActor=lever
data[net].Container=drawerChild;data[net].SwitchChildActor=switchChild
recipe=actor("Recipe"); basicRecipe=actor("BasicRecipe"); unrelated=actor("OtherRecipe")
local skillPath="/Game/Data/Assets/Skill/Modules/DA_Skill_Engineering_Winch_Automator.DA_Skill_Engineering_Winch_Automator"
local skill=actor("WinchSkill")
local basicSkill=actor("BasicWinchSkill")
local playerState=actor("PlayerState",{["/Script/Voyage.VoyagePlayerState"]=true})
data[controller].PlayerState=playerState
researched=true;basicResearched=false
data[playerState].HasSkill=function(_,which)
    if which==basicSkill then return basicResearched end
    assert(which==skill);return researched
end
gen=actor("Generator",{[GEN]=true}); builder=actor("Builder",{[BLDR]=true})
data[builder].owner=pawn;data[builder].CurrentItem=recipe
data[gen].PlacementComponent=builder;data[gen].PlacementLocation=xyz(7,8,9);data[gen].PlacementRotation=rotation(0)
data[builder].SourceActor=actor("PlayerBuildTool")
data[builder].GeneratorCurrent=gen;data[builder].CanPlace=true
local hit={bBlockingHit=true,ImpactPoint=nominal}
data[gen]["Out Hit"]=hit
function aim(actor,point)
    hit.Component=weak(actor and component(actor,"HitPart") or nil)
    hit.bBlockingHit=actor~=nil;hit.ImpactPoint=point or nominal
end
aim(net)
local mathlib={
    MakeTransform=function(_,p,r) return frame(p,r) end,
    ComposeTransforms=function(_,child,parent)
        return frame(transform(parent,child.Translation),rotation(child.Rotation.Yaw+parent.Rotation.Yaw))
    end,
    TransformLocation=function(_,f,p) return transform(f,p) end,
    InverseTransformLocation=function(_,f,p)
        local o=f.Translation
        return spin(xyz(p.X-o.X,p.Y-o.Y,p.Z-o.Z),-f.Rotation.Yaw)
    end,
    Quat_Rotator=function(_,q) return q end,
}
local system={}
function system:BoxTraceMultiForObjects(context,start,finish,half,orient,types,complex,ignore,draw,out)
    assert(context==controller and half.X>0 and half.Y>0 and half.Z>0)
    lastTrace={center=start,extent=half,orientation=orient,ignore=ignore}
    if blocker then
        if blockerType then
            local included=false
            for _,id in ipairs(types) do if id==blockerType then included=true end end
            if not included then return false end
        end
        for _,ignored in ipairs(ignore) do if ignored==blocker then return false end end
        local r=remote_param({Component=weak(component(blocker,"Obstacle"))})
        if namedHits then out.OutHits={ForEach=function(_,visit) visit(1,r) end}
        else out[1]=r end
        return true
    end
    return false
end
local helpers={}
helpers[skillPath]=skill;helpers[BASIC.skill]=basicSkill;helpers[BASIC.item]=basicRecipe
helpers[ITEM]=recipe;helpers["/Script/Engine.Default__KismetMathLibrary"]=mathlib
helpers["/Script/Engine.Default__KismetSystemLibrary"]=system
scoped=actor("ScopedFactory");helpers[FACTORY]=scoped
data[gen].BuildFactoryClass=scoped
data[recipe].CraftingLocationGenerator=gen
data[basicRecipe].CraftingLocationGenerator=gen
syncLoads=0
function system:LoadClassAsset_Blocking() syncLoads=syncLoads+1;error("Blocking factory load during placement") end
function LoadAsset() syncLoads=syncLoads+1;error("Blocking asset load during placement") end
activeFactory=actor("PlayerConstructionFactory");stockCDO=actor("StockFactoryCDO")
data[activeFactory].GetCDO=function() return stockCDO end
data[stockCDO].Fabricate=function() error("Lua validator must not enter the stock Blueprint factory") end
factoryInstance=actor("WinchFactoryInstance",{[FACTORY]=true})
rawset(factoryInstance,"bCommitAllowed",false)
stockCalls=0;siteResult=actor("InProgressSite")
local function stockFabricate(owner,item,t,attachment)
    stockCalls=stockCalls+1;lastStock={owner=owner,item=item,frame=t,attach=attachment};return siteResult
end
rawset(builder,"Fabricator Factory",activeFactory)
locationPath=SOCKET..":GenerateLocation"
setItemPath=BLDR..":SetCurrentItem";validatePath=FACTORY..":ValidateWinchBuild"
pressPath="/Script/Voyage.VoyageCharacterInputControlsComponent:OnInteractOneStarted"
materialsPath="/Script/Voyage.VoyageFabricatorComponent:CanFabricateItem"
interactionPath="/Script/Voyage.VoyagePlayerController:OnPlayerInteraction"
actionPath=BLDR..":Fabricate";sitePath=SOCKET..":OnFabricate"
completedPath="/Game/Blueprints/Fabrication/BP_Location_Fabricator.BP_Location_Fabricator_C:AttachSpawnedActor"
for _,key in ipairs({locationPath,setItemPath,validatePath,pressPath,materialsPath,interactionPath,actionPath,sitePath,completedPath,BLDR}) do helpers[key]=actor(key) end
controls=actor("CharacterInputControls")
data[controls].owner=pawn
data[pawn].GetComponentByClass=function(_,class) assert(class==helpers[BLDR]);return builder end
local lookup=StaticFindObject
function StaticFindObject(path) return helpers[path] or lookup(path) end
local find=FindAllOf
built,basicBuilt,sites={},{},{}
function FindAllOf(name)
    if name=="BP_Module_WinchAutomator_C" then return built end
    if name==BASIC.carrierName then return basicBuilt end
    if name=="BP_Location_Fabricator_C" then return sites end
    if name=="BP_FabricationPlacementComponent_C" then return {builder} end
    return find(name)
end
function fixture_actor(isSite,parent,pos,item,basic)
    local a=actor("SiteOrBuild"..tostring(#sites+#built+#basicBuilt),{[basic and BASIC.carrier or BUILT]=not isSite})
    data[a].IsActorBeingDestroyed=function(self) return data[self].destroying==true end
    data[a].attachment=parent;data[a].K2_GetActorLocation=function() return pos or nominal end
    data[a].FabricationItemOrPattern=item
    table.insert(isSite and sites or (basic and basicBuilt or built),a)
    return a
end
function FText(s) return s end
hooks={}; unhooked={}
function RegisterHook(path,pre,post)
    hooks[path]={pre=pre,post=post}
    return 10,11
end
function UnregisterHook(path,a,b) assert(a==10 and b==11);unhooked[path]=true end
record={ship=ship:GetFullName(),net=net:GetFullName(),coordinateFrame="ship_loaded_level"}
package.loaded["shipnet.survey"]={capture=function() return record end}
messages={}
completed=0
placement=require("shipnet.build_placement").new({log=function(s) messages[#messages+1]=s end,
    onCompleted=function() completed=completed+1 end})
placement:tick()
function ask(generator)
    return hooks[locationPath].pre(remote_param(generator or gen),remote_param(controller))
end
data[gen].GenerateLocation=function() error("Nested Blueprint return hook") end
function validate(item,attachment,requested,owner)
    local hook=hooks[validatePath]
    if hook then
        local result=hook.pre(remote_param(factoryInstance),remote_param(owner),remote_param(item),
            remote_param(requested),remote_param(attachment))
        assert(result==nil,"ValidateWinchBuild is void")
    end
end
function confirm(item,attachment,position,owner)
    local requested=frame(position or nominal,rotation(270))
    owner,attachment=owner or pawn,attachment or root
    -- Model the scoped Blueprint's Fabricate body around the real Lua callback.
    factoryInstance.bCommitAllowed=false
    validate(item,attachment,requested,owner)
    if factoryInstance.bCommitAllowed then
        factoryInstance.bCommitAllowed=false
        return stockFabricate(owner,item,requested,attachment)
    end
end
function aimAtBasic() aim(net,transform(frame(nominal,rotation(270)),xyz(100,80,20))) end
function sailAndTurn()
    winchFrame=frame(xyz(43000,27900,20),rotation(125))
    nominal=transform(winchFrame,origin)
end
function selectItem(item)
    data[builder].CurrentItem=item;hooks[setItemPath].pre(remote_param(builder),remote_param(item))
end
function press() hooks[pressPath].pre(remote_param(controls)) end
function finishAction() return hooks[actionPath].pre(remote_param(builder)) end
function siteReturned(site) return hooks[sitePath].pre(remote_param(gen),remote_param(site)) end
"""


class BuildPlacementTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts=SCRIPTS.as_posix()
        self.lua.execute('package.path=scripts.."/?.lua;"..package.path')
        self.lua.execute(WORLD)
        self.lua.execute(PLACEMENT)

    def check_moving_winch(self,item,aim):
        self.lua.execute(f"selectItem({item});basicResearched=true;{aim};assert(ask().bSuccess)")
        self.lua.execute(f"""
            data[builder].WaitingForConfirmation=true
            local oldPosition=nominal
            sailAndTurn()
            assert(not confirm({item},root,oldPosition))
            blocker=actor("NewObstruction");assert(not confirm({item}));blocker=nil
            local other=fixture_actor(true,nil,nominal,{item})
            assert(not confirm({item}));data[other].destroying=true
            assert(confirm({item})==siteResult and stockCalls==1)
        """)

    def test_advanced_follows_its_green_preview_on_a_moving_winch(self):
        self.check_moving_winch("recipe","aim(net)")

    def test_basic_follows_its_green_preview_on_a_moving_winch(self):
        self.check_moving_winch("basicRecipe","aimAtBasic()")

    def test_fabricated_automators_are_enabled_when_attached(self):
        self.lua.execute("""
            local saved=fixture_actor(false,ship,nominal,recipe)
            rawset(saved,"WinchAutomationEnabled",false)
            for _,basic in ipairs({false,true}) do
                local item=basic and basicRecipe or recipe
                local site=fixture_actor(true,ship,nominal,item)
                local new=fixture_actor(false,nil,nominal,item,basic)
                rawset(new,"WinchAutomationEnabled",false)
                local notify=hooks[completedPath].pre
                notify(remote_param(site),remote_param(new),remote_param(root))
                assert(not new.WinchAutomationEnabled)
                data[new].attachment=ship
                notify(remote_param(site),remote_param(new),remote_param(root))
                assert(new.WinchAutomationEnabled and not saved.WinchAutomationEnabled)
            end
            assert(completed==2)
        """)

    def test_locked_target_requires_a_matching_green_preview(self):
        self.lua.execute("""
            selectItem(recipe);assert(ask().bSuccess)
            aim(nil);assert(not ask().bSuccess);data[builder].WaitingForConfirmation=true
            assert(not confirm(recipe))
            aim(net);assert(ask().bSuccess)
            selectItem(basicRecipe);basicResearched=true;assert(not confirm(basicRecipe))
            aimAtBasic();assert(ask().bSuccess)
            basicResearched=false;assert(not confirm(basicRecipe));basicResearched=true
            assert(not confirm(basicRecipe,actor("ForeignRoot")))
            data[net].invalid=true;assert(not confirm(basicRecipe))
            assert(stockCalls==0)
        """)

    def test_basic_build_input_and_each_stock_stage_share_attempt_number(self):
        self.lua.execute("""
            selectItem(basicRecipe);basicResearched=true;aimAtBasic()
            for i=1,10 do assert(ask().bSuccess) end
            assert(#messages==0)
            press();data[builder].WaitingForConfirmation=true;finishAction()
            press();data[builder].WaitingForConfirmation=false
            assert(confirm(basicRecipe)==siteResult)
            local siteClass="/Game/Blueprints/Fabrication/BP_Location_Fabricator.BP_Location_Fabricator_C"
            local fabricator=actor("NativeFabricator")
            data[fabricator].owner=actor("ConstructionSite",{[siteClass]=true})
            assert(hooks[materialsPath].post(remote_param(fabricator),remote_param(false),remote_param(basicRecipe))==nil)
            assert(siteReturned(nil)==nil and finishAction()==nil)
            press();assert(confirm(basicRecipe)==siteResult);siteReturned(siteResult);finishAction()
            selectItem(unrelated);press();finishAction()
        """)
        lines=list(self.lua.globals().messages.values())
        self.assertEqual(len(lines),11,lines)
        self.assertTrue(all("[Winch Automator Basic]" in line for line in lines))
        for index,part in enumerate(("input pressed","waiting for another confirmation","input pressed",
                                     "validation passed","CanFabricateItem=false","no construction site","action handled",
                                     "input pressed","validation passed","InProgressSite","action handled")):
            self.assertIn(part,lines[index])
            self.assertIn(f"Build #{1 if index<2 else 2 if index<7 else 3} ",lines[index])

    def test_build_input_blocked_before_dispatch_records_each_press_and_reason(self):
        self.lua.execute("""
            selectItem(basicRecipe);data[builder].CanPlace=false
            data[builder].FailureReason={ToString=function() return "Mount obstructed" end}
            data[controls].owner=controller
            press();press();advance(4);placement:tick()
        """)
        lines=list(self.lua.globals().messages.values())
        self.assertEqual(len(lines),6,lines)
        for start in (0,3):
            self.assertIn("CanPlace=false",lines[start])
            self.assertIn("disabled: Mount obstructed",lines[start+1])
            self.assertIn("no Fabricate action observed",lines[start+2])

    def test_commit_failure_reports_specific_object_or_measured_difference(self):
        self.lua.execute("selectItem(basicRecipe);basicResearched=true;aimAtBasic();assert(ask().bSuccess)")
        for setup,call,expect in (
            ("fixture_actor(false,ship,nominal,nil,false)", "confirm(basicRecipe)", "SiteOrBuild0"),
            ("built={};blocker=actor('CableAfterDismantle')","confirm(basicRecipe)", "owner=Class /Test.CableAfterDismantle"),
            ("blocker=nil","confirm(basicRecipe,actor('WrongParent'))","WrongParent"),
            ("","confirm(basicRecipe,root,xyzOffset)","distance=6.00 cm limit=5 cm"),
            ("data[builder].GeneratorCurrent=nil","confirm(basicRecipe)","location generator unavailable"),
            ("data[builder].GeneratorCurrent=gen","confirm(basicRecipe,root,nil,actor('WrongOwner'))","WrongOwner"),
            ("basicResearched=false","confirm(basicRecipe)","Research Winch Automator Basic"),
        ):
            with self.subTest(reason=expect):
                self.lua.execute("xyzOffset={X=nominal.X+6,Y=nominal.Y,Z=nominal.Z};"+setup)
                self.lua.execute(f"press();assert({call}==nil)")
                self.assertIn(expect,self.lua.eval("messages[#messages]"))
                self.assertIn("winch validation rejected:",self.lua.eval("messages[#messages]"))
                self.lua.execute("siteReturned(nil);finishAction()")
        self.assertEqual(self.lua.globals().stockCalls,0)

    def test_green_build_input_routed_to_another_interaction(self):
        self.lua.execute("""
            selectItem(basicRecipe);basicResearched=true;aimAtBasic();assert(ask().bSuccess)
            press()
            hooks[interactionPath].pre(remote_param(controller),remote_param(drawer),remote_param(root))
            advance(4);placement:tick()
            assert(table.concat(messages," "):find("game routed interaction to Class /Test.Drawer",1,true))
            assert(messages[#messages]:find("no Fabricate action observed",1,true))
            assert(stockCalls==0)
        """)

    def test_ship_relative_pose_is_composed_once_and_stock_parts_are_ignored(self):
        for name in ("net","drawer","lever"):
            with self.subTest(name=name):
                self.lua.execute(f"aim({name});blocker={name};result=ask()")
                self.assertTrue(self.lua.eval("result.bSuccess and result.AttachToComponent==root"))
                self.assertAlmostEqual(self.lua.eval("result.Location.Translation.X"),41189.824)
                self.assertAlmostEqual(self.lua.eval("result.Location.Translation.Y"),27147.779)
                self.assertAlmostEqual(self.lua.eval("result.Location.Translation.Z"),26.859)
                self.assertAlmostEqual(self.lua.eval("result.Location.Rotation.Yaw")%360,270)

    def test_wrong_aim_foreign_winch_and_remote_impact_are_rejected(self):
        for aim in ("nil","ship","other_net(other_ship())","net,{X=-999,Y=999,Z=20}","net,{X=0/0,Y=0/0,Z=0/0}"):
            with self.subTest(aim=aim):
                self.lua.execute(f"aim({aim});result=ask()")
                self.assertFalse(self.lua.eval("result.bSuccess"))
                self.assertIsNotNone(self.lua.eval("result.FailureReason"))

    def test_competing_objects_and_completed_or_in_progress_fabrication(self):
        self.lua.execute("blocker=actor('Obstruction')")
        self.assertFalse(self.lua.eval("ask().bSuccess"))
        self.lua.execute("blocker=nil;fixture_actor(true,ship,nominal,unrelated)")
        self.assertTrue(self.lua.eval("ask().bSuccess"))
        self.lua.execute("fixture_actor(true,ship,nominal,recipe)")
        self.assertFalse(self.lua.eval("ask().bSuccess"))
        self.lua.execute("sites={};fixture_actor(false,net,nil)")
        self.assertFalse(self.lua.eval("ask().bSuccess"))
        self.lua.execute("built={};fixture_actor(false,ship,{X=100000,Y=10000,Z=1})")
        self.assertTrue(self.lua.eval("ask().bSuccess"))

    def test_stock_generator_keeps_its_own_result_and_shutdown_releases_hook(self):
        self.assertIsNone(self.lua.eval("ask(actor('VanillaGenerator'))"))
        self.lua.execute("data[builder].CurrentItem=unrelated")
        self.assertFalse(self.lua.eval("ask().bSuccess"))
        self.lua.execute("placement:shutdown()")
        self.assertTrue(self.lua.eval("unhooked[locationPath]"))

    def test_unattached_cabinet_ghost_and_destroyed_site_do_not_reserve_the_mount(self):
        self.lua.execute("cabinet=fixture_actor(false,nil,nominal,recipe)")
        self.assertTrue(self.lua.eval("ask().bSuccess"))
        self.lua.execute("data[cabinet].attachment=other_ship()")
        self.assertTrue(self.lua.eval("ask().bSuccess"))
        self.lua.execute("data[cabinet].attachment=ship")
        self.assertFalse(self.lua.eval("ask().bSuccess"))
        self.lua.execute("data[cabinet].destroying=true")
        self.assertTrue(self.lua.eval("ask().bSuccess"))
        self.lua.execute("pending=fixture_actor(true,nil,nominal,recipe)")
        self.assertFalse(self.lua.eval("ask().bSuccess"))
        self.lua.execute("data[pending].world=actor('OtherWorld')")
        self.assertTrue(self.lua.eval("ask().bSuccess"))
        self.lua.execute("data[pending].world=world;data[pending].destroying=true")
        self.assertTrue(self.lua.eval("ask().bSuccess"))

    def test_named_out_hits_block_the_mount(self):
        self.lua.execute("blocker=actor('NewModule');namedHits=true")
        self.assertFalse(self.lua.eval("ask().bSuccess"))

    def test_basic_requires_its_own_skill(self):
        self.lua.execute("""
            selectItem(basicRecipe);aimAtBasic()
            assert(not ask().bSuccess)
            researched=false;basicResearched=true
            assert(ask().bSuccess and confirm(basicRecipe)==siteResult)
        """)

    def test_other_automator_reserves_the_winch_at_preview_and_confirmation(self):
        self.lua.execute("researched=true; basicResearched=true")
        for requested, existing, aim in (
            ("basicRecipe", "recipe", "aimAtBasic()"),
            ("recipe", "basicRecipe", "aim(net)"),
        ):
            for phase, reservation in (
                ("installed", f"fixture_actor(false,ship,nominal,nil,{existing}==basicRecipe)"),
                ("under construction", f"fixture_actor(true,nil,nominal,{existing})"),
            ):
                with self.subTest(requested=requested, phase=phase):
                    self.lua.execute(f"selectItem({requested}); {aim}")
                    self.assertTrue(self.lua.eval("ask().bSuccess"))
                    stock_calls = self.lua.eval("stockCalls")
                    self.lua.execute(f"occupant={reservation}")
                    # Confirm the previously green preview before asking for another one.
                    self.assertIsNone(self.lua.eval(f"confirm({requested})"))
                    self.assertEqual(self.lua.eval("stockCalls"), stock_calls)
                    self.lua.execute("preview=ask()")
                    self.assertFalse(self.lua.eval("preview.bSuccess"))
                    self.assertEqual(self.lua.eval("preview.FailureReason"), "This winch already has an automator.")
                    self.lua.execute("data[occupant].destroying=true")
                    self.assertTrue(self.lua.eval(f"ask().bSuccess and confirm({requested})==siteResult"))

    def test_old_vault_entry_or_stale_hotbar_cannot_authorize_construction(self):
        self.lua.execute("selectItem(recipe);researched=false")
        self.assertIn("Research",self.lua.eval("ask().FailureReason"))
        self.assertIsNone(self.lua.eval("confirm(recipe)"))
        self.lua.execute("researched=true;assert(ask().bSuccess);researched=false")
        self.assertIsNone(self.lua.eval("confirm(recipe)"))
        self.lua.execute("researched=true")
        self.assertTrue(self.lua.eval("confirm(recipe)==siteResult and stockCalls==1"))

    def test_loose_physics_object_and_another_vehicle_block_the_mount(self):
        self.lua.execute("blocker=actor('MovingObstruction')")
        for object_type in (3,4):
            with self.subTest(object_type=object_type):
                self.lua.globals().blockerType=object_type
                self.assertFalse(self.lua.eval("ask().bSuccess"))

    def test_missing_native_attachment_cannot_authorize_world_space_placement(self):
        self.lua.execute("data[ship].K2_GetRootComponent=function() return actor('SceneRoot') end")
        self.assertFalse(self.lua.eval("ask().bSuccess"))

    def test_overlap_hit_at_the_stock_winch_is_still_a_valid_target(self):
        self.lua.execute('gen["Out Hit"].bBlockingHit=false')
        self.assertTrue(self.lua.eval("ask().bSuccess"))

    def test_native_confirm_rechecks_occupancy_and_limits_interception_to_this_item(self):
        self.assertTrue(self.lua.eval("ask().bSuccess"))
        self.assertTrue(self.lua.eval("confirm(recipe)==siteResult and stockCalls==1"))
        self.assertTrue(self.lua.eval("lastStock.owner==pawn and lastStock.item==recipe and lastStock.attach==root"))
        self.lua.execute("fixture_actor(true,ship,nominal,recipe)")
        self.assertIsNone(self.lua.eval("confirm(recipe)"))
        self.assertEqual(self.lua.eval("stockCalls"), 1)
        self.assertIsNone(self.lua.eval("confirm(unrelated)"))
        # Selection has changed but UE is finishing a call through the interim factory.
        self.lua.execute("data[builder].CurrentItem=unrelated;aim(nil);blocker=actor('BlockedWinch')")
        self.assertTrue(self.lua.eval("confirm(unrelated)==siteResult and stockCalls==2"))
        self.assertTrue(self.lua.eval("lastStock.item==unrelated and not factoryInstance.bCommitAllowed"))
        self.assertIsNone(self.lua.eval("confirm(unrelated,root,nominal,actor('OtherPawn'))"))
        self.assertEqual(self.lua.eval("stockCalls"),2)

    def test_native_confirm_rejects_another_parent_and_obstruction_after_preview(self):
        self.assertTrue(self.lua.eval("ask().bSuccess"))
        self.assertIsNone(self.lua.eval("confirm(recipe,actor('OtherRoot'))"))
        self.assertIsNone(self.lua.eval("confirm(recipe,root,{X=0,Y=0,Z=0})"))
        self.assertIsNone(self.lua.eval("confirm(recipe,root,nominal,actor('RemoteBuilder'))"))
        self.lua.execute("blocker=actor('ObstacleAfterPreview')")
        self.assertIsNone(self.lua.eval("confirm(recipe)"))
        self.assertEqual(self.lua.eval("stockCalls"),0)

    def test_void_validator_clears_stale_approval_and_missing_hook_creates_no_site(self):
        self.lua.execute("""
            assert(ask().bSuccess)
            factoryInstance.bCommitAllowed=true
            validate(unrelated,root,{Translation=nominal},pawn)
            assert(factoryInstance.bCommitAllowed==false)
            hooks[validatePath]=nil
            assert(not confirm(recipe) and stockCalls==0)
        """)

    def test_recipe_change_map_reset_and_shutdown_restore_the_stock_factory(self):
        for release in ("selectItem(unrelated)", "placement:reset()", "placement:shutdown()"):
            self.lua.execute("selectItem(recipe);assert(ask().bSuccess)")
            self.assertTrue(self.lua.eval('builder["Fabricator Factory"]==scoped'))
            self.lua.execute(release)
            self.assertTrue(self.lua.eval('builder["Fabricator Factory"]==activeFactory'))
        self.assertTrue(self.lua.eval("unhooked[locationPath] and unhooked[setItemPath] and unhooked[validatePath]"))

    def test_selecting_into_a_red_ghost_cannot_reuse_a_previous_recipes_green_state(self):
        self.lua.execute("selectItem(unrelated);data[builder].CanPlace=true;aim(nil);selectItem(recipe)")
        self.assertTrue(self.lua.eval('builder["Fabricator Factory"]==scoped'))
        self.assertIsNone(self.lua.eval("confirm(recipe)"))
        self.assertEqual(self.lua.eval("stockCalls"),0)

    def test_registration_waits_for_pawn_and_cooked_factory_reference_after_travel(self):
        self.lua.execute("""
            placement:shutdown();hooks={};data[controller].Pawn=nil
            placement:tick();assert(not placement.ready and next(hooks)==nil)
            data[controller].Pawn=pawn;data[gen].BuildFactoryClass=nil;advance(2)
            placement:tick();assert(not placement.ready and next(hooks)==nil)
            data[gen].BuildFactoryClass=scoped;advance(2);placement:tick()
            assert(placement.ready and ask().bSuccess)
            selectItem(unrelated);data[gen].BuildFactoryClass=nil;selectItem(recipe)
            assert(not ask().bSuccess and builder["Fabricator Factory"]==activeFactory)
        """)
        self.assertEqual(self.lua.eval("syncLoads"),0)
