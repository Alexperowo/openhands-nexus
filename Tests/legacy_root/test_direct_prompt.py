import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
URL = "http://127.0.0.1:8080/v1/chat/completions"

def test_q(name, msgs, extra):
    p = {
        "model": "Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
        "messages": msgs,
        "max_tokens": 128,
        "temperature": 0.7,
        "stream": False
    }
    p.update(extra)
    req = urllib.request.Request(URL, data=json.dumps(p).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        d = json.loads(r.read().decode("utf-8"))
        msg = d["choices"][0]["message"]
        c = msg.get("content", "")
        rc = msg.get("reasoning_content", "")
        u = d.get("usage", {})
        print(f"=== {name} ===")
        print(f"  prompt_tokens: {u.get('prompt_tokens')}, comp_tokens: {u.get('completion_tokens')}")
        print(f"  reasoning_content: len={len(rc)}, text={repr(rc[:60])}")
        print(f"  content: {repr(c[:80])}")
        print(f"  has '<think>': {'<think>' in c or '<think>' in rc}")

# Test 1: System prompt saying "Answer directly without thinking." with enable_thinking=False
test_q("1. enable_thinking=False + Direct system instruction", [
    {"role": "system", "content": "Direct response mode. Do not think. Answer directly."},
    {"role": "user", "content": "What is 2+2? Answer in one word."}
], {"chat_template_kwargs": {"enable_thinking": False}})

# Test 2: System prompt saying "Answer directly without thinking." with enable_thinking=True, low
test_q("2. enable_thinking=True, reasoning_effort=low + Direct system instruction", [
    {"role": "system", "content": "Direct response mode. Do not think. Answer directly."},
    {"role": "user", "content": "What is 2+2? Answer in one word."}
], {"chat_template_kwargs": {"reasoning_effort": "low"}})

# Test 3: Stop tokens: adding "</think>" or similar?
test_q("3. enable_thinking=False + stop: ['<think>']", [
    {"role": "user", "content": "What is 2+2? Answer in one word."}
], {"chat_template_kwargs": {"enable_thinking": False}, "stop": ["<think>"]})

# Test 4: enable_thinking=False + assistant prefill "4"
test_q("4. enable_thinking=False + assistant prefill", [
    {"role": "user", "content": "What is 2+2? Answer in one word."},
    {"role": "assistant", "content": "4"}
], {"chat_template_kwargs": {"enable_thinking": False}})
