import urllib.request
import urllib.error
import json
import time
import os
import sys
import base64
import re
from datetime import datetime

# Configure UTF-8 stdout
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "Android-Smoke-01")
os.makedirs(OUTPUT_DIR, exist_ok=True)

api_key_path = os.path.join(os.environ.get("USERPROFILE") or os.environ.get("HOME") or os.path.expanduser("~"), ".openhands", "agent-canvas", "api-key.txt")
with open(api_key_path, "r", encoding="utf-8") as f:
    API_KEY = f.read().strip()

BASE_URL = "http://127.0.0.1:18000"

def api_request(method, path, data=None, extra_headers=None):
    url = f"{BASE_URL}{path}"
    headers = {
        "X-Session-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    if extra_headers:
        headers.update(extra_headers)
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            if content:
                return json.loads(content)
            return {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"HTTPError {e.code} on {method} {path}: {err_body}", flush=True)
        raise

print("1. Fetching current OpenHands settings (with encrypted secrets)...", flush=True)
settings = api_request("GET", "/api/settings", extra_headers={"X-Expose-Secrets": "encrypted"})
agent_settings = settings.get("agent_settings", {})
print("   LLM Model:", agent_settings.get("llm", {}).get("model"), flush=True)
print("   LLM Base URL:", agent_settings.get("llm", {}).get("base_url"), flush=True)
print("   MCP servers:", list(agent_settings.get("mcp_config", {}).keys()), flush=True)

USER_PROMPT = """На подключённом Android-планшете безопасно проведи диагностику интерфейса.

1. Найди подключённое Android-устройство.
2. Определи модель устройства и версию Android.
3. Получи текущий screenshot.
4. Получи UI hierarchy / список элементов текущего экрана.
5. Определи, какое приложение сейчас открыто.
6. Через Android MCP открой системное приложение Settings.
7. Используя UI hierarchy, screenshot и обычные действия tap/swipe, самостоятельно найди раздел 'About tablet' / 'Сведения о планшете'.
8. Ничего в настройках НЕ изменяй.
9. Прочитай с экрана доступную информацию:
   - название/модель устройства;
   - Android version, если она доступна;
   - другие 2–3 безопасные информационные поля, которые видны без изменения настроек.
10. Сделай финальный screenshot найденного экрана.
11. Вернись на главный экран Android.
12. Подготовь отчёт о проделанных действиях."""

start_payload = {
    "workspace": {
        "working_dir": r"K:\Project",
        "kind": "LocalWorkspace"
    },
    "initial_message": {
        "content": [
            {
                "text": USER_PROMPT
            }
        ]
    },
    "secrets_encrypted": True,
    "agent_settings": agent_settings
}

print("2. Starting conversation with OpenHands...", flush=True)
conv_info = api_request("POST", "/api/conversations", start_payload)
conv_id = conv_info.get("id") or conv_info.get("conversation_id")
print(f"   Conversation started: ID = {conv_id}", flush=True)

start_time = time.time()
print(f"3. Monitoring agent execution (start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})...", flush=True)

events_seen = set()
all_events = []
tool_calls = []
screenshots = []
agent_responses = []
is_finished = False
last_event_time = time.time()
consecutive_no_events = 0

# Poll events
while not is_finished:
    time.sleep(3)
    elapsed = time.time() - start_time
    
    # Get conversation status
    try:
        conv_status = api_request("GET", f"/api/conversations/{conv_id}")
        conv_state = conv_status.get("status", "unknown")
    except Exception as e:
        conv_state = "unknown"
    
    # Fetch events
    try:
        events_resp = api_request("GET", f"/api/conversations/{conv_id}/events/search?limit=100")
        items = events_resp.get("items", []) if isinstance(events_resp, dict) else events_resp
    except Exception as e:
        print(f"   [WARN] Events fetch error: {e}", flush=True)
        items = []

    new_count = 0
    for ev in items:
        ev_id = ev.get("id") or json.dumps(ev)
        if ev_id in events_seen:
            continue
        events_seen.add(ev_id)
        all_events.append(ev)
        new_count += 1
        
        kind = ev.get("kind", "") or ev.get("type", "")
        source = ev.get("source", "")
        print(f"[{elapsed:.1f}s] Event: {kind} (source: {source})", flush=True)
        
        # Check tool calls
        if "action" in kind.lower() or "tool" in kind.lower():
            # Check for specific tool call actions
            tool_name = ev.get("tool_name") or ev.get("action") or ev.get("name") or ev.get("tool_call")
            thought = ev.get("thought", "")
            if thought:
                print(f"   [THOUGHT] {thought[:250]}...", flush=True)
            args = ev.get("arguments") or ev.get("args") or ev.get("params") or ev.get("action_payload") or {}
            print(f"   [TOOL CALL] {tool_name} | Args: {json.dumps(args, ensure_ascii=False)[:200]}", flush=True)
            tool_calls.append({
                "time_sec": round(elapsed, 2),
                "event_id": ev_id,
                "kind": kind,
                "source": source,
                "thought": thought,
                "tool": str(tool_name),
                "args": args,
                "raw": ev
            })
            
        # Check observations / images
        obs = ev.get("observation") or ev.get("content") or ev.get("output") or ev.get("text") or ""
        if isinstance(obs, str) and len(obs) > 0:
            # Check for base64 images
            b64_matches = re.findall(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", obs)
            for b64_str in b64_matches:
                try:
                    img_data = base64.b64decode(b64_str)
                    img_path = os.path.join(OUTPUT_DIR, f"screenshot_{len(screenshots)+1}.png")
                    with open(img_path, "wb") as img_file:
                        img_file.write(img_data)
                    screenshots.append(img_path)
                    print(f"   [SAVED SCREENSHOT] {img_path}", flush=True)
                except Exception as ex:
                    print(f"   [WARN] Failed to decode base64 screenshot: {ex}", flush=True)
            print(f"   [OBSERVATION] {obs[:300]}...", flush=True)
        elif isinstance(obs, list):
            for part in obs:
                if isinstance(part, dict) and part.get("type") == "image":
                    img_src = part.get("image_url", {}).get("url", "")
                    if "base64," in img_src:
                        b64_str = img_src.split("base64,")[1]
                        try:
                            img_data = base64.b64decode(b64_str)
                            img_path = os.path.join(OUTPUT_DIR, f"screenshot_{len(screenshots)+1}.png")
                            with open(img_path, "wb") as img_file:
                                img_file.write(img_data)
                            screenshots.append(img_path)
                            print(f"   [SAVED SCREENSHOT] {img_path}", flush=True)
                        except Exception as ex:
                            print(f"   [WARN] Failed to decode image: {ex}", flush=True)

        # Check agent message / final response
        if "agent" in kind.lower() or "message" in kind.lower() or "response" in kind.lower():
            text_content = ""
            if isinstance(ev.get("content"), str):
                text_content = ev.get("content")
            elif isinstance(ev.get("content"), list):
                for p in ev.get("content"):
                    if isinstance(p, dict) and "text" in p:
                        text_content += p["text"] + "\n"
                    elif isinstance(p, str):
                        text_content += p + "\n"
            elif isinstance(ev.get("llm_message"), dict):
                llm_c = ev["llm_message"].get("content", "")
                if isinstance(llm_c, str):
                    text_content = llm_c
                elif isinstance(llm_c, list):
                    for p in llm_c:
                        if isinstance(p, dict) and "text" in p:
                            text_content += p["text"] + "\n"
            if text_content and source != "user":
                print(f"   [AGENT RESPONSE]\n{text_content}\n", flush=True)
                agent_responses.append(text_content)

        # Check if conversation is finished
        if kind in ["StopAction", "AgentFinishAction", "FinishAction"]:
            print(f"   -> Finish action detected ({kind})", flush=True)
            is_finished = True
        elif kind == "ConversationStateUpdateEvent" and ev.get("key") == "execution_status":
            val = str(ev.get("value", "")).lower()
            if val in ["finished", "stopped", "error", "idle", "paused"]:
                print(f"   -> Agent execution status is: {val}", flush=True)
                if val in ["finished", "stopped", "idle"]:
                    is_finished = True

    if conv_state in ["finished", "stopped", "error", "completed"]:
        print(f"   -> Conversation status is now: {conv_state}", flush=True)
        is_finished = True
        
    # Safety timeout (10 minutes)
    if elapsed > 600:
        print("   -> TIMEOUT (600s reached). Stopping monitoring.", flush=True)
        break

total_duration = time.time() - start_time
print(f"\n==================================================", flush=True)
print(f"Execution finished in {total_duration:.1f}s", flush=True)
print(f"Total events captured: {len(all_events)}", flush=True)
print(f"Total tool calls: {len(tool_calls)}", flush=True)
print(f"Total screenshots extracted: {len(screenshots)}", flush=True)
print(f"==================================================\n", flush=True)

# Save tool calls
with open(os.path.join(OUTPUT_DIR, "tool-calls.json"), "w", encoding="utf-8") as f:
    json.dump(tool_calls, f, ensure_ascii=False, indent=2)

# Save initial-screen.png and final-about-tablet.png if screenshots exist
if len(screenshots) >= 1:
    import shutil
    shutil.copyfile(screenshots[0], os.path.join(OUTPUT_DIR, "initial-screen.png"))
    shutil.copyfile(screenshots[-1], os.path.join(OUTPUT_DIR, "final-about-tablet.png"))

# Save agent transcript
with open(os.path.join(OUTPUT_DIR, "agent-transcript.md"), "w", encoding="utf-8") as f:
    f.write(f"# OpenHands Agent Transcript - Android Smoke Test 01\n\n")
    f.write(f"- **Date/Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- **Conversation ID**: `{conv_id}`\n")
    f.write(f"- **Total Duration**: `{total_duration:.1f}s`\n")
    f.write(f"- **Total Events**: `{len(all_events)}`\n")
    f.write(f"- **Total Tool Calls**: `{len(tool_calls)}`\n\n")
    f.write(f"## Task Prompt\n\n```text\n{USER_PROMPT}\n```\n\n")
    f.write(f"## Chronological Events\n\n")
    for i, ev in enumerate(all_events, 1):
        f.write(f"### Step {i}: {ev.get('kind', ev.get('type', 'Event'))}\n")
        f.write(f"```json\n{json.dumps(ev, ensure_ascii=False, indent=2)}\n```\n\n")

print("Artifacts saved in K:\\Project\\OpenHands-Tests\\Android-Smoke-01", flush=True)