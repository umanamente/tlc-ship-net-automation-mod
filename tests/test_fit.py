"""Runtime rail fit, actor lifetime, placement, cable guards and pose readback."""
import unittest
from lupa.lua54 import LuaRuntime
from test_observer import SCRIPTS, WORLD

FIT = r"""
local function xyz(x,y,z) return {X=x,Y=y,Z=z} end
local function spin(v,yaw)
    local a=math.rad(yaw)
    return xyz(v.X*math.cos(a)-v.Y*math.sin(a),v.X*math.sin(a)+v.Y*math.cos(a),v.Z)
end
local function add(a,b) return xyz(a.X+b.X,a.Y+b.Y,a.Z+b.Z) end
local function sub(a,b) return xyz(a.X-b.X,a.Y-b.Y,a.Z-b.Z) end
local function world_transform(t,p) return add(t.xyz,spin(p,t.yaw)) end
local function local_transform(t,p) return spin(sub(p,t.xyz),-t.yaw) end
local function place(ob,origin,yaw)
    data[ob].GetTransform=function() return {xyz=origin,yaw=yaw} end
    data[ob].K2_GetActorLocation=function() return origin end
end
local function component(owner,title,point)
    local comp=actor(title)
    data[comp].owner=owner
    data[comp].K2_GetComponentLocation=function() return world_transform(owner:GetTransform(),point) end
    data[comp].K2_GetComponentToWorld=function() return {xyz=comp:K2_GetComponentLocation(),yaw=owner:GetTransform().yaw} end
    return comp
end
place(net,xyz(41000,27000,-100),90); place(ship,xyz(0,0,0),0)
local netroot=component(net,"NetRoot",xyz(0,0,0))
local shiproot=component(ship,"ShipRoot",xyz(0,0,0))
data[net].K2_GetRootComponent=function() return netroot end
data[ship].K2_GetRootComponent=function() return shiproot end
local toggle=actor("Switch")
place(toggle,world_transform(net:GetTransform(),xyz(30,-290,180)),90)
local attachment=component(net,"SwitchChild",xyz(22,-291,187)); data[attachment].ChildActor=toggle
data[net].SwitchChildActor=attachment
data[toggle].Pivot=component(toggle,"HandlePivot",xyz(0,0,5))
local boxAttachment=component(net,"DrawerChild",xyz(140,-190,60))
data[boxAttachment].ChildActor=container
data[net].ContainerChildActor=boxAttachment
data[net].ContainerLocation=component(net,"Landing",xyz(265,-190,60))
rail=component(net,"FrameMesh",xyz(0,0,0));data[net].SM_miscInt_e=rail
data[rail].GetLocalBounds=function(_,lo,hi) lo.min=xyz(-80,-280,0);hi.max=xyz(217,-120,200) end
data[rail].GetCollisionResponseToChannel=function(_,ch) assert(ch==3);return 2 end
data[rail].K2_LineTraceComponent=function(_,p,q,complex,show,persist,hit,n)
    assert(not show and not persist)
    local localP=local_transform(net:GetTransform(),p)
    local localQ=local_transform(net:GetTransform(),q)
    assert(localP.Z>localQ.Z)
    if math.abs(localP.X-214)>.1 or (singleHit and math.abs(localP.Y+190)>.1) then return false end
    hit.HitLocation=world_transform(net:GetTransform(),xyz(localP.X,localP.Y,126))
    n.HitNormal=xyz(0,0,1)
    return true
end
place(container,boxAttachment:K2_GetComponentLocation(),90)
local cb=component(container,"CargoShell",xyz(0,0,0))
data[cb].GetLocalBounds=function(_,low,high)
    low.min=xyz(-60,-20,-30); high.max=xyz(60,20,45)
end
data[container].K2_GetComponentsByClass=function() return {remote_param(cb)} end
local mathlib=actor("Math")
data[mathlib].InverseTransformLocation=function(_,t,p) return local_transform(t,p) end
data[mathlib].TransformLocation=function(_,t,p) return world_transform(t,p) end
data[mathlib].InverseTransformDirection=function(_,t,n) return spin(n,-t.yaw) end
data[mathlib].MakeTransform=function(_,p,r,s) return {xyz=p,yaw=r.Yaw} end
local cls=actor("StaticMeshActor")
EFindName={FNAME_Find=0}
local names={}
function FName(v,mode)
    assert(mode==0)
    names[v]=names[v] or {name=v}
    return names[v]
end
function saved_tags(owner,...)
    local tags={GetArrayNum=function(t) return #t end}
    tags.Empty=function(t)
        data[owner].tagRewrites=(data[owner].tagRewrites or 0)+1
        for i=#t,1,-1 do t[i]=nil end
    end
    for _,name in ipairs({...}) do tags[#tags+1]=FName(name,0) end
    data[owner].Tags=tags
    data[owner].ActorHasTag=function(_,tag)
        for _,existing in ipairs(tags) do if existing.name==tag.name then return true end end
        return false
    end
end
local lookup=StaticFindObject
function StaticFindObject(path)
    if path=="/Script/Engine.StaticMeshActor" or path=="/Script/Engine.StaticMeshComponent" then return cls end
    if path=="/Script/Engine.Default__KismetMathLibrary" then return mathlib end
    return lookup(path)
end
spawnCount=0; destroyed=0
data[world].SpawnActor=function(_,class,location,rot)
    assert(class==cls and rawget(location,"X") and rawget(rot,"Pitch"))
    spawnCount=spawnCount+1
    preview=actor("Preview"..spawnCount)
    local root=component(preview,"PreviewRoot"..spawnCount,xyz(0,0,0))
    data[root].SetMobility=function(_,value) assert(value==2) end
    data[root].SetCollisionEnabled=function(_,value) assert(value==0) end
    data[preview].K2_GetRootComponent=function() return root end
    data[preview].K2_AttachToComponent=function(_,parent,socket,lr,rr,sr,weld)
        assert(type(socket)=="table" and socket.name=="None" and lr==2 and rr==2 and sr==2 and not weld)
        if attachmentFailure then return false end
        data[preview].attachment=parent:GetOwner()
        return true
    end
    data[root].K2_SetRelativeLocationAndRotation=function(_,p,r,sweep,hit,teleport)
        assert(not sweep and teleport)
        local parent=data[preview].attachment:GetTransform()
        place(preview,world_transform(parent,p),parent.yaw+r.Yaw)
    end
    data[preview].K2_DestroyActor=function(self) destroyed=destroyed+1;data[self].invalid=true end
    return preview
end
local power={new=function() return {
    before_remove=function() return {allowed=not connected,status=connected and "detach_cable_first" or "clear"} end,
    inspect=function() return {status="ready",connected=connected or false} end,
    bindBuilt=function() return {status="native_input"} end,
    builtStatus=function() return {status="native_input"} end,
    reset=function() end,mount=function() return {status="ready"} end
} end}
local model=require("shipnet.model")
function model.build() return {ok=not meshFailure,error=meshFailure and "mesh failure",triangles=11} end
function model.pose(_,h,r) posed={h,r};return true end
survey={status="measured",ship=ship:GetFullName(),net=net:GetFullName(),coordinateFrame="same_world",candidates={}}
package.loaded["shipnet.model"]=model
package.loaded["shipnet.fit_power"]=power
package.loaded["shipnet.survey"]={capture=function() return survey end}
fit=require("shipnet.fit").new()
"""

class FitTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts = SCRIPTS.as_posix()
        self.lua.execute('package.path = scripts .. "/?.lua;" .. package.path')
        self.lua.execute(WORLD)
        self.lua.execute(FIT)

    def test_live_pivot_in_winch_frame_and_signed_drawer_diagnostic(self):
        self.assertEqual(self.lua.eval("fit:show().status"), "shown")
        self.lua.execute("data[net].FullyRaised=false")
        self.assertIs(self.lua.eval("fit:status().stockFullyRaised"),False)
        self.assertIs(self.lua.eval("fit:status().stockNetDropped"),True)
        row=self.lua.eval("fit:report()")
        self.assertIsNone(row["measurementError"])
        self.assertEqual(row["pivotSource"], "switch_pivot_component")
        self.assertAlmostEqual(row["datums"]["coupling"]["X"], 30)
        self.assertAlmostEqual(row["datums"]["coupling"]["Z"], 185)
        self.assertAlmostEqual(row["couplingToSwitchCm"], 0, places=5)
        self.assertAlmostEqual(row["drawerTopCm"],105)
        self.assertAlmostEqual(row["seatPlaneMinusDrawerTopCm"],185-60.2-105)
        self.assertEqual(row["railSurvey"]["status"],"crossmember_surface")
        self.assertAlmostEqual(row["railSurvey"]["seatPlaneMinusSupportCm"],185-60.2-126)
        self.assertAlmostEqual(row["footprint"]["currentOverlapCm"]["X"],112.29)
        self.assertAlmostEqual(row["footprint"]["landingOverlapCm"]["X"],18.71)
        self.assertAlmostEqual(row["footprint"]["landingOverlapCm"]["Y"],40)
        case=row["footprint"]["caseBaseAabbCm"]
        self.assertAlmostEqual(case["max"]["Y"]-case["min"]["Y"],116)
        self.assertGreater(len(row["footprint"]["rightProfileLocalCm"]),2)
        self.lua.execute('fit:move("Yaw",45); fit:move("X",7)')
        row=self.lua.eval("fit:report()")
        self.assertAlmostEqual(row["couplingToSwitchCm"], 7, places=5)
        self.assertAlmostEqual(row["datums"]["coupling"]["Y"],-290)
        pose=self.lua.eval("fit:pose(85,90)")
        self.assertEqual(pose["driveDegrees"],90)
        self.assertEqual(pose["hatchDegrees"],2)
        self.assertEqual(self.lua.eval("posed[1]"),2)
        self.assertEqual(self.lua.eval("fit:reset().offset.X"),0)
        self.assertEqual(self.lua.eval("fit:show().status"),"shown")
        self.assertEqual(self.lua.eval("spawnCount"),1)

    def test_socket_guard_protects_attached_cable_and_travel_cleans_up(self):
        self.lua.execute('fit:show({Z=8}); connected=true')
        self.assertEqual(self.lua.eval('fit:hide("debug_disabled").status'),"cable_guard")
        self.assertEqual(self.lua.eval('fit:move("Z",5).offset.Z'),8)
        self.assertEqual(self.lua.eval('fit:reset().status'),"cable_guard")
        self.assertEqual(self.lua.eval('fit:show({X=2}).power.guard.status'),"detach_cable_first")
        self.assertEqual(self.lua.eval('fit:hide("map_change").visible'),False)
        self.assertEqual(self.lua.eval("destroyed"),1)

    def test_built_carrier_skips_ghosts_and_unbinds_without_destroying_the_saved_actor(self):
        self.lua.execute("""
            local api=require("shipnet.fit")
            local path=api.builtClass
            local persist="/Script/Voyage.Default__VoyagePersistentSubsystem"
            carrier=actor("Built",{[path]=true}); local root=actor("BoxMesh"); data[root].owner=carrier
            saved_tags(carrier,"Detachable","Custom_42","Snapped","Detachable","Custom_42")
            data[carrier].attachment=net; data[carrier].K2_GetRootComponent=function() return root end
            data[carrier].StaticMesh=root; data[root].visible=true
            inv=actor("BuiltInventory",{["/Script/Voyage.VoyageInventoryWeightLimitedComponent"]=true})
            data[inv].owner=carrier; data[inv].Access=2
            getmetatable(inv).__newindex=function(self,key,value)
                assert(key=="Access")
                data[self].Access=value
            end
            data[carrier].VoyageInventoryWeightLimited=inv
            data[root].IsVisible=function(self) return data[self].visible end
            data[root].SetVisibility=function(self,v) data[self].visible=v end
            local sub=actor("Persistence")
            data[sub].GetPersistentSubsystem=function(_,w) assert(w==world);return sub end
            data[sub].IsPersistentActor=function(_,a) return a==carrier and purchased==true end
            data[sub].GetPersistentActorComponent=function() return {PersistentUniqueIdRuntime=123} end
            local cls=actor("BuiltClass")
            local old=StaticFindObject
            function StaticFindObject(p) if p==persist then return sub elseif p==path then return cls else return old(p) end end
            function FindAllOf(name) assert(name=="BP_Module_WinchAutomator_C");return {carrier} end
            manager=require("shipnet.built_controller").new({handlers={}})
            builtLocation,builtAngle=api.builtMount(ship,net)
            manager:tick()
        """)
        self.assertFalse(self.lua.eval("manager:isBound()"))
        self.assertEqual(self.lua.eval("#carrier.Tags"),5)
        self.assertEqual(self.lua.eval("inv.Access"),2)
        self.assertEqual(self.lua.eval("builtAngle.Yaw"),180)
        self.assertAlmostEqual(self.lua.eval("builtLocation.X"),147.779)
        self.lua.execute("purchased=true;advance(2);manager:tick(); builtRuntime=manager:runtimeForInteraction()")
        self.assertTrue(self.lua.eval("manager:isBound() and builtRuntime:status().visible"))
        self.assertTrue(self.lua.eval('''#carrier.Tags==4 and carrier.Tags[1].name=="Custom_42"
            and carrier.Tags[2].name=="Snapped" and carrier.Tags[3].name=="Custom_42" and carrier.Tags[4].name=="NoGrab"'''))
        self.assertEqual(self.lua.eval("inv.Access"),0)
        self.assertFalse(self.lua.eval("carrier.StaticMesh:IsVisible()"))
        self.lua.execute("manager:reset()")
        self.assertTrue(self.lua.eval("not manager:isBound() and carrier:IsValid() and carrier.StaticMesh:IsVisible()"))
        self.assertEqual(self.lua.eval("spawnCount+destroyed"),0)

    def test_hidden_box_labels_cannot_intercept_the_drawer_and_cleanup_restores_their_state(self):
        self.lua.execute("""
            local persist=actor("Persistence")
            data[persist].GetPersistentSubsystem=function() return persist end
            data[persist].IsPersistentActor=function() return true end
            local old=StaticFindObject
            function StaticFindObject(path)
                if path=="/Script/Voyage.Default__VoyagePersistentSubsystem" then return persist end
                return old(path)
            end
            package.loaded["shipnet.device_storage"]={forCarrier=function() return {} end}
            function visual(owner,key,visible,collision)
                local part=actor(key)
                data[owner][key]=part
                local state=data[part]
                state.owner,state.visible,state.collision=owner,visible,collision
                state.IsVisible=function() return state.visible end
                state.GetCollisionEnabled=function() return state.collision end
                state.SetVisibility=function(_,v) state.visible=v end
                state.SetCollisionEnabled=function(_,v) state.collision=v end
                return state
            end
        """)
        for variant in ("basic", "advanced"):
            with self.subTest(variant=variant):
                self.lua.globals().variant = variant
                self.lua.execute("""
                    local kind=require("shipnet.variants")[variant]
                    local carrier=actor("Built"..variant,{[kind.carrier]=true})
                    saved_tags(carrier,"NoFabrication","NoGrab","Snapped","NoGrab","Detachable")
                    data[carrier].attachment=ship
                    data[carrier].K2_GetRootComponent=function() return carrier.StaticMesh end
                    if variant=="basic" then
                        local p=actor("PersistentComponent")
                        local none={ToString=function() return "None" end}
                        data[p].owner,data[p].PersistentUniqueIdRuntime=carrier,123
                        data[p].LastStoredZoneId,data[p].CurrentRuntimeZoneId=none,none
                        data[carrier].PersistentComponent=p
                        data[StaticFindObject("/Script/Voyage.Default__VoyagePersistentSubsystem")].PersistentActors={
                            Contains=function() return false end}
                    end
                    local hull=visual(carrier,"StaticMesh",true,3)
                    local label,text
                    if variant=="advanced" then
                        label=visual(carrier,"VoyageContainerTextWidget",true,1)
                        text=visual(carrier,"TextRender",false,0)
                    end
                    local socket=visual(carrier,"WinchPowerInlet",true,1)
                    local drawer=visual(container,"LeftIconPlane",true,3)
                    data[carrier].LeftIconPlane=container.LeftIconPlane
                    local fit=require("shipnet.fit").new()
                    local hasTag=data[carrier].ActorHasTag
                    data[carrier].ActorHasTag=function() return false end
                    assert(fit:bindBuilt(carrier,ship,net).status=="error")
                    assert(#carrier.Tags==5 and carrier.Tags[4].name=="NoGrab" and carrier.Tags[5].name=="Detachable")
                    data[carrier].ActorHasTag=hasTag
                    local bindPower=fit.power.bindBuilt
                    fit.power.bindBuilt=function() error("later binding failed") end
                    assert(fit:bindBuilt(carrier,ship,net).status=="error")
                    assert(hull.visible and hull.collision==3)
                    if label then assert(label.visible and label.collision==1) end
                    fit.power.bindBuilt=bindPower
                    assert(fit:bindBuilt(carrier,ship,net).visible)
                    assert(not hull.visible and hull.collision==3)
                    if label then assert(not label.visible and label.collision==0) end
                    assert(socket.visible and socket.collision==1 and drawer.visible and drawer.collision==3)
                    fit:hide("map_change")
                    if label then assert(label.visible and label.collision==1 and not text.visible and text.collision==0) end
                    assert(hull.visible and hull.collision==3)
                    assert(#carrier.Tags==3 and carrier.tagRewrites==3)
                    assert(carrier.Tags[1].name=="NoFabrication" and carrier.Tags[2].name=="NoGrab"
                        and carrier.Tags[3].name=="Snapped")
                """)

    def test_spawn_failure_rolls_back_and_allows_retry(self):
        for key in ("attachmentFailure","meshFailure"):
            with self.subTest(key=key):
                self.lua.execute(f"{key}=true")
                row=self.lua.eval("fit:show()")
                self.assertEqual(row["status"],"error")
                self.assertFalse(row["visible"])
                self.lua.execute(f"{key}=false")
        self.assertEqual(self.lua.eval("spawnCount"),2)
        self.assertEqual(self.lua.eval("destroyed"),2)
        self.assertEqual(self.lua.eval("fit:show().status"),"shown")

    def test_ambiguous_target_and_nonfinite_offset_cannot_spawn(self):
        self.lua.execute('survey.status="ambiguous_net";survey.net=nil;survey.coordinateFrame=nil')
        self.assertEqual(self.lua.eval("fit:show().status"),"ambiguous_net")
        self.assertEqual(self.lua.eval("fit:show({Z=0/0}).status"),"error")
        self.assertEqual(self.lua.eval("spawnCount"),0)

    def test_single_point_and_foreign_collision_never_establish_support(self):
        self.lua.execute("singleHit=true; fit:show()")
        self.assertEqual(self.lua.eval("fit:report().railSurvey.status"),"no_crossmember_surface")
        self.assertIsNone(self.lua.eval("fit:report().railSurvey.supportHeightCm"))
        self.lua.execute("data[rail].owner=ship")
        self.assertEqual(self.lua.eval("fit:report().railSurvey.status"),"fixed_mesh_unavailable")

    def test_relief_envelope_only_applies_to_verified_mesh_at_measured_pose(self):
        self.lua.execute("""
            fit:show()
            data[rail].StaticMesh=actor("HousingMesh")
            data[data[rail].StaticMesh].GetFullName=function() return "StaticMesh /Game/AssetSets/Modules/Fishing/Fishing.Fishing" end
        """)
        self.assertEqual(self.lua.eval("fit:report().housingRelief.status"),"outside_measured_pose")
        self.lua.execute('fit:show({X=-7.9314,Y=-.623675,Z=2.05929})')
        result=self.lua.eval("fit:report().housingRelief")
        self.assertEqual(result["status"],"nominal_relief_profile")
        self.assertAlmostEqual(result["minimumSampledGapXCm"],.33,places=2)
        self.assertEqual(result["testedModelReference"]["bodyMinimumGapXCm"],1.36)
        self.assertAlmostEqual(result["rightBracket"]["insertionCm"],.45)
        self.lua.execute('fit:move("Yaw",5)')
        self.assertEqual(self.lua.eval("fit:report().housingRelief.status"),"outside_measured_pose")

    def test_device_status_reuses_the_inventory_and_net_requested_by_the_user(self):
        self.lua.execute("""
          local switch=data[net].SwitchChildActor.ChildActor
          rotor=actor("SwitchRotator");data[switch].SwitchRotator=rotor
          data[rotor].RelativeRotation={Roll=-80}
          data[switch].TurnON=function() lowered=true end
          data[switch].TurnOFF=function() raised=true end
          function LoopInGameThreadWithDelay(delay,callback)
            assert(delay==20);switchTick=callback
          end
          data[net].NetWeight=23;data[net].FullyRaised=false
          package.loaded["shipnet.model"].setFill=function(mesh,ratio) lastBar=ratio;return true end
          fit.storage={inspect=function(_,a,b) assert(a==preview and b==ship);return {fillRatio=.45} end,
            open=function(_,p,a,b) assert(a==preview and b==ship and p==controller);return true,{} end}
          fit:show()
        """)
        row=self.lua.eval("fit:deviceStatus()")
        self.assertIs(row["netAvailable"],True)
        self.assertIs(row["fullyRaised"],False)
        self.assertEqual(row["netWeightKg"],23)
        self.assertAlmostEqual(self.lua.eval("lastBar"),.45)
        self.assertTrue(self.lua.eval('fit:controlNet("lower")')[0])
        self.lua.execute('data[rotor].RelativeRotation.Roll=23')
        self.assertFalse(self.lua.eval('switchTick()'))
        self.assertEqual(self.lua.eval("posed[2]"),23)
        self.lua.execute('data[rotor].RelativeRotation.Roll=80')
        self.assertTrue(self.lua.eval('switchTick()'))
        self.assertEqual(self.lua.eval("fit.driveDegrees"),80)
        self.assertTrue(self.lua.eval('fit:controlNet("raise")')[0])
        self.lua.execute('data[rotor].RelativeRotation.Roll=-80')
        self.assertTrue(self.lua.eval('switchTick()'))
        self.assertEqual(self.lua.eval("fit.driveDegrees"),-80)
        self.lua.execute('fit:controlNet("lower"); fit:pose(2,35); data[rotor].RelativeRotation.Roll=80')
        self.assertTrue(self.lua.eval('switchTick()'))
        self.assertEqual(self.lua.eval("posed[2]"),35)
        self.assertTrue(self.lua.eval('lowered and raised'))
        self.assertTrue(self.lua.eval('fit:openStorage(controller)')[0])
        self.lua.execute('fit:hide("user")')
        self.assertFalse(self.lua.eval('fit:controlNet("lower")')[0])
        self.assertFalse(self.lua.eval('fit:openStorage(controller)')[0])

    def test_built_cargo_alarm_follows_capacity_and_catch_fit_independently(self):
        self.lua.execute("""
            fit:show()
            fit.built=true
            local weight, capacity = 47.99, 50
            local catch = {ready=true,status="full",remaining=1}
            local reads = 0
            fit.storage={inspect=function()
                return {weightKg=weight,capacityKg=capacity,fillRatio=weight/capacity}
            end}
            package.loaded["shipnet.automation_cargo"]={weight=function() return 5,30 end, inspect=function(winch,cabinet)
                assert(winch==net and cabinet==preview)
                reads=reads+1
                return catch
            end}
            local fraction, alarm
            package.loaded["shipnet.model"].setFill=function(_,fill,warning)
                fraction,alarm=fill,warning
                return true
            end
            local function check(expected)
                local status=fit:deviceStatus()
                assert(not status.automationEnabled and fraction==weight/capacity and alarm==expected)
            end

            data[net].FullyRaised=false
            check(false)
            weight=48;check(true)
            capacity=75;check(false)
            weight=73;check(true)
            assert(reads==0)

            weight=47
            data[net].FullyRaised=true
            catch.ready=false;check(false)
            catch.ready=true;check(true)
            catch.status="available";check(false)
            catch.status="full";check(true)
            data[net].FullyRaised=false;check(false)
            data[net].FullyRaised=true;check(true)
            catch.status="empty";catch.remaining=0;check(false)
            catch.status="unavailable";catch.remaining=nil;check(false)
        """)

    def start_panel_cycle(self):
        self.lua.execute("""
            fit:show()
            fit.built=true
            rawset(preview,"WinchAutomationEnabled",true)
            local game=actor("GameTime")
            data[game].GetTimeSeconds=function(_,cabinet) assert(cabinet==preview);return os.time() end
            local lookup=StaticFindObject
            function StaticFindObject(path)
                if path=="/Script/Engine.Default__GameplayStatics" then return game end
                return lookup(path)
            end
            lever=data[net].SwitchChildActor.ChildActor
            leverOn=true; raises=0; lowers=0
            data[lever].IsOn=function() return leverOn end
            data[lever].TurnOFF=function()
                if rejectRaise then error("switch unavailable") end
                raises=raises+1
                if immediate then leverOn=false end
            end
            data[lever].TurnON=function() lowers=lowers+1;leverOn=true end
            data[net].FullyRaised=false
            catch={space=true,ready=false,remaining=2,status="available"}
            package.loaded["shipnet.automation_cargo"]={
                weight=function() return 29.9,30 end,
                storageFreeWeight=function() return 50 end,
                inspect=function() return catch end,
                unload=function()
                    assert(net.FullyRaised and catch.ready and catch.remaining>0)
                    catch.remaining=catch.remaining-1
                    return {status="moved",remaining=catch.remaining,movedKg=1.25}
                end,
            }
            package.loaded["shipnet.automation_power"]={new=function()
                return {consume=function(_,cabinet,seconds,mode)
                    assert(cabinet==preview);return mode~="off",mode
                end}
            end}
            fit.cycle=require("shipnet.automation").new()
            function poll(n)
                for i=1,n or 1 do
                    advance(.25);fit:tick();assert(not fit.lastCycleError,fit.lastCycleError)
                end
            end
            poll(2)
        """)

    def test_missing_winch_lever_interrupts_the_haul_wait(self):
        self.start_panel_cycle()
        self.lua.execute("""
            poll(10)
            data[lever].invalid=true;poll(8)
            data[lever].invalid=false;poll(12)
            assert(raises==0 and preview.WinchAutomationEnabled)
            poll();assert(raises==1)
        """)

    def test_panel_raise_with_delayed_lever_response_unloads_then_redeploys(self):
        self.start_panel_cycle()
        self.lua.execute("""
            assert(fit.cycle.haulCheck and raises==0)
            assert(fit:controlNet("raise"))
            assert(not fit.cycle.haulCheck and preview.WinchAutomationEnabled)
            poll(2)
            leverOn=false;data[net].NetDropped=false;poll(3)
            data[net].FullyRaised=true;poll(2)
            assert(catch.remaining==2 and raises==1 and lowers==0)
            catch.ready=true;poll(4)
            assert(catch.remaining==2 and lowers==0)
            poll(2)
            assert(catch.remaining==0 and lowers==0)
            poll(4)
            assert(raises==1 and lowers==1 and preview.WinchAutomationEnabled)
        """)

    def test_panel_raise_with_automation_off_does_not_trigger_stock_lever_pickup(self):
        self.start_panel_cycle()
        self.lua.execute("""
            fit:setAutomation(false);poll()
            assert(fit:controlNet("raise"));poll()
            leverOn=false;poll()
            data[net].NetDropped=false;data[net].FullyRaised=true;catch.ready=true;poll(6)
            assert(raises==1 and lowers==0 and catch.remaining==2 and not preview.WinchAutomationEnabled)
            leverOn=true;data[net].NetDropped=true;data[net].FullyRaised=false;catch.ready=false;poll()
            leverOn=false;data[net].NetDropped=false;data[net].FullyRaised=true;catch.ready=true;poll(6)
            assert(raises==1 and lowers==0 and catch.remaining==0 and not preview.WinchAutomationEnabled)
        """)

    def test_native_raise_failure_leaves_cycle_intact_and_physical_reversal_stops_it(self):
        self.start_panel_cycle()
        self.lua.execute("""
            local deadline=fit.cycle.haulCheck.dueAt
            rejectRaise=true
            local sent,err=fit:controlNet("raise")
            assert(not sent and err:find("switch unavailable",1,true))
            assert(preview.WinchAutomationEnabled and not fit.cycle.request and fit.cycle.haulCheck.dueAt==deadline)
            rejectRaise=false;immediate=true
            assert(fit:controlNet("raise"))
            leverOn=true;poll()
            assert(not preview.WinchAutomationEnabled and fit.cycle.status=="Paused by manual control")
            assert(fit:controlNet("raise"))
            assert(not preview.WinchAutomationEnabled)
            fit:setAutomation(true);assert(fit:controlNet("lower"))
            assert(not preview.WinchAutomationEnabled and lowers==1)
        """)

    def test_panel_raise_replaces_pending_automatic_lower(self):
        self.start_panel_cycle()
        self.lua.execute("""
            data[net].FullyRaised=true;catch.ready=true;catch.remaining=0
            poll(5);assert(lowers==1 and fit.cycle.request.on)
            data[net].FullyRaised=false;catch.ready=false;catch.remaining=1
            assert(fit:controlNet("raise"))
            leverOn=false;data[net].NetDropped=false;poll()
            assert(preview.WinchAutomationEnabled and catch.remaining==1)
            data[net].FullyRaised=true;catch.ready=true;poll(9)
            assert(catch.remaining==0 and raises==1 and lowers==2)
        """)

    def test_collision_shape_fallback_clips_to_the_actual_outboard_seat(self):
        self.lua.execute("""
            singleHit=true
            data[rail].StaticMesh={BodySetup={AggGeom={BoxElems={
                GetArrayNum=function() return 1 end,
                {Center={X=212,Y=-190,Z=90},Rotation={Yaw=0},X=9,Y=130,Z=74}}}}}
            fit:show()
        """)
        rail=self.lua.eval("fit:report().railSurvey")
        self.assertEqual(rail["traceStatus"],"no_crossmember_surface")
        self.assertEqual(rail["status"],"authored_collision_box")
        self.assertAlmostEqual(rail["supportHeightCm"],127)
        self.assertAlmostEqual(rail["seatPlaneMinusSupportCm"],185-60.2-127)
        # Slide along the stock axis until the seat no longer covers this box.
        self.lua.execute('fit:move("X",40)')
        self.assertEqual(self.lua.eval("fit:report().railSurvey.status"),"no_crossmember_surface")

    def test_fallback_distinguishes_saved_hull_reference_from_live_geometry(self):
        self.lua.execute('survey.net=nil;survey.status="no_net";survey.coordinateFrame=nil;fit:show()')
        row=self.lua.eval("fit:report()")
        self.assertEqual(row["placementMode"],"saved_barge_reference")
        self.assertEqual(row["stockGeometry"],"unresolved")
        self.assertAlmostEqual(row["datums"]["coupling"]["X"],-1968+22)
        self.lua.execute('survey.net=net:GetFullName();survey.status="measured";survey.coordinateFrame="same_world"')
        live=self.lua.eval("fit:report()")
        self.assertEqual(live["placementMode"],"saved_barge_reference")
        self.assertEqual(live["stockGeometry"],"live")
        self.assertIs(live["stockNetDropped"],True)
        self.assertEqual(self.lua.eval("fit:tick()"),None)
        self.lua.execute('data[controller].world=actor("WorldAfterTravel"); advance(3)')
        self.assertEqual(self.lua.eval("fit:tick().status"),"lost_preview")
        self.assertFalse(self.lua.eval("fit:status().visible"))

if __name__=="__main__":
    unittest.main()
