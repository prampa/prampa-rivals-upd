import pathlib

p = pathlib.Path(r"C:\RivalsUPDtest\patch_ue2.py")
s = p.read_text(encoding="utf-8")


def sub(old, new, count=1):
    global s
    assert s.count(old) == count, (s.count(old), old[:80])
    s = s.replace(old, new)


# a ScreenGui that sits above the menu and swallows clicks is the one failure
# that keeps the base drawing while making every control dead
sub(
    """    local function watchTitle()""",
    """    local MENU_ORDER = 500000

    local function menuScreenGui()
        for _, gui in ipairs(guiRoots()) do
            local ok, descendants = pcall(function()
                return gui:GetDescendants()
            end)
            if ok then
                for _, obj in ipairs(descendants) do
                    if obj:IsA('TextLabel') and (isMenuTitle(obj.Text) or obj.Text == ADDON_TITLE) then
                        return gui
                    end
                end
            end
        end
        return nil
    end

    local function raiseMenu()
        local gui = menuScreenGui()
        if not gui then
            return false
        end
        if gui:GetAttribute('prampa_Raised') then
            return true
        end

        pcall(function()
            gui.DisplayOrder = MENU_ORDER
            gui:SetAttribute('prampa_Raised', true)
        end)

        local parent = guiParent()
        if parent then
            for _, child in ipairs(parent:GetChildren()) do
                if child.Name == ISLAND_NAME or child.Name == WATERMARK_NAME then
                    pcall(function()
                        child.DisplayOrder = MENU_ORDER + 10
                    end)
                end
            end
        end

        print('[' .. BRAND .. '] menu raised above overlays, display order ' .. MENU_ORDER)
        return true
    end

    local function watchTitle()""",
)

sub(
    """                    applyTitle()
                end
            end
        end)
    end""",
    """                    applyTitle()
                    raiseMenu()
                end
            end
        end)
    end""",
)

sub(
    """                step('island', buildIsland)""",
    """                step('island', buildIsland)
                step('menu raise', raiseMenu)""",
)

p.write_text(s, encoding="utf-8", newline="")
print("raise patch ok:", len(s))
