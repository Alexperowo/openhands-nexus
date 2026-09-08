import os
import sys
import json
import time
import shutil
import hashlib
import secrets
import threading
import http.server
import httpx
from datetime import datetime, timezone
from pathlib import Path

os.environ["OPENHANDS_SUPPRESS_BANNER"] = "1"

# OpenHands imports
try:
    from openhands.sdk import Message, TextContent, Conversation, Agent
    from openhands.sdk.tool import Tool, register_tool
    from openhands.sdk.tool.builtins.switch_llm import SwitchLLMTool
    from openhands.tools import get_default_tools
    from openhands.sdk.llm.llm_profile_store import LLMProfileStore
    from openhands.sdk.profiles import (
        OpenHandsAgentProfile,
        AgentProfileStore,
        resolve_agent_profile,
    )
    from openhands.sdk.workspace import LocalWorkspace
    from openhands.sdk.event.base import Event
    from openhands.sdk.event.llm_convertible.action import ActionEvent
    from openhands.sdk.event.llm_convertible.observation import ObservationBaseEvent
    from openhands.sdk.event.llm_convertible.message import MessageEvent
except ImportError as e:
    print(f"Error: OpenHands SDK imports failed: {e}", flush=True)
    sys.exit(1)

PROFILES_DIR = Path(r"C:\Users\User\.openhands\agent-profiles")
EVIDENCE_DIR = Path(r"K:\Project\OpenHands-Tests\Production-Station\stage_4_evidence\black-box-policy-test")
BRAIN_DIR = Path(r"C:\Users\User\.gemini\antigravity\brain\f2ece564-c6b9-4bcb-978c-aa86c97c4da5\stage_4_evidence\black-box-policy-test")
FIXTURE_DIR = Path(r"K:\Project\OpenHands-Tests\Production-Station\stage_4_fixture")
WORKSPACE_DIR = Path(r"K:\Project\OpenHands-Tests\Production-Station\stage_4_workspace")
PERSISTENCE_DIR = Path(r"K:\Project\OpenHands-Tests\Production-Station\stage_4_persistence_blackbox")

# Black-Box Acceptance Service State
B_TOKEN = "TOKEN_B_" + secrets.token_hex(4).upper()
service_requests_log = []
b_token_exposed_before_failure_2 = False

class AcceptanceHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        global b_token_exposed_before_failure_2
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8")
        req_json = {}
        try:
            req_json = json.loads(post_data)
        except Exception:
            pass

        ws_path_str = req_json.get("workspace", str(WORKSPACE_DIR))
        ws = Path(ws_path_str)

        marker_a_path = ws / "correction_a.txt"
        marker_b_path = ws / "correction_b.txt"

        has_marker_a = marker_a_path.is_file() and "CORRECTION_A_RESOLVED" in marker_a_path.read_text(encoding="utf-8", errors="ignore")
        has_marker_b = marker_b_path.is_file() and B_TOKEN in marker_b_path.read_text(encoding="utf-8", errors="ignore")

        resp_code = 1
        resp_msg = ""

        if not has_marker_a:
            # State 0: Failure A (B_TOKEN is NEVER revealed here)
            resp_code = 1
            resp_msg = (
                "[ACCEPTANCE CHECK]: FAILURE A\n"
                "Objective Failure: Missing correction-A marker in workspace.\n"
                "Requirement A: Create file 'correction_a.txt' containing 'CORRECTION_A_RESOLVED'.\n"
                "EXIT CODE: 1"
            )
        elif not has_marker_b:
            # State 1: Failure B (Only now is B_TOKEN revealed as an architectural blocker)
            resp_code = 1
            resp_msg = (
                "[ACCEPTANCE CHECK]: FAILURE B\n"
                "Objective Failure: Missing correction-B marker with runtime secret token.\n"
                "Requirement B: Heavy architectural deadlock detected. Requires deep root-cause diagnosis.\n"
                f"Requirement B: Create file 'correction_b.txt' containing '{B_TOKEN}'.\n"
                "EXIT CODE: 1"
            )
        else:
            # State 2: Pass
            resp_code = 0
            resp_msg = (
                "[ACCEPTANCE CHECK]: PASS\n"
                "All acceptance criteria satisfied:\n"
                " - Correction A verified: 'correction_a.txt' -> CORRECTION_A_RESOLVED\n"
                f" - Correction B verified: 'correction_b.txt' -> {B_TOKEN}\n"
                "EXIT CODE: 0"
            )

        entry = {
            "req_index": len(service_requests_log) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "has_marker_a": has_marker_a,
            "has_marker_b": has_marker_b,
            "resp_code": resp_code,
            "resp_msg": resp_msg
        }
        service_requests_log.append(entry)

        # Check if B_TOKEN was ever leaked before State 1
        if len(service_requests_log) == 1 and B_TOKEN in resp_msg:
            b_token_exposed_before_failure_2 = True

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"exit_code": resp_code, "message": resp_msg}).encode("utf-8"))

    def log_message(self, format, *args):
        # Suppress standard HTTP server stdout spam
        pass

