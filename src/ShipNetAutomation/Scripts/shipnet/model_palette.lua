-- Distant rigid parts share a lit material. Each original linear colour/roughness pair samples one texel.
local M = {}
local path = "/Game/Mods/ShipNetAutomation/MI_WinchPalette.MI_WinchPalette"
local source = debug.getinfo(1,"S").source:gsub("\\","/")
local directory = assert(source:match("^@(.*)/model_palette%.lua$"))
local palette

local function key(r,g,b,roughness)
    return ("%.6f %.6f %.6f %.6f"):format(r,g,b,roughness)
end

function M.load()
    if palette and palette.material:IsValid() then return palette end
    local material = StaticFindObject(path)
    if not material or not material:IsValid() then material = LoadAsset(path) end
    assert(material and material:IsValid(),"Distant PBR palette material unavailable")
    local texels = {}
    for line in io.lines(directory.."/pbr_palette.layout") do
        if line:sub(1,1) ~= "#" and line:find("%S") then
            local v = {}
            for n in line:gmatch("%S+") do v[#v+1] = assert(tonumber(n)) end
            assert(#v==6 and v[5]>0 and v[5]<1 and v[6]>0 and v[6]<1,"Invalid PBR palette coordinates")
            texels[key(v[1],v[2],v[3],v[4])] = {X=v[5],Y=v[6]}
        end
    end
    assert(next(texels),"Empty distant PBR palette")
    palette = {material=material,texels=texels}
    return palette
end

function M.newBatch()
    return {positions={},normals={},uv={},indices={}}
end

function M.append(batch,p,positions,normals,indices,r,g,b,roughness)
    local uv = assert(p.texels[key(r,g,b,roughness)],"Missing original finish in distant PBR palette")
    local offset = #batch.positions
    for i,v in ipairs(positions) do
        batch.positions[offset+i] = v
        batch.normals[offset+i] = normals[i]
        batch.uv[offset+i] = uv
    end
    for _,index in ipairs(indices) do batch.indices[#batch.indices+1] = offset+index end
end

function M.upload(batch,component,p)
    local slot = component:GetNumSections()
    component:CreateMeshSection_LinearColor(slot,batch.positions,batch.indices,batch.normals,batch.uv,
        {},{},{},{},{},false,false)
    local section = component.ProcMeshSections[slot+1]
    assert(section and section.ProcVertexBuffer:GetArrayNum()==#batch.positions
        and section.ProcIndexBuffer:GetArrayNum()==#batch.indices,"Distant combined mesh upload failed")
    component:SetMaterial(slot,p.material)
end

return M
