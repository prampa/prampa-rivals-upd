import pathlib

p = pathlib.Path(r"C:\RivalsUPDtest\patch_ue2.py")
s = p.read_text(encoding="utf-8")

old = """        local parent = guiParent()
        local ok, children = pcall(function()
            return parent:GetChildren()
        end)
        if ok then
            for _, child in ipairs(children) do
                if child:IsA('ScreenGui')
                    and child.Name ~= ISLAND_NAME
                    and child.Name ~= WATERMARK_NAME
                    and not table.find(roots, child) then
                    table.insert(roots, child)
                end
            end
        end

        return roots"""

new = """        -- gethui() only covers the hidden layer.  the menu can be parented in
        -- PlayerGui, in which case nothing here would ever find it.
        local parents = { guiParent() }

        local okPlayer, playerGui = pcall(function()
            return LocalPlayer and LocalPlayer:FindFirstChild('PlayerGui')
        end)
        if okPlayer and playerGui then
            table.insert(parents, playerGui)
        end

        for _, parent in ipairs(parents) do
            if parent then
                local ok, children = pcall(function()
                    return parent:GetChildren()
                end)
                if ok then
                    for _, child in ipairs(children) do
                        if child:IsA('ScreenGui')
                            and child.Name ~= ISLAND_NAME
                            and child.Name ~= WATERMARK_NAME
                            and not table.find(roots, child) then
                            table.insert(roots, child)
                        end
                    end
                end
            end
        end

        return roots"""

assert s.count(old) == 1, s.count(old)
s = s.replace(old, new)
p.write_text(s, encoding="utf-8", newline="")
print("guiRoots now scans PlayerGui:", len(s))