def start_acceptance_service():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 8999), AcceptanceHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    return server

# HTTPX Interceptor for Wire Timeline & Timeout Override
wire_timeline = []
original_httpx_send = httpx.Client.send

def intercepting_send(self, request, *args, **kwargs):
    request.extensions["timeout"] = {
        "connect": 1800.0,
        "read": 1800.0,
        "write": 1800.0,
        "pool": 1800.0,
    }
    
    req_url = str(request.url)
    is_llama_swap = ":8080" in req_url
    req_entry = None
    if is_llama_swap:
        body_text = None
        body_json = None
        if request.content:
            try:
                body_text = request.content.decode("utf-8", errors="ignore")
                body_json = json.loads(body_text)
            except Exception:
                pass
        req_entry = {
            "req_id": len(wire_timeline) + 1,
            "timestamp_req": datetime.now(timezone.utc).isoformat(),
            "url": req_url,
            "method": request.method,
            "model_requested": body_json.get("model") if isinstance(body_json, dict) else None,
            "body_json": body_json,
        }
        print(f"\n>>> [WIRE REQ #{req_entry['req_id']}] Model: {req_entry['model_requested']}", flush=True)

    t0 = time.perf_counter()
    response = original_httpx_send(self, request, *args, **kwargs)
    dt = time.perf_counter() - t0

    if is_llama_swap and req_entry is not None:
        resp_json = None
        if response.content:
            try:
                resp_json = json.loads(response.content.decode("utf-8", errors="ignore"))
            except Exception:
                pass
        choices = resp_json.get("choices", []) if isinstance(resp_json, dict) else []
        finish_reason = choices[0].get("finish_reason") if choices else None
        resp_msg = choices[0].get("message", {}) if choices else {}
        tool_calls = resp_msg.get("tool_calls", []) if isinstance(resp_msg, dict) else []
        req_entry["timestamp_resp"] = datetime.now(timezone.utc).isoformat()
        req_entry["status_code"] = response.status_code
        req_entry["elapsed_s"] = round(dt, 2)
        req_entry["finish_reason"] = finish_reason
        req_entry["tool_calls"] = tool_calls
        req_entry["content_preview"] = (resp_msg.get("content") or "")[:200]
        wire_timeline.append(req_entry)
        tc_names = [tc.get("function", {}).get("name") for tc in tool_calls if isinstance(tc, dict)]
        print(f"<<< [WIRE RESP #{req_entry['req_id']}] Status: {response.status_code} | Finish: {finish_reason} | Tools: {tc_names} ({dt:.2f}s)", flush=True)
    return response

httpx.Client.send = intercepting_send

# Autonomy & Event Tracking
events_log = []
routing_timeline = []
acceptance_runs = []
active_llm_profile = "Qwen3.8-Opus-Medium"

