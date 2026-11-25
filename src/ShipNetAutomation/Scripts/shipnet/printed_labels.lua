local Labels = {}
local materialPath = "/Game/Mods/ShipNetAutomation/MI_WinchMarkings.MI_WinchMarkings"
local source = debug.getinfo(1, "S").source:gsub("\\", "/")
local directory = assert(source:match("^@(.*)/printed_labels%.lua$"))
local layout, material

local function readLayout()
    if layout then return layout end
    local rows = {advanced={}, basic={}}
    for line in io.lines(directory .. "/printed_labels.layout") do
        if line:sub(1, 1) ~= "#" and line ~= "" then
            local fields = {}
            for field in line:gmatch("[^\t\r]+") do fields[#fields + 1] = field end
            assert(#fields == 10 and rows[fields[1]], "Invalid printed-label atlas layout")
            local box = {}
            for i = 3, 10 do box[#box + 1] = assert(tonumber(fields[i])) end
            table.insert(rows[fields[1]], box)
        end
    end
    assert(#rows.basic == 5 and #rows.advanced == 1, "Incomplete printed-label atlas layout")
    layout = rows
    return rows
end

local function uvFor(p, basic, boxes)
    local s, z = basic and p.X or p.Y, p.Z
    for _, box in ipairs(boxes) do
        local x0, x1, z0, z1, left, top, width, height = table.unpack(box)
        if s >= x0 - .011 and s <= x1 + .011 and z >= z0 - .011 and z <= z1 + .011 then
            return {X=(left + width * (s - x0)/(x1 - x0))/512,
                    Y=(top + height * (z1 - z)/(z1 - z0))/256}
        end
    end
    error("Printed-label vertex outside atlas layout")
end

function Labels.apply(component, slot, positions, triangles, normals, basic)
    local uv, colors = {}, {}
    local ok, reason = pcall(function()
        local boxes = readLayout()[basic and "basic" or "advanced"]
        for i, point in ipairs(positions) do
            uv[i] = uvFor(point, basic, boxes)
            colors[i] = {R=1,G=1,B=1,A=1}
        end
        if not material or not material:IsValid() then
            material = StaticFindObject(materialPath)
            if not material or not material:IsValid() then material = LoadAsset(materialPath) end
        end
        assert(material and material:IsValid(), "Printed-label material unavailable")
    end)
    component:CreateMeshSection_LinearColor(slot, positions, triangles, normals,
        ok and uv or {}, {}, {}, {}, ok and colors or {}, {}, false, false)
    if ok then ok, reason = pcall(function() component:SetMaterial(slot, material) end) end
    if not ok then component:SetMeshSectionVisible(slot, false) end
    return ok, reason
end

return Labels
