# -*- coding: utf-8 -*-
import urllib.request, json, time, sys, os

with open(r'C:\Users\User\.openhands\agent-canvas\api-key.txt', 'r') as f:
    key = f.read().strip()

headers = {'X-Session-API-Key': key, 'Content-Type': 'application/json'}

prompt = """Please execute the following test steps in the current workspace directory:
1. Identify and print the current working directory.
2. Create a file named test.txt with the content: 'Hello from Qwen3.8 Opus on RTX 2080 Ti!'
3. Read test.txt back to verify its content.
4. Execute PowerShell command: Get-Date
5. Create a PowerShell script named test.ps1 with content:
Write-Output 'PowerShell Script Executed Successfully'
Get-Date
6. Execute test.ps1 via PowerShell and show the output.
7. Return a complete summary of all completed steps."""

# 1. Create Conversation
req_body = {
    'workspace': {
        'working_dir': r'K:\Project\AgentCanvas-Test',
        'kind': 'LocalWorkspace'
    },
    'agent_profile_id': 'e3de816d-0a24-483f-811d-b8d9a2b8ab30'
}

req = urllib.request.Request('http://localhost:8000/api/conversations', data=json.dumps(req_body).encode('utf-8'), headers=headers, method='POST')
with urllib.request.urlopen(req) as r:
    conv = json.loads(r.read().decode())
    cid = conv['id']
    print(f"Conversation created: {cid}")

# 2. Send Message
msg_body = {
    'role': 'user',
    'content': [{'type': 'text', 'text': prompt}],
    'run': True
}
msg_req = urllib.request.Request(f'http://localhost:8000/api/conversations/{cid}/events', data=json.dumps(msg_body).encode('utf-8'), headers=headers, method='POST')
with urllib.request.urlopen(msg_req) as r:
    print("User prompt submitted successfully (HTTP 200).")

# 3. Poll events until done
seen_ids = set()
start_t = time.time()
print("Waiting for agent to execute all tool steps...")

while time.time() - start_t < 240:
    time.sleep(3)
    try:
        s_req = urllib.request.Request(f'http://localhost:8000/api/conversations/{cid}/events/search', headers={'X-Session-API-Key': key})
        with urllib.request.urlopen(s_req) as r:
            res = json.loads(r.read().decode())
            for ev in res.get('items', []):
                eid = ev.get('id')
                if eid and eid not in seen_ids:
                    seen_ids.add(eid)
                    src = ev.get('source', '')
                    t_call = ev.get('tool_call')
                    t_resp = ev.get('tool_call_response')
                    thought = ev.get('thought')
                    content = ev.get('content')
                    
                    if t_call:
                        print(f"  [AGENT TOOL CALL] {t_call.get('function_name')}: {json.dumps(t_call.get('arguments'), ensure_ascii=False)[:200]}")
                    elif t_resp:
                        print(f"  [TOOL OUTPUT] {str(t_resp.get('content', t_resp))[:200]}")
                    elif thought:
                        print(f"  [AGENT THOUGHT] {thought[:150]}")
                    elif content and src == 'agent':
                        print(f"  [AGENT RESPONSE] {str(content)[:250]}")
    except Exception as e:
        print("Error search:", e)

    try:
        c_req = urllib.request.Request(f'http://localhost:8000/api/conversations/{cid}', headers={'X-Session-API-Key': key})
        with urllib.request.urlopen(c_req) as r:
            c_data = json.loads(r.read().decode())
            st = c_data.get('execution_status')
            ast = c_data.get('agent_state')
            if st in ['idle', 'completed', 'finished', 'stopped'] and len(seen_ids) > 4:
                print(f"\nExecution finished! status='{st}', agent_state='{ast}' in {round(time.time()-start_t, 1)}s")
                break
    except Exception as e:
        pass

print("\n--- Files on disk in K:\\Project\\AgentCanvas-Test ---")
for f in os.listdir(r'K:\Project\AgentCanvas-Test'):
    p = os.path.join(r'K:\Project\AgentCanvas-Test', f)
    print(f"- {f} ({os.path.getsize(p)} bytes)")
    if os.path.isfile(p):
        with open(p, 'r', encoding='utf-8', errors='ignore') as fp:
            print("  Content:\n  " + fp.read().strip().replace("\n", "\n  "))
