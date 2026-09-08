import urllib.request
import json
import time
import os
import subprocess

SWAP_URL = "http://127.0.0.1:8080/v1/chat/completions"
PROFILES_DIR = r"C:\Users\User\.openhands\profiles"

def get_next_pid():
    try:
        cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"Name like \'llama-server%\'\\" | Select-Object ProcessId, ExecutablePath | ConvertTo-Json"'
        out = subprocess.check_output(cmd, shell=True, encoding="utf-8").strip()
        if not out:
            return None
        data = json.loads(out)
        if isinstance(data, dict):
            return data.get("ProcessId")
        elif isinstance(data, list) and len(data) > 0:
            return data[0].get("ProcessId")
        return None
    except:
        return None

def test_profile(profile_name, expected_budget):
    profile_path = os.path.join(PROFILES_DIR, f"{profile_name}.json")
    with open(profile_path, "r", encoding="utf-8") as f:
        pdata = json.load(f)
    
    extra_body = pdata.get("litellm_extra_body", {})
    budget = extra_body.get("thinking_budget_tokens", pdata.get("extended_thinking_budget"))
    
    print(f"\n==========================================")
    print(f"Testing Profile: {profile_name}")
    print(f"Configured thinking_budget_tokens: {budget} (Expected: {expected_budget})")
    print(f"==========================================")
    
    pid_before = get_next_pid()
    t0 = time.time()
    
    payload = {
        "model": pdata.get("model", "openai/next"),
        "messages": [
            {"role": "user", "content": "How many 'r's are in the word strawberry? Think briefly and answer."}
        ],
        "max_tokens": pdata.get("max_output_tokens", 5120),
        "temperature": pdata.get("temperature", 0.6),
        "thinking_budget_tokens": budget,
        "chat_template_kwargs": {
            "thinking_budget_tokens": budget
        }
    }
    
    req = urllib.request.Request(
        SWAP_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    with urllib.request.urlopen(req, timeout=300) as r:
        res = json.loads(r.read().decode("utf-8"))
    
    t1 = time.time()
    pid_after = get_next_pid()
    
    choice = res["choices"][0]["message"]
    reasoning = choice.get("reasoning_content", "")
    content = choice.get("content", "")
    usage = res.get("usage", {})
    
    print(f"Elapsed time: {t1 - t0:.2f}s")
    print(f"PID before: {pid_before}, PID after: {pid_after} (Reloaded: {pid_before != pid_after})")
    print(f"Prompt tokens: {usage.get('prompt_tokens')}, Completion tokens: {usage.get('completion_tokens')}")
    print(f"Reasoning length: {len(reasoning)} chars")
    print(f"Response preview: {content.strip()[:100]!r}")
    
    return {
        "profile": profile_name,
        "budget": budget,
        "elapsed_s": round(t1 - t0, 2),
        "pid_before": pid_before,
        "pid_after": pid_after,
        "reloaded": pid_before != pid_after,
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_chars": len(reasoning),
        "response": content.strip()
    }

if __name__ == "__main__":
    res_normal = test_profile("Next-Normal", 2048)
    res_deep = test_profile("Next-Deep", 4096)
    
    print("\n=== SUMMARY ===")
    print(f"Next-Normal: {res_normal['elapsed_s']}s, reloaded={res_normal['reloaded']}")
    print(f"Next-Deep:   {res_deep['elapsed_s']}s, reloaded={res_deep['reloaded']}")
    
    zero_reload = (res_normal['pid_after'] == res_deep['pid_after']) and (not res_deep['reloaded'])
    print(f"Zero reload between Normal and Deep: {zero_reload}")
