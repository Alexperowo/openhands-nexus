import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
URL = "http://127.0.0.1:8080/v1/chat/completions"

def test_b(q, extra):
    p = {
        "model": "Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
        "messages": [{"role": "user", "content": q}],
        "max_tokens": 256,
        "temperature": 0.7,
        "stream": False
    }
    p.update(extra)
    req = urllib.request.Request(URL, data=json.dumps(p).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        d = json.loads(r.read().decode("utf-8"))
        msg = d["choices"][0]["message"]
        rc = msg.get("reasoning_content", "")
        c = msg.get("content", "")
        u = d.get("usage", {})
        print(f"Q: {q}")
        print(f"  extra: {extra}")
        print(f"  completion_tokens: {u.get('completion_tokens')}")
        print(f"  reasoning_content: {repr(rc)}")
        print(f"  content: {repr(c[:100])}")
        print()

test_b("Explain what DNS is in one sentence.", {"reasoning_budget_tokens": 0})
test_b("Explain what DNS is in one sentence.", {"reasoning_budget_tokens": 0, "reasoning_format": "deepseek"})
test_b("Explain what DNS is in one sentence.", {"chat_template_kwargs": {"reasoning_effort": "low"}})
test_b("Explain what DNS is in one sentence.", {"chat_template_kwargs": {"reasoning_effort": "medium"}})
test_b("Explain what DNS is in one sentence.", {"chat_template_kwargs": {"reasoning_effort": "xhigh"}})