import json, time, os, urllib.request, urllib.error, psutil
from pathlib import Path

BASE_URL = "http://127.0.0.1:18000"
API_KEY_FILE = Path(r"C:\Users\User\.openhands\agent-canvas\api-key.txt")
WORKSPACE_DIR = r"K:\Project\OpenHands-Tests\Production-Station\stage_6b_workspace"
EVIDENCE_DIR = Path(r"K:\Project\OpenHands-Tests\Production-Station\stage_6b_evidence")
conv_id = "3065c3e9-e9b5-445d-8219-46f225803202"

def get_headers():
    key = API_KEY_FILE.read_text(encoding="utf-8").strip()
    return {
        "X-Session-API-Key": key,
        "Content-Type": "application/json"
    }

def request(method, path, body=None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=get_headers(), method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        content = resp.read().decode("utf-8")
        return json.loads(content) if content else {}

# Monitor loop
start_time = time.time()
last_status = None
captured_cmdline = None
captured_pid = None

while time.time() - start_time < 120:
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        if 'llama-server' in p.info['name'].lower():
            cmd = ' '.join(p.info['cmdline'])
            if 'Qwen3.8' in cmd:
                captured_cmdline = cmd
                captured_pid = p.info['pid']
                break
                
    info = request("GET", f"/api/conversations/{conv_id}")
    status = info.get("execution_status")
    if status != last_status:
        print(f"[{time.strftime('%H:%M:%S')}] Execution status: {status}")
        last_status = status
        
    target_file = Path(WORKSPACE_DIR) / "smoke_test_qwen.txt"
    if status in ("finished", "idle", "paused", "error", "stuck"):
        if target_file.exists() or status == "finished":
            print(f"Settled: status={status}, file_exists={target_file.exists()}")
            break
            
    time.sleep(3)

target_file = Path(WORKSPACE_DIR) / "smoke_test_qwen.txt"
file_exists = target_file.exists()
file_content = target_file.read_text(encoding="utf-8").strip() if file_exists else ""
print(f"File exists: {file_exists}")
print(f"File content: {file_content}")

events = request("GET", f"/api/conversations/{conv_id}/events").get("events", [])
print(f"Events received: {len(events)}")

# Verify criteria
k_path_present = r"K:\Project\Models\Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf" in (captured_cmdline or "")
d_path_present = r"D:\Project\models" in (captured_cmdline or "")

validation_result = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "stage": "STAGE_6B",
    "conversation_id": conv_id,
    "profile_id": "44761011-15fd-4981-971c-6b3ea145efbc",
    "profile_name": "Qwen-Standalone",
    "final_execution_status": last_status,
    "target_file": str(target_file),
    "file_exists": file_exists,
    "file_content": file_content,
    "content_matches": "QWEN STAGE 6B VERIFIED K_DRIVE" in file_content,
    "events_count": len(events),
    "runtime_process_evidence": {
        "pid": captured_pid,
        "command_line": captured_cmdline,
        "k_path_verified": k_path_present,
        "d_path_absent": not d_path_present
    },
    "qwen_production_validation": "PASS" if (file_exists and k_path_present and not d_path_present) else "FAIL"
}

out_path = EVIDENCE_DIR / "qwen_runtime_validation.json"
out_path.write_text(json.dumps(validation_result, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Result: {validation_result['qwen_production_validation']}")
print(f"Saved to {out_path}")
