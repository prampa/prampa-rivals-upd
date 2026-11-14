import subprocess
import sys
from pathlib import Path

TMP = Path(r"C:\Users\Administrator\AppData\Local\Temp\opencode")
PROBE = Path(r"C:\RivalsTest\tools\ue_probe.luau")
MOCK = TMP / "mock_ue_probe.lua"
OUT = TMP / "run_mock_probe.lua"
LUAU = TMP / "luau" / "luau.exe"

probe = PROBE.read_text(encoding="utf-8")
mock = MOCK.read_text(encoding="utf-8")

# the probe ends with `return {...}`; wrapping it in a function keeps that legal
source = "local function __probe()\n" + probe + "\nend\n\n" + mock
OUT.write_text(source, encoding="ascii", errors="replace")

res = subprocess.run([str(LUAU), str(OUT)], capture_output=True, text=True)
print(res.stdout)
if res.stderr:
    print("STDERR:", res.stderr)
sys.exit(res.returncode)
