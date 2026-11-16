-- doctor_ui.luau v4 — read the menu's own click handlers from outside
--   loadstring(game:HttpGet("https://raw.githubusercontent.com/prampa/prampa-rivals-upd/main/doctor_ui.luau"))()
--
-- v3 found the menu and showed clicks reaching its buttons. That means the
-- failure is one step deeper: either no handler is connected, or the handler
-- runs and dies. `getconnections` exposes those connections, and invoking the
-- handler returns its own error text - which names whatever the update broke.
--
-- Button 1: how many handlers each button has.
-- Button 2: invoke them and print the error they throw.

local Players = game:GetService("Players")
local UIS = game:GetService("UserInputService")
local plr = Players.LocalPlayer
local pg = plr:FindFirstChild("PlayerGui")

local function hostGui()
    if gethui then
        local ok, value = pcall(gethui)
        if ok and value then
            return value
        end
    end
    return pg
end

local HOST = hostGui()

local screen = Instance.new("ScreenGui")
screen.Name = "prampa_Doctor"
screen.ResetOnSpawn = false
screen.IgnoreGuiInset = true
screen.DisplayOrder = 2000000
screen.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
screen.Parent = HOST

local panel = Instance.new("Frame")
panel.Size = UDim2.fromOffset(486, 486)
panel.Position = UDim2.fromOffset(12, 12)
panel.BackgroundColor3 = Color3.fromRGB(10, 10, 13)
panel.BackgroundTransparency = 0.06
panel.BorderSizePixel = 0
panel.Active = true
panel.Parent = screen

local corner = Instance.new("UICorner")
corner.CornerRadius = UDim.new(0, 10)
corner.Parent = panel

local stroke = Instance.new("UIStroke")
stroke.Color = Color3.fromRGB(70, 60, 120)
stroke.Thickness = 1
stroke.Transparency = 0.3
stroke.Parent = panel

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, -20, 0, 22)
title.Position = UDim2.fromOffset(12, 6)
title.BackgroundTransparency = 1
title.Font = Enum.Font.GothamBold
title.TextSize = 13
title.TextColor3 = Color3.fromRGB(230, 230, 255)
title.TextXAlignment = Enum.TextXAlignment.Left
title.Text = "INPUT DOCTOR v4   build " .. tostring(getgenv().prampa_BuildID or "?")
title.Parent = panel

local status = Instance.new("TextLabel")
status.Size = UDim2.new(1, -24, 0, 220)
status.Position = UDim2.fromOffset(12, 30)
status.BackgroundTransparency = 1
status.Font = Enum.Font.Code
status.TextSize = 11
status.TextWrapped = true
status.TextXAlignment = Enum.TextXAlignment.Left
status.TextYAlignment = Enum.TextYAlignment.Top
status.TextColor3 = Color3.fromRGB(185, 205, 195)
status.Text = "scanning..."
status.Parent = panel

local lines = {}
local function say(text)
    lines[#lines + 1] = tostring(text)
    if #lines > 18 then
        table.remove(lines, 1)
    end
end

local function render()
    local info = {}
    info[#info + 1] = "getconnections=" .. tostring(type(getconnections) == "function")
    info[#info + 1] = "mouse=" .. tostring(UIS.MouseBehavior)
    info[#info + 1] = "clicks=" .. tostring(CLICKS)
    status.Text = table.concat(lines, "\n") .. "\n\n-- live --\n" .. table.concat(info, "\n")
end

-- find the menu ---------------------------------------------------------------

local function allScreenGuis()
    local out, seen = {}, {}
    local roots = {}
    if pg then
        roots[#roots + 1] = pg
    end
    if HOST and HOST ~= pg then
        roots[#roots + 1] = HOST
    end
    pcall(function()
        local core = game:GetService("CoreGui")
        if core and core ~= pg and core ~= HOST then
            roots[#roots + 1] = core
        end
    end)
    for _, root in ipairs(roots) do
        pcall(function()
            for _, obj in ipairs(root:GetDescendants()) do
                if obj:IsA("ScreenGui") and obj ~= screen and not seen[obj] then
                    seen[obj] = true
                    out[#out + 1] = obj
                end
            end
        end)
    end
    return out
end

local function hudGui()
    for _, gui in ipairs(allScreenGuis()) do
        local ok, hit = pcall(function()
            return gui:FindFirstChild("Island", true) or gui:FindFirstChild("HudRoot", true)
        end)
        if ok and hit then
            return gui
        end
    end
    return nil
end

local function menuGui()
    local hud = hudGui()
    local best, bestN = nil, 0
    for _, gui in ipairs(allScreenGuis()) do
        if gui ~= hud then
            local n = 0
            pcall(function()
                for _, obj in ipairs(gui:GetDescendants()) do
                    if obj:IsA("TextButton") then
                        n += 1
                    end
                end
            end)
            if n > bestN then
                best, bestN = gui, n
            end
        end
    end
    if bestN < 3 then
        return nil
    end
    return best
end

local function menuButtons(limit)
    local gui = menuGui()
    local out = {}
    if not gui then
        return out
    end
    pcall(function()
        for _, obj in ipairs(gui:GetDescendants()) do
            if obj:IsA("TextButton") and obj.Visible and #out < (limit or 200) then
                out[#out + 1] = obj
            end
        end
    end)
    return out
end

CLICKS = 0

local function conns(signal)
    local out = {}
    if type(getconnections) ~= "function" then
        return out
    end
    local ok, list = pcall(getconnections, signal)
    if ok and type(list) == "table" then
        return list
    end
    return out
end

-- buttons ---------------------------------------------------------------------

local function button(text, y, onClick)
    local b = Instance.new("TextButton")
    b.Size = UDim2.new(1, -24, 0, 30)
    b.Position = UDim2.fromOffset(12, y)
    b.BackgroundColor3 = Color3.fromRGB(28, 26, 40)
    b.BorderSizePixel = 0
    b.AutoButtonColor = true
    b.Font = Enum.Font.GothamMedium
    b.TextSize = 12
    b.TextColor3 = Color3.fromRGB(225, 225, 245)
    b.Text = text
    b.ZIndex = 5
    b.Parent = panel

    local c = Instance.new("UICorner")
    c.CornerRadius = UDim.new(0, 7)
    c.Parent = b

    b.MouseButton1Click:Connect(function()
        lines = {}
        local ok, err = pcall(onClick)
        if not ok then
            say("error: " .. tostring(err))
        end
        pcall(render)
    end)
    return b
end

button("1. count handlers on menu buttons", 250, function()
    local buttons = menuButtons(400)
    say(("menu buttons visible: %d"):format(#buttons))

    local withClick, withDown, withActivated = 0, 0, 0
    for _, obj in ipairs(buttons) do
        local a = #conns(obj.MouseButton1Click)
        local b = #conns(obj.MouseButton1Down)
        local c = #conns(obj.Activated)
        if a > 0 then
            withClick += 1
        end
        if b > 0 then
            withDown += 1
        end
        if c > 0 then
            withActivated += 1
        end
    end

    say(("MouseButton1Click handlers: %d"):format(withClick))
    say(("MouseButton1Down  handlers: %d"):format(withDown))
    say(("Activated         handlers: %d"):format(withActivated))
    say("")
    say("sample:")
    for i = 1, math.min(5, #buttons) do
        local obj = buttons[i]
        say(("  %s | click=%d down=%d act=%d"):format(
            tostring(obj.Name), #conns(obj.MouseButton1Click),
            #conns(obj.MouseButton1Down), #conns(obj.Activated)))
    end
    if withClick == 0 and withDown == 0 and withActivated == 0 then
        say("")
        say("=> NOTHING is connected. the base built the")
        say("   menu but never bound input to it.")
    end
end)

button("2. run the handlers, read errors", 282, function()
    local buttons = menuButtons(400)
    local ran, failed = 0, 0
    local shownErrors = 0

    for _, obj in ipairs(buttons) do
        for _, signal in ipairs({ obj.MouseButton1Click, obj.MouseButton1Down, obj.Activated }) do
            for _, conn in ipairs(conns(signal)) do
                local fn = conn.Function
                if type(fn) == "function" then
                    local ok, err = pcall(fn, 1, 1)
                    ran += 1
                    if not ok then
                        failed += 1
                        if shownErrors < 6 then
                            shownErrors += 1
                            local text = tostring(err)
                            if #text > 150 then
                                text = text:sub(1, 150) .. "..."
                            end
                            say("ERR " .. obj.Name .. ":")
                            say("  " .. text)
                        end
                    end
                end
            end
        end
    end

    say(("invoked %d handlers, %d threw"):format(ran, failed))
    if ran == 0 then
        say("=> no handler functions to run")
    elseif failed == 0 then
        say("=> handlers run clean; the state change")
        say("   happens somewhere unreachable")
    end
    say("did anything on the menu change?")
end)

button("3. disable prampa HUD", 314, function()
    local hud = hudGui()
    if not hud then
        say("prampa HUD not found")
        return
    end
    hud.Enabled = not hud.Enabled
    say(("prampa HUD %s"):format(hud.Enabled and "ON" or "OFF"))
end)

button("4. raise menu to top", 346, function()
    local gui = menuGui()
    if not gui then
        say("menu not found")
        return
    end
    gui.DisplayOrder = 1999998
    say("raised " .. gui.Name .. " -> 1999998")
end)

button("5. input connections in engine", 378, function()
    local names = {
        "InputBegan", "InputEnded", "InputChanged",
    }
    for _, name in ipairs(names) do
        local ok, signal = pcall(function()
            return UIS[name]
        end)
        if ok and signal then
            say(("UIS.%s = %d conns"):format(name, #conns(signal)))
        end
    end

    local menu = menuGui()
    if menu then
        local total = 0
        pcall(function()
            for _, obj in ipairs(menu:GetDescendants()) do
                if obj:IsA("GuiButton") then
                    total += #conns(obj.MouseButton1Click) + #conns(obj.MouseButton1Down)
                end
            end
        end)
        say(("menu gui total button conns: %d"):format(total))
    end
end)

button("6. close doctor", 410, function()
    screen:Destroy()
end)

-- live ------------------------------------------------------------------------

task.spawn(function()
    while screen.Parent do
        local ok = pcall(render)
        if not ok then
            break
        end
        task.wait(0.4)
    end
end)

pcall(render)
print("doctor_ui v4: panel up, build", tostring(getgenv().prampa_BuildID))
