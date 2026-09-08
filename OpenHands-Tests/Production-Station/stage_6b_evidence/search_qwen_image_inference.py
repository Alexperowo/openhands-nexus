import json

transcript_path = r'C:\Users\User\.gemini\antigravity\brain\f2ece564-c6b9-4bcb-978c-aa86c97c4da5\.system_generated\logs\transcript_full.jsonl'

matches = []
with open(transcript_path, 'r', encoding='utf-8') as f:
    for idx, line in enumerate(f):
        if 'image' in line.lower() and ('qwen3.8' in line or 'qwen 3.8' in line):
            if any(term in line.lower() for term in ['base64', 'chat/completions', 'image_url', 'vision_test', 'inference']):
                matches.append(idx)

print("Found candidate inference steps:", len(matches), matches[:20])
