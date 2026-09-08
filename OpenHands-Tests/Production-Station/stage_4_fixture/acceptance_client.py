import sys
import json
import urllib.request
from pathlib import Path

# Get current workspace directory
workspace = str(Path.cwd().resolve())

req_data = json.dumps({"workspace": workspace}).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:8999/check",
    data=req_data,
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(req, timeout=10) as response:
        res = json.loads(response.read().decode("utf-8"))
        msg = res.get("message", "")
        exit_code = int(res.get("exit_code", 1))
        print(msg)
        sys.exit(exit_code)
except Exception as e:
    print(f"[ACCEPTANCE CLIENT ERROR]: Verification service unreachable: {e}")
    sys.exit(1)
