import urllib.request, json, time, sys, os

api_key_path = os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"), ".openhands", "agent-canvas", "api-key.txt")
with open(api_key_path, 'r') as f:
    key = f.read().strip()

headers = {'X-Session-API-Key': key}
cid = '011a0c67-250c-4ce7-aa6e-46b9ec910f33'

print(f"Monitoring conversation: {cid}")
seen_ids = set()
start_time = time.time()

while time.time() - start_time < 240:
    time.sleep(3)
    try:
        req = urllib.request.Request(f'http://localhost:8000/api/conversations/{cid}/events/search', headers=headers)
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read().decode())
            for ev in data.get('items', []):
                eid = ev.get('id')
                if eid and eid not in seen_ids:
                    seen_ids.add(eid)
                    src = ev.get('source', '')
                    action = ev.get('action', '')
                    obs = ev.get('observation', '')
                    tool_call = ev.get('tool_call', {})
                    tool_resp = ev.get('tool_call_response', {})
                    msg = ev.get('message', '')
                    content = ev.get('content', '')
                    thought = ev.get('thought', '')
                    
                    print(f"\n--- Event [{src}] ---")
                    if thought: print(f"  Thought: {thought[:200]}")
                    if action: print(f"  Action: {str(action)[:200]}")
                    if tool_call: print(f"  Tool Call: {tool_call}")
                    if tool_resp: print(f"  Tool Resp: {str(tool_resp)[:200]}")
                    if msg: print(f"  Message: {str(msg)[:200]}")
                    if content: print(f"  Content: {str(content)[:200]}")
    except Exception as e:
        print(f"  Error polling events: {e}")

    try:
        req_c = urllib.request.Request(f'http://localhost:8000/api/conversations/{cid}', headers=headers)
        with urllib.request.urlopen(req_c) as r:
            c_info = json.loads(r.read().decode())
            status = c_info.get('execution_status', '')
            state = c_info.get('agent_state', '')
            if status in ['idle', 'completed', 'finished', 'stopped'] and len(seen_ids) > 3:
                print(f"\n>> Execution finished with status='{status}', state='{state}' in {round(time.time()-start_time, 1)}s")
                break
    except Exception as e:
        print(f"  Error polling status: {e}")

print("\n--- Disk verification in K:\\Project\\AgentCanvas-Test ---")
for fn in os.listdir(r'K:\Project\AgentCanvas-Test'):
    fp = os.path.join(r'K:\Project\AgentCanvas-Test', fn)
    print(f"File: {fn} ({os.path.getsize(fp)} bytes)")
    if os.path.isfile(fp):
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            print(f"  Content:\n{f.read().strip()}")