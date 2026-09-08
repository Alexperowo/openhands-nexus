import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
URL = "http://127.0.0.1:8080/v1/chat/completions"

p = {
    "model": "Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
    "messages": [
        {"role": "user", "content": "What is 2+2? Answer in one word."}
    ],
    "max_tokens": 128,
    "temperature": 0.7,
    "stream": False,
    "chat_template_kwargs": {"enable_thinking": False},
    "reasoning_format": "deepseek"
}
req = urllib.request.Request(URL, data=json.dumps(p).encode("utf-8"), headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req) as r:
    d = json.loads(r.read().decode("utf-8"))
    msg = d["choices"][0]["message"]
    print("reasoning_content:", repr(msg.get("reasoning_content", "")))
    print("content:", repr(msg.get("content", "")))
    print("usage:", d.get("usage"))