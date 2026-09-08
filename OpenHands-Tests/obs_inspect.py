import json

with open(r"K:\Project\OpenHands-Tests\Android-Smoke-01\agent-transcript.md", "r", encoding="utf-8") as f:
    text = f.read()

import re
# Find first android_take_screenshot observation
match = re.search(r'### Event \d+: ObservationEvent[\s\S]*?android_take_screenshot[\s\S]*?```json\n([\s\S]*?)\n```', text)
if match:
    ev = json.loads(match.group(1))
    print("Event keys:", list(ev.keys()))
    print("Observation object keys:", list(ev.get("observation", {}).keys()))
    obs = ev.get("observation", {})
    for k, v in obs.items():
        if isinstance(v, str):
            print(f"Key {k}: len={len(v)}, start={v[:80]}")
        elif isinstance(v, list):
            print(f"Key {k}: list of len {len(v)}")
            for item in v:
                if isinstance(item, dict):
                    print("  item keys:", list(item.keys()))
                    for ik, iv in item.items():
                        if isinstance(iv, str):
                            print(f"    {ik}: len={len(iv)}, start={iv[:60]}")
                        elif isinstance(iv, dict):
                            print(f"    {ik}: dict keys={list(iv.keys())}")