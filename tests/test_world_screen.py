"""Physical screen state, language selection and units with the engine offline."""
from pathlib import Path
import unittest

from lupa.lua54 import LuaRuntime


class WorldScreenTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime()
        self.lua.globals().scripts = (Path(__file__).resolve().parents[1] / "src/ShipNetAutomation/Scripts").as_posix()
        self.lua.execute('package.path=scripts.."/?.lua;"..package.path; text=require("shipnet.screen_text")')

    def test_all_game_languages_and_regional_aliases(self):
        self.lua.execute("""
            local cultures={
                en="On",de="Ein",["es-ES"]="Sí",["es-419"]="Sí",fi="Päällä",fr="Marche",
                it="On",ja="オン",pl="Wł.",["pt-BR"]="Ligada",ru="Вкл",["sv-FI"]="På",
                uk="Увімк",["zh-Hans"]="开"}
            for tag,mode in pairs(cultures) do
                assert(text.resolve(tag)==tag)
                local r=text.readout({automationEnabled=true},tag,tag)
                assert(r.mode==mode and r.warning~="" and r.label~="" and r.catch~="")
                local disabled=text.readout({automationEnabled=false},tag,tag)
                assert(r.action~="" and disabled.action~="" and r.action~=disabled.action)
            end
            assert(text.resolve("es_Latn_MX")=="es-419" and text.resolve("es")=="es-ES")
            assert(text.resolve("sv-SE")=="sv-FI" and text.resolve("zh-CN")=="zh-Hans")
            assert(text.resolve("zh-Hant-TW")=="en" and text.resolve("unsupported")=="en")
        """)

    def test_capacity_changes_and_empty_buffer(self):
        self.lua.execute("""
            local s={netWeightKg=2.5,netCapacityKg=300,automationDrawKW=.5}
            local function read() return text.readout(s,"ru","ru-RU") end
            assert(read().weight=="2,5 / 300 кг" and read().power=="500 Вт")
            assert(read().action=="Включить" and read().mode=="Выкл")
            s.automationEnabled=true
            assert(read().action=="Выключить" and read().mode=="Вкл")
            s.netWeightKg=.00005;s.netCapacityKg=.0001
            assert(read().weight=="50 / 100 мг" and read().fraction==.5)
            s.netWeightKg=3000;s.netCapacityKg=30000
            assert(read().weight=="3 / 30 т" and read().fraction==.1)
            s.netCapacityKg=0;assert(read().fraction==0)
            s.netWeightKg=nil;s.netCapacityKg=nil;assert(read().weight=="— / — кг")
            s.power={status="waiting_for_socket",electricity=0};assert(not read().empty)
            s.power={status="native_input",electricity=.001};assert(not read().empty)
            s.power.electricity=0;assert(read().empty)
        """)

    def test_changed_readings_repaint_without_focus(self):
        self.lua.execute("""
            local Screen=require("shipnet.world_screen")
            FText=function(s) return s end
            local function element()
                return {SetText=function(e,t)e.text=t end,SetBrushColor=function(e,c)e.tint=c end,
                    SetColorAndOpacity=function(e,c)e.tint=c.SpecifiedColor end,
                    SetVisibility=function(e,v)e.visibility=v end,SetSize=function()end,
                    SetRenderTranslation=function(e,p)e.translation=p end,
                    SetPosition=function(e,p)e.position=p end,ForceLayoutPrepass=function()end,
                    GetDesiredSize=function()return {Y=52} end,SetIsEnabled=function(e,b)e.enabled=b end}
            end
            local screen=setmetatable({h=302,cache={},component={count=0,
                RequestRenderUpdate=function(e)e.count=e.count+1 end}},Screen)
            for _,k in ipairs({"auto","mode","action","catch","weight","warning","power","face",
                "switchLayer","switchBack","switchFace","switchRim","warningLayer","fill","fillSlot"}) do
                screen[k]=element()
            end
            screen.warning.Slot=element()
            screen.cx,screen.height,screen.glass=18,22,{maxZ=44,Y=50}
            screen.bolt=element()
            screen.bolt.IsValid=function()return true end
            screen.bolt.K2_SetRelativeLocation=function(e,p)e.position=p end
            local s={netWeightKg=12,netCapacityKg=300,automationEnabled=false,
                automationDrawKW=0,power={status="native_input",electricity=1}}
            screen:update(s);screen:update(s);assert(screen.component.count==1)
            local off=screen.switchFace.tint
            assert(off.R>off.G*3 and off.R>off.B*3 and screen.mode.tint.R>screen.mode.tint.G)
            assert(screen.action.text=="Turn on" and screen.mode.text=="• Off")
            assert(screen.switchRim.tint.R>off.R and screen.switchBack.tint.R<off.R)
            s.netWeightKg=13;screen:update(s)
            assert(screen.component.count==2 and screen.weight.text=="13 / 300 kg")
            screen.focus={button=element(),switchVisible=true,clicked=true}
            s.power.electricity=0;screen:update(s)
            assert(screen.face.visibility==1 and screen.switchLayer.visibility==1 and screen.bolt.visibility)
            assert(screen.focus.button.visibility==1 and not screen.focus.button.enabled and not screen.focus.clicked)
            assert(screen.bolt.position.X==screen.cx and screen.warning.Slot.position.X==480)
            local top=(screen.glass.maxZ-screen.bolt.position.Z)*screen.h/screen.height-screen.h*.16
            local bottom=screen.warning.Slot.position.Y+52/2
            assert(math.abs(top+bottom-screen.h)<1e-6)
            screen.focus=nil;screen:update(s);assert(screen.switchLayer.visibility==1)
            screen.focus={button=element()};s.power.electricity=1;screen:update(s)
            assert(screen.face.visibility==0 and screen.warningLayer.visibility==1 and screen.switchLayer.visibility==0)
            assert(screen.focus.switchVisible and screen.focus.button.visibility==0 and screen.focus.needsFocus)
            s.automationEnabled=true;screen:update(s)
            local on=screen.switchFace.tint
            assert(on.G>on.R and on.G>on.B and screen.mode.tint.G>on.G)
            assert(screen.action.text=="Turn off" and screen.mode.text=="• On")
            screen.focus.hovered=true;screen.focus.pressed=true
            s.netWeightKg=14;screen:update(s)
            assert(screen.switchFace.tint.G>on.G and screen.action.translation.Y>0)
            screen:close()
            assert(screen.switchFace.tint==on and screen.action.translation.Y==0)
            s.automationEnabled=false;screen:update(s);assert(screen.switchFace.tint==off)
        """)
