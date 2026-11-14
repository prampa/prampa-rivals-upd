"""Build tools/ue_probe.luau from the template + the base's readable name pool.

The candidate list is every PascalCase identifier the base carries in its
constant table. Running the probe tells us which of them still exist in the
live game, which is the first half of the version diff.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "ue_probe.template.luau"
STRINGS = ROOT / "ue_strings.txt"
OUT = ROOT / "ue_probe.luau"

# engine type names carry no structural signal
BLOCK = {
    "Instance", "Vector2", "Vector3", "Vector2int16", "Vector3int16", "CFrame",
    "UDim", "UDim2", "Color3", "ColorSequence", "NumberSequence", "NumberRange",
    "BrickColor", "Rect", "TweenInfo", "Faces", "Axes", "Ray", "Region3",
    "Region3int16", "PhysicalProperties", "PathWaypoint", "DateTime", "Random",
    "Enum", "EnumItem", "RBXScriptSignal", "RBXScriptConnection", "DockWidgetPluginGui",
    "GetService", "GetChildren", "GetDescendants", "GetAttribute", "GetAttributes",
    "SetAttribute", "SetAttributes", "FindFirstAncestor", "FindFirstAncestorOfClass",
    "FindFirstAncestorWhichIsA", "FindFirstChild", "FindFirstChildOfClass",
    "FindFirstChildWhichIsA", "IsDescendantOf", "IsA", "GetPropertyChangedSignal",
    "GetFullName", "Destroy", "Clone", "WaitForChild", "HttpGet", "HttpPost",
}

names = []
seen = set()
for line in STRINGS.read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if not re.fullmatch(r"[A-Z][A-Za-z0-9]{3,39}", s):
        continue
    if s in BLOCK or s in seen:
        continue
    seen.add(s)
    names.append(s)

names.sort()

# wrap so the generated file stays readable
rows, row = [], []
for n in names:
    if sum(len(x) + 1 for x in row) + len(n) > 108:
        rows.append(" ".join(row))
        row = []
    row.append(n)
if row:
    rows.append(" ".join(row))

block = "\n".join(rows)
text = TEMPLATE.read_text(encoding="utf-8").replace("@@CANDIDATES@@", block)
OUT.write_text(text, encoding="utf-8")

print(f"candidates : {len(names)}")
print(f"template   : {TEMPLATE.stat().st_size} B")
print(f"output     : {OUT} ({OUT.stat().st_size} B)")
print("sample     :", ", ".join(names[:12]))
