import subprocess
import sys
from pathlib import Path

TMP = Path(r"C:\Users\Administrator\AppData\Local\Temp\opencode")
MOCK = TMP / "mock_shim.lua"
SHIM = TMP / "shim_extracted.luau"
OUT = TMP / "run_mock_shim.lua"
LUAU = TMP / "luau" / "luau.exe"

source = MOCK.read_text(encoding="ascii")
shim = SHIM.read_text(encoding="utf-8")
source = source.replace("-- [[SHIM]] --", shim)
OUT.write_text(source, encoding="ascii", errors="replace")

res = subprocess.run([str(LUAU), str(OUT)], capture_output=True, text=True)
print(res.stdout)
if res.stderr:
    print("STDERR:", res.stderr)
sys.exit(res.returncode)
