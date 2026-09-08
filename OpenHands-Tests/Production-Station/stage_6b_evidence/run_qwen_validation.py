import json, time, os, urllib.request, urllib.error, subprocess
from pathlib import Path

BASE_URL = "http://127.0.0.1:18000"
API_KEY_FILE = Path(r"C:\Users\User\.openhands\agent-canvas\api-key.txt")
WORKSPACE_DIR = r"K:\Project\OpenHands-Tests\Production-Station\stage_6b_workspace"
EVIDENCE_DIR = Path(r"K:\Project\OpenHands-Tests\Production-Station\stage_6b_evidence")

os.makedirs(WORKSPACE_DIR, exist_ok=True)
os.makedirs(EVIDENCE_DIR, exist_ok=True)

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

def get_llama_process_info():
    cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"name = \'llama-server.exe\'\\" | Select-Object ProcessId, CommandLine, ExecutablePath | ConvertTo-Json"'
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            if isinstance(data, dict):
                return [data]
            return data
    except Exception as e:
        print("Error getting process info:", e)
    return []

def get_swap_running_info():
    try:
        req = urllib.request.Request("http://127.0.0.1:8080/running")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print("=== QWEN PRODUCTION VALIDATION RUNNER ===")
    
    # Verify active profile
    ap_info = request("GET", "/api/agent-profiles")
    active_id = ap_info.get("active_agent_profile_id")
    active_profile = next((p for p in ap_info.get("profiles", []) if p["id"] == active_id), {})
    print(f"Active Profile: {active_profile.get('name')} ({active_id})")
    
    # Create conversation
    payload = {
        "workspace": {
            "kind": "LocalWorkspace",
            "working_dir": WORKSPACE_DIR
        },
        "agent_profile_id": active_id,
        "initial_message": {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Please create a text file named smoke_test_qwen.txt in the current workspace containing exactly 'QWEN STAGE 6B VERIFIED K_DRIVE'. Read it back to verify, then call finish."
                }
            ]
        },
        "autotitle": False
    }
    
    print("Creating conversation...")
    conv_info = request("POST", "/api/conversations", payload)
    conv_id = conv_info["id"]
    print(f"Conversation created: {conv_id}")
    
    print("Starting conversation run...")
    run_resp = request("POST", f"/api/conversations/{conv_id}/run")
    print("Run initiated:", run_resp)
    
    # Poll and monitor llama process
    start_time = time.time()
    last_status = None
    captured_process_info = []
    captured_swap_info = []
    
    while time.time() - start_time < 180:
        info = request("GET", f"/api/conversations/{conv_id}")
        status = info.get("execution_status")
        if status != last_status:
            t_str = time.strftime("%H:%M:%S")
            print(f"[{t_str}] Status: {status}")
            last_status = status
            
        # Capture process info while running
        procs = get_llama_process_info()
        if procs:
            for p in procs:
                cmdline = p.get("CommandLine") or ""
                if "Qwen3.8" in cmdline or "qwen" in cmdline.lower():
                    if not any(cp.get("ProcessId") == p.get("ProcessId") for cp in captured_process_info):
                        captured_process_info.append(p)
                        print(f"Captured llama-server Qwen process! PID={p.get('ProcessId')}")
                        print(f"CommandLine: {cmdline}")
        
        swap_info = get_swap_running_info()
        if swap_info and not swap_info.get("error"):
            captured_swap_info.append(swap_info)
            
        if status in ("finished", "idle", "paused", "error", "stuck"):
            target_file = Path(WORKSPACE_DIR) / "smoke_test_qwen.txt"
            if target_file.exists() and (status == "finished" or (status == "idle" and time.time() - start_time > 10)):
                print(f"Settled with file present: {status}")
                break
        time.sleep(2)
        
    # Final check of file
    target_file = Path(WORKSPACE_DIR) / "smoke_test_qwen.txt"
    file_exists = target_file.exists()
    file_content = target_file.read_text(encoding="utf-8").strip() if file_exists else ""
    print(f"File exists: {file_exists}")
    print(f"File content: '{file_content}'")
    
    # If process was not captured during loop, capture now
    if not captured_process_info:
        captured_process_info = get_llama_process_info()
        
    events = request("GET", f"/api/conversations/{conv_id}/events").get("events", [])
    print(f"Events count: {len(events)}")
    
    # Evidence verification
    k_path_present = False
    d_path_present = False
    qwen_cmdline = ""
    for cp in captured_process_info:
        cmdline = cp.get("CommandLine") or ""
        if "Qwen3.8" in cmdline:
            qwen_cmdline = cmdline
            if r"K:\Project\Models\Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf" in cmdline:
                k_path_present = True
            if r"D:\Project\models" in cmdline:
                d_path_present = True
                
    validation_passed = (
        file_exists and
        "QWEN STAGE 6B VERIFIED K_DRIVE" in file_content and
        k_path_present and
        not d_path_present
    )
    
    validation_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stage": "STAGE_6B",
        "conversation_id": conv_id,
        "profile_id": active_id,
        "profile_name": active_profile.get("name"),
        "final_status": last_status,
        "elapsed_seconds": round(time.time() - start_time, 2),
        "target_file": str(target_file),
        "file_exists": file_exists,
        "file_content": file_content,
        "content_matches": "QWEN STAGE 6B VERIFIED K_DRIVE" in file_content,
        "events_count": len(events),
        "runtime_process_evidence": {
            "captured_processes": captured_process_info,
            "qwen_command_line": qwen_cmdline,
            "k_path_verified": k_path_present,
            "d_path_absent": not d_path_present
        },
        "swap_runtime_evidence": captured_swap_info[-1] if captured_swap_info else {},
        "qwen_production_validation": "PASS" if validation_passed else "FAIL"
    }
    
    out_file = EVIDENCE_DIR / "qwen_runtime_validation.json"
    out_file.write_text(json.dumps(validation_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Validation result: {validation_data['qwen_production_validation']}")
    print(f"Evidence written to: {out_file}")
