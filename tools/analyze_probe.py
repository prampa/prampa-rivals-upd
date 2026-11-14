"""Summarise a ue_probe report against the base's own name pool.

Usage:
    python tools/analyze_probe.py ue_probe_YYYYMMDD_HHMMSS.txt
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(path):
    meta, sections = {}, {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("|")
        tag = parts[0]
        sections.setdefault(tag, []).append(parts[1:])
    if "META" in sections:
        keys = ["place", "game", "job", "creator", "executor", "roblox", "clock"]
        meta = dict(zip(keys, sections["META"][0]))
    return meta, sections


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    path = sys.argv[1]
    meta, s = load(path)

    print("== meta ==")
    for k, v in meta.items():
        print(f"  {k:9} {v}")

    missing = [p[0] for p in s.get("SVC", []) if p[1:] == ["missing"]]
    print(f"\n== services ==\n  missing: {', '.join(missing) or 'none'}")

    remotes = s.get("REM", [])
    print(f"\n== remotes ({len(remotes)}) ==")
    by_class = Counter(r[1] for r in remotes)
    for cls, n in by_class.most_common():
        print(f"  {cls:12} {n}")

    nodes = s.get("NODE", [])
    print(f"\n== tree ==\n  nodes: {len(nodes)}  player rows: {len(s.get('PLAY', []))}")

    look = s.get("LOOK", [])
    kinds = Counter(e[0] for e in look)
    print("\n== what the base asked for ==")
    for kind, n in kinds.most_common():
        print(f"  {kind:14} {n}")

    for kind in ("ffc_nil", "ffc_class_nil"):
        rows = [e for e in look if e[0] == kind]
        if rows:
            print(f"\n-- {kind} ({len(rows)}) --")
            for e in sorted(rows, key=lambda r: -int(r[4] or 1))[:40]:
                print(f"  {e[2]:30} in {e[1]}  {e[3]}  x{e[4]}")

    waits = [e for e in look if e[0] == "wait"]
    if waits:
        names = {n[0] for n in nodes}
        print(f"\n-- wait ({len(waits)}) --")
        for e in sorted(waits, key=lambda r: -int(r[4] or 1))[:40]:
            flag = "" if e[2] in names else "   <-- not in tree"
            print(f"  {e[2]:30} in {e[1]}  timeout={e[3]}  x{e[4]}{flag}")

    nilprops = [e for e in look if e[0] == "nilprop"]
    if nilprops:
        print(f"\n-- nil property reads ({len(nilprops)}) --")
        for e in sorted(nilprops, key=lambda r: -int(r[4] or 1))[:60]:
            print(f"  {e[2]:28} on {e[1]}  x{e[4]}")

    http = [e for e in look if e[0] == "http"]
    if http:
        print(f"\n-- http ({len(http)}) --")
        for e in http[:20]:
            print(f"  {e[2]}")

    for tag in ("CAND_ABSENT", "CAND_PRESENT"):
        for row in s.get(tag, []):
            names = row[1].split()
            print(f"\n== {tag.split('_')[1].lower()} candidates: {row[0]} ==")
            print("  " + ", ".join(names[:80]))
            if len(names) > 80:
                print(f"  ... +{len(names) - 80}")

    con = s.get("CON", [])
    if con:
        print(f"\n== base console ({len(con)}) ==")
        for c in con[:60]:
            print("  " + " ".join(c)[:180])

    err = s.get("ERR", [])
    if err:
        print("\n== error ==")
        for e in err:
            print("  " + " ".join(e)[:400])

    return 0


if __name__ == "__main__":
    sys.exit(main())
