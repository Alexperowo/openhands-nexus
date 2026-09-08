import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
URL = "http://127.0.0.1:8080/completion"

def test_raw(name, prompt):
    p = {
        "prompt": prompt,
        "n_predict": 64,
        "temperature": 0.7,
        "top_p": 0.8,
        "min_p": 0.05,
        "stream": False
    }
    req = urllib.request.Request(URL, data=json.dumps(p).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        d = json.loads(r.read().decode("utf-8"))
        c = d.get("content", "")
        print(f"=== {name} ===")
        print(f"  OUTPUT: {repr(c[:100])}")

test_raw("1: assistant\\n", "<|im_start|>user\nWhat is 2+2? Answer in one word.<|im_end|>\n<|im_start|>assistant\n")
test_raw("2: assistant\\n<think>\\n\\n</think>\\n\\n", "<|im_start|>user\nWhat is 2+2? Answer in one word.<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n")
test_raw("3: assistant\\n<think>\\n</think>", "<|im_start|>user\nWhat is 2+2? Answer in one word.<|im_end|>\n<|im_start|>assistant\n<think>\n</think>")
test_raw("4: assistant\\n<think>\\n</think>\\n", "<|im_start|>user\nWhat is 2+2? Answer in one word.<|im_end|>\n<|im_start|>assistant\n<think>\n</think>\n")
test_raw("5: assistant\\n[THINKING OFF]\\n", "<|im_start|>system\nYou are in non-thinking direct mode.<|im_end|>\n<|im_start|>user\nWhat is 2+2? Answer in one word.<|im_end|>\n<|im_start|>assistant\n")