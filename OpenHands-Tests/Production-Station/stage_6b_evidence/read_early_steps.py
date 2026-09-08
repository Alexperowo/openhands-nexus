import json, sys
sys.stdout.reconfigure(encoding='utf-8')

transcript_path = r'C:\Users\User\.gemini\antigravity\brain\f2ece564-c6b9-4bcb-978c-aa86c97c4da5\.system_generated\logs\transcript_full.jsonl'

with open(transcript_path, 'r', encoding='utf-8') as f:
    for idx, line in enumerate(f):
        if 118 <= idx <= 142:
            obj = json.loads(line)
            step = obj.get('step_index')
            source = obj.get('source')
            typ = obj.get('type')
            content = obj.get('content', '')
            tcs = obj.get('tool_calls', [])
            print(f"=== Step {step} ({source}, {typ}) ===")
            if tcs:
                for tc in tcs:
                    print("TOOL CALL:", tc['name'], json.dumps(tc['args']))
            if content:
                print("CONTENT:", content[:500].replace('\n', ' '))
