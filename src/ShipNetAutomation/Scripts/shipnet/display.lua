local valid = require("shipnet.observer").valid
local Display = {}

local crt = "/Game/UI/Terminal/Materials/M_Terminal_Retainer_Widget_ForcePower.M_Terminal_Retainer_Widget_ForcePower"
local artwork = "/Game/Mods/ShipNetAutomation/T_WinchControlScreen.T_WinchControlScreen"

local function load_asset(path)
    local asset = StaticFindObject(path)
    if not valid(asset) then asset = LoadAsset(path) end
    assert(valid(asset), "Missing screen asset " .. path)
    return asset
end

function Display.crtMaterial() return load_asset(crt) end

function Display.lens(component,w,h)
    -- Use the game's clear boat window, with a light reflection at grazing angles.
    local parent=load_asset("/Game/External/Vegetables_Big_Pack/Materials/Turntable/M_Glass_BoatWindows.M_Glass_BoatWindows")
    local quad={{X=-w/2,Y=0,Z=-h/2},{X=w/2,Y=0,Z=-h/2},{X=w/2,Y=0,Z=h/2},{X=-w/2,Y=0,Z=h/2}}
    local n={X=0,Y=1,Z=0}
    component:CreateMeshSection_LinearColor(0,quad,{0,1,2,0,2,3},{n,n,n,n},
        {{X=0,Y=1},{X=1,Y=1},{X=1,Y=0},{X=0,Y=0}},{},{},{},{},{},false,false)
    local mid=component:CreateDynamicMaterialInstance(0,parent,FName("None",EFindName.FNAME_Find))
    assert(valid(mid),"Could not mount the screen lens")
    mid:SetScalarParameterValue(FName("Opacity",EFindName.FNAME_Find),.045)
    mid:SetScalarParameterValue(FName("StainOpacity",EFindName.FNAME_Find),0)
    mid:SetScalarParameterValue(FName("StainOpacityB",EFindName.FNAME_Find),0)
    return mid
end

-- The baked construction mesh has a solid octagonal cap behind its SETTINGS
-- artwork. Open only that cap in the built model, retaining its outer bevel.
function Display.openBezel(g,positions,normals,indices)
    local rim,seen,triangles={},{},{}
    local cx,cz=(g.minX+g.maxX)/2,(g.minZ+g.maxZ)/2
    local function cap(i)
        local v=positions[i+1]
        return math.abs(v.Y-g.rimY)<.001 and v.X>=g.minX-6 and v.X<=g.maxX+6
            and v.Z>=g.minZ-6 and v.Z<=g.maxZ+6
    end
    for k=1,#indices,3 do
        local a,b,c=indices[k],indices[k+1],indices[k+2]
        if cap(a) and cap(b) and cap(c) then
            for j=k,k+2 do
                local i=indices[j]
                if not seen[i] then rim[#rim+1]=i;seen[i]=true end
            end
        else
            triangles[#triangles+1]=a;triangles[#triangles+1]=b;triangles[#triangles+1]=c
        end
    end
    assert(#rim==8 and #indices-#triangles==18,"Unexpected screen bezel cap")
    local rx,rz=0,0
    for _,i in ipairs(rim) do
        local p=positions[i+1]
        rx=math.max(rx,math.abs(p.X-cx));rz=math.max(rz,math.abs(p.Z-cz))
    end
    table.sort(rim,function(a,b)
        local p,q=positions[a+1],positions[b+1]
        return math.atan(p.Z-cz,p.X-cx)<math.atan(q.Z-cz,q.X-cx)
    end)
    local function ring(scaleX,scaleZ,y)
        local out={}
        for j,i in ipairs(rim) do
            local p=positions[i+1]
            out[j]=#positions
            positions[#positions+1]={X=cx+(p.X-cx)*scaleX,Y=y,Z=cz+(p.Z-cz)*scaleZ}
            normals[#normals+1]={X=0,Y=1,Z=0}
        end
        return out
    end
    local function bridge(outer,inner)
        for j=1,#outer do
            local k=j%#outer+1
            for _,i in ipairs({outer[j],outer[k],inner[k],outer[j],inner[k],inner[j]}) do
                triangles[#triangles+1]=i
            end
        end
    end
    local w,h=(g.maxX-g.minX)/2,(g.maxZ-g.minZ)/2
    local lip=ring(w/rx,h/rz,g.rimY)
    bridge(rim,lip)
    bridge(lip,ring((w-.22)/rx,(h-.22)/rz,g.lcdY-.09))
    return triangles
end

function Display.apply(body, glass, fallbackY)
    local parent, texture = load_asset(crt), load_asset(artwork)
    local slot = body:GetNumSections()
    -- Keep the CRT in front of the outlined SETTINGS artwork baked into the builder mesh.
    local y = fallbackY or glass.Y + 0.20
    local vertices = {
        {X=glass.minX, Y=y, Z=glass.minZ}, {X=glass.maxX, Y=y, Z=glass.minZ},
        {X=glass.maxX, Y=y, Z=glass.maxZ}, {X=glass.minX, Y=y, Z=glass.maxZ},
    }
    local front = {X=0, Y=1, Z=0}
    local uv = {{X=0,Y=1}, {X=1,Y=1}, {X=1,Y=0}, {X=0,Y=0}}
    local ok, result = pcall(function()
        body:CreateMeshSection_LinearColor(slot, vertices, {0,1,2, 0,2,3}, {front,front,front,front},
            uv, {}, {}, {}, {}, {}, false, false)
        local mid = body:CreateDynamicMaterialInstance(slot, parent, FName("None", EFindName.FNAME_Find))
        assert(valid(mid), "Could not create the fishing winch CRT material")
        local input = FName("SlateUI", EFindName.FNAME_Add)
        mid:SetTextureParameterValue(input, texture)
        local bound = mid:K2_GetTextureParameterValue(input)
        assert(valid(bound) and bound:GetAddress() == texture:GetAddress(), "CRT artwork did not bind to SlateUI")
        return mid
    end)
    if not ok then
        -- The cabinet's glass and SETTINGS lettering remain usable if the material cannot load.
        body:ClearMeshSection(slot)
        error(result, 0)
    end
    return result
end

return Display
