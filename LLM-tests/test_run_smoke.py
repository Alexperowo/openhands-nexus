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
7. Сообщи подробный итоговый отчет в чат со всеми полученными результатами."""

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
    print("User message posted, status:", r.status)

# 3. Monitor
seen_ids = set()
start_t = time.time()
while time.time() - start_t < 180:
    time.sleep(3)
    # Events
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
                    act = ev.get('action')
                    msg = ev.get('message')
                    content = ev.get('content')
                    thought = ev.get('thought')
                    print(f"[{src}]", end=" ")
                    if thought: print(f"THOUGHT: {thought[:100]}...", end=" ")
                    if t_call: print(f"TOOL_CALL: {t_call.get('function_name')} args={t_call.get('arguments')}", end=" ")
                    if t_resp: print(f"TOOL_RESP: {str(t_resp.get('content', t_resp))[:100]}...", end=" ")
                    if msg: print(f"MSG: {str(msg)[:100]}...", end=" ")
                    if content and not t_call and not t_resp: print(f"CONTENT: {str(content)[:100]}...", end=" ")
                    print()
    except Exception as e:
        print("Error search events:", e)

    # Status
    try:
        c_req = urllib.request.Request(f'http://localhost:8000/api/conversations/{cid}', headers={'X-Session-API-Key': key})
        with urllib.request.urlopen(c_req) as r:
            c_data = json.loads(r.read().decode())
            st = c_data.get('execution_status')
            ast = c_data.get('agent_state')
            if st in ['idle', 'completed', 'finished', 'stopped'] and len(seen_ids) > 2:
                print(f"\nExecution finished with status={st}, agent_state={ast} in {round(time.time()-start_t, 1)}s")
                break
    except Exception as e:
        print("Error get conv:", e)

print("\nFiles in K:\\Project\\AgentCanvas-Test:")
for f in os.listdir(r'K:\Project\AgentCanvas-Test'):
    p = os.path.join(r'K:\Project\AgentCanvas-Test', f)
    print(f"- {f} ({os.path.getsize(p)} bytes)")
    if os.path.isfile(p):
        with open(p, 'r', encoding='utf-8', errors='ignore') as fp:
            print("  " + fp.read().strip().replace("\n", "\n  "))