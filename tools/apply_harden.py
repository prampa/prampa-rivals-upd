import pathlib

p = pathlib.Path(r"C:\RivalsUPDtest\patch_ue2.py")
s = p.read_text(encoding="utf-8")


def sub(old, new, count=1):
    global s
    assert s.count(old) == count, (s.count(old), old[:80])
    s = s.replace(old, new)


# exports and global overrides must never be able to kill the addon block
sub(
    """        env.print = function(...)
            captureConsole('print', ...)
            return outerPrint(...)
        end
        env.warn = function(...)
            captureConsole('warn', ...)
            return outerWarn(...)
        end""",
    """        pcall(function()
            env.print = function(...)
                captureConsole('print', ...)
                return outerPrint(...)
            end
            env.warn = function(...)
                captureConsole('warn', ...)
                return outerWarn(...)
            end
        end)""",
)

sub(
    """        env.UE_ShimReport = function(reason)
            return report(reason or 'manual')
        end

        env.UE_ShimAlias = function(from, to)
            aliases[tostring(from)] = tostring(to)
            resolveCache = setmetatable({}, { __mode = 'k' })
            outerPrint(TAG .. ': alias ' .. tostring(from) .. ' -> ' .. tostring(to))
        end

        env.UE_ShimAggressive = function(flag)
            S.aggressive = flag ~= false
            return S.aggressive
        end

        env.UE_ShimOff = function()
            S.enabled = false
        end""",
    """        local function export(name, value)
            pcall(function()
                env[name] = value
            end)
        end

        export('UE_ShimReport', function(reason)
            return report(reason or 'manual')
        end)

        export('UE_ShimAlias', function(from, to)
            aliases[tostring(from)] = tostring(to)
            resolveCache = setmetatable({}, { __mode = 'k' })
            outerPrint(TAG .. ': alias ' .. tostring(from) .. ' -> ' .. tostring(to))
        end)

        export('UE_ShimAggressive', function(flag)
            S.aggressive = flag ~= false
            return S.aggressive
        end)

        export('UE_ShimOff', function()
            S.enabled = false
        end)""",
)

p.write_text(s, encoding="utf-8", newline="")
print("hardened, bytes:", len(s))
