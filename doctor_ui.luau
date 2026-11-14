-- doctor_ui.luau — on-screen input doctor, no console needed
--   loadstring(game:HttpGet("https://raw.githubusercontent.com/prampa/prampa-rivals-upd/main/doctor_ui.luau"))()
--
-- Draws a panel above everything, in the same GUI layer as the prampa island
-- (which we know receives clicks). Buttons manipulate the other GUIs so you can
-- see which one is eating the menu's input.

local Players = game:GetService("Players")
local UIS = game:GetService("UserInputService")

local plr = Players.LocalPlayer
local pg = plr:FindFirstChild("PlayerGui")
local hui = nil
if gethui then
    local ok, value = pcall(gethui)
    if ok then
        hui = value
    end
end

local parent = hui or pg
local screen = Instance.new("ScreenGui")
screen.Name = "prampa_Doctor"
screen.ResetOnSpawn = false
screen.IgnoreGuiInset = true
screen.DisplayOrder = 2000000
screen.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
screen.Parent = parent

local panel = Instance.new("Frame")
panel.Size = UDim2.fromOffset(400, 300)
panel.Position = UDim2.fromOffset(14, 14)
panel.BackgroundColor3 = Color3.fromRGB(10, 10, 13)
panel.BackgroundTransparency = 0.08
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
title.Size = UDim2.new(1, -20, 0, 24)
title.Position = UDim2.fromOffset(12, 8)
title.BackgroundTransparency = 1
title.Font = Enum.Font.GothamBold
title.TextSize = 13
title.TextColor3 = Color3.fromRGB(230, 230, 255)
title.TextXAlignment = Enum.TextXAlignment.Left
title.Text = "INPUT DOCTOR   build " .. tostring(getgenv().prampa_BuildID or "?")
title.Parent = panel

local status = Instance.new("TextLabel")
status.Size = UDim2.new(1, -24, 1, -150)
status.Position = UDim2.fromOffset(12, 34)
status.BackgroundTransparency = 1
status.Font = Enum.Font.Code
status.TextSize = 12
status.TextWrapped = true
status.TextXAlignment = Enum.TextXAlignment.Left
status.TextYAlignment = Enum.TextYAlignment.Top
status.TextColor3 = Color3.fromRGB(180, 200, 190)
status.Text = "starting..."
status.Parent = panel

local lines = {}
local function say(text)
    lines[#lines + 1] = tostring(text)
    if #lines > 12 then
        table.remove(lines, 1)
    end
    status.Text = table.concat(lines, "\n")
end

-- find the menu's ScreenGui by its title label --------------------------------

local function allScreenGuis()
    local out = {}
    for _, root in ipairs({ pg, parent }) do
        if root then
            for _, child in ipairs(root:GetChildren()) do
                if child:IsA("ScreenGui") and child ~= screen and not table.find(out, child) then
                    out[#out + 1] = child
                end
            end
        end
    end
    return out
end

local function menuGui()
    for _, gui in ipairs(allScreenGuis()) do
        local ok, kids = pcall(function()
            return gui:GetDescendants()
        end)
        if ok then
            for _, obj in ipairs(kids) do
                if obj:IsA("TextLabel") then
                    local text = obj.Text
                    if text == "Prampa Menu" or text:find("Unnamed Enhancements") then
                        return gui, obj
                    end
                end
            end
        end
    end
    return nil
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
    end)
    return b
end

button("1. What is under the cursor", 172, function()
    local mx, my = UIS:GetMouseLocation()
    say(("cursor %.0f,%.0f  mouse=%s"):format(mx, my, tostring(UIS.MouseBehavior)))
    local found = 0
    for _, root in ipairs({ pg, parent }) do
        if root then
            for _, obj in ipairs(root:GetDescendants()) do
                pcall(function()
                    if obj:IsA("GuiObject") and obj.Visible then
                        local p, s = obj.AbsolutePosition, obj.AbsoluteSize
                        if mx >= p.X and mx <= p.X + s.X and my >= p.Y and my <= p.Y + s.Y then
                            if found < 5 then
                                local gui = obj
                                while gui and not gui:IsA("ScreenGui") do
                                    gui = gui.Parent
                                end
                                say(("%s | %s | active=%s"):format(
                                    obj.Name, obj.ClassName, tostring(obj.Active)))
                                if gui then
                                    say("   in " .. gui.Name .. " order=" .. gui.DisplayOrder)
                                end
                            end
                            found += 1
                        end
                    end
                end)
            end
        end
    end
    if found == 0 then
        say("nothing under cursor")
    end
end)

button("2. Raise the UE menu", 208, function()
    local gui = menuGui()
    if not gui then
        say("menu ScreenGui not found")
        return
    end
    gui.DisplayOrder = 1999999
    say("raised " .. gui.Name .. " -> 1999999")
    say("was it clickable now?")
end)

button("3. Toggle game GUIs", 244, function()
    local toggled = 0
    local menu = menuGui()
    if pg then
        for _, gui in ipairs(pg:GetChildren()) do
            if gui:IsA("ScreenGui") and gui ~= menu and gui.Name ~= "prampa_Doctor" then
                gui.Enabled = not gui.Enabled
                toggled += 1
            end
        end
    end
    say(("toggled %d game ScreenGuis"):format(toggled))
    say("did the menu wake up?")
end)

button("4. Remove doctor", 280, function()
    screen:Destroy()
end)

-- live status -----------------------------------------------------------------

task.spawn(function()
    while screen.Parent do
        local gui = menuGui()
        local info = {}
        info[#info + 1] = "mouse=" .. tostring(UIS.MouseBehavior)
        if gui then
            info[#info + 1] = ("menu=%s order=%d enabled=%s"):format(gui.Name, gui.DisplayOrder, tostring(gui.Enabled))
        else
            info[#info + 1] = "menu=NOT FOUND"
        end
        status.Text = table.concat(lines, "\n") .. "\n\n" .. table.concat(info, "\n")
        task.wait(0.5)
    end
end)

print("doctor_ui: panel up, build", tostring(getgenv().prampa_BuildID))
