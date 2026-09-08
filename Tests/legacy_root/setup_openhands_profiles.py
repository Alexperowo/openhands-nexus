import urllib.request
import json

import os

user_home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
api_key_path = os.path.join(user_home, ".openhands", "agent-canvas", "api-key.txt")
with open(api_key_path, "r") as f:
    key = f.read().strip()

profile_path = os.path.join(user_home, ".openhands", "profiles", "Qwen38_Opus_96K.json")
with open(profile_path, "r", encoding="utf-8") as f:
    base_cfg = json.load(f)

# Define the 4 target profiles
profiles_def = [
    {
        "name": "Qwen3.8-Opus-Direct",
        "description": "Без reasoning. Для простых команд и быстрых действий.",
        "reasoning_effort": "none",
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": False},
            "reasoning_budget_tokens": 0
        }
    },
    {
        "name": "Qwen3.8-Opus-Low",
        "description": "Короткое рассуждение. Для обычных рутинных агентных задач.",
        "reasoning_effort": "low",
        "extra_body": {
            "chat_template_kwargs": {"reasoning_effort": "low"}
        }
    },
    {
        "name": "Qwen3.8-Opus-Medium",
        "description": "Среднее рассуждение. Основной рабочий режим.",
        "reasoning_effort": "medium",
        "extra_body": {
            "chat_template_kwargs": {"reasoning_effort": "medium"}
        }
    },
    {
        "name": "Qwen3.8-Opus-XHigh",
        "description": "Максимальное рассуждение. Для сложной диагностики, архитектуры и трудных многошаговых задач.",
        "reasoning_effort": "high",
        "extra_body": {
            "chat_template_kwargs": {"reasoning_effort": "xhigh"}
        }
    }
]

headers = {
    "X-Session-API-Key": key,
    "X-Expose-Secrets": "encrypted",
    "Content-Type": "application/json"
}

for p_def in profiles_def:
    cfg = dict(base_cfg)
    cfg["reasoning_effort"] = p_def["reasoning_effort"]
    cfg["litellm_extra_body"] = p_def["extra_body"]
    
    payload = {
        "llm": cfg,
        "include_secrets": True
    }
    
    url = f"http://127.0.0.1:18000/api/profiles/{p_def['name']}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req) as r:
        print(f"Created/Updated {p_def['name']}: {r.read().decode()}")

# Set Qwen3.8-Opus-Medium as the active profile (Medium: основной рабочий режим)
req_act = urllib.request.Request(
    "http://127.0.0.1:18000/api/profiles/Qwen3.8-Opus-Medium/activate",
    headers=headers,
    method="POST"
)
with urllib.request.urlopen(req_act) as r:
    print(f"Activated Qwen3.8-Opus-Medium: {r.read().decode()}")

# Fetch all profiles
req_all = urllib.request.Request("http://127.0.0.1:18000/api/profiles", headers=headers)
with urllib.request.urlopen(req_all) as r:
    all_p = json.loads(r.read().decode())
    print("\nCurrent Profiles in OpenHands:")
    for p in all_p.get("profiles", []):
        is_act = " [ACTIVE]" if p["name"] == all_p.get("active_profile") else ""
        print(f" - {p['name']}{is_act}")