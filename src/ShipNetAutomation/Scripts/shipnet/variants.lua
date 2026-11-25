local function variant(suffix, title)
    local item = "DA_Item_Module_WinchAutomator" .. suffix
    local skill = "DA_Skill_Engineering_Winch_Automator" .. suffix
    local carrier = "BP_Module_WinchAutomator" .. suffix .. "_C"
    return {
        item = "/Game/Data/Assets/Modules/" .. item .. "." .. item,
        skill = "/Game/Data/Assets/Skill/Modules/" .. skill .. "." .. skill,
        carrier = "/Game/Mods/ShipNetAutomation/" .. carrier:sub(1, -3) .. "." .. carrier,
        itemName = item, skillName = skill, carrierName = carrier, title = title,
    }
end

local M = {
    advanced = variant("", "Winch Automator Advanced"),
    basic = variant("Basic", "Winch Automator Basic"),
}
M.basic.manualUnload = true
M.basic.geometry = {
    anchors = {inlet={X=180.6,Y=120.4,Z=-26.9}},
    fitGeometry = {display={minX=97.4,maxX=147.0,minZ=-29.95,maxZ=-15.65,Y=116.25,
        rimY=115.90,lensY=115.71,lcdY=115.31,rearShift=1.23,bezelSlot=3,glassSlot=9}},
}
M.all = {M.advanced, M.basic}

function M.forItem(item)
    if not item or not item:IsValid() then return end
    for _, kind in ipairs(M.all) do
        local asset = StaticFindObject(kind.item)
        if asset and asset:IsValid() and item:GetAddress() == asset:GetAddress() then return kind end
    end
end

function M.forActor(actor)
    if not actor or not actor:IsValid() then return end
    for _, kind in ipairs(M.all) do
        if actor:IsA(kind.carrier) then return kind end
    end
end

return M
