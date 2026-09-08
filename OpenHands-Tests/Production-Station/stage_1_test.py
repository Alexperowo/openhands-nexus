import os
import sys
import json
import time
import subprocess
import httpx
from datetime import datetime, timezone

# Ensure openhands is available
try:
    from openhands.sdk import Message, TextContent
    from openhands.sdk.llm.llm_profile_store import LLMProfileStore
except ImportError:
    print("Error: openhands.sdk not found in python path.")
    sys.exit(1)

EVIDENCE_FILE_K = r"K:\Project\OpenHands-Tests\Production-Station\stage_1_evidence.json"
EVIDENCE_FILE_BRAIN = r"C:\Users\User\.gemini\antigravity\brain\f2ece564-c6b9-4bcb-978c-aa86c97c4da5\stage_1_evidence.json"
LLAMA_SWAP_LOG = r"K:\Project\llama-swap\logs\llama-swap.log"

# Intercept outgoing HTTP requests made by httpx (used by LiteLLM)
captured_wire_requests = []
original_httpx_send = httpx.Client.send

def intercepting_send(self, request, *args, **kwargs):
    req_url = str(request.url)
    if ":8080" in req_url:
        body_text = None
        body_json = None
        if request.content:
            try:
                body_text = request.content.decode("utf-8", errors="ignore")
                body_json = json.loads(body_text)
            except Exception:
                pass
        captured_wire_requests.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": req_url,
            "method": request.method,
            "headers": dict(request.headers),
            "body_json": body_json,
            "body_raw": body_text
        })
    return original_httpx_send(self, request, *args, **kwargs)

httpx.Client.send = intercepting_send

def get_llama_server_pid():
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", "Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
            text=True
        ).strip()
        pids = [int(line.strip()) for line in out.splitlines() if line.strip().isdigit()]
        return pids[0] if pids else None
    except Exception:
        return None

def get_vram_usage():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True
        ).strip()
        return int(out.splitlines()[0].strip())
    except Exception:
        return None

def extract_response_fields(resp):
    content = ""
    reasoning = ""
    finish_reason = ""
    
    # 1. Check resp.message
    if hasattr(resp, "message") and resp.message:
        if hasattr(resp.message, "content") and resp.message.content:
            parts = []
            for item in resp.message.content:
                if hasattr(item, "text"):
                    parts.append(item.text)
                elif isinstance(item, str):
                    parts.append(item)
            content = "".join(parts)
        if hasattr(resp.message, "reasoning_content") and resp.message.reasoning_content:
            reasoning = resp.message.reasoning_content

    # 2. Check resp.raw_response
    if hasattr(resp, "raw_response") and resp.raw_response:
        raw = resp.raw_response
        choices = getattr(raw, "choices", None)
        if choices and len(choices) > 0:
            c0 = choices[0]
            if not finish_reason:
                finish_reason = getattr(c0, "finish_reason", "")
            msg = getattr(c0, "message", None)
            if msg:
                if not content:
                    content = getattr(msg, "content", "") or ""
                if not reasoning:
                    reasoning = getattr(msg, "reasoning_content", "") or ""
                    
    return content, reasoning, finish_reason

