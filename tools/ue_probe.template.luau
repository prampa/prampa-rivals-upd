-- ue_probe.luau — live structure probe for the UE base
-- ---------------------------------------------------------------------------
-- Run this BEFORE the base, then run the base, then call UE_PROBE_REPORT().
--
--   loadstring(readfile("ue_probe.luau"))()      -- 1. install
--   UE_PROBE_RUN("ue-v2-cracked.luau.txt")       -- 2. load the base under xpcall
--   UE_PROBE_REPORT()                            -- 3. dump ue_probe_<ts>.txt
--
-- The probe never edits the base. It records what the base asks the engine for:
-- every FindFirstChild / FindFirstChildOfClass / WaitForChild / GetService that
-- comes back empty, every property read that comes back nil, UE's own console
-- output, and the error traceback. Then it snapshots the live tree so the
-- recorded lookups can be diffed against what the game actually has now.
-- ---------------------------------------------------------------------------

local PROBE_VERSION = "1.0"

local CONFIG = {
    maxLookups = 4000,
    maxConsole = 600,
    treeDepth = 4,
    treeNodes = 3000,
    remoteDepth = 8,
    remoteNodes = 4000,
    nameHist = 400,
}

-- Names lifted from the base's constant pool. Present/absent against the live
-- tree is the cheapest first-pass diff we can do.
local CANDIDATES = [[@@CANDIDATES@@]]

-- ---------------------------------------------------------------------------
-- state
-- ---------------------------------------------------------------------------

local State = {
    installed = false,
    hookedIndex = false,
    order = {},
    seen = {},
    console = {},
    errors = {},
    snapshot = nil,
}

local busy = false
local pathCache = setmetatable({}, { __mode = "k" })

local function now()
    return os.clock()
end

