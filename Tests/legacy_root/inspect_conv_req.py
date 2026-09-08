import urllib.request
import json

import os

api_key_path = os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"), ".openhands", "agent-canvas", "api-key.txt")
with open(api_key_path, "r") as f:
    key = f.read().strip()

r = urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18000/openapi.json", headers={"X-Session-API-Key": key}))
spec = json.loads(r.read().decode())
print(json.dumps(spec["paths"]["/api/conversations"]["post"], indent=2)[:1000])