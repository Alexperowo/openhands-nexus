import urllib.request
import json
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

URL = "http://127.0.0.1:8080/v1/chat/completions"

def test_p(name, extra):
    p = {
        "model": "Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
        "messages": [
            {"role": "user", "content": "How many r's in strawberry? Give a quick answer."}
        ],
        "max_tokens": 512,
        "temperature": 0.7,
        "stream": False
    }
    p.update(extra)
    req = urllib.request.Request(URL, data=json.dumps(p).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            msg = data["choices"][0]["message"]
            c = msg.get("content", "")
            r = msg.get("reasoning_content", "")
            usage = data.get("usage", {})
            comp_tokens = usage.get("completion_tokens", 0)
            print(f"=== {name} ===")
            print(f"  completion_tokens: {comp_tokens}")
            print(f"  reasoning_content len: {len(r)}")
            if r:
                print(f"  reasoning: {r[:100].strip()}...")
            print(f"  content: {c[:120].strip()}...")
            print(f"  has '<think>': {'<think>' in c or '<think>' in r}")
    except urllib.error.HTTPError as e:
        print(f"=== {name} ERROR {e.code}: {e.read().decode('utf-8')[:150]}")

print("Testing different parameters for turning OFF thinking...")
test_p("reasoning_budget=0", {"reasoning_budget": 0})
test_p("reasoning='off'", {"reasoning": "off"})
test_p("chat_template_kwargs={'enable_thinking': False}, reasoning_budget=0", {"chat_template_kwargs": {"enable_thinking": False}, "reasoning_budget": 0})
test_p("thinking={'type': 'disabled'}", {"thinking": {"type": "disabled"}})
test_p("thinking={'budget_tokens': 0}", {"thinking": {"budget_tokens": 0}})
test_p("reasoning_effort='none'", {"reasoning_effort": "none"})
test_p("chat_template_kwargs={'enable_thinking': False}", {"chat_template_kwargs": {"enable_thinking": False}})