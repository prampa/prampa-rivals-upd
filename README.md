# prampa-rivals-upd

UE (Unnamed Enhancements) build with the prampa addon plus a **version-drift shim**.

Rivals updated and the base stopped working. The base is a cracked, obfuscated binary —
there is no source to patch. This build does not rewrite the base. It sits between the
base and the engine, and it is staged so a crash can be attributed instead of guessed at.

## Load

Safe mode (default, nothing is hooked):

```lua
loadstring(game:HttpGet("https://raw.githubusercontent.com/prampa/prampa-rivals-upd/main/rivals_menu.luau?v=c6c8767f"))()
```

Full mode (shim resolves lookups):

```lua
getgenv().UE_SHIM = "full"
loadstring(game:HttpGet("https://raw.githubusercontent.com/prampa/prampa-rivals-upd/main/rivals_menu.luau?v=c6c8767f"))()
```

Build `c6c8767f`.

## Modes

| mode | hooks `__index` | resolves | reports | use |
|---|---|---|---|---|
| `safe` (default) | no | no | yes | isolate a crash, snapshot the tree |
| `full` | yes | yes | yes | actually patch renames at runtime |

Safe mode still wraps the base's boot in `xpcall`, captures `print`/`warn`, writes
`ue_shim_boot.txt` before the base starts, and writes the full report on error or
after 25 s.

## What full mode resolves

When a lookup returns nil it retries, in this order:

| rule | example |
|---|---|
| manual alias | `UE_ShimAlias('Combat', 'combat_system')` |
| case only | `Health` → `health` |
| separators / punctuation | `CombatSystem` → `combat_system` |
| version or numeric suffix | `Attack` → `AttackV2` |
| unique match down the tree (depth 3, 700 nodes) | `Weapons` found two folders deep |
| sole remote in the folder | `Shoot` → `Fire` when the folder holds exactly one remote |

`WaitForChild` is capped at 4 s so a renamed child cannot hang the script forever.
Every substitution is logged.

## The report

```
ue_shim_<timestamp>.txt
```

in the executor workspace, plus `ue_shim_boot.txt` written before boot.

```
SHIM|build|date
META|place|game|executor|library|hooked
SUB|kind|from|to|why|parentPath
MISS|kind|name|parentPath|extra|count
CON|print/warn line from the base
ERR|boot traceback
NODE|path|class          (ReplicatedStorage depth 4, Workspace depth 3)
```

## Commands

```lua
UE_ShimReport()              -- write the report now
UE_ShimAlias('Old', 'New')   -- pin a rename by hand
UE_ShimAggressive(false)     -- disable the tree-wide and sole-remote guesses
UE_ShimOff()                 -- stop resolving, keep reporting
```

## Builds

| build | what |
|---|---|
| `c6c8767f` | safe-by-default shim, hardened exports |
| `c77df91c` | first shim build, hook always on |
| `64cd587c` | plain addon, no shim (`prampa/prampa-rivals`) |
