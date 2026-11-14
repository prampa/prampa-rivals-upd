import pathlib

p = pathlib.Path(r"C:\RivalsUPDtest\patch_ue2.py")
s = p.read_text(encoding="utf-8")


def sub(old, new, count=1):
    global s
    assert s.count(old) == count, (s.count(old), old[:70])
    s = s.replace(old, new)


# 1. mode + safe default -------------------------------------------------------
sub(
    """        local S = {
            subs = {},""",
    """        local MODE = tostring(env.UE_SHIM or 'safe')
        local FULL = MODE == 'full'

        local S = {
            subs = {},""",
)

sub(
    """            aggressive = true,
            enabled = true,""",
    """            aggressive = true,
            enabled = FULL,""",
)

# 2. drop the GetService wrapper (highest-frequency, lowest-value hook surface) --
sub(
    """            for _, key in ipairs({ 'FindFirstChild', 'FindFirstChildOfClass', 'WaitForChild', 'GetService' }) do""",
    """            for _, key in ipairs({ 'FindFirstChild', 'FindFirstChildOfClass', 'WaitForChild' }) do""",
)

sub(
    """
            if originals.GetService then
                wrappers.GetService = function(self, name)
                    local ok, value = pcall(function()
                        return originals.GetService(self, name)
                    end)
                    if not ok or value == nil then
                        recordMiss('service', self, name)
                    end
                    return value
                end
            end
""",
    "",
)

# 3. never let resolver errors reach the engine's hot path ---------------------
sub(
    """                    if value == nil then
                        local hit, why = resolve(self, name)""",
    """                    if value == nil then
                        local hit, why
                        pcall(function()
                            hit, why = resolve(self, name)
                        end)""",
    count=2,
)

# 4. mode-aware install + boot marker ------------------------------------------
sub(
    """        local okHook = install()
        outerPrint(TAG .. ': ' .. (okHook and 'hook installed' or 'hook unavailable, reporting only'))""",
    """        S.mode = MODE
        local okHook = false
        if FULL then
            okHook = install()
        end

        outerPrint(TAG .. ': mode=' .. MODE .. '  build=' .. BUILD_ID)
        if FULL then
            outerPrint(TAG .. ': hook ' .. (okHook and 'installed' or 'unavailable, reporting only'))
        end

        -- written before the base boots, so a crash still leaves a fingerprint
        if writefile then
            pcall(writefile, 'ue_shim_boot.txt', table.concat({
                'BOOT|' .. BUILD_ID .. '|' .. MODE .. '|' .. tostring(okHook) .. '|' .. os.date('%Y-%m-%d %H:%M:%S'),
                'META|' .. tostring(game.PlaceId) .. '|' .. tostring(game.GameId),
            }, '\\n'))
            outerPrint(TAG .. ': boot file ue_shim_boot.txt')
        end""",
)

# 5. boot markers so the console shows exactly how far the base got ------------
sub(
    """                local results = table.pack(xpcall(originalRun, function(err)""",
    """                outerPrint(TAG .. ': entering base boot')
                local results = table.pack(xpcall(originalRun, function(err)""",
)

sub(
    """                return table.unpack(results, 2, results.n)""",
    """                outerPrint(TAG .. ': base boot returned')
                return table.unpack(results, 2, results.n)""",
)

p.write_text(s, encoding="utf-8", newline="")
print("patched, bytes:", len(s))
