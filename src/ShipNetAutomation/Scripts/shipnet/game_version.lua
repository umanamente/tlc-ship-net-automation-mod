local storage = require("shipnet.storage")
local M = {}

function M.steam_build(dir)
    local steamapps = dir:match("^(.*)/common/[^/]+/Voyage/Binaries/Win64/ue4ss/Mods/[^/]+$")
    local file = steamapps and io.open(steamapps .. "/appmanifest_1783560.acf", "rb")
    if not file then return end
    local manifest = file:read(65536)
    file:close()
    if manifest and manifest:match('"appid"%s+"1783560"') then
        return manifest:match('"buildid"%s+"(%d+)"')
    end
end

local function release_version(project)
    local ok, version = pcall(function()
        for _, settings in ipairs(FindAllOf("SentrySettings") or {}) do
            local release = settings.Release:ToString()
            local full = release:match("(%d+%.%d+%.%d+%.%d+)$")
            if full and full:sub(1, #project + 1) == project .. "." then return full end
        end
    end)
    if ok then return version end
end

function M.capture(dir, steam_build, mod_version, allow_project_version)
    local ok, version = pcall(function()
        local library = StaticFindObject("/Script/Voyage.Default__VoyageBlueprintLibrary")
        if not library or not library:IsValid() then return end
        return library:GetProjectVersion():ToString()
    end)
    if not ok or type(version) ~= "string" or not version:match("^%d+%.%d+%.%d+") then
        return nil, "Voyage project version unavailable"
    end
    local full = release_version(version)
    if not full and not allow_project_version then
        return nil, "Voyage release version unavailable"
    end
    local saved, reason = storage.save_build_identity(dir, {
        schema=1, steam_app_id=steam_build and 1783560, steam_build_id=steam_build,
        game_version=full or version, project_version=version, mod_version=mod_version, captured_utc=os.date("!%Y-%m-%dT%H:%M:%SZ"),
    })
    if not saved then return nil, reason end
    return full or version
end

return M
