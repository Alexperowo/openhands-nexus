import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
URL = "http://127.0.0.1:8080/v1/chat/completions"

def test_rf(name, extra):
    p = {
        "model": "Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
        "messages": [
            {"role": "user", "content": "What is 2+2? Answer in one word."}
        ],
        "max_tokens": 128,
        "temperature": 0.7,
        "stream": False
    }
    p.update(extra)
    req = urllib.request.Request(URL, data=json.dumps(p).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            d = json.loads(r.read().decode("utf-8"))
            msg = d["choices"][0]["message"]
            c = msg.get("content", "")
            rc = msg.get("reasoning_content", "")
            print(f"=== {name} ===")
            print(f"  reasoning_content: {repr(rc[:50])}")
            print(f"  content: {repr(c[:50])}")
    except urllib.error.HTTPError as e:
        print(f"=== {name} ERROR: HTTP {e.code} ===")
        print(e.read().decode("utf-8")[:200])

test_rf("reasoning_format='none'", {"reasoning_format": "none"})
test_rf("reasoning_format='deepseek'", {"reasoning_format": "deepseek"})
test_rf("reasoning_format='deepseek-legacy'", {"reasoning_format": "deepseek-legacy"})