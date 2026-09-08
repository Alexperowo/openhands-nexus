import urllib.request
import json

with open(r"C:\Users\User\.openhands\agent-canvas\api-key.txt", "r") as f:
    key = f.read().strip()

# Load base config from Qwen38_Opus_96K
with open(r"C:\Users\User\.openhands\profiles\Qwen38_Opus_96K.json", "r", encoding="utf-8") as f:
    base_cfg = json.load(f)

# Modify for low
cfg_low = dict(base_cfg)
cfg_low["reasoning_effort"] = "low"
cfg_low["litellm_extra_body"] = {"chat_template_kwargs": {"reasoning_effort": "low"}}

payload = {
    "llm": cfg_low,
    "include_secrets": True
}

req = urllib.request.Request(
    "http://127.0.0.1:18000/api/profiles/Qwen3.8-Opus-Low",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "X-Session-API-Key": key,
        "X-Expose-Secrets": "encrypted",
        "Content-Type": "application/json"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as r:
        print("Profile create response:", r.read().decode())
except urllib.error.HTTPError as e:
    print("Error HTTP", e.code, e.read().decode())