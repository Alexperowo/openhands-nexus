import urllib.request, json, time, sys, os

with open(r'C:\Users\User\.openhands\agent-canvas\api-key.txt', 'r') as f:
    key = f.read().strip()

headers = {'X-Session-API-Key': key, 'Content-Type': 'application/json'}

prompt = """Пожалуйста, выполни следующие действия в текущей рабочей папке:
1. Выведи текущий рабочий каталог.
2. Создай текстовый файл test.txt с содержимым: 'Hello from Qwen3.8 Opus on RTX 2080 Ti!'
3. Прочитай файл test.txt обратно и проверь его содержимое.
4. Выполни команду PowerShell: Get-Date
5. Создай файл test.ps1 с содержимым:
Write-Output 'PowerShell Script Executed Successfully'
Get-Date
6. Выполни скрипт test.ps1 через PowerShell.
7. Сообщи об успешном завершении всех шагов."""

# 1. Start Conversation
req_body = {
    'workspace': {
        'working_dir': r'K:\Project\AgentCanvas-Test',
        'kind': 'LocalWorkspace'
    },
    'agent_profile_id': 'e3de816d-0a24-483f-811d-b8d9a2b8ab30'
}

print("1. Creating conversation...")
req = urllib.request.Request('http://localhost:8000/api/conversations', data=json.dumps(req_body).encode('utf-8'), headers=headers, method='POST')
with urllib.request.urlopen(req) as r:
    conv = json.loads(r.read().decode())
    conv_id = conv['id']
    print(f"Conversation created: {conv_id}")

# 2. Send Message with run=True
print("2. Sending user message to agent with run=True...")
msg_body = {
    'role': 'user',
    'content': [{'type': 'text', 'text': prompt}],
    'run': True
}
msg_req = urllib.request.Request(f'http://localhost:8000/api/conversations/{conv_id}/events', data=json.dumps(msg_body).encode('utf-8'), headers=headers, method='POST')
with urllib.request.urlopen(msg_req) as r:
    print("Message sent, response:", r.read().decode())

# 3. Monitor execution
print("3. Monitoring agent events...")
seen_event_ids = set()
start_time = time.time()
max_wait = 180

while time.time() - start_time < max_wait:
    time.sleep(2)
    # Check events
    try:
        ev_req = urllib.request.Request(f'http://localhost:8000/api/conversations/{conv_id}/events', headers={'X-Session-API-Key': key})
        with urllib.request.urlopen(ev_req) as r:
            events = json.loads(r.read().decode())
            for ev in events:
                eid = ev.get('id') or ev.get('timestamp') or str(ev)
                if eid not in seen_event_ids:
                    seen_event_ids.add(eid)
                    src = ev.get('source', '')
                    action = ev.get('action', '')
                    obs = ev.get('observation', '')
                    tool_call = ev.get('tool_call', {})
                    tool_resp = ev.get('tool_call_response', {})
                    msg = ev.get('message', '')
                    llm_resp = ev.get('llm_response', '')
                    content = ev.get('content', '')
                    
                    info = f"[{src}]"
                    if action: info += f" action={action}"
                    if tool_call: info += f" tool_call={tool_call.get('function_name', tool_call)}"
                    if tool_resp: info += f" tool_resp={str(tool_resp)[:120]}"
                    if msg: info += f" msg={str(msg)[:120]}"
                    if content: info += f" content={str(content)[:120]}"
                    print(f"  Event: {info[:180]}")
    except Exception as e:
        print(f"  Error polling events: {e}")

    # Check conversation state
    try:
        c_req = urllib.request.Request(f'http://localhost:8000/api/conversations/{conv_id}', headers={'X-Session-API-Key': key})
        with urllib.request.urlopen(c_req) as r:
            c_info = json.loads(r.read().decode())
            status = c_info.get('execution_status', '')
            state = c_info.get('agent_state', '')
            if status in ['idle', 'completed', 'finished', 'stopped'] and len(seen_event_ids) > 2:
                print(f"\nExecution reached status='{status}', state='{state}' after {round(time.time()-start_time, 1)}s")
                break
    except Exception as e:
        print(f"  Error polling status: {e}")

# Check files created in K:\Project\AgentCanvas-Test
print("\n4. Verifying created files on disk:")
for fn in os.listdir(r'K:\Project\AgentCanvas-Test'):
    fp = os.path.join(r'K:\Project\AgentCanvas-Test', fn)
    print(f"  File: {fn} (size: {os.path.getsize(fp)} bytes)")
    if os.path.isfile(fp):
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            print(f"    Content: {f.read().strip()}")
