"""Pull readable string literals out of the obfuscated UE base.

The VM keeps its constants in one flat table. Some entries are plain ASCII
(option names, instance names, method names), the rest are byte-escaped
ciphertext. This dumps the readable half so it can be diffed against a live
game snapshot.
"""
import re
import sys
from collections import Counter
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\RivalsTest\ue-v2-cracked.luau.txt")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else r"C:\RivalsTest\tools\ue_strings.txt")

raw = SRC.read_text(encoding="utf-8", errors="replace")

# single-quoted Lua strings, no newlines inside
lits = re.findall(r"'((?:[^'\\\n]|\\.)*)'", raw)

readable = []
for s in lits:
    if "\\" in s:
        continue
    if len(s) < 2 or len(s) > 120:
        continue
    # printable ascii only
    if not all(32 <= ord(c) < 127 for c in s):
        continue
    readable.append(s)

uniq = sorted(set(readable), key=lambda s: (len(s), s))
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(uniq), encoding="utf-8")

print(f"literals scanned : {len(lits)}")
print(f"readable kept    : {len(readable)}")
print(f"unique           : {len(uniq)}")
print(f"written          : {OUT}")

# quick buckets that matter for a game-version diff
def show(title, pred, limit=25):
    hits = [s for s in uniq if pred(s)]
    if hits:
        print(f"\n-- {title} ({len(hits)}) --")
        for s in hits[:limit]:
            print("   ", s)

ALPHA = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]*$")
show("PascalCase identifiers", lambda s: bool(ALPHA.match(s)) and s[0].isupper(), 40)
show("snake_case keys", lambda s: re.fullmatch(r"[a-z][a-z0-9_]{3,}", s) is not None, 40)
show("dotted / slash paths",
     lambda s: ("/" in s or "." in s or ":" in s) and " " not in s and len(s) < 60, 40)
