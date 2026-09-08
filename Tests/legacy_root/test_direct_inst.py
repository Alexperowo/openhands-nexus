import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
URL = "http://127.0.0.1:8080/v1/chat/completions"

def test_direct(instruction, user_prompt):
    p = {
        "model": "Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 128,
        "temperature": 0.7,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False}
    }
    req = urllib.request.Request(URL, data=json.dumps(p).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        d = json.loads(r.read().decode("utf-8"))
        msg = d["choices"][0]["message"]
        c = msg.get("content", "")
        print(f"Instruction: {instruction[:50]}...")
        print(f"  Response: {repr(c[:100])}")
        print(f"  Has <think>: {'<think>' in c}")
        print()

test_direct(
    "Respond directly without thinking. Do not use <think> tags.",
    "What is the capital of France?"
)
test_direct(
    "/no_thinking",
    "What is the capital of France?"
)
test_direct(
    "You are a helpful assistant. Output only the final answer directly without any reasoning.",
    "What is the capital of France?"
)