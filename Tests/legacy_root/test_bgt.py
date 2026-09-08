import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
URL = "http://127.0.0.1:8080/v1/chat/completions"

def test_bgt(val):
    p = {
        "model": "Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
        "messages": [
            {"role": "user", "content": "How many r's are in strawberry? Explain in detail."}
        ],
        "max_tokens": 256,
        "temperature": 0.7,
        "stream": False,
        "reasoning_budget_tokens": val
    }
    req = urllib.request.Request(URL, data=json.dumps(p).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        d = json.loads(r.read().decode("utf-8"))
        msg = d["choices"][0]["message"]
        rc = msg.get("reasoning_content", "")
        c = msg.get("content", "")
        u = d.get("usage", {})
        print(f"reasoning_budget_tokens: {val}")
        print(f"  completion_tokens: {u.get('completion_tokens')}")
        print(f"  reasoning_content: {repr(rc[:100])}")
        print(f"  content: {repr(c[:100])}")
        print()

test_bgt(0)
test_bgt(30)
test_bgt(100)
test_bgt(-1)