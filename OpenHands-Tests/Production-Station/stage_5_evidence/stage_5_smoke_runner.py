import json
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = 'http://127.0.0.1:18000'
API_KEY_FILE = Path(r'C:\Users\User\.openhands\agent-canvas\api-key.txt')
WORKSPACE_DIR = r'K:\Project\OpenHands-Tests\Production-Station\stage_5_workspace'
EVIDENCE_DIR = Path(r'K:\Project\OpenHands-Tests\Production-Station\stage_5_evidence')

def get_headers():
    key = API_KEY_FILE.read_text(encoding='utf-8').strip()
    return {
        'X-Session-API-Key': key,
        'Content-Type': 'application/json'
    }

def request(method, path, body=None):
    url = f'{BASE_URL}{path}'
    data = json.dumps(body).encode('utf-8') if body else None
    req = urllib.request.Request(url, data=data, headers=get_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read().decode('utf-8')
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        print(f'HTTPError {e.code} for {path}: {err_body}')
        raise

if __name__ == '__main__':
    # 0. Get active profile
    ap_info = request('GET', '/api/agent-profiles')
    active_profile_id = ap_info.get('active_agent_profile_id')
    active_profile_name = next((p['name'] for p in ap_info.get('profiles', []) if p['id'] == active_profile_id), 'unknown')
    print(f'Active profile: {active_profile_name} ({active_profile_id})')

    # 1. Create conversation with active profile
    payload = {
        'workspace': {
            'kind': 'LocalWorkspace',
            'working_dir': WORKSPACE_DIR
        },
        'agent_profile_id': active_profile_id,
        'initial_message': {
            'role': 'user',
            'content': [
                {
                    'type': 'text',
                    'text': 'Create a short text file in the current workspace directory named smoke_test.txt containing exactly: STAGE 5 SMOKE TEST PASSED 2026. Then read it back to confirm, and call finish.'
                }
            ]
        },
        'autotitle': False
    }

    print('Creating conversation via Agent Server API...')
    conv_info = request('POST', '/api/conversations', payload)
    conv_id = conv_info['id']
    print(f'Conversation created: {conv_id}')

    # 2. Run conversation
    print('Starting conversation run...')
    run_resp = request('POST', f'/api/conversations/{conv_id}/run')
    print('Run response:', run_resp)

    # 3. Poll until done
    start_time = time.time()
    last_status = None
    while time.time() - start_time < 240:
        info = request('GET', f'/api/conversations/{conv_id}')
        status = info.get('execution_status')
        if status != last_status:
            t_str = time.strftime('%H:%M:%S')
            print(f'[{t_str}] Execution status: {status}')
            last_status = status
        if status in ('finished', 'idle', 'paused', 'error', 'stuck'):
            # If idle and has run for at least 5s, check if file exists or agent completed
            if status == 'finished' or (status == 'idle' and (time.time() - start_time) > 10):
                print(f'Terminal/settled execution status: {status}')
                break
        time.sleep(3)

    # 4. Fetch events
    events = request('GET', f'/api/conversations/{conv_id}/events')
    ev_list = events.get('events', [])
    print(f'Total events received: {len(ev_list)}')

    # 5. Verify file
    target_file = Path(WORKSPACE_DIR) / 'smoke_test.txt'
    file_exists = target_file.exists()
    file_content = target_file.read_text(encoding='utf-8').strip() if file_exists else ''
    print(f'smoke_test.txt exists: {file_exists}')
    print(f'smoke_test.txt content: {file_content}')

    result = {
        'conversation_id': conv_id,
        'active_profile_id': active_profile_id,
        'active_profile_name': active_profile_name,
        'final_execution_status': last_status,
        'elapsed_seconds': round(time.time() - start_time, 2),
        'file_exists': file_exists,
        'file_content': file_content,
        'content_matches': 'STAGE 5 SMOKE TEST PASSED 2026' in file_content,
        'events_count': len(ev_list),
        'events': ev_list
    }

    out_path = EVIDENCE_DIR / 'smoke_test_result.json'
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Evidence saved to:', out_path)
