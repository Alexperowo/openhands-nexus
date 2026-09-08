import urllib.request
import json
import time

URL = "http://127.0.0.1:8080/v1/chat/completions"

def test_request(name, payload_extra):
    payload = {
        "model": "Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
        "messages": [
            {"role": "user", "content": "How many r's in strawberry? Give a quick answer."}
        ],
        "max_tokens": 512,
        "temperature": 0.7,
        "stream": False
    }
    payload.update(payload_extra)
    
    t0 = time.time()
    req = urllib.request.Request(URL, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed = time.time() - t0
            msg = data["choices"][0]["message"]
            content = msg.get("content", "")
            reasoning = msg.get("reasoning_content", "")
            usage = data.get("usage", {})
            print(f"=== TEST: {name} ({elapsed:.2f}s) ===")
            print(f"  Reasoning content present: {bool(reasoning)} (len: {len(reasoning)})")
            if reasoning:
                print(f"  Reasoning preview: {reasoning[:120].strip()}...")
            print(f"  Content preview: {content[:120].strip()}...")
            print(f"  Usage: {usage}")
            return data
    except urllib.error.HTTPError as e:
        print(f"=== TEST: {name} FAILED: HTTP {e.code} ===")
        print(e.read().decode("utf-8")[:300])
        return None

print("Testing direct request formats...")
# Baseline
test_request("Default (no extra params)", {})

# Test 1: chat_template_kwargs with enable_thinking: False
test_request("chat_template_kwargs: enable_thinking=False", {
    "chat_template_kwargs": {"enable_thinking": False}
})

# Test 2: chat_template_kwargs with reasoning_effort=low
test_request("chat_template_kwargs: reasoning_effort=low", {
    "chat_template_kwargs": {"reasoning_effort": "low"}
})

# Test 3: root reasoning_effort='low'
test_request("Root reasoning_effort=low", {
    "reasoning_effort": "low"
})

# Test 4: root enable_thinking=False
test_request("Root enable_thinking=False", {
    "enable_thinking": False
})