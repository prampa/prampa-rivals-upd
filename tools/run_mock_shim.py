import re
import subprocess
import sys
from pathlib import Path

TMP = Path(r"C:\Users\Administrator\AppData\Local\Temp\opencode")
MOCK = TMP / "mock_shim.lua"
SHIM = TMP / "shim_extracted.luau"
LUAU = TMP / "luau" / "luau.exe"

mode = sys.argv[1] if len(sys.argv) > 1 else "full"

source = MOCK.read_text(encoding="ascii")
shim = SHIM.read_text(encoding="utf-8")
source = source.replace("-- [[SHIM]] --", shim)
source = re.sub(r"local env = \{ Library", 'local env = { UE_SHIM = "%s", Library' % mode, source, count=1)

out = TMP / f"run_mock_shim_{mode}.lua"
out.write_text(source, encoding="ascii", errors="replace")

res = subprocess.run([str(LUAU), str(out)], capture_output=True, text=True)
print(res.stdout)
if res.stderr:
    print("STDERR:", res.stderr)
sys.exit(res.returncode)
