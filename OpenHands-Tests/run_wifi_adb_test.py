import urllib.request
import urllib.error
import json
import time
import os
import sys
import re
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

OUTPUT_DIR = r"K:\Project\OpenHands-Tests\Android-WiFi-ADB"
os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(r"C:\Users\User\.openhands\agent-canvas\api-key.txt", "r", encoding="utf-8") as f:
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

print("1. Fetching OpenHands settings...", flush=True)
settings = api_request("GET", "/api/settings", extra_headers={"X-Expose-Secrets": "encrypted"})
agent_settings = settings.get("agent_settings", {})
print("   LLM Model:", agent_settings.get("llm", {}).get("model"), flush=True)

PROMPT = """Выполни беспроводное ADB подключение к подключённому планшету Samsung Galaxy Tab S9 Ultra (ADB serial: R52W70AXVTL).

1. Найди подключённое Android-устройство (R52W70AXVTL).
2. Определи IP-адрес планшета в локальной сети Wi-Fi (через команду terminal 'adb -s R52W70AXVTL shell ip route' или 'adb -s R52W70AXVTL shell ip addr show wlan0').
3. Переведи планшет в режим TCP/IP на порту 5555 через терминал ('adb -s R52W70AXVTL tcpip 5555').
4. Подключись к планшету по беспроводному ADB с помощью инструмента android_connect_wifi(host='IP:5555') или через терминал ('adb connect IP:5555').
5. Проверь список подключённых устройств (android_list_devices или 'adb devices') и убедись, что планшет отображается как подключённое сетевое устройство (IP:5555).
6. Выполни быструю проверку связи по беспроводному каналу (например, android_device_info или android_take_screenshot).
7. Подготовь краткий отчёт: укажи найденный IP-адрес, порт, статус подключения и результат проверки."""

start_payload = {
    "workspace": {
        "working_dir": r"K:\Project",
        "kind": "LocalWorkspace"
    },
    "secrets_encrypted": True,
    "agent_settings": agent_settings,
    "autotitle": False
}

print("2. Creating new conversation in OpenHands...", flush=True)
conv_info = api_request("POST", "/api/conversations", start_payload)
conv_id = conv_info.get("id") or conv_info.get("conversation_id")
print(f"   Conversation created: ID = {conv_id}", flush=True)

print("3. Sending task message with run=True...", flush=True)
msg_payload = {
    "role": "user",
    "content": [{"text": PROMPT}],
    "run": True
}
api_request("POST", f"/api/conversations/{conv_id}/events", msg_payload)
print("   Task submitted to agent loop.", flush=True)

start_time = time.time()
print(f"4. Monitoring agent execution (started at {datetime.now().strftime('%H:%M:%S')})...", flush=True)

events_seen = set()
all_events = []
tool_calls = []
agent_responses = []
is_finished = False

while not is_finished:
    time.sleep(3)
    elapsed = time.time() - start_time

    # Fetch events
    try:
        data = api_request("GET", f"/api/conversations/{conv_id}/events/search?limit=100")
        items = data.get("items", [])
        page_id = data.get("next_page_id")
        while page_id:
            data2 = api_request("GET", f"/api/conversations/{conv_id}/events/search?limit=100&page_id={page_id}")
            items.extend(data2.get("items", []))
            page_id = data2.get("next_page_id")
    except Exception as e:
        items = []

    for ev in items:
        ev_id = ev.get("id") or json.dumps(ev)
        if ev_id in events_seen:
            continue
        events_seen.add(ev_id)
        all_events.append(ev)

        kind = ev.get("kind", "")
        source = ev.get("source", "")

        if "action" in kind.lower() or ev.get("tool_name"):
            t_name = ev.get("tool_name") or ev.get("action")
            summary = ev.get("summary", "")
            thought = ev.get("reasoning_content") or ev.get("thought", "")
            if thought and isinstance(thought, str):
                print(f"[{elapsed:.1f}s] [THOUGHT] {thought[:180]}...", flush=True)
            print(f"[{elapsed:.1f}s] [TOOL] {t_name} | {summary}", flush=True)
            tool_calls.append({"time": round(elapsed, 1), "tool": t_name, "summary": summary, "ev": ev})

        if kind == "ObservationEvent":
            obs = ev.get("observation", {})
            content = obs.get("content", [])
            txt = ""
            if isinstance(content, list):
                for p in content:
                    if isinstance(p, dict) and p.get("type") == "text":
                        txt += p.get("text", "")
            elif isinstance(content, str):
                txt = content
            if txt:
                print(f"[{elapsed:.1f}s] [OBS] {txt[:160]}...", flush=True)

        if kind == "MessageEvent" and source == "agent":
            llm_msg = ev.get("llm_message", {})
            c = llm_msg.get("content", "")
            final_txt = ""
            if isinstance(c, list):
                for p in c:
                    if isinstance(p, dict) and "text" in p:
                        final_txt += p["text"] + "\n"
            elif isinstance(c, str):
                final_txt = c
            if final_txt:
                print(f"\n[{elapsed:.1f}s] [AGENT FINAL REPORT]\n{final_txt}\n", flush=True)
                agent_responses.append(final_txt)
                is_finished = True

        if kind == "ConversationStateUpdateEvent" and ev.get("key") == "execution_status":
            val = str(ev.get("value", "")).lower()
            if val in ["finished", "stopped"]:
                is_finished = True

    if elapsed > 450:
        print("Timeout (450s reached).", flush=True)
        break

total_dur = time.time() - start_time
print(f"\nTest finished in {total_dur:.1f}s. Total events: {len(all_events)}, Tool calls: {len(tool_calls)}", flush=True)

# Save artifacts
with open(os.path.join(OUTPUT_DIR, "wifi-adb-events.json"), "w", encoding="utf-8") as f:
    json.dump(all_events, f, ensure_ascii=False, indent=2)

with open(os.path.join(OUTPUT_DIR, "wifi-adb-report.md"), "w", encoding="utf-8") as f:
    f.write(f"# Android Wireless ADB Connection Report\n\n")
    f.write(f"- Conversation ID: `{conv_id}`\n")
    f.write(f"- Duration: `{total_dur:.1f}s`\n\n")
    if agent_responses:
        f.write("## Agent Response\n\n" + agent_responses[-1] + "\n\n")
    f.write("## Tool Calls Summary\n\n")
    for tc in tool_calls:
        f.write(f"- `{tc['tool']}`: {tc['summary']}\n")

print("Artifacts saved in K:\\Project\\OpenHands-Tests\\Android-WiFi-ADB", flush=True)