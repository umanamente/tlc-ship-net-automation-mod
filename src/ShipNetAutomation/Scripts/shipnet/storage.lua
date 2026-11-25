-- Local preferences and flushed, ordered JSON Lines traces.
local M = {}

local function read_setting(path)
    local file = io.open(path, "rb")
    if not file then return nil end
    local line = file:read("l")
    file:close()
    if line then line = line:match("^debug_enabled=(%a+)%s*$") end
    if line == "true" then return true end
    if line == "false" then return false end
end

function M.load_debug(dir)
    local path = dir .. "/settings.ini"
    local enabled = read_setting(path)
    if enabled == nil then enabled = read_setting(path .. ".bak") end
    return enabled == true
end

local function replace_file(path, contents)
    local tmp, backup = path .. ".tmp", path .. ".bak"
    local file, err = io.open(tmp, "wb")
    if not file then return nil, err end
    local written, write_error = file:write(contents)
    local closed, close_error = file:close()
    if not written or not closed then return nil, write_error or close_error end
    -- Windows rename will not replace an existing file. Retain the previous
    -- preference until the complete replacement is in place.
    local old = io.open(path, "rb")
    if old then
        old:close()
        os.remove(backup)
        local moved, reason = os.rename(path, backup)
        if not moved then return nil, reason end
    end
    local moved, reason = os.rename(tmp, path)
    if not moved then
        if old then os.rename(backup, path) end
        return nil, reason
    end
    os.remove(backup)
    return true
end

function M.save_debug(dir, enabled)
    return replace_file(dir .. "/settings.ini", "debug_enabled=" .. tostring(enabled) .. "\n")
end

local function read_fit(path)
    local file = io.open(path, "rb")
    if not file then return end
    local contents = file:read(256)
    file:close()
    local x, y, z, yaw = (contents or ""):match("^rail_fit_v1%s+([%+%-%.%deE]+)%s+([%+%-%.%deE]+)%s+([%+%-%.%deE]+)%s+([%+%-%.%deE]+)%s*$")
    local offset = {X=tonumber(x), Y=tonumber(y), Z=tonumber(z), Yaw=tonumber(yaw)}
    for _, axis in ipairs({"X", "Y", "Z", "Yaw"}) do
        local n = offset[axis]
        if not n or n ~= n or math.abs(n) == math.huge then return end
    end
    return offset
end

function M.load_fit(dir)
    return read_fit(dir .. "/rail-fit.ini") or read_fit(dir .. "/rail-fit.ini.bak")
end

function M.save_fit(dir, offset)
    local numbers = {}
    for _, axis in ipairs({"X", "Y", "Z", "Yaw"}) do
        local n = offset and offset[axis]
        if type(n) ~= "number" or n ~= n or math.abs(n) == math.huge then return nil, "invalid offset" end
        numbers[#numbers + 1] = string.format("%.12g", n):gsub(",", ".")
    end
    return replace_file(dir .. "/rail-fit.ini", "rail_fit_v1 " .. table.concat(numbers, " ") .. "\n")
end

local function quote(value)
    return '"' .. value:gsub('[%z\1-\31\\"]', function(char)
        if char == "\\" then return "\\\\" end
        if char == '"' then return '\\"' end
        return string.format("\\u%04x", char:byte())
    end) .. '"'
end

function M.encode(value, key)
    local kind = type(value)
    if kind == "string" then return quote(value) end
    if kind == "boolean" then return tostring(value) end
    if kind == "number" then
        if value ~= value or math.abs(value) == math.huge then return "null" end
        return (tostring(value):gsub(",", "."))
    end
    if kind == "nil" then return "null" end
    assert(kind == "table", "Trace requires plain Lua values")
    local parts = {}
    if value[1] ~= nil or key == "items" or key == "changed" or key == "anchors" or key == "candidates" then
        for i, item in ipairs(value) do parts[i] = M.encode(item) end
        return "[" .. table.concat(parts, ",") .. "]"
    end
    local keys = {}
    for name in pairs(value) do keys[#keys + 1] = name end
    table.sort(keys)
    for i, name in ipairs(keys) do parts[i] = quote(name) .. ":" .. M.encode(value[name], name) end
    return "{" .. table.concat(parts, ",") .. "}"
end

function M.save_build_identity(dir, identity)
    return replace_file(dir .. "/Logs/game-version.json", M.encode(identity) .. "\n")
end

local function engine_time_ms()
    local ok, seconds, partial = pcall(function()
        local api = StaticFindObject("/Script/Engine.Default__GameplayStatics")
        if not api or not api:IsValid() then return end
        local out = {}
        api:GetAccurateRealTime(out, out)
        return out.Seconds, out.PartialSeconds
    end)
    if ok and type(seconds) == "number" and type(partial) == "number"
        and seconds >= 0 and partial >= 0 and partial < 1 then
        return math.floor((seconds + partial) * 1000)
    end
end

local next_number = 0
function M.open(dir, prefix)
    local stamp = os.date("!%Y%m%dT%H%M%SZ")
    local name, path
    repeat
        next_number = next_number + 1
        name = string.format("%s-%s-%03d.jsonl", prefix or "shipnet", stamp, next_number)
        path = dir .. "/Logs/" .. name
        local existing = io.open(path, "rb")
        if not existing then break end
        existing:close()
    until false
    local file, err = io.open(path, "ab")
    if not file then return nil, err end
    local writer = {name = name, seq = 0}
    function writer:append(row)
        self.seq = self.seq + 1
        row.seq, row.utc = self.seq, os.date("!%Y-%m-%dT%H:%M:%SZ")
        if row.state then row.engineTimeMs = engine_time_ms() end
        local ok, line = pcall(M.encode, row)
        if not ok then return nil, line end
        local written, reason = file:write(line, "\n")
        if not written then return nil, reason end
        return file:flush()
    end
    function writer:close() return file:close() end
    return writer
end

return M
