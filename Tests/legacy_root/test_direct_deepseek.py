import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
URL = "http://127.0.0.1:8080/v1/chat/completions"

PROMPT = "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost? Show your steps."

def test_d(name, extra):
    p = {
        "model": "Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 256,
        "temperature": 0.7,
        "stream": False
    }
    p.update(extra)
    req = urllib.request.Request(URL, data=json.dumps(p).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        msg = d["choices"][0]["message"]
        c = msg.get("content", "")
        rc = msg.get("reasoning_content", "")
        print(f"=== {name} ===")
        print(f"  reasoning_content len: {len(rc)}")
        print(f"  content len: {len(c)}")
        print(f"  has <think> in content: {'<think>' in c}")
        print(f"  content start: {repr(c[:100])}")
        print()

test_d("Direct 1: reasoning_format=deepseek, reasoning_budget_tokens=0", {
    "reasoning_format": "deepseek",
    "reasoning_budget_tokens": 0
})

test_d("Direct 2: reasoning_budget_tokens=0", {
    "reasoning_budget_tokens": 0
})

test_d("Direct 3: enable_thinking=False, reasoning_format=deepseek, reasoning_budget_tokens=0", {
    "chat_template_kwargs": {"enable_thinking": False},
    "reasoning_format": "deepseek",
    "reasoning_budget_tokens": 0
})