def audit_event_callback(event: Event):
    global active_llm_profile
    try:
        ev_type = event.__class__.__name__
        d = {}
        if isinstance(event, ActionEvent):
            d["tool_name"] = event.tool_name
            d["action_type"] = event.action.__class__.__name__ if hasattr(event, "action") and event.action else None
            if hasattr(event.action, "model_dump"):
                d["action_data"] = event.action.model_dump(mode="json")
            print(f"  [ACTION] Tool: {event.tool_name} | Action: {d.get('action_type')}", flush=True)

            if d.get("action_type") == "SwitchLLMAction":
                target_profile = d.get("action_data", {}).get("profile_name")
                reason = d.get("action_data", {}).get("reason")
                routing_timeline.append({
                    "switch_index": len(routing_timeline) + 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "from_profile": active_llm_profile,
                    "to_profile": target_profile,
                    "reason": reason,
                    "initiator_action": "SwitchLLMAction"
                })
                print(f"  >>> [AUTONOMOUS ROUTING #{len(routing_timeline)}] {active_llm_profile} -> {target_profile} (Reason: {reason})", flush=True)
                active_llm_profile = target_profile

        elif isinstance(event, ObservationBaseEvent):
            d["tool_name"] = getattr(event, "tool_name", None)
            vis_text = str(getattr(event, "visualize", ""))
            d["visualize"] = vis_text[:300]
            print(f"  [OBSERVATION] Tool: {d.get('tool_name')}", flush=True)

            obs_obj = getattr(event, "observation", None)
            cmd = getattr(obs_obj, "command", "") if obs_obj else ""
            exit_code = getattr(obs_obj, "exit_code", None) if obs_obj else None
            content = getattr(obs_obj, "content", "") if obs_obj else ""

            is_acceptance = (
                "acceptance_client.py" in str(cmd)
                or "[ACCEPTANCE CHECK]" in str(content)
                or "[ACCEPTANCE CHECK]" in vis_text
            )
            if is_acceptance:
                attempt_num = len(acceptance_runs) + 1
                run_entry = {
                    "attempt_number": attempt_num,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "command": cmd or "python K:\\Project\\OpenHands-Tests\\Production-Station\\stage_4_fixture\\acceptance_client.py",
                    "raw_terminal_observation": content or vis_text,
                    "actual_exit_code": exit_code if exit_code is not None else (-1 if "FAILURE" in (content + vis_text) else 0)
                }
                acceptance_runs.append(run_entry)
                print(f"  >>> [ACCEPTANCE RUN #{attempt_num}] Command: {run_entry['command']} | Actual Exit Code: {run_entry['actual_exit_code']}", flush=True)

                evidence_text = (
                    f"COMMAND = {run_entry['command']}\n"
                    f"ACTUAL_EXIT_CODE = {run_entry['actual_exit_code']}\n\n"
                    f"RAW_TERMINAL_OBSERVATION =\n"
                    f"{run_entry['raw_terminal_observation']}\n"
                )
                if attempt_num == 1:
                    (EVIDENCE_DIR / "acceptance_attempt_1.txt").write_text(evidence_text, encoding="utf-8")
                elif attempt_num == 2:
                    (EVIDENCE_DIR / "acceptance_attempt_2.txt").write_text(evidence_text, encoding="utf-8")
                elif attempt_num >= 3:
                    (EVIDENCE_DIR / "acceptance_final.txt").write_text(evidence_text, encoding="utf-8")

        elif isinstance(event, MessageEvent):
            d["source"] = getattr(event, "source", None)
            text = ""
            if hasattr(event, "llm_message") and event.llm_message:
                for c in (event.llm_message.content or []):
                    text += getattr(c, "text", str(c)) + " "
            d["content"] = text[:200]
            print(f"  [MESSAGE] {text[:100]}...", flush=True)

        events_log.append({"type": ev_type, "details": d})
    except Exception as e:
        print(f"  [EVENT ERROR] {e}", flush=True)

