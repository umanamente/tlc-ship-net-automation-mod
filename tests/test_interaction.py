"""The exact center ray and primary mapped input route only visible controller surfaces."""
import unittest
from lupa.lua54 import LuaRuntime
from test_observer import SCRIPTS

class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().scripts=SCRIPTS.as_posix()
        self.lua.execute(r"""
            package.path=scripts.."/?.lua;"..package.path
            local function object(id)
                return {IsValid=function() return true end, GetAddress=function() return id end}
            end
            actor=object(5);part=object(7);wall=object(9);socket=object(11);pawn=object(2);pc=object(3);ptr=object(4)
            pc.Pawn=pawn;ptr.bAllowInteract=true;ptr.MaxReach=200
            function ptr:GetOwner() return pawn end
            function pc:GetPlayerFocusWidget() return menu and wall end
            function part:GetOwner() return actor end
            function socket:GetOwner() return actor end
            function wall:GetOwner() return pawn end
            function wall:IsA(_) return false end
            function actor:GetTransform() return {} end
            function ptr:GetHoverResult() return {Component={Get=function() return coarse or part end},TraceStart={},TraceEnd={}} end
            local p={X=-4,Y=57.6,Z=30};local n={X=0,Y=1,Z=0}
            function StaticFindObject(path)
                if path:find("GameplayStatics") then return {IsGamePaused=function() return paused or false end} end
                if path:find("KismetSystem") then return {LineTraceSingle=function(_,who,a,b,channel,complex,ignore,debug,hit)
                    assert(who==pc and complex and ignore[1]==pawn and debug==0)
                    if channel==0 then
                        hit.Distance=foreground;hit.Component={Get=function() return wall end};return foreground~=nil
                    end
                    assert(channel==2)
                    hit.Distance=distance or 100;hit.ImpactPoint=point or p;hit.ImpactNormal=normal or n
                    hit.Component={Get=function() return exact or part end};return true
                end} end
                return {InverseTransformLocation=function(_,f,v) return v end,InverseTransformDirection=function(_,f,v) return v end,
                    GetForwardVector=function(_,v) return v end}
            end
            w=require("shipnet.interaction").new()
            w.actor,w.pc,w.pointer,w.parts,w.geometry=actor,pc,ptr,{[7]="body"},require("shipnet.model")
            calls={}
            w.dispatch=function(kind,player) assert(player==pc);calls[#calls+1]=kind;return true end
            w._keyState=function() return pressed,pulse end
        """)
    def test_different_mesh_surfaces(self):
        self.assertEqual(self.lua.eval("select(1,w:target())")[0],"screen")
        self.lua.execute("point={X=35,Y=57.6,Z=30}")
        self.assertEqual(self.lua.eval("select(1,w:target())")[0],"storage")
        self.lua.execute("point={X=-4,Y=58,Z=46};normal={X=0,Y=1,Z=0}")
        self.assertEqual(self.lua.eval("select(1,w:target())")[0],"storage")
        self.lua.execute("point={X=-68,Y=0,Z=29.5};normal={X=-1,Y=0,Z=0}")
        self.assertIsNone(self.lua.eval("w:target()"))
    def test_occluded_foreign_unreachable_and_menu_do_not_trigger(self):
        for setup,undo in [("foreground=60","foreground=nil"),("coarse=wall","coarse=nil"),
                           ("exact=wall","exact=nil"),("distance=205","distance=nil"),
                           ("menu=true","menu=false"),("pc.bShowMouseCursor=true","pc.bShowMouseCursor=false"),
                           ("ptr.bAllowInteract=false","ptr.bAllowInteract=true"),("paused=true","paused=false")]:
            self.lua.execute(setup)
            self.assertIsNone(self.lua.eval("w:target()"),setup)
            self.lua.execute(undo)
    def test_one_dispatch_per_bound_key_press_and_releases_through_menus(self):
        self.lua.execute("pressed=true; w:poll();w:poll();pressed=false;w:poll();pressed=true;w:poll();w:poll()")
        self.assertEqual(self.lua.eval("#calls"),1)
        self.lua.execute("menu=true;pressed=false;w:poll();pressed=true;w:poll();menu=false;w:poll()")
        self.assertEqual(self.lua.eval("#calls"),1)
        self.lua.execute("pressed=false;w:poll();pressed=true;w:poll()")
        self.assertEqual(self.lua.eval("#calls"),2)

    def test_short_tap_reported_by_engine_once(self):
        self.lua.execute("pressed=false;pulse=false;w:poll();pulse=true;w:poll();w:poll();pulse=false;w:poll()")
        self.assertEqual(self.lua.eval("#calls"),1)

    def test_cooked_carrier_and_runtime_faces_target_same_screen(self):
        self.lua.execute("""
            native={IsValid=function() return true end,GetAddress=function() return 22 end,GetOwner=function() return actor end}
            w.carrierMesh=native;coarse=native;exact=part
        """)
        self.assertEqual(self.lua.eval("select(1,w:target())")[0],"screen")
        self.lua.execute("coarse=part;exact=native;point={X=35,Y=57.6,Z=30}")
        self.assertEqual(self.lua.eval("select(1,w:target())")[0],"storage")
        self.lua.execute("coarse=socket")
        self.assertIsNone(self.lua.eval("w:target()"))

    def test_socket_and_storage_do_not_share_a_press_on_left_fascia(self):
        self.lua.execute("""
            point={X=-48,Y=56,Z=31}
            function socket:SetCollisionResponseToChannel(n,v) if n==14 then coarse=v==0 and part or socket end end
            w.socketShapes={{c=socket,responses={[14]=2}}}
            w.socketFace={X=-74.4,Y=-.5,Z=29.8}
            function actor:K2_GetActorLocation() return {X=0,Y=0,Z=0} end
            pc.PlayerCameraManager={IsValid=function() return true end,
                GetCameraLocation=function() return eye end,GetCameraRotation=function() return dir end}
            eye={X=-48,Y=155,Z=31};dir={X=0,Y=-1,Z=0}
            w:_enableInletWhenAimed()
        """)
        self.assertIs(self.lua.eval("w.socketAllowed"),False)
        self.assertEqual(self.lua.eval("select(1,w:target())")[0],"storage")
        self.lua.execute("coarse=socket")
        self.assertIsNone(self.lua.eval("w:target()"))  # No duplicate if last frame still belongs to the socket.
        self.lua.execute("eye={X=-160,Y=-.5,Z=29.8};dir={X=1,Y=0,Z=0};w:_enableInletWhenAimed();exact=socket")
        self.assertIs(self.lua.eval("w.socketAllowed"),True)
        self.assertIsNone(self.lua.eval("w:target()"))

    def test_enhanced_action_and_physical_key_consume_the_same_press_once(self):
        self.lua.execute("""
            w._keyState=nil
            w.lastKeyRefresh=os.time();w.keys={{KeyName="rebinding"}};w.action=part
            local record={TriggerEvent=0,LastTriggeredWorldTime=0}
            pc.PlayerInput={IsValid=function() return true end,
                ActionInstanceData={Contains=function(_,a) return a==part end, Find=function() return record end}}
            function pc:IsInputKeyDown(key) assert(key.KeyName=="rebinding");return held end
            function pc:WasInputKeyJustPressed(key) return false end
            held=false;w:poll();record.TriggerEvent=1;record.LastTriggeredWorldTime=5;w:poll()
            held=true;record.TriggerEvent=1;record.LastTriggeredWorldTime=6;w:poll()
            record.TriggerEvent=16;held=false;w:poll();record.TriggerEvent=0;w:poll()
            -- A tap occurred and completed between two loop callbacks.
            record.LastTriggeredWorldTime=7;w:poll()
        """)
        self.assertEqual(self.lua.eval("#calls"),2)

    def test_basic_module_without_container_routes_only_its_display_to_settings(self):
        self.lua.execute("""
            local basic=require("shipnet.variants").basic
            local display={X=120,Y=116.25,Z=-21}
            local lookup=StaticFindObject
            function StaticFindObject(path)
                if path:sub(1,#basic.carrier+1)==basic.carrier..":" then return actor end
                return lookup(path)
            end
            setmetatable(actor,{__index=function(_,key)
                assert(key~="InteractiveObject" and key~="InteractEnabled","Basic has no container")
            end})
            EFindName={FNAME_Find=0}
            FName=function(id) return id end
            LoopInGameThreadWithDelay=function() return 1 end
            function part:SetCollisionProfileName() end
            function part:SetCollisionEnabled() end
            function part:SetCollisionResponseToChannel() end
            function part:SetGenerateOverlapEvents() end
            local hooks={}
            function RegisterHook(path,fn) hooks[path:match(":(.*)$")]=fn;return 1,2 end
            function UnregisterHook(path) hooks[path:match(":(.*)$")]=nil end
            function ptr:GetPointerLocation(start,direction)
                start.X,start.Y,start.Z=120,165,-21;direction.X,direction.Y,direction.Z=0,-1,0
                return true
            end
            local dispatch=w.dispatch
            w:mount(actor,{body=part,drive=part},basic.geometry,dispatch,nil,nil,true,basic)
            w.pc,w.pointer=pc,ptr
            local function wrap(x) return {get=function() return x end} end
            point=display
            hooks.ResolveWinchSurface(wrap(actor),wrap(pawn))
            assert(actor.WinchAimSurface==1)
            hooks.WinchControlTriggered(wrap(actor),wrap({Controller=pc}))
            point={X=160,Y=116.25,Z=-21}
            hooks.ResolveWinchSurface(wrap(actor),wrap(pawn))
            assert(actor.WinchAimSurface==2)
            hooks.WinchControlTriggered(wrap(actor),wrap({Controller=pc}))
            exact=socket;point=display
            hooks.ResolveWinchSurface(wrap(actor),wrap(pawn))
            assert(actor.WinchAimSurface==2)
            w:unmount()
            assert(next(hooks)==nil)
        """)
        self.assertEqual(self.lua.eval("table.concat(calls,',')"),"screen")

    def test_constructed_screen_uses_only_native_action_and_rechecks_aim_on_press(self):
        self.lua.execute("""
            w.native=true;w.nextNativeCheck=0
            boxAction={InteractType=1,IsValid=function() return true end}
            w.containerAction=boxAction
            local lookup=StaticFindObject
            function StaticFindObject(path)
                if path:find("WinchAutomator_C:",1,true) then return actor end
                return lookup(path)
            end
            function ptr:GetPointerLocation(start,direction)
                start.X,start.Y,start.Z=-4,157.6,30;direction.X,direction.Y,direction.Z=0,-1,0
                return true
            end
            callbacks={}
            function RegisterHook(path,fn) callbacks[path:match(":(.*)$")]=fn;return 1,2 end
            function UnregisterHook(path) callbacks[path:match(":(.*)$")]=nil end
            function wrap(x) return {get=function() return x end} end
            w:_registerNative()
            coarse=wall -- previous frame; current ray now lands on the screen
            callbacks.ResolveWinchSurface(wrap(actor),wrap(pawn))
        """)
        self.assertEqual(self.lua.eval("actor.WinchAimSurface"),1)
        self.assertEqual(self.lua.eval("boxAction.InteractType"),3)
        self.assertIsNone(self.lua.eval("w:hint()"))
        self.lua.execute("pressed=true;w:poll()")
        self.assertEqual(self.lua.eval("#calls"),0)
        self.lua.execute("callbacks.WinchControlTriggered(wrap(actor),wrap({Controller=wall}))")
        self.assertEqual(self.lua.eval("#calls"),0)
        self.lua.execute("callbacks.WinchControlTriggered(wrap(actor),wrap({Controller=pc}))")
        self.assertEqual(self.lua.eval("#calls"),1)
        self.lua.execute("""
            point={X=50,Y=57.6,Z=30}
            callbacks.WinchControlTriggered(wrap(actor),wrap({Controller=pc}))
            callbacks.ResolveWinchSurface(wrap(actor),wrap(pawn))
        """)
        self.assertEqual(self.lua.eval("#calls"),1)
        self.assertEqual(self.lua.eval("actor.WinchAimSurface"),0)
        self.assertEqual(self.lua.eval("boxAction.InteractType"),1)
        self.lua.execute("exact=socket; callbacks.ResolveWinchSurface(wrap(actor),wrap(pawn))")
        self.assertEqual(self.lua.eval("actor.WinchAimSurface"),2)
        self.assertEqual(self.lua.eval("boxAction.InteractType"),3)
        self.lua.execute("exact=part; callbacks.ResolveWinchSurface(wrap(actor),wrap(wall))")
        self.assertEqual(self.lua.eval("actor.WinchAimSurface"),2)
        self.lua.execute("w:unmount()")
        self.assertTrue(self.lua.eval("next(callbacks)==nil"))
        self.assertEqual(self.lua.eval("boxAction.InteractType"),1)

if __name__=="__main__":
    unittest.main()