def get_recent_log_tail(n_lines=30):
    try:
        if os.path.exists(LLAMA_SWAP_LOG):
            with open(LLAMA_SWAP_LOG, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                return [line.strip() for line in lines[-n_lines:]]
    except Exception:
        pass
    return []

def main():
    print("=" * 70)
    print("STAGE 1: BASELINE WORKSTATION & STANDALONE ACCESS VERIFICATION")
    print("=" * 70)

    store = LLMProfileStore()
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "STAGE_1",
        "tests": {},
        "overall_status": "FAILED"
    }

    # -------------------------------------------------------------
    # Test 1: Standalone Next-Normal (Profile: Next-Normal, Target budget: 2048)
    # Tested first since Next-80B is already warm in memory!
    # -------------------------------------------------------------
    print("\n[1/4] Testing Next-Normal (Profile: Next-Normal, Target budget: 2048)...")
    pid_next_normal = None
    try:
        llm_next_normal = store.load("Next-Normal")
        t0 = time.perf_counter()

        req_count_before = len(captured_wire_requests)
        resp_next_normal = llm_next_normal.completion(
            messages=[Message(role="user", content=[TextContent(text="How many letter r are in strawberry? Explain concisely then give the final count.")])]
        )
        elapsed_next_normal = time.perf_counter() - t0
        vram_next_normal = get_vram_usage()
        pid_next_normal = get_llama_server_pid()

        captured_req = captured_wire_requests[-1] if len(captured_wire_requests) > req_count_before else None
        
        # Verify wire body has thinking_budget_tokens == 2048
        wire_body = captured_req.get("body_json", {}) if captured_req else {}
        budget_in_body = wire_body.get("thinking_budget_tokens")
        if budget_in_body is None and "chat_template_kwargs" in wire_body:
            budget_in_body = wire_body["chat_template_kwargs"].get("thinking_budget_tokens")
        if budget_in_body is None and "extra_body" in wire_body:
            budget_in_body = wire_body["extra_body"].get("thinking_budget_tokens")

        normal_content, normal_reasoning, normal_finish = extract_response_fields(resp_next_normal)

        budget_pass = (budget_in_body == 2048)
        content_pass = (len(normal_content.strip()) > 0)
        reasoning_pass = (len(normal_reasoning.strip()) > 0)
        finish_pass = (normal_finish == "stop")
        test1_pass = budget_pass and content_pass and finish_pass

        print(f"  Wire request thinking_budget_tokens: {budget_in_body} (Expected: 2048) -> {'PASS' if budget_pass else 'FAIL'}")
        print(f"  Reasoning length: {len(normal_reasoning)} chars | Content length: {len(normal_content)} chars")
        print(f"  Response preview: {normal_content[:120].strip()!r}")
        print(f"  Finish Reason: {normal_finish}")
        print(f"  Elapsed: {elapsed_next_normal:.2f}s | PID: {pid_next_normal} | VRAM: {vram_next_normal} MiB")
        print(f"  Status: {'PASS' if test1_pass else 'FAIL'}")

        results["tests"]["next_normal"] = {
            "status": "PASS" if test1_pass else "FAIL",
            "profile": "Next-Normal",
            "target_budget": 2048,
            "wire_budget_received": budget_in_body,
            "budget_pass": budget_pass,
            "reasoning_content_chars": len(normal_reasoning),
            "content": normal_content,
            "finish_reason": normal_finish,
            "elapsed_seconds": round(elapsed_next_normal, 2),
            "llama_server_pid": pid_next_normal,
            "vram_mib": vram_next_normal,
            "captured_wire_request": {
                "url": captured_req.get("url") if captured_req else None,
                "body_keys": list(wire_body.keys()) if wire_body else [],
                "thinking_budget_tokens": budget_in_body
            }
        }
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        results["tests"]["next_normal"] = {"status": "FAIL", "error": str(e)}

    # -------------------------------------------------------------
    # Test 2: Standalone Next-Deep (Profile: Next-Deep, Target budget: 4096)
    # -------------------------------------------------------------
    print("\n[2/4] Testing Next-Deep (Profile: Next-Deep, Target budget: 4096, NO RELOAD)...")
    try:
        llm_next_deep = store.load("Next-Deep")
        t0 = time.perf_counter()

        req_count_before = len(captured_wire_requests)
        resp_next_deep = llm_next_deep.completion(
            messages=[Message(role="user", content=[TextContent(text="How many letter r are in strawberry? Explain concisely then give the final count.")])]
        )
        elapsed_next_deep = time.perf_counter() - t0
        vram_next_deep = get_vram_usage()
        pid_next_deep = get_llama_server_pid()

        captured_req = captured_wire_requests[-1] if len(captured_wire_requests) > req_count_before else None

        wire_body = captured_req.get("body_json", {}) if captured_req else {}
        budget_in_body = wire_body.get("thinking_budget_tokens")
        if budget_in_body is None and "chat_template_kwargs" in wire_body:
            budget_in_body = wire_body["chat_template_kwargs"].get("thinking_budget_tokens")
        if budget_in_body is None and "extra_body" in wire_body:
            budget_in_body = wire_body["extra_body"].get("thinking_budget_tokens")

        deep_content, deep_reasoning, deep_finish = extract_response_fields(resp_next_deep)

        budget_pass = (budget_in_body == 4096)
        content_pass = (len(deep_content.strip()) > 0)
        reasoning_pass = (len(deep_reasoning.strip()) > 0)
        finish_pass = (deep_finish == "stop")
        no_reload = (pid_next_deep is not None) and (pid_next_deep == pid_next_normal)

        test2_pass = budget_pass and content_pass and finish_pass and no_reload

        print(f"  Wire request thinking_budget_tokens: {budget_in_body} (Expected: 4096) -> {'PASS' if budget_pass else 'FAIL'}")
        print(f"  PID before: {pid_next_normal} | PID after: {pid_next_deep} -> Zero reload: {no_reload}")
        print(f"  Reasoning length: {len(deep_reasoning)} chars | Content length: {len(deep_content)} chars")
        print(f"  Response preview: {deep_content[:120].strip()!r}")
        print(f"  Finish Reason: {deep_finish}")
        print(f"  Elapsed: {elapsed_next_deep:.2f}s | VRAM: {vram_next_deep} MiB")
        print(f"  Status: {'PASS' if test2_pass else 'FAIL'}")

        results["tests"]["next_deep"] = {
            "status": "PASS" if test2_pass else "FAIL",
            "profile": "Next-Deep",
            "target_budget": 4096,
            "wire_budget_received": budget_in_body,
            "budget_pass": budget_pass,
            "zero_reload": no_reload,
            "pid_before": pid_next_normal,
            "pid_after": pid_next_deep,
            "reasoning_content_chars": len(deep_reasoning),
            "content": deep_content,
            "finish_reason": deep_finish,
            "elapsed_seconds": round(elapsed_next_deep, 2),
            "llama_server_pid": pid_next_deep,
            "vram_mib": vram_next_deep,
            "captured_wire_request": {
                "url": captured_req.get("url") if captured_req else None,
                "body_keys": list(wire_body.keys()) if wire_body else [],
                "thinking_budget_tokens": budget_in_body
            }
        }
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        results["tests"]["next_deep"] = {"status": "FAIL", "error": str(e)}

    # -------------------------------------------------------------
    # Test 3: Standalone Qwen (Qwen38_Opus_96K)
    # -------------------------------------------------------------
    print("\n[3/4] Testing Standalone Qwen (Profile: Qwen38_Opus_96K)...")
    try:
        llm_qwen = store.load("Qwen38_Opus_96K")
        vram_before = get_vram_usage()
        t0 = time.perf_counter()
        
        req_count_before = len(captured_wire_requests)
        resp_qwen = llm_qwen.completion(
            messages=[Message(role="user", content=[TextContent(text="Solve: 12 * 12 = ? Return only the number.")])]
        )
        elapsed_qwen = time.perf_counter() - t0
        vram_after = get_vram_usage()
        pid_qwen = get_llama_server_pid()

        captured_req = captured_wire_requests[-1] if len(captured_wire_requests) > req_count_before else None
        qwen_content, qwen_reasoning, qwen_finish = extract_response_fields(resp_qwen)
        qwen_pass = ("144" in qwen_content) and (qwen_finish == "stop")

        print(f"  Response: {qwen_content.strip()!r}")
        print(f"  Elapsed: {elapsed_qwen:.2f}s | PID: {pid_qwen} | VRAM: {vram_after} MiB")
        print(f"  Finish Reason: {qwen_finish}")
        print(f"  Status: {'PASS' if qwen_pass else 'FAIL'}")

        results["tests"]["qwen_standalone"] = {
            "status": "PASS" if qwen_pass else "FAIL",
            "profile": "Qwen38_Opus_96K",
            "model": llm_qwen.model,
            "response": qwen_content,
            "finish_reason": qwen_finish,
            "elapsed_seconds": round(elapsed_qwen, 2),
            "llama_server_pid": pid_qwen,
            "vram_mib": vram_after
        }
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        results["tests"]["qwen_standalone"] = {"status": "FAIL", "error": str(e)}

    # -------------------------------------------------------------
    # Test 4: Standalone Ornith (Ornith-Coding)
    # -------------------------------------------------------------
    print("\n[4/4] Testing Standalone Ornith (Profile: Ornith-Coding)...")
    try:
        llm_ornith = store.load("Ornith-Coding")
        vram_before = get_vram_usage()
        t0 = time.perf_counter()

        req_count_before = len(captured_wire_requests)
        resp_ornith = llm_ornith.completion(
            messages=[Message(role="user", content=[TextContent(text="Solve: 15 * 15 = ? Return only the number.")])]
        )
        elapsed_ornith = time.perf_counter() - t0
        vram_after = get_vram_usage()
        pid_ornith = get_llama_server_pid()

        captured_req = captured_wire_requests[-1] if len(captured_wire_requests) > req_count_before else None
        ornith_content, ornith_reasoning, ornith_finish = extract_response_fields(resp_ornith)
        ornith_pass = ("225" in ornith_content) and (ornith_finish == "stop")

        print(f"  Response: {ornith_content.strip()!r}")
        print(f"  Elapsed: {elapsed_ornith:.2f}s | PID: {pid_ornith} | VRAM: {vram_after} MiB")
        print(f"  Finish Reason: {ornith_finish}")
        print(f"  Status: {'PASS' if ornith_pass else 'FAIL'}")

        results["tests"]["ornith_standalone"] = {
            "status": "PASS" if ornith_pass else "FAIL",
            "profile": "Ornith-Coding",
            "model": llm_ornith.model,
            "response": ornith_content,
            "finish_reason": ornith_finish,
            "elapsed_seconds": round(elapsed_ornith, 2),
            "llama_server_pid": pid_ornith,
            "vram_mib": vram_after
        }
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        results["tests"]["ornith_standalone"] = {"status": "FAIL", "error": str(e)}

    # Check overall STAGE 1 status
    all_passed = (
        results["tests"].get("qwen_standalone", {}).get("status") == "PASS" and
        results["tests"].get("ornith_standalone", {}).get("status") == "PASS" and
        results["tests"].get("next_normal", {}).get("status") == "PASS" and
        results["tests"].get("next_deep", {}).get("status") == "PASS"
    )

    results["overall_status"] = "PASS" if all_passed else "FAIL"
    results["recent_llama_swap_logs"] = get_recent_log_tail(25)

    print("\n" + "=" * 70)
    print(f"STAGE 1 OVERALL OUTCOME: {results['overall_status']}")
    print("=" * 70)

    # Persist evidence
    evidence_json = json.dumps(results, indent=2, ensure_ascii=False)
    with open(EVIDENCE_FILE_K, "w", encoding="utf-8") as f:
        f.write(evidence_json)
    with open(EVIDENCE_FILE_BRAIN, "w", encoding="utf-8") as f:
        f.write(evidence_json)

    print(f"Evidence saved to: {EVIDENCE_FILE_K}")
    print(f"Evidence mirrored to: {EVIDENCE_FILE_BRAIN}")

    if not all_passed:
        sys.exit(1)

if __name__ == "__main__":
    main()
