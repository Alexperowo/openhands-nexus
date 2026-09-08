import urllib.request
import json
import time
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

if len(sys.argv) < 2:
    print("Usage: python test_single_profile.py <profile_name>")
    sys.exit(1)

prof_name = sys.argv[1]
TEST_PROMPT = "Explain what RAM is in one sentence. Be direct and concise."

api_key_path = os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"), ".openhands", "agent-canvas", "api-key.txt")
with open(api_key_path, "r") as f:
    API_KEY = f.read().strip()

BASE_URL = "http://127.0.0.1:18000"
headers = {
    "X-Session-API-Key": API_KEY,
    "X-Expose-Secrets": "encrypted",
    "Content-Type": "application/json"
}

print(f"=== Testing Profile: {prof_name} ===", flush=True)

# 1. Activate profile
act_url = f"{BASE_URL}/api/profiles/{prof_name}/activate"
req_act = urllib.request.Request(act_url, headers=headers, method="POST")
with urllib.request.urlopen(req_act) as r:
    act_resp = json.loads(r.read().decode())
    print(f"  Activated: {act_resp.get('name')}", flush=True)

# 2. Get current settings
settings_url = f"{BASE_URL}/api/settings"
req_set = urllib.request.Request(settings_url, headers=headers)
with urllib.request.urlopen(req_set) as r:
    current_settings = json.loads(r.read().decode())

agent_settings = current_settings.get("agent_settings", {})
llm_cfg = agent_settings.get("llm", {})
print(f"  Active reasoning_effort = {llm_cfg.get('reasoning_effort')}", flush=True)
print(f"  Active extra_body = {llm_cfg.get('litellm_extra_body')}", flush=True)

# 3. Create conversation
start_payload = {
    "workspace": {
        "working_dir": r"K:\Project",
        "kind": "LocalWorkspace"
    },
    "secrets_encrypted": True,
    "agent_settings": agent_settings,
    "autotitle": False
}
conv_req = urllib.request.Request(f"{BASE_URL}/api/conversations", data=json.dumps(start_payload).encode(), headers=headers)
with urllib.request.urlopen(conv_req) as r:
    conv_info = json.loads(r.read().decode())
    conv_id = conv_info.get("id") or conv_info.get("conversation_id")
    print(f"  Created conversation: {conv_id}", flush=True)

# 4. Send message with run=True
msg_payload = {
    "role": "user",
    "content": [{"text": TEST_PROMPT}],
    "run": True
}
urllib.request.urlopen(urllib.request.Request(
    f"{BASE_URL}/api/conversations/{conv_id}/events",
    data=json.dumps(msg_payload).encode(),
    headers=headers
))
print(f"  Submitted prompt to agent loop.", flush=True)

# 5. Poll events until done
t0 = time.time()
reasoning_text = ""
agent_msg = ""
done = False

for _ in range(40):
    time.sleep(2)
    try:
        r_ev = urllib.request.urlopen(urllib.request.Request(f"{BASE_URL}/api/conversations/{conv_id}/events/search?limit=100", headers=headers))
        ev_data = json.loads(r_ev.read().decode())
        items = ev_data.get("items", [])
        for ev in items:
            kind = ev.get("kind", "")
            source = ev.get("source", "")
            
            # Check for reasoning_content in ActionEvent or MessageEvent
            rc = ev.get("reasoning_content") or ev.get("llm_message", {}).get("reasoning_content") or ""
            if rc and isinstance(rc, str):
                reasoning_text = rc
                
            if kind == "ActionEvent" and source == "agent":
                act = ev.get("action", {})
                if act and isinstance(act, dict) and "message" in act:
                    agent_msg = act["message"]
                    done = True
            if kind == "MessageEvent" and source == "agent":
                llm_msg = ev.get("llm_message", {})
                c = llm_msg.get("content", "")
                if isinstance(c, list):
                    for part in c:
                        if isinstance(part, dict) and "text" in part:
                            agent_msg += part["text"] + "\n"
                elif isinstance(c, str):
                    agent_msg = c
                done = True
        if done:
            break
    except Exception as e:
        pass

elapsed = round(time.time() - t0, 2)
print(f"  Completed in: {elapsed}s", flush=True)
print(f"  Reasoning length: {len(reasoning_text)} chars", flush=True)
if reasoning_text:
    print(f"  Reasoning snippet: {repr(reasoning_text[:120])}...", flush=True)
else:
    print(f"  Reasoning: NONE (0 chars / disabled)", flush=True)
print(f"  Agent output: {repr(agent_msg.strip()[:140])}", flush=True)

# Append to JSON results
res_file = r"K:\Project\OpenHands-Tests\Reasoning-Modes\verified_profiles.json"
os.makedirs(os.path.dirname(res_file), exist_ok=True)
existing = []
if os.path.exists(res_file):
    try:
        with open(res_file, "r", encoding="utf-8") as f:
            existing = json.load(f)
    except Exception:
        existing = []

# Filter out old entry for same profile if exists
existing = [x for x in existing if x.get("profile") != prof_name]

existing.append({
    "profile": prof_name,
    "conversation_id": conv_id,
    "elapsed_s": elapsed,
    "reasoning_effort": llm_cfg.get("reasoning_effort"),
    "extra_body": llm_cfg.get("litellm_extra_body"),
    "reasoning_len": len(reasoning_text),
    "reasoning_preview": reasoning_text[:150] if reasoning_text else "",
    "agent_output": agent_msg.strip()
})

with open(res_file, "w", encoding="utf-8") as f:
    json.dump(existing, f, ensure_ascii=False, indent=2)
print(f"  Saved to {res_file}\n", flush=True)