import urllib.request
import urllib.parse
import urllib.error

import os

api_key_path = os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"), ".openhands", "agent-canvas", "api-key.txt")
with open(api_key_path, "r") as f:
    key = f.read().strip()

for test_name in ['Qwen3.8-Opus-Direct', 'Qwen3.8_Opus_Direct', 'Qwen3.8 Opus — Direct']:
    url = f"http://127.0.0.1:18000/api/profiles/{urllib.parse.quote(test_name)}/validate"
    req = urllib.request.Request(url, headers={"X-Session-API-Key": key}, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            print(f"Name '{test_name}': VALID ({r.status})")
    except urllib.error.HTTPError as e:
        print(f"Name '{test_name}': INVALID (HTTP {e.code}: {e.read().decode()[:100]})")