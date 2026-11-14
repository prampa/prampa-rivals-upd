# prampa-rivals-upd

UE (Unnamed Enhancements) build with the prampa addon plus a **version-drift shim**.

Rivals updated and the base stopped working. The base is a cracked, obfuscated binary —
there is no source to patch. This build does not try to rewrite the base. It sits
between the base and the engine and does two things:

1. **resolves renames it can prove** before the base gives up on them
2. **records everything it could not resolve**, so the next build is driven by data

## Load

```lua
loadstring(game:HttpGet("https://raw.githubusercontent.com/prampa/prampa-rivals-upd/main/rivals_menu.luau"))()
```

Build `c77df91c`.

## What the shim resolves

When a lookup returns nil it retries, in this order:

| rule | example |
|---|---|
| manual alias | `UE_ShimAlias('Combat', 'combat_system')` |
| case only | `Health` → `health` |
| separators / punctuation | `CombatSystem` → `combat_system` |
| version or numeric suffix | `Attack` → `AttackV2` |
| unique match down the tree (depth 3, 700 nodes) | `Weapons` found two folders deep |
| sole remote in the folder | `Shoot` → `Fire` when the folder holds exactly one remote |

`WaitForChild` is capped at 4 s so a renamed child can no longer hang the whole
script forever. Every substitution is logged; nothing is silent.

## The report

Written automatically when the base errors during boot, or after 25 s if no menu
appeared:

```
ue_shim_<timestamp>.txt
```

in the executor workspace. Inside:

```
SHIM|build|date
META|place|game|executor|library|hooked
SUB|kind|from|to|why|parentPath
MISS|kind|name|parentPath|extra|count
CON|print/warn line from the base
ERR|boot traceback
NODE|path|class          (ReplicatedStorage depth 4, Workspace depth 3)
```

`MISS` lines are the ones that matter: what the base asked for, where, and how
often. `SUB` lines are what the shim already papered over.

## Commands

```lua
UE_ShimReport()              -- write the report now
UE_ShimAlias('Old', 'New')   -- pin a rename by hand
UE_ShimAggressive(false)     -- disable the tree-wide and sole-remote guesses
UE_ShimOff()                 -- stop resolving, keep reporting
```

## Previous build

`64cd587c` — the plain addon, no shim. Kept in `prampa/prampa-rivals` main.
