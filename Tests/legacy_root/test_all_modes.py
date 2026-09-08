import urllib.request
import json
import time
import sys

sys.stdout.reconfigure(encoding="utf-8")
URL = "http://127.0.0.1:8080/v1/chat/completions"

PROMPT = "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost? Show your steps."

modes = [
    ("1. Direct (enable_thinking=False)", {
        "chat_template_kwargs": {"enable_thinking": False}
    }),
    ("2. Low (reasoning_effort=low)", {
        "chat_template_kwargs": {"reasoning_effort": "low"}
    }),
    ("3. Medium (reasoning_effort=medium)", {
        "chat_template_kwargs": {"reasoning_effort": "medium"}
    }),
    ("4. XHigh (reasoning_effort=xhigh)", {
        "chat_template_kwargs": {"reasoning_effort": "xhigh"}
    })
]

results = []

for name, kwargs in modes:
    payload = {
        "model": "Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
        "messages": [
            {"role": "user", "content": PROMPT}
        ],
        "max_tokens": 512,
        "temperature": 0.7,
        "top_p": 0.8,
        "min_p": 0.05,
        "stream": False
    }
    payload.update(kwargs)
    
    t0 = time.time()
    req = urllib.request.Request(URL, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - t0
        msg = d["choices"][0]["message"]
        usage = d.get("usage", {})
        
        res_info = {
            "name": name,
            "elapsed_s": round(elapsed, 2),
            "payload": payload,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "reasoning_content": msg.get("reasoning_content", ""),
            "content": msg.get("content", "")
        }
        results.append(res_info)
        print(f"=== {name} ({elapsed:.2f}s) ===")
        print(f"  prompt_tokens: {usage.get('prompt_tokens')}, comp_tokens: {usage.get('completion_tokens')}")
        print(f"  reasoning_content len: {len(msg.get('reasoning_content', ''))}")
        if msg.get("reasoning_content"):
            print(f"  reasoning_preview: {repr(msg['reasoning_content'][:100])}")
        print(f"  content_preview: {repr(msg.get('content', '')[:120])}")
        print()

with open(r"K:\Project\all_modes_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("Saved K:\\Project\\all_modes_results.json")