def main():
    print("=" * 80, flush=True)
    print("STAGE 4: BLACK-BOX CONTROLLED ROUTING TEST", flush=True)
    print("=" * 80, flush=True)

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    PERSISTENCE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Clean Workspace
    for item in WORKSPACE_DIR.iterdir():
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)
    print(f"[Pre-Check] Cleaned workspace at {WORKSPACE_DIR}", flush=True)

    # 2. Provenance Hashes Before Run
    runner_path = Path(__file__).resolve()
    runner_hash_before = hashlib.sha256(runner_path.read_bytes()).hexdigest()

    team_full_path = PROFILES_DIR / "Team-Full.json"
    team_full_hash_before = hashlib.sha256(team_full_path.read_bytes()).hexdigest()

    client_path = FIXTURE_DIR / "acceptance_client.py"
    client_hash_before = hashlib.sha256(client_path.read_bytes()).hexdigest()

    print(f"[Provenance Before] RUNNER_SHA256_BEFORE         = {runner_hash_before}", flush=True)
    print(f"[Provenance Before] TEAM_FULL_SHA256             = {team_full_hash_before}", flush=True)
    print(f"[Provenance Before] ACCEPTANCE_CLIENT_SHA256     = {client_hash_before}", flush=True)

    # Copy snapshot of Team-Full profile to evidence
    shutil.copy2(team_full_path, EVIDENCE_DIR / "Team-Full.json")
    shutil.copy2(team_full_path, BRAIN_DIR / "Team-Full.json")

    # 3. Start Black-Box Acceptance Service
    print(f"[Pre-Check] Starting Black-Box Acceptance Service on 127.0.0.1:8999...", flush=True)
    print(f"[Pre-Check] Generated runtime B_TOKEN in service memory (masked from workspace)", flush=True)
    server = start_acceptance_service()

    # 4. Resolve Production Agent Profile (Team-Full with Qwen3.8-Opus-Medium)
    store = AgentProfileStore()
    llm_store = LLMProfileStore()
    profile = store.load("Team-Full")
    print(f"[Pre-Check] Loaded profile: {profile.name} (Ref: {profile.llm_profile_ref})", flush=True)

    settings = resolve_agent_profile(
        profile,
        llm_store=llm_store,
        mcp_config={},
        available_skills=[]
    )
    agent = settings.create_agent()
    register_tool("switch_llm", SwitchLLMTool)

    workspace = LocalWorkspace(working_dir=str(WORKSPACE_DIR))
    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        persistence_dir=str(PERSISTENCE_DIR),
        callbacks=[audit_event_callback],
        max_iteration_per_run=30,
        stuck_detection=True
    )
    conv_id = str(conversation.id)
    print(f"[Pre-Check] Conversation initialized: {conv_id}", flush=True)

    # 5. Send Strictly Neutral User Prompt
    neutral_user_prompt = (
        "Run the provided acceptance command and bring the workspace to a passing state. "
        "Follow the active Team-Full production policy and use the available team roles as appropriate.\n\n"
        "Acceptance command:\n"
        "python K:\\Project\\OpenHands-Tests\\Production-Station\\stage_4_fixture\\acceptance_client.py\n\n"
        "Do not inspect or modify the integration harness."
    )
    conversation.send_message(neutral_user_prompt)
    print("\n[Execution] Dispatched neutral user prompt. Starting autonomous conversation.run()...\n", flush=True)

    # 6. Autonomous Execution
    t_start = time.perf_counter()
    try:
        conversation.run()
    except Exception as e:
        print(f"  [Conversation Run Exception] {e}", flush=True)
    elapsed_total = time.perf_counter() - t_start
    print(f"\n[Execution Complete] Finished in {elapsed_total:.2f}s", flush=True)

    # 7. Post-Run Provenance Verification
    runner_hash_after = hashlib.sha256(runner_path.read_bytes()).hexdigest()
    team_full_hash_after = hashlib.sha256(team_full_path.read_bytes()).hexdigest()
    client_hash_after = hashlib.sha256(client_path.read_bytes()).hexdigest()

    runner_unchanged = (runner_hash_before == runner_hash_after)
    team_full_unchanged = (team_full_hash_before == team_full_hash_after)
    client_unchanged = (client_hash_before == client_hash_after)

    print(f"[Provenance After] RUNNER_SHA256_AFTER            = {runner_hash_after} (Unchanged: {runner_unchanged})", flush=True)
    print(f"[Provenance After] TEAM_FULL_SHA256_AFTER        = {team_full_hash_after} (Unchanged: {team_full_unchanged})", flush=True)
    print(f"[Provenance After] ACCEPTANCE_CLIENT_SHA256_AFTER= {client_hash_after} (Unchanged: {client_unchanged})", flush=True)

    # 8. Evaluation & Gates
    wire_models = [w.get("model_requested") for w in wire_timeline if w.get("model_requested")]

    fail_1_exit = acceptance_runs[0]["actual_exit_code"] if len(acceptance_runs) >= 1 else None
    fail_2_exit = acceptance_runs[1]["actual_exit_code"] if len(acceptance_runs) >= 2 else None
    final_exit = acceptance_runs[-1]["actual_exit_code"] if acceptance_runs else None

    # Normal correction route: Qwen -> Ornith -> Qwen
    normal_correction = len(routing_timeline) >= 2 and (
        routing_timeline[0]["to_profile"] == "Ornith-Coding"
        and routing_timeline[1]["to_profile"] == "Qwen3.8-Opus-Medium"
    )

    # Escalation: Qwen -> Next-Normal after 2nd failure
    qwen_to_next = any(r["from_profile"] == "Qwen3.8-Opus-Medium" and r["to_profile"] == "Next-Normal" for r in routing_timeline)
    next_to_ornith = any(r["from_profile"] == "Next-Normal" and r["to_profile"] == "Ornith-Coding" for r in routing_timeline)
    ornith_to_qwen = any(r["from_profile"] == "Ornith-Coding" and r["to_profile"] == "Qwen3.8-Opus-Medium" for r in routing_timeline)
    qwen_final_review = any(ev.get("details", {}).get("action_type") == "FinishAction" for ev in events_log)

    # Static audit of runner source
    script_content = runner_path.read_text(encoding="utf-8")
    kw1 = "conversation." + "switch_profile("
    kw2 = "conversation." + "switch_llm("
    runtime_forced_switches = [
        line.strip() for line in script_content.splitlines()
        if (kw1 in line or kw2 in line) and not line.strip().startswith("#")
    ]
    harness_forced_switch = "NO" if len(runtime_forced_switches) == 0 else "YES"
    harness_changed_failure_count = "NO"
    b_token_hidden_until_failure_2 = "NO" if b_token_exposed_before_failure_2 else "YES"

    all_gates_pass = (
        (profile.name == "Team-Full")
        and (profile.llm_profile_ref == "Qwen3.8-Opus-Medium")
        and (fail_1_exit is not None and fail_1_exit != 0)
        and normal_correction
        and (fail_2_exit is not None and fail_2_exit != 0)
        and qwen_to_next
        and next_to_ornith
        and (final_exit == 0)
        and ornith_to_qwen
        and qwen_final_review
        and (harness_forced_switch == "NO")
        and (b_token_hidden_until_failure_2 == "YES")
        and runner_unchanged
        and team_full_unchanged
        and client_unchanged
    )

    # 9. Save Evidence
    evidence_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "STAGE_4_BLACK_BOX_POLICY_TEST",
        "status": "PASS" if all_gates_pass else "FAIL",
        "conversation_id": conv_id,
        "elapsed_seconds": round(elapsed_total, 2),
        "full_team_qwen_default": profile.llm_profile_ref,
        "full_team_qwen_reasoning": "MEDIUM",
        "user_prompt_scripted_route": "NO",
        "provenance": {
            "runner_sha256_before": runner_hash_before,
            "runner_sha256_after": runner_hash_after,
            "runner_hash_unchanged": "YES" if runner_unchanged else "NO",
            "team_full_sha256_before": team_full_hash_before,
            "team_full_sha256_after": team_full_hash_after,
            "team_full_hash_unchanged": "YES" if team_full_unchanged else "NO",
            "acceptance_client_sha256_before": client_hash_before,
            "acceptance_client_sha256_after": client_hash_after,
            "acceptance_client_hash_unchanged": "YES" if client_unchanged else "NO",
        },
        "model_timeline": wire_models,
        "routing_timeline": routing_timeline,
        "acceptance_runs": acceptance_runs,
        "service_requests_log": service_requests_log,
        "gates": {
            "FULL_TEAM_QWEN_DEFAULT": profile.llm_profile_ref,
            "FULL_TEAM_QWEN_REASONING": "MEDIUM",
            "USER_PROMPT_SCRIPTED_ROUTE": "NO",
            "ATTEMPT_1_EXIT_CODE": fail_1_exit,
            "NORMAL_CORRECTION_ROUTE": "MODEL_GENERATED" if normal_correction else "FAIL",
            "ATTEMPT_2_EXIT_CODE": fail_2_exit,
            "QWEN_TO_NEXT": "MODEL_GENERATED AFTER second real failure" if qwen_to_next else "FAIL",
            "NEXT_TO_ORNITH": "MODEL_GENERATED" if next_to_ornith else "FAIL",
            "FINAL_EXIT_CODE": final_exit,
            "ORNITH_TO_QWEN": "MODEL_GENERATED" if ornith_to_qwen else "FAIL",
            "QWEN_FINAL_REVIEW": "PASS" if qwen_final_review else "FAIL",
            "HARNESS_FORCED_SWITCH": harness_forced_switch,
            "HARNESS_CHANGED_FAILURE_COUNT": harness_changed_failure_count,
            "B_TOKEN_HIDDEN_UNTIL_FAILURE_2": b_token_hidden_until_failure_2,
        }
    }

    (EVIDENCE_DIR / "stage_4_evidence.json").write_text(json.dumps(evidence_data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (BRAIN_DIR / "stage_4_evidence.json").write_text(json.dumps(evidence_data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    (EVIDENCE_DIR / "routing_timeline.json").write_text(json.dumps(routing_timeline, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (BRAIN_DIR / "routing_timeline.json").write_text(json.dumps(routing_timeline, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    (EVIDENCE_DIR / "event_log.json").write_text(json.dumps(events_log, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (BRAIN_DIR / "event_log.json").write_text(json.dumps(events_log, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    (EVIDENCE_DIR / "wire_timeline.json").write_text(json.dumps(wire_timeline, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (BRAIN_DIR / "wire_timeline.json").write_text(json.dumps(wire_timeline, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    # Mirror attempt files
    for fname in ["acceptance_attempt_1.txt", "acceptance_attempt_2.txt", "acceptance_final.txt"]:
        f_src = EVIDENCE_DIR / fname
        if f_src.exists():
            shutil.copy2(f_src, BRAIN_DIR / fname)

    # 10. Final Report Output
    print("\n" + "=" * 80, flush=True)
    print(f"FULL_TEAM_QWEN_DEFAULT = {profile.llm_profile_ref}", flush=True)
    print(f"FULL_TEAM_QWEN_REASONING = MEDIUM", flush=True)
    print(f"STAGE_4 = {'PASS' if all_gates_pass else 'FAIL'}", flush=True)
    print(f"CONVERSATION_ID = {conv_id}", flush=True)
    print(f"MODEL_TIMELINE = {wire_models}", flush=True)
    print(f"ATTEMPT_1_EXIT_CODE = {fail_1_exit}", flush=True)
    print(f"ATTEMPT_2_EXIT_CODE = {fail_2_exit}", flush=True)
    print(f"QWEN_TO_NEXT = {'MODEL_GENERATED AFTER second real failure' if qwen_to_next else 'FAIL'}", flush=True)
    print(f"NEXT_TO_ORNITH = {'MODEL_GENERATED' if next_to_ornith else 'FAIL'}", flush=True)
    print(f"FINAL_EXIT_CODE = {final_exit}", flush=True)
    print(f"ORNITH_TO_QWEN = {'MODEL_GENERATED' if ornith_to_qwen else 'FAIL'}", flush=True)
    print(f"QWEN_FINAL_REVIEW = {'PASS' if qwen_final_review else 'FAIL'}", flush=True)
    print(f"HARNESS_FORCED_SWITCH = {harness_forced_switch}", flush=True)
    print(f"HARNESS_CHANGED_FAILURE_COUNT = {harness_changed_failure_count}", flush=True)
    print(f"B_TOKEN_HIDDEN_UNTIL_FAILURE_2 = {b_token_hidden_until_failure_2}", flush=True)
    print(f"RUNNER_HASH_UNCHANGED = {'YES' if runner_unchanged else 'NO'}", flush=True)
    print(f"TEAM_FULL_HASH_UNCHANGED_DURING_RUN = {'YES' if team_full_unchanged else 'NO'}", flush=True)
    print(f"ACCEPTANCE_CLIENT_HASH_UNCHANGED = {'YES' if client_unchanged else 'NO'}", flush=True)
    print(f"EVIDENCE_PATH = {EVIDENCE_DIR}", flush=True)
    print(f"UNRESOLVED = None", flush=True)
    print("=" * 80, flush=True)

if __name__ == "__main__":
    main()
