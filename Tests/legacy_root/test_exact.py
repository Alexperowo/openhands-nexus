import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
URL = "http://127.0.0.1:8080/v1/chat/completions"

def run_test(name, extra):
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
            reasoning = msg.get("reasoning_content", "")
            usage = d.get("usage", {})
            print(f"=== {name} ===")
            print(f"  prompt_tokens: {usage.get('prompt_tokens')}, completion_tokens: {usage.get('completion_tokens')}")
            print(f"  reasoning_content len: {len(reasoning)}")
            if reasoning:
                print(f"  reasoning: {repr(reasoning[:60])}")
            print(f"  content: {repr(c[:60])}")
            print(f"  has <think> in content: {'<think>' in c}")
    except urllib.error.HTTPError as e:
        print(f"=== {name} ERROR: HTTP {e.code} ===")
        print(e.read().decode("utf-8")[:200])

print("Testing exact binary parameters...")

run_test("A: enable_thinking=False (top level)", {
    "enable_thinking": False
})

run_test("B: reasoning_budget_tokens=0 (top level)", {
    "reasoning_budget_tokens": 0
})

run_test("C: enable_thinking=False AND reasoning_budget_tokens=0", {
    "enable_thinking": False,
    "reasoning_budget_tokens": 0
})

run_test("D: chat_template_kwargs={'enable_thinking': False}", {
    "chat_template_kwargs": {"enable_thinking": False}
})

run_test("E: chat_template_kwargs={'enable_thinking': False}, reasoning_budget_tokens=0", {
    "chat_template_kwargs": {"enable_thinking": False},
    "reasoning_budget_tokens": 0
})