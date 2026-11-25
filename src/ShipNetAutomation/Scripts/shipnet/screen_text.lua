-- One catalogue for the two physical displays. Rows: catch, automation, on, off,
-- empty supply, tonne, kilogram, gram, milligram, watt, kilowatt, turn on, turn off.
local rows = {
    en={"Net catch","Automation","On","Off","No power","t","kg","g","mg","W","kW","Turn on","Turn off"},
    de={"Fang im Netz","Automatik","Ein","Aus","Kein Strom","t","kg","g","mg","W","kW","Einschalten","Ausschalten"},
    ["es-ES"]={"Captura en la red","Automatización","Sí","No","Sin energía","t","kg","g","mg","W","kW","Activar","Desactivar"},
    ["es-419"]={"Pesca en la red","Automatización","Sí","No","Sin energía","t","kg","g","mg","W","kW","Activar","Desactivar"},
    fi={"Verkon saalis","Automatiikka","Päällä","Pois","Ei virtaa","t","kg","g","mg","W","kW","Kytke päälle","Kytke pois"},
    fr={"Prise du filet","Automatisme","Marche","Arrêt","Hors tension","t","kg","g","mg","W","kW","Activer","Désactiver"},
    it={"Pescato nella rete","Automazione","On","Off","Alimentazione assente","t","kg","g","mg","W","kW","Attiva","Disattiva"},
    ja={"網の漁獲量","自動運転","オン","オフ","電源なし","t","kg","g","mg","W","kW","有効にする","無効にする"},
    pl={"Połów w sieci","Automatyka","Wł.","Wył.","Brak zasilania","t","kg","g","mg","W","kW","Włącz","Wyłącz"},
    ["pt-BR"]={"Pesca na rede","Automação","Ligada","Desligada","Sem energia","t","kg","g","mg","W","kW","Ligar","Desligar"},
    ru={"Улов в сети","Автоматика","Вкл","Выкл","Нет питания","т","кг","г","мг","Вт","кВт","Включить","Выключить"},
    ["sv-FI"]={"Fångst i nätet","Automatik","På","Av","Ingen ström","t","kg","g","mg","W","kW","Slå på","Slå av"},
    uk={"Улов у сітці","Автоматика","Увімк","Вимк","Немає живлення","т","кг","г","мг","Вт","кВт","Увімкнути","Вимкнути"},
    ["zh-Hans"]={"渔网收获","自动控制","开","关","无电源","吨","千克","克","毫克","瓦","千瓦","开启","关闭"},
}
local aliases = {es="es-ES", pt="pt-BR", sv="sv-FI", zh="zh-Hans"}
local prompts={
    en="Winch settings",de="Windeneinstellungen",["es-ES"]="Ajustes del cabrestante",
    ["es-419"]="Configurar cabrestante",fi="Vinssin asetukset",fr="Réglages du treuil",
    it="Impostazioni del verricello",ja="ウィンチの設定",pl="Ustawienia wciągarki",
    ["pt-BR"]="Configurar guincho",ru="Настройки лебёдки",["sv-FI"]="Vinschinställningar",
    uk="Налаштування лебідки",["zh-Hans"]="绞盘设置",
}
for code in pairs(rows) do aliases[code:lower()]=code end
for region in ("ar bo cl co cr cu do ec gt hn mx ni pa pe pr py sv us uy ve"):gmatch("%S+") do
    aliases["es-"..region]="es-419"
end
for _,tag in ipairs({"zh-hant","zh-tw","zh-hk","zh-mo","zh-cht"}) do aliases[tag]="en" end
local M = {}
function M.resolve(tag)
    tag=(tag or ""):lower():gsub("_","-"):gsub("^es%-latn%-","es-")
    while tag~="" do
        if aliases[tag] then return aliases[tag] end
        tag=tag:match("^(.*)%-[^-]+$") or ""
    end
    return "en"
end

local function string_value(x) return type(x)=="string" and x or x:ToString() end
function M.culture()
    local ok,tag,locale=pcall(function()
        local api=StaticFindObject("/Script/Engine.Default__KismetInternationalizationLibrary")
        return string_value(api:GetCurrentLanguage()),string_value(api:GetCurrentLocale())
    end)
    return M.resolve(ok and tag or "en"),ok and locale or "en"
end

function M.noPower(fallback)
    local ok,value=pcall(function()
        local id=FName("/Game/LocalizationStringTables/ST_Modules.ST_Modules",EFindName.FNAME_Find)
        local tables=StaticFindObject("/Script/Engine.Default__KismetStringTableLibrary")
        if tables:IsRegisteredTableEntry(id,"NoPower") then
            local lib=StaticFindObject("/Script/Engine.Default__KismetTextLibrary")
            return lib:TextFromStringTable(id,"NoPower")
        end
    end)
    if ok and value then return value end
    return FText(fallback)
end

local decimalComma={de=true,es=true,fi=true,fr=true,it=true,pl=true,pt=true,ru=true,sv=true,uk=true}
local function finite(v) return type(v)=="number" and v>=0 and v<math.huge end
local function number(v,locale)
    if not finite(v) then return "—" end
    local scientific=v>=1e6 or (v>0 and v<.001)
    local exp=scientific and math.floor(math.log(v,10)) or 0
    local scaled=scientific and v/10^exp or v
    local precision=scaled>=100 and 0 or scaled>=10 and 1 or 2
    local ok,value=pcall(function()
        local lib=StaticFindObject("/Script/Engine.Default__KismetTextLibrary")
        return lib:Conv_DoubleToText(scaled,0,false,false,1,12,0,precision):ToString()
    end)
    if not ok then
        value=string.format("%."..precision.."f",scaled)
        if precision>0 then value=value:gsub("0+$",""):gsub("%.$","") end
        if decimalComma[locale:lower():match("^[a-z]+")] then
            value=value:gsub("%.",",")
        end
    end
    return value..(scientific and ("e"..exp) or "")
end
function M.emptyBuffer(power)
    return power~=nil and power.status=="native_input" and power.electricity==0
end
function M.readout(status, tag, locale)
    local r=rows[tag] or rows.en
    local cap,w=status.netCapacityKg,status.netWeightKg
    local magnitude=finite(cap) and cap>0 and cap or (finite(w) and w or 1)
    local scale,unit=1,r[7]
    if magnitude>=1000 then scale,unit=1000,r[6]
    elseif magnitude<.001 then scale,unit=.000001,r[9]
    elseif magnitude<1 then scale,unit=.001,r[8] end
    local kw=status.automationDrawKW
    local power=not finite(kw) and "—" or kw>=1 and number(kw,locale).." "..r[11] or number(kw*1000,locale).." "..r[10]
    return {catch=r[1], label=r[2], mode=status.automationEnabled and r[3] or r[4],
        action=status.automationEnabled and r[13] or r[12], warning=r[5], prompt=prompts[tag] or prompts.en,
        weight=number(finite(w) and w/scale,locale).." / "..number(finite(cap) and cap/scale,locale).." "..unit,
        fraction=finite(w) and finite(cap) and cap>0 and math.min(1,w/cap) or 0,
        power=power, empty=M.emptyBuffer(status.power)}
end
return M
