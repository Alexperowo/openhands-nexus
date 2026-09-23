import json
import sys

filename = sys.argv[1] if len(sys.argv) > 1 else 'K:/Project/Tests/cognitive/results_qwen122.json'
with open(filename, 'r', encoding='utf-8') as f:
    data = json.load(f)

for item in data:
    v_id = item.get("id")
    tok = item.get("tokens_generated")
    speed = item.get("tok_per_sec")
    ttft = item.get("ttft_sec")
    think_len = len(item.get("reasoning_content", ""))
    ans_len = len(item.get("content", ""))
    print(f"[{v_id}] {tok} tokens in {item.get('duration_sec')}s | {speed} tok/s | TTFT: {ttft}s | Think: {think_len} chars | Ans: {ans_len} chars")