local function record(kind, path, key, extra)
    if State.silent then
        return
    end
    local id = kind .. "|" .. tostring(path) .. "|" .. tostring(key)
    local e = State.seen[id]
    if e then
        e.count = e.count + 1
        return
    end
    if #State.order >= CONFIG.maxLookups then
        return
    end
    e = { kind = kind, path = path, key = key, extra = extra, count = 1 }
    State.seen[id] = e
    State.order[#State.order + 1] = e
end

local function ipath(inst)
    local p = pathCache[inst]
    if p then
        return p
    end
    local ok, full = pcall(function()
        return inst:GetFullName()
    end)
    p = ok and tostring(full) or "?"
    pathCache[inst] = p
    return p
end

local function isInst(x)
    local ok, cls = pcall(function()
        return x.ClassName
    end)
    return ok and type(cls) == "string"
end

local collectionService
local function safeTags(inst)
    if not collectionService then
        pcall(function()
            collectionService = game:GetService("CollectionService")
        end)
    end
    if not collectionService then
        return ""
    end
    local ok, tags = pcall(function()
        return collectionService:GetTags(inst)
    end)
    if ok and type(tags) == "table" and #tags > 0 then
        return table.concat(tags, ",")
    end
    return ""
end

local function safeAttrs(inst)
    local ok, attrs = pcall(function()
        return inst:GetAttributes()
    end)
    if not ok or type(attrs) ~= "table" then
        return ""
    end
    local parts = {}
    for k, v in pairs(attrs) do
        parts[#parts + 1] = tostring(k) .. "=" .. tostring(v)
    end
    table.sort(parts)
    return table.concat(parts, ",")
end

-- ---------------------------------------------------------------------------
-- console capture (UE prints its own diagnostics, including its version guards)
-- ---------------------------------------------------------------------------

local function captureConsole(kind, ...)
    if #State.console >= CONFIG.maxConsole then
        return
    end
    local n = select("#", ...)
    local parts = {}
    for i = 1, n do
        local v = select(i, ...)
        local ok, s = pcall(tostring, v)
        parts[i] = ok and s or "?"
    end
    State.console[#State.console + 1] = kind .. "|" .. table.concat(parts, " ")
end

local function installConsoleHook()
    local genv = (getgenv and getgenv()) or _G
    local origPrint = genv.print or print
    local origWarn = genv.warn or warn
    genv.print = function(...)
        captureConsole("print", ...)
        return origPrint(...)
    end
    genv.warn = function(...)
        captureConsole("warn", ...)
        return origWarn(...)
    end
    State.origPrint = origPrint
end

-- ---------------------------------------------------------------------------
-- index hook
--
-- One __index hook covers every instance in the game. Method lookups for the
-- four calls we care about are replaced with logging wrappers; property reads
-- that return nil are recorded with the instance's full path.
-- ---------------------------------------------------------------------------

local originals = {}
local wrappers = {}

local WATCHED = {
    FindFirstChild = true,
    FindFirstChildOfClass = true,
    WaitForChild = true,
    GetService = true,
    HttpGet = true,
    HttpGetAsync = true,
}

local function buildWrappers(oldIndex)
    local probe = game
    for key in pairs(WATCHED) do
        local ok, fn = pcall(function()
            return oldIndex(probe, key)
        end)
        if ok and type(fn) == "function" then
            originals[key] = fn
        end
    end

    if originals.FindFirstChild then
        wrappers.FindFirstChild = function(self, name, recursive)
            local res = originals.FindFirstChild(self, name, recursive)
            if res == nil then
                busy = true
                pcall(record, "ffc_nil", ipath(self), tostring(name), recursive and "deep" or "shallow")
                busy = false
            end
            return res
        end
    end

    if originals.FindFirstChildOfClass then
        wrappers.FindFirstChildOfClass = function(self, class)
            local res = originals.FindFirstChildOfClass(self, class)
            if res == nil then
                busy = true
                pcall(record, "ffc_class_nil", ipath(self), tostring(class))
                busy = false
            end
            return res
        end
    end

    if originals.WaitForChild then
        wrappers.WaitForChild = function(self, name, timeout)
            busy = true
            pcall(record, "wait", ipath(self), tostring(name), tostring(timeout))
            busy = false
            return originals.WaitForChild(self, name, timeout)
        end
    end

    if originals.GetService and probe then
        wrappers.GetService = function(self, name)
            busy = true
            pcall(record, "service", "-", tostring(name))
            busy = false
            return originals.GetService(self, name)
        end
    end

    if originals.HttpGet then
        wrappers.HttpGet = function(self, url, ...)
            busy = true
            pcall(record, "http", "-", tostring(url))
            busy = false
            return originals.HttpGet(self, url, ...)
        end
    end

    if originals.HttpGetAsync then
        wrappers.HttpGetAsync = function(self, url, ...)
            busy = true
            pcall(record, "http", "-", tostring(url))
            busy = false
            return originals.HttpGetAsync(self, url, ...)
        end
    end
end

local function observeNil(self, key)
    if busy then
        return
    end
    busy = true
    local ok = pcall(function()
        if isInst(self) then
            record("nilprop", ipath(self), key)
        end
    end)
    busy = false
    if not ok then
        -- never let the probe take the game down
        busy = false
    end
end

local function makeIndexHook(oldIndex)
    return function(self, key)
        if State.paused then
            return oldIndex(self, key)
        end
        -- the original __index is only guaranteed to be callable from here, so
        -- the wrappers are built on the first dispatch rather than at install
        if not State.wrappersBuilt then
            State.wrappersBuilt = true
            pcall(buildWrappers, oldIndex)
        end
        local value = oldIndex(self, key)
        if WATCHED[key] and wrappers[key] then
            return wrappers[key]
        end
        if value == nil and type(key) == "string" then
            observeNil(self, key)
        end
        return value
    end
end

local function installIndexHook()
    if State.hookedIndex then
        return true
    end

    -- eager pass when the raw original is readable, so the very first lookup is
    -- already covered; otherwise makeIndexHook builds them lazily
    if type(getrawmetatable) == "function" then
        pcall(function()
            local mt = getrawmetatable(game)
            if type(mt) == "table" and type(mt.__index) == "function" then
                buildWrappers(mt.__index)
                State.wrappersBuilt = true
            end
        end)
    end

    if type(hookmetamethod) == "function" then
        -- exclusive: if this errors we stop rather than risk wrapping twice
        local ok = pcall(function()
            local original
            original = hookmetamethod(game, "__index", makeIndexHook(function(self, key)
                return original(self, key)
            end))
            State.indexOriginal = original
        end)
        if ok then
            State.hookedIndex = true
            return true
        end
        return false
    end

    if getrawmetatable and setreadonly then
        local ok, res = pcall(function()
            local mt = getrawmetatable(game)
            if type(mt) ~= "table" or type(mt.__index) ~= "function" then
                return false
            end
            local oldIndex = mt.__index
            setreadonly(mt, false)
            mt.__index = makeIndexHook(oldIndex)
            setreadonly(mt, true)
            return true
        end)
        if ok and res then
            State.hookedIndex = true
            return true
        end
    end

    return false
end

-- ---------------------------------------------------------------------------
-- snapshot
-- ---------------------------------------------------------------------------

local REMOTE_CLASSES = {
    RemoteEvent = true,
    UnreliableRemoteEvent = true,
    RemoteFunction = true,
}

local function walk(root, maxDepth, maxNodes, sink)
    if not root or type(root) ~= "userdata" and type(root) ~= "table" then
        return 0
    end
    local count = 0
    local stack = { { inst = root, depth = 0, base = "" } }
    while #stack > 0 and count < maxNodes do
        local item = table.remove(stack)
        local inst = item.inst
        count = count + 1
        local cls = "?"
        pcall(function()
            cls = inst.ClassName
        end)
        local path = item.base .. tostring(inst.Name)
        sink(inst, path, cls, item.depth)
        if item.depth < maxDepth then
            local ok, kids = pcall(function()
                return inst:GetChildren()
            end)
            if ok and type(kids) == "table" then
                for i = #kids, 1, -1 do
                    stack[#stack + 1] = { inst = kids[i], depth = item.depth + 1, base = path .. "." }
                end
            end
        end
    end
    return count
end

local function snapshot()
    State.silent = true
    local snap = {
        meta = {},
        services = {},
        nodes = {},
        remotes = {},
        names = {},      -- name -> { cls, count, path }
        player = {},
        nodeCount = 0,
    }

    pcall(function()
        snap.meta.place = tostring(game.PlaceId)
        snap.meta.game = tostring(game.GameId)
        snap.meta.job = tostring(game.JobId)
        snap.meta.creator = tostring(game.CreatorId)
    end)
    pcall(function()
        snap.meta.executor = tostring(identifyexecutor and identifyexecutor() or "?")
    end)
    pcall(function()
        snap.meta.roblox = tostring(version and version() or "?")
    end)
    snap.meta.clock = os.date("%Y-%m-%d %H:%M:%S")

    local svcNames = {
        "Players", "ReplicatedStorage", "Workspace", "Lighting", "SoundService",
        "StarterGui", "StarterPlayer", "Teams", "RunService", "CollectionService",
        "ReplicatedFirst", "UserInputService", "ContextActionService", "TweenService",
        "HttpService", "MarketplaceService", "TeleportService", "VirtualUser",
        "VirtualInputManager", "CoreGui", "Chat", "TextChatService", "Stats",
    }
    for _, name in ipairs(svcNames) do
        local ok, svc = pcall(function()
            return game:GetService(name)
        end)
        snap.services[#snap.services + 1] = { name = name, ok = ok and svc ~= nil }
    end

    local function sink(inst, path, cls, depth)
        snap.nodes[#snap.nodes + 1] = {
            path = path, cls = cls,
            attrs = safeAttrs(inst), tags = safeTags(inst),
        }
        snap.nodeCount = snap.nodeCount + 1
        local okName, name = pcall(function()
            return inst.Name
        end)
        if not okName then
            name = "?"
        end
        local entry = snap.names[name]
        if entry then
            entry.count = entry.count + 1
        else
            snap.names[name] = { cls = cls, count = 1, path = path }
        end
        if REMOTE_CLASSES[cls] then
            snap.remotes[#snap.remotes + 1] = { path = path, cls = cls }
        end
    end

    local roots = {}
    pcall(function()
        roots[#roots + 1] = game:GetService("ReplicatedStorage")
    end)
    pcall(function()
        roots[#roots + 1] = game:GetService("Workspace")
    end)
    for _, root in ipairs(roots) do
        walk(root, CONFIG.treeDepth, math.max(1, CONFIG.treeNodes - snap.nodeCount), sink)
    end

    -- remotes live in ReplicatedStorage almost always; walk that one deeper
    pcall(function()
        local rs = game:GetService("ReplicatedStorage")
        walk(rs, CONFIG.remoteDepth, CONFIG.remoteNodes, function(inst, path, cls)
            if REMOTE_CLASSES[cls] then
                local dup = false
                for _, r in ipairs(snap.remotes) do
                    if r.path == path then
                        dup = true
                        break
                    end
                end
                if not dup then
                    snap.remotes[#snap.remotes + 1] = { path = path, cls = cls }
                end
            end
        end)
    end)

    -- the local player, the thing every cheat reads first
    pcall(function()
        local lp = game:GetService("Players").LocalPlayer
        if not lp then
            return
        end
        snap.player[#snap.player + 1] = { path = lp:GetFullName(), cls = lp.ClassName, attrs = "", tags = "" }
        walk(lp, 3, 400, function(inst, path, cls)
            snap.player[#snap.player + 1] = {
                path = path, cls = cls, attrs = safeAttrs(inst), tags = safeTags(inst),
            }
        end)
        local char = lp.Character
        if char then
            for _, child in ipairs(char:GetChildren()) do
                snap.player[#snap.player + 1] = {
                    path = "Character." .. tostring(child.Name),
                    cls = child.ClassName,
                    attrs = safeAttrs(child), tags = safeTags(child),
                }
            end
        else
            snap.player[#snap.player + 1] = { path = "Character", cls = "nil", attrs = "", tags = "" }
        end
        local cam = workspace.CurrentCamera
        snap.player[#snap.player + 1] = {
            path = "CurrentCamera", cls = cam and cam.ClassName or "nil", attrs = "", tags = "",
        }
        local backpack = lp:FindFirstChild("Backpack")
        if backpack then
            for _, child in ipairs(backpack:GetChildren()) do
                snap.player[#snap.player + 1] = {
                    path = "Backpack." .. tostring(child.Name), cls = child.ClassName, attrs = "", tags = "",
                }
            end
        end
    end)

    State.silent = false
    State.snapshot = snap
    return snap
end

-- ---------------------------------------------------------------------------
-- report
-- ---------------------------------------------------------------------------

local function candidateCheck(snap)
    if not snap or CANDIDATES == "" then
        return {}
    end
    local out = {}
    for name in CANDIDATES:gmatch("%S+") do
        local hit = snap.names[name]
        out[#out + 1] = { name = name, cls = hit and hit.cls or nil, count = hit and hit.count or 0 }
    end
    return out
end

local function buildReport()
    local snap = State.snapshot or snapshot()
    local lines = {}
    local function add(s)
        lines[#lines + 1] = s
    end

    add("UEPROBE|" .. PROBE_VERSION)

    local m = snap.meta or {}
    add(table.concat({
        "META", m.place or "?", m.game or "?", m.job or "?", m.creator or "?",
        m.executor or "?", m.roblox or "?", m.clock or "?",
    }, "|"))

    for _, s in ipairs(snap.services) do
        add("SVC|" .. s.name .. "|" .. (s.ok and "ok" or "missing"))
    end

    for _, r in ipairs(snap.remotes) do
        add("REM|" .. r.path .. "|" .. r.cls)
    end

    for _, n in ipairs(snap.nodes) do
        add("NODE|" .. n.path .. "|" .. n.cls .. "|" .. n.attrs .. "|" .. n.tags)
    end

    for _, p in ipairs(snap.player) do
        add("PLAY|" .. p.path .. "|" .. p.cls .. "|" .. (p.attrs or "") .. "|" .. (p.tags or ""))
    end

    -- name histogram, most common first
    local hist = {}
    for name, e in pairs(snap.names) do
        hist[#hist + 1] = { name = name, cls = e.cls, count = e.count, path = e.path }
    end
    table.sort(hist, function(a, b)
        if a.count ~= b.count then
            return a.count > b.count
        end
        return a.name < b.name
    end)
    for i = 1, math.min(#hist, CONFIG.nameHist) do
        local h = hist[i]
        add("NAMEHIST|" .. h.name .. "|" .. h.cls .. "|" .. h.count)
    end

    local cands = candidateCheck(snap)
    local present, absent = {}, {}
    for _, c in ipairs(cands) do
        if c.count > 0 then
            present[#present + 1] = c.name
        else
            absent[#absent + 1] = c.name
        end
    end
    add("CAND_PRESENT|" .. #present .. "|" .. table.concat(present, " "))
    add("CAND_ABSENT|" .. #absent .. "|" .. table.concat(absent, " "))

    for _, e in ipairs(State.order) do
        add("LOOK|" .. e.kind .. "|" .. tostring(e.path) .. "|" .. tostring(e.key) .. "|" .. tostring(e.extra or "") .. "|" .. e.count)
    end

    for _, c in ipairs(State.console) do
        add("CON|" .. c)
    end

    for _, e in ipairs(State.errors) do
        add("ERR|" .. e)
    end

    add("END|" .. #lines)

    return table.concat(lines, "\n")
end

local function writeReport(text)
    local name = "ue_probe_" .. os.date("%Y%m%d_%H%M%S") .. ".txt"
    if writefile then
        local ok, err = pcall(writefile, name, text)
        if ok then
            return name
        end
        local ok2 = pcall(function()
            writefile("/" .. name, text)
        end)
        if ok2 then
            return "/" .. name
        end
        return nil, tostring(err)
    end
    return nil, "no writefile in this executor"
end
-- ---------------------------------------------------------------------------
-- exports
-- ---------------------------------------------------------------------------

local function UE_PROBE_REPORT()
    local text = buildReport()
    local path, err = writeReport(text)
    local out = State.origPrint or print
    if path then
        out("ue_probe: wrote " .. path .. " (" .. #text .. " bytes)")
    else
        if setclipboard then
            local okCopy = pcall(setclipboard, text)
            if okCopy then
                out("ue_probe: no file (" .. tostring(err) .. "), report copied to clipboard")
            else
                out("ue_probe: no file (" .. tostring(err) .. "), printing report below")
                out(text)
            end
        else
            out("ue_probe: no file (" .. tostring(err) .. "), printing report below")
            out(text)
        end
    end
    local snap = State.snapshot
    out(string.format(
        "ue_probe: %d nodes, %d remotes, %d lookups, %d console lines, %d errors",
        snap and snap.nodeCount or 0, snap and #snap.remotes or 0,
        #State.order, #State.console, #State.errors
    ))
    return text
end

local function UE_PROBE_RUN(path, ...)
    path = path or "ue-v2-cracked.luau.txt"
    local source
    if isfile and isfile(path) then
        source = readfile(path)
    elseif readfile then
        local ok, data = pcall(readfile, path)
        if ok then
            source = data
        end
    end
    if not source then
        State.errors[#State.errors + 1] = "UE_PROBE_RUN: cannot read " .. tostring(path)
        return false, "cannot read " .. tostring(path)
    end

    local loader = loadstring or load
    local chunk, compileErr = loader(source, "@ue")
    if not chunk then
        local msg = "compile: " .. tostring(compileErr)
        State.errors[#State.errors + 1] = msg
        return false, msg
    end

    local ok, runErr = xpcall(chunk, function(e)
        return tostring(e) .. "\n" .. debug.traceback("", 2)
    end)
    if not ok then
        State.errors[#State.errors + 1] = "runtime: " .. tostring(runErr)
    end
    return ok, runErr
end

local function UE_PROBE_SNAPSHOT()
    snapshot()
    return State.snapshot
end

local function UE_PROBE_LOG()
    for _, e in ipairs(State.order) do
        print(e.kind, e.path, e.key, e.extra or "", e.count)
    end
end

local function UE_PROBE_CLEAR()
    State.order = {}
    State.seen = {}
    State.console = {}
    State.errors = {}
end

local function UE_PROBE_PAUSE(flag)
    State.paused = flag ~= false
    return State.paused
end

local function UE_PROBE_INSTALL(mode)
    if State.installed then
        return true, "already installed"
    end
    installConsoleHook()
    local hooked = false
    if mode ~= "snapshot" then
        hooked = installIndexHook()
    end
    State.installed = true
    State.mode = mode or "full"
    return hooked, State.mode
end

local genv = (getgenv and getgenv()) or _G
genv.UE_PROBE_REPORT = UE_PROBE_REPORT
genv.UE_PROBE_RUN = UE_PROBE_RUN
genv.UE_PROBE_SNAPSHOT = UE_PROBE_SNAPSHOT
genv.UE_PROBE_LOG = UE_PROBE_LOG
genv.UE_PROBE_CLEAR = UE_PROBE_CLEAR
genv.UE_PROBE_PAUSE = UE_PROBE_PAUSE
genv.UE_PROBE_INSTALL = UE_PROBE_INSTALL
genv.UE_PROBE_STATE = State

-- auto-install on load; UE_PROBE_MODE = "snapshot" skips the __index hook
local genv0 = (getgenv and getgenv()) or _G
local mode = genv0.UE_PROBE_MODE
local okInstall, hooked = pcall(UE_PROBE_INSTALL, mode)
if not okInstall then
    print("ue_probe: install failed: " .. tostring(hooked))
elseif hooked then
    print("ue_probe: hooks installed. run the base, then UE_PROBE_REPORT()")
else
    print("ue_probe: no metamethod hook available, snapshot-only mode")
end

return {
    version = PROBE_VERSION,
    report = UE_PROBE_REPORT,
    run = UE_PROBE_RUN,
    snapshot = UE_PROBE_SNAPSHOT,
}
