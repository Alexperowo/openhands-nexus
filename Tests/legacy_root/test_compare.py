import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
URL = "http://127.0.0.1:8080/v1/chat/completions"

def call_api(name, extra):
    p = {
        "model": "Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
        "messages": [{"role": "user", "content": "Explain what 2+2 is in one sentence."}],
        "max_tokens": 256,
        "temperature": 0.7,
        "stream": False
    }
    p.update(extra)
    req = urllib.request.Request(URL, data=json.dumps(p).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        d = json.loads(r.read().decode("utf-8"))
        print(f"[{name}]")
        print("  prompt_tokens:", d["usage"]["prompt_tokens"])
        print("  completion_tokens:", d["usage"]["completion_tokens"])
        print("  reasoning_content len:", len(d["choices"][0]["message"].get("reasoning_content", "")))
        print("  content:", d["choices"][0]["message"]["content"][:80])

call_api("1. Default", {})
call_api("2. Root reasoning_effort=low", {"reasoning_effort": "low"})
call_api("3. chat_template_kwargs: reasoning_effort=low", {"chat_template_kwargs": {"reasoning_effort": "low"}})
call_api("4. chat_template_kwargs: reasoning_effort=medium", {"chat_template_kwargs": {"reasoning_effort": "medium"}})
call_api("5. chat_template_kwargs: reasoning_effort=xhigh", {"chat_template_kwargs": {"reasoning_effort": "xhigh"}})
call_api("6. chat_template_kwargs: enable_thinking=False", {"chat_template_kwargs": {"enable_thinking": False}})