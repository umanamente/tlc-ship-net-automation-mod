"""Reparented Basic imports old receiver/health by actor ID and old name, once."""
import unittest
from lupa.lua54 import LuaRuntime
from test_observer import SCRIPTS


class BasicSavedStateTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime()
        self.lua.globals().scripts=SCRIPTS.as_posix()
        self.lua.execute("""
            package.path=scripts.."/?.lua;"..package.path
            local names={}
            function FName(name)
                if not names[name] then names[name]={ToString=function() return name end} end
                return names[name]
            end
            local function wrap(v) return {get=function() return v end} end
            function map(rows)
                return {rows=rows,Contains=function(m,k) return m.rows[k]~=nil end,
                    Find=function(m,k) return wrap(assert(m.rows[k])) end,
                    ForEach=function(m,f) for k,v in pairs(m.rows) do if f(wrap(k),wrap(v)) then break end end end}
            end
            shell={IsValid=function() return true end,GetAddress=function() return 41 end,
                GetFullName=function() return "Class /Test.World.Actor" end,Tags={GetArrayNum=function(t) return #t end}}
            local function component(key)
                return {hash=key,GetOwner=function() return shell end,IsValid=shell.IsValid}
            end
            md,health=component(1412174911),component(3969631812)
            md.bHasInitialized=true;md.value=0;health.value=500
            shell.ModuleComponent,shell.DestructibleObjectComponent=md,health
            function shell:ActorHasTag(tag)
                for _,current in ipairs(self.Tags) do if tag==current then return true end end
                return false
            end
            pid=0x8000001631e6729d;zone=FName("125:-3");none=FName("None")
            persist=component(514);shell.PersistentComponent=persist
            persist.LastStoredZoneId,persist.CurrentRuntimeZoneId,persist.PersistentUniqueIdRuntime=zone,zone,pid
            function blob(value)
                return {ByteData={value=value,GetArrayNum=function() return 16 end}}
            end
            oldMd,oldHp=0x9bc5645e,0x7e5f7f36
            data=map({[oldMd]=blob(8),[oldHp]=blob(337),[0x6f424d3a]=blob("cable")})
            actors=map({[pid]={persistentId=pid,ComponentData=data}})
            sub={PersistentActors=map({[zone]={actors=actors}})}
            function sub:GetComponentHash(target,onlyActor) assert(onlyActor==false);return target.hash end
            writes=0
            function sub:DeserializeSaveGameProperties(target,bytes)
                assert(target==md or target==health)
                if target==fail then return false end
                target.value=bytes.value;writes=writes+1;return true
            end
            local objects={["/Script/Engine.CurveFloat"]={}}
            tokens=0
            function StaticFindObject(path) return objects[path] end
            function StaticConstructObject(class,owner,name,flags)
                assert(class==objects["/Script/Engine.CurveFloat"] and owner==shell and flags==0x40)
                local path="/Test.World.Actor."..name:ToString()
                assert(not objects[path])
                local token={IsValid=shell.IsValid,GetOuter=function() return owner end,GetFName=function() return name end,
                    HasAnyFlags=function(_,f) return f==0x40 end,IsA=function(_,p) return objects[p]==class end,
                    hash=({VoyageModule=oldMd,VoyageDestructibleObject=oldHp})[name:ToString()]}
                objects[path]=token;tokens=tokens+1;return token
            end
            restore=require("shipnet.basic_saved_state").restore
        """)

    def test_one_import_per_component_and_exact_old_owner(self):
        self.lua.execute("""
            restore(shell,sub)
            assert(md.value==8 and health.value==337 and writes==2 and tokens==2)
            assert(#shell.Tags==2)
            md.value=3;health.value=198
            restore(shell,sub)
            assert(md.value==3 and health.value==198 and writes==2 and tokens==2)
        """)

    def test_newer_saved_keys_take_priority_even_when_stale_keys_coexist(self):
        self.lua.execute("""
            data.rows[md.hash]=blob(2);md.value=2
            data.rows[health.hash]=blob(223);health.value=223
            restore(shell,sub)
            assert(md.value==2 and health.value==223 and tokens==0 and writes==0 and #shell.Tags==0)
            data.rows[health.hash]=nil
            restore(shell,sub)
            assert(md.value==2 and health.value==337 and tokens==1 and writes==1 and #shell.Tags==1)
        """)

    def test_fresh_fabrication_ignores_other_devices_and_creates_no_placeholders(self):
        self.lua.execute("""
            persist.LastStoredZoneId=none
            actors.rows[pid]=nil
            actors.rows[pid+1]={persistentId=pid+1,ComponentData=data}
            sub.PersistentActors.ForEach=function() error("fresh install scanned unrelated zones") end
            restore(shell,sub)
            assert(md.value==0 and health.value==500 and writes==0 and tokens==0 and #shell.Tags==0)
        """)

    def test_travel_and_partial_failures_keep_the_completed_import(self):
        self.lua.execute("""
            persist.LastStoredZoneId,persist.CurrentRuntimeZoneId=FName("12:4"),FName("13:4")
            fail=health
            assert(not pcall(restore,shell,sub))
            assert(md.value==8 and health.value==500 and #shell.Tags==1 and writes==1)
            md.value=4;fail=nil
            restore(shell,sub)
            assert(md.value==4 and health.value==337 and #shell.Tags==2 and writes==2 and tokens==2)
        """)
