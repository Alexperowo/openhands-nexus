import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
URL = "http://127.0.0.1:8080/completion"

p = {
    "prompt": "<|im_start|>user\nExplain the difference between TCP and UDP in 2 bullet points.<|im_end|>\n<|im_start|>assistant\n<think>\n</think>",
    "n_predict": 128,
    "temperature": 0.7,
    "top_p": 0.8,
    "min_p": 0.05,
    "stream": False
}
req = urllib.request.Request(URL, data=json.dumps(p).encode("utf-8"), headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req) as r:
    d = json.loads(r.read().decode("utf-8"))
    c = d.get("content", "")
    print("OUTPUT:\n" + c)
    print("HAS <think>:", "<think>" in c)