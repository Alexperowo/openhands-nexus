import urllib.request
import json
import base64
import os
import sys
import re
from datetime import datetime

OUTPUT_DIR = r"K:\Project\OpenHands-Tests\Android-Smoke-01"
os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(r"C:\Users\User\.openhands\agent-canvas\api-key.txt", "r", encoding="utf-8") as f:
    API_KEY = f.read().strip()

conv_id = "fbf3610f-87a4-4c8d-86b8-52bf48507698"

# 1. Fetch all events across all pages
all_events = []
page_id = None

while True:
    url = f"http://127.0.0.1:18000/api/conversations/{conv_id}/events/search?limit=100"
    if page_id:
        url += f"&page_id={page_id}"
    req = urllib.request.Request(url, headers={"X-Session-API-Key": API_KEY})
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read().decode("utf-8"))
        items = data.get("items", [])
        all_events.extend(items)
        page_id = data.get("next_page_id")
        if not page_id or not items:
            break

print(f"Total events fetched: {len(all_events)}")

# 2. Extract tool calls and screenshots
tool_calls = []
screenshots = []
agent_final_text = ""

for i, ev in enumerate(all_events, 1):
    kind = ev.get("kind", "")
    source = ev.get("source", "")
    
    # Tool call actions
    if "action" in kind.lower() or ev.get("tool_name") or ev.get("tool_call"):
        tool_name = ev.get("tool_name") or ev.get("action") or ev.get("name")
        args = ev.get("arguments") or ev.get("args") or ev.get("params") or {}
        thought = ev.get("thought", "")
        reasoning = ev.get("reasoning_content", "")
        summary = ev.get("summary", "")
        tool_calls.append({
            "step": i,
            "timestamp": ev.get("timestamp"),
            "tool_name": tool_name,
            "summary": summary,
            "args": args,
            "thought": thought or reasoning,
            "security_risk": ev.get("security_risk")
        })
        
    # Extract images from observations / tool responses
    obs = ev.get("observation") or ev.get("content") or ev.get("llm_message", {}).get("content") or []
    if isinstance(obs, list):
        for part in obs:
            if isinstance(part, dict):
                text_part = part.get("text", "")
                if "data:image/" in text_part:
                    b64_matches = re.findall(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", text_part)
                    for b64_str in b64_matches:
                        try:
                            img_bytes = base64.b64decode(b64_str)
                            img_path = os.path.join(OUTPUT_DIR, f"extracted_screenshot_{len(screenshots)+1}.png")
                            with open(img_path, "wb") as f_img:
                                f_img.write(img_bytes)
                            screenshots.append(img_path)
                        except Exception as ex:
                            print("Error decoding image:", ex)
                img_url = part.get("image_url", {}).get("url", "")
                if "base64," in img_url:
                    b64_str = img_url.split("base64,")[1]
                    try:
                        img_bytes = base64.b64decode(b64_str)
                        img_path = os.path.join(OUTPUT_DIR, f"extracted_screenshot_{len(screenshots)+1}.png")
                        with open(img_path, "wb") as f_img:
                            f_img.write(img_bytes)
                        screenshots.append(img_path)
                    except Exception as ex:
                        print("Error decoding image:", ex)
    elif isinstance(obs, str) and "data:image/" in obs:
        b64_matches = re.findall(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", obs)
        for b64_str in b64_matches:
            try:
                img_bytes = base64.b64decode(b64_str)
                img_path = os.path.join(OUTPUT_DIR, f"extracted_screenshot_{len(screenshots)+1}.png")
                with open(img_path, "wb") as f_img:
                    f_img.write(img_bytes)
                screenshots.append(img_path)
            except Exception as ex:
                print("Error decoding image:", ex)

    # Final agent message
    if kind == "MessageEvent" and source == "agent":
        llm_msg = ev.get("llm_message", {})
        c = llm_msg.get("content", "")
        if isinstance(c, list):
            for p in c:
                if isinstance(p, dict) and "text" in p:
                    agent_final_text += p["text"] + "\n"
        elif isinstance(c, str):
            agent_final_text += c + "\n"

# Check if screenshots exist in K:\Project or OUTPUT_DIR
if os.path.exists(r"K:\Project\final_about_tablet.png"):
    import shutil
    shutil.copyfile(r"K:\Project\final_about_tablet.png", os.path.join(OUTPUT_DIR, "final-about-tablet.png"))

if len(screenshots) > 0:
    import shutil
    shutil.copyfile(screenshots[0], os.path.join(OUTPUT_DIR, "initial-screen.png"))
    if not os.path.exists(os.path.join(OUTPUT_DIR, "final-about-tablet.png")):
        shutil.copyfile(screenshots[-1], os.path.join(OUTPUT_DIR, "final-about-tablet.png"))

print(f"Total tool calls extracted: {len(tool_calls)}")
print(f"Total screenshots found: {len(screenshots)}")

# Save tool-calls.json
with open(os.path.join(OUTPUT_DIR, "tool-calls.json"), "w", encoding="utf-8") as f:
    json.dump(tool_calls, f, ensure_ascii=False, indent=2)

# Save agent-transcript.md
with open(os.path.join(OUTPUT_DIR, "agent-transcript.md"), "w", encoding="utf-8") as f:
    f.write(f"# OpenHands Agent Transcript - Android Smoke Test 01\n\n")
    f.write(f"- **Conversation ID**: `{conv_id}`\n")
    f.write(f"- **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- **Total Events**: {len(all_events)}\n")
    f.write(f"- **Total Tool Calls**: {len(tool_calls)}\n\n")
    f.write(f"## Final Agent Response\n\n{agent_final_text}\n\n")
    f.write(f"## Chronological Events\n\n")
    for i, ev in enumerate(all_events, 1):
        f.write(f"### Event {i}: {ev.get('kind')} (Source: {ev.get('source')})\n")
        f.write(f"```json\n{json.dumps(ev, ensure_ascii=False, indent=2)}\n```\n\n")

print("Artifacts generated successfully.")