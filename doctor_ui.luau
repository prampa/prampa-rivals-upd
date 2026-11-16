-- doctor_ui.luau v3 — on-screen input doctor, no console, no name lookup
--   loadstring(game:HttpGet("https://raw.githubusercontent.com/prampa/prampa-rivals-upd/main/doctor_ui.luau"))()
--
-- v3 changes:
--   * finds ScreenGuis at ANY depth (folders under gethui / CoreGui / PlayerGui)
--   * finds the menu structurally (most TextButtons), never by title text
--   * counts clicks that actually REACH the menu's buttons
--   * one button disables the prampa HUD entirely

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
panel.Size = UDim2.fromOffset(478, 480)
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
title.Text = "INPUT DOCTOR v3   build " .. tostring(getgenv().prampa_BuildID or "?")
title.Parent = panel

local status = Instance.new("TextLabel")
status.Size = UDim2.new(1, -24, 0, 208)
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
    if #lines > 13 then
        table.remove(lines, 1)
    end
end

-- scan ------------------------------------------------------------------------

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

local function buttonCount(gui)
    local n = 0
    pcall(function()
        for _, obj in ipairs(gui:GetDescendants()) do
            if obj:IsA("TextButton") then
                n += 1
            end
        end
    end)
    return n
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
            local n = buttonCount(gui)
            if n > bestN then
                best, bestN = gui, n
            end
        end
    end
    if bestN < 3 then
        return nil, 0
    end
    return best, bestN
end

local function guiPath(gui)
    local parts = {}
    local node = gui
    local ok = pcall(function()
        while node and node ~= game do
            table.insert(parts, 1, node.Name)
            node = node.Parent
        end
    end)
    if not ok then
        return gui:GetFullName()
    end
    return table.concat(parts, "/")
end

local function summary()
    say("layer: " .. tostring(HOST and HOST.Name) .. "   guis: " .. #allScreenGuis())

    local gui, n = menuGui()
    if gui then
        say(("menu: %s  order=%s  enabled=%s  buttons=%d"):format(
            gui.Name, tostring(gui.DisplayOrder), tostring(gui.Enabled), n))
        say("  at " .. guiPath(gui))
    else
        say("menu: not found structurally")
    end

    local hud = hudGui()
    if hud then
        say(("hud: %s  enabled=%s  order=%s"):format(
            hud.Name, tostring(hud.Enabled), tostring(hud.DisplayOrder)))

        -- what inside our own HUD can eat a click?
        local eaters = 0
        pcall(function()
            for _, obj in ipairs(hud:GetDescendants()) do
                if obj:IsA("GuiButton") and obj.Visible then
                    local s = obj.AbsoluteSize
                    if s.X >= 400 and s.Y >= 400 then
                        eaters += 1
                        say(("  big button: %s %s visible=true"):format(obj.Name, obj.ClassName))
                    end
                end
            end
        end)
        if eaters == 0 then
            say("  no fullscreen buttons visible in hud")
        end
    else
        say("hud: not found")
    end

    say("clicks reaching menu buttons: " .. tostring(CLICKS or 0))
    say("mouse: " .. tostring(UIS.MouseBehavior))
end

CLICKS = 0

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
    end)
    return b
end

button("1. find the menu (structural)", 244, function()
    local gui, n = menuGui()
    if not gui then
        say("no ScreenGui has 3+ TextButtons")
        say("=> the menu is not in PlayerGui, gethui or CoreGui")
        return
    end
    say(("found %s with %d buttons"):format(gui.Name, n))
    say(guiPath(gui))
    gui.DisplayOrder = 1999998
    say("raised to 1999998 - try clicking it now")
end)

button("2. raise EVERY ScreenGui", 276, function()
    local list = allScreenGuis()
    local order = 1999000
    for _, gui in ipairs(list) do
        pcall(function()
            gui.DisplayOrder = order
        end)
        order += 1
    end
    say(("raised %d ScreenGuis to the top stack"):format(#list))
    say("did the menu wake up?")
end)

button("3. disable prampa HUD", 308, function()
    local hud = hudGui()
    if not hud then
        say("prampa HUD not found")
        return
    end
    hud.Enabled = not hud.Enabled
    say(("prampa HUD %s (%s)"):format(hud.Enabled and "ON" or "OFF", hud.Name))
    say("if the menu wakes up now, our HUD was the blocker")
end)

button("4. count clicks on menu", 340, function()
    local gui = menuGui()
    if not gui then
        say("menu not found, nothing to hook")
        return
    end
    CLICKS = 0
    local hooked = 0
    pcall(function()
        for _, obj in ipairs(gui:GetDescendants()) do
            if obj:IsA("TextButton") and hooked < 300 then
                local ok = pcall(function()
                    obj.MouseButton1Down:Connect(function()
                        CLICKS += 1
                    end)
                end)
                if ok then
                    hooked += 1
                end
            end
        end
    end)
    say(("listening on %d buttons of %s"):format(hooked, gui.Name))
    say("now click the menu - the counter runs live")
end)

button("5. toggle game ScreenGuis", 372, function()
    local menu = menuGui()
    local hud = hudGui()
    local n = 0
    if pg then
        for _, gui in ipairs(pg:GetChildren()) do
            if gui:IsA("ScreenGui") and gui ~= menu and gui ~= hud and gui ~= screen then
                gui.Enabled = not gui.Enabled
                n += 1
            end
        end
    end
    say(("toggled %d game ScreenGuis"):format(n))
    say("did the menu wake up?")
end)

button("6. close doctor", 404, function()
    screen:Destroy()
end)

-- live ------------------------------------------------------------------------

task.spawn(function()
    while screen.Parent do
        local ok = pcall(function()
            local gui, n = menuGui()
            local hud = hudGui()
            local info = {
                "clicks=" .. tostring(CLICKS),
                "mouse=" .. tostring(UIS.MouseBehavior),
            }
            if gui then
                info[#info + 1] = ("menu=%s order=%s btn=%d"):format(
                    gui.Name, tostring(gui.DisplayOrder), n)
            else
                info[#info + 1] = "menu=not found"
            end
            if hud then
                info[#info + 1] = ("hud=%s enabled=%s"):format(hud.Name, tostring(hud.Enabled))
            else
                info[#info + 1] = "hud=not found"
            end
            status.Text = table.concat(lines, "\n") .. "\n\n-- live --\n" .. table.concat(info, "\n")
        end)
        if not ok then
            break
        end
        task.wait(0.4)
    end
end)

-- first scan straight away
pcall(summary)

print("doctor_ui v3: panel up, build", tostring(getgenv().prampa_BuildID))
