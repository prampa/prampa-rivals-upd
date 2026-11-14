-- input_doctor.luau — find out what is eating clicks
-- Run this while the UE menu is open, click on the menu during the 6 s window.
--   loadstring(game:HttpGet("https://raw.githubusercontent.com/prampa/prampa-rivals-upd/main/input_doctor.luau"))()

local Players = game:GetService("Players")
local UIS = game:GetService("UserInputService")
local plr = Players.LocalPlayer
local pg = plr:FindFirstChild("PlayerGui")
local cam = workspace.CurrentCamera
local lines = {}

local function say(text)
    lines[#lines + 1] = text
    print(text)
end

local hui = nil
if gethui then
    local ok, value = pcall(gethui)
    if ok then
        hui = value
    end
end

local vp = cam.ViewportSize
local mx, my = UIS:GetMouseLocation()

say(("cursor=%.0f,%.0f viewport=%.0fx%.0f mouse=%s focused=%s"):format(
    mx, my, vp.X, vp.Y,
    tostring(UIS.MouseBehavior),
    tostring(UIS:GetFocusedTextBox())
))

-- ScreenGui inventory ---------------------------------------------------------

local function inventory(root, label)
    if not root then
        say("SG " .. label .. " (not available)")
        return
    end
    for _, gui in ipairs(root:GetChildren()) do
        if gui:IsA("ScreenGui") then
            local biggest, area = nil, 0
            for _, d in ipairs(gui:GetDescendants()) do
                local ok = pcall(function()
                    if d:IsA("GuiObject") and d.Visible then
                        local a = d.AbsoluteSize.X * d.AbsoluteSize.Y
                        if a > area then
                            area = a
                            biggest = d
                        end
                    end
                end)
            end
            say(("SG %-6s %-30s order=%3d enabled=%-5s biggest=%s %.0fx%.0f"):format(
                label, gui.Name, gui.DisplayOrder, tostring(gui.Enabled),
                biggest and biggest.ClassName or "-",
                biggest and biggest.AbsoluteSize.X or 0,
                biggest and biggest.AbsoluteSize.Y or 0
            ))
        end
    end
end

say("")
inventory(pg, "PLAYER")
inventory(hui, "CORE")

-- what is under the cursor ----------------------------------------------------

local function hitsAt(root, label)
    if not root then
        return
    end
    for _, d in ipairs(root:GetDescendants()) do
        pcall(function()
            if not d:IsA("GuiObject") or not d.Visible then
                return
            end
            local pos = d.AbsolutePosition
            local size = d.AbsoluteSize
            if mx >= pos.X and mx <= pos.X + size.X and my >= pos.Y and my <= pos.Y + size.Y then
                local gui = d
                while gui and not gui:IsA("ScreenGui") do
                    gui = gui.Parent
                end
                say(("HIT %-6s %-42s %-14s z=%4d bg=%.2f active=%s"):format(
                    label, d:GetFullName(), d.ClassName, d.ZIndex,
                    d.BackgroundTransparency, tostring(d.Active)
                ))
            end
        end)
    end
end

say("")
say("-- under cursor --")
hitsAt(pg, "PLAYER")
hitsAt(hui, "CORE")

-- full-screen click eaters ----------------------------------------------------

say("")
say("-- fullscreen gui objects --")
local function fullscreen(root, label)
    if not root then
        return
    end
    for _, d in ipairs(root:GetDescendants()) do
        pcall(function()
            if not d:IsA("GuiObject") or not d.Visible then
                return
            end
            local size = d.AbsoluteSize
            if size.X >= vp.X * 0.9 and size.Y >= vp.Y * 0.9 then
                say(("FULL %-6s %-42s %-12s active=%-5s bg=%.2f"):format(
                    label, d:GetFullName(), d.ClassName,
                    tostring(d.Active), d.BackgroundTransparency
                ))
            end
        end)
    end
end

fullscreen(pg, "PLAYER")
fullscreen(hui, "CORE")

-- do input events reach the engine at all -------------------------------------

say("")
say("-- click the menu now, 6 s --")
local seen = {}
local conn = UIS.InputBegan:Connect(function(input, processed)
    if #seen < 40 then
        seen[#seen + 1] = input.UserInputType.Name .. ":gpe=" .. tostring(processed)
    end
end)

task.delay(6, function()
    conn:Disconnect()
    say("input events: " .. (#seen > 0 and table.concat(seen, " ") or "NONE"))

    local text = table.concat(lines, "\n")
    if writefile then
        local ok = pcall(writefile, "input_doctor.txt", text)
        if ok then
            print("input_doctor: wrote input_doctor.txt")
        end
    end
    if setclipboard then
        pcall(setclipboard, text)
        print("input_doctor: also copied to clipboard")
    end
end)
