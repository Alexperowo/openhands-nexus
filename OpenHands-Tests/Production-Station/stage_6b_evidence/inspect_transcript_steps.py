import json, sys
sys.stdout.reconfigure(encoding='utf-8')

transcript_path = r'C:\Users\User\.gemini\antigravity\brain\f2ece564-c6b9-4bcb-978c-aa86c97c4da5\.system_generated\logs\transcript_full.jsonl'
target_indices = [3, 120, 121, 129, 140, 1488, 5674, 5675, 5742]

with open(transcript_path, 'r', encoding='utf-8') as f:
    for idx, line in enumerate(f):
        if idx in target_indices:
            obj = json.loads(line)
            step = obj.get('step_index')
            content = obj.get('content', '')
            tool_calls = obj.get('tool_calls', [])
            print(f"=== Line {idx} (Step {step}, {obj.get('type')}) ===")
            if content:
                print('Content excerpt:', content[:300].replace('\n', ' '))
            if tool_calls:
                for tc in tool_calls:
                    print('Tool call:', tc.get('name'), str(tc.get('args'))[:200])
