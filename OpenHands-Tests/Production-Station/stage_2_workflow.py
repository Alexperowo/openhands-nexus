import os
import sys
import json
import time
import shutil
import subprocess
import httpx
from pathlib import Path
from datetime import datetime, timezone

# Ensure openhands is available
try:
    from openhands.sdk import Message, TextContent, Conversation, Agent
    from openhands.sdk.tool import Tool, register_tool
    from openhands.sdk.tool.builtins.switch_llm import SwitchLLMTool
    from openhands.tools import get_default_tools
    from openhands.sdk.llm.llm_profile_store import LLMProfileStore
    from openhands.sdk.workspace import LocalWorkspace
    from openhands.sdk.conversation.response_utils import get_agent_final_response
    from openhands.sdk.event.base import Event
    from openhands.sdk.event.llm_convertible.action import ActionEvent
    from openhands.sdk.event.llm_convertible.observation import ObservationBaseEvent
    from openhands.sdk.event.llm_convertible.message import MessageEvent
except ImportError as e:
    print(f"Error: OpenHands SDK imports failed: {e}", flush=True)
    sys.exit(1)

WORKSPACE_DIR = r"K:\Project\OpenHands-Tests\Production-Station\stage_2_workspace"
PERSISTENCE_DIR = r"K:\Project\OpenHands-Tests\Production-Station\stage_2_persistence"
EVIDENCE_DIR_K = r"K:\Project\OpenHands-Tests\Production-Station\stage_2_evidence"
EVIDENCE_DIR_BRAIN = r"C:\Users\User\.gemini\antigravity\brain\f2ece564-c6b9-4bcb-978c-aa86c97c4da5\stage_2_evidence"

# Intercept outgoing HTTP requests made by httpx (used by LiteLLM)
captured_wire_timeline = []
original_httpx_send = httpx.Client.send

def intercepting_send(self, request, *args, **kwargs):
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
        
        model_name = body_json.get("model") if isinstance(body_json, dict) else None
        tools_count = len(body_json.get("tools", [])) if isinstance(body_json, dict) and "tools" in body_json else 0
        messages_count = len(body_json.get("messages", [])) if isinstance(body_json, dict) and "messages" in body_json else 0
        
        req_entry = {
            "req_id": len(captured_wire_timeline) + 1,
            "timestamp_req": datetime.now(timezone.utc).isoformat(),
            "url": req_url,
            "method": request.method,
            "model_requested": model_name,
            "messages_count": messages_count,
            "tools_count": tools_count,
            "body_json": body_json
        }
        print(f"\n>>> [WIRE REQUEST #{req_entry['req_id']}] {request.method} {req_url} | Model: {model_name} | Msgs: {messages_count}", flush=True)
    
    t_start = time.perf_counter()
    response = original_httpx_send(self, request, *args, **kwargs)
    elapsed = time.perf_counter() - t_start
    
    if is_llama_swap and req_entry is not None:
        resp_text = None
        resp_json = None
        if response.content:
            try:
                resp_text = response.content.decode("utf-8", errors="ignore")
                resp_json = json.loads(resp_text)
            except Exception:
                pass
        
        choices = resp_json.get("choices", []) if isinstance(resp_json, dict) else []
        finish_reason = choices[0].get("finish_reason") if choices else None
        resp_msg = choices[0].get("message", {}) if choices else {}
        tool_calls = resp_msg.get("tool_calls", []) if isinstance(resp_msg, dict) else []
        usage = resp_json.get("usage", {}) if isinstance(resp_json, dict) else {}
        
        tool_call_names = [tc.get("function", {}).get("name") for tc in tool_calls if isinstance(tc, dict)]
        
        req_entry["timestamp_resp"] = datetime.now(timezone.utc).isoformat()
        req_entry["status_code"] = response.status_code
        req_entry["elapsed_s"] = round(elapsed, 2)
        req_entry["finish_reason"] = finish_reason
        req_entry["tool_calls"] = tool_calls
        req_entry["tool_call_names"] = tool_call_names
        req_entry["usage"] = usage
        req_entry["content_preview"] = (resp_msg.get("content") or "")[:200]
        req_entry["reasoning_preview"] = (resp_msg.get("reasoning_content") or "")[:200]
        req_entry["response_json"] = resp_json
        
        captured_wire_timeline.append(req_entry)
        print(f"<<< [WIRE RESPONSE #{req_entry['req_id']}] Status: {response.status_code} | Duration: {elapsed:.2f}s | Finish: {finish_reason} | Tools: {tool_call_names}", flush=True)
    
    return response

httpx.Client.send = intercepting_send

# Event collector
collected_events = []

def event_callback(event: Event):
    try:
        ev_type = event.__class__.__name__
        ts = datetime.now(timezone.utc).isoformat()
        
        details = {}
        if isinstance(event, ActionEvent):
            details["tool_name"] = event.tool_name
            details["thought"] = (event.thought or "")[:200]
            details["reasoning_content"] = (event.reasoning_content or "")[:200]
            if hasattr(event, "action") and event.action is not None:
                action_obj = event.action
                details["action_type"] = action_obj.__class__.__name__
                if hasattr(action_obj, "model_dump"):
                    details["action_data"] = action_obj.model_dump(mode="json")
                else:
                    details["action_data"] = str(action_obj)
            print(f"  [EVENT: Action] Tool: {event.tool_name} | Action: {details.get('action_type')} | Data: {details.get('action_data')}", flush=True)
            
        elif isinstance(event, ObservationBaseEvent):
            details["tool_name"] = getattr(event, "tool_name", None)
            if hasattr(event, "visualize"):
                details["visualize"] = str(event.visualize)[:300]
            if hasattr(event, "model_dump"):
                details["obs_data"] = event.model_dump(mode="json")
            print(f"  [EVENT: Observation] Tool: {details.get('tool_name')} | Visual: {details.get('visualize')}", flush=True)
            
        elif isinstance(event, MessageEvent):
            details["source"] = getattr(event, "source", None)
            msg_text = ""
            if hasattr(event, "llm_message") and event.llm_message:
                for c in (event.llm_message.content or []):
                    if hasattr(c, "text"):
                        msg_text += c.text + " "
            details["content"] = msg_text[:300]
            print(f"  [EVENT: Message] Source: {details.get('source')} | Content: {details.get('content')}", flush=True)
        else:
            print(f"  [EVENT: Other] Type: {ev_type}", flush=True)
            
        collected_events.append({
            "timestamp": ts,
            "type": ev_type,
            "details": details
        })
    except Exception as e:
        print(f"  [EVENT Callback Error] {e}", flush=True)

def main():
    print("=" * 80, flush=True)
    print("STAGE 2: PRODUCTION OPENHANDS WORKFLOW VALIDATION", flush=True)
    print("Architecture: Qwen (Architect) -> SwitchLLM -> Ornith (Coder/Test) -> SwitchLLM -> Qwen (Reviewer)", flush=True)
    print("=" * 80, flush=True)

    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    os.makedirs(PERSISTENCE_DIR, exist_ok=True)
    os.makedirs(EVIDENCE_DIR_K, exist_ok=True)
    os.makedirs(EVIDENCE_DIR_BRAIN, exist_ok=True)

    # 1. Register tools
    print("\n[Step 1] Registering built-in switch_llm tool...", flush=True)
    register_tool("switch_llm", SwitchLLMTool)
    tools = [*get_default_tools(enable_browser=False), Tool(name="switch_llm")]
    print(f"  Configured tools: {[t.name for t in tools]}", flush=True)

    # 2. Load starting profile: Qwen38_Opus_96K
    print("\n[Step 2] Loading initial profile 'Qwen38_Opus_96K'...", flush=True)
    store = LLMProfileStore()
    llm = store.load("Qwen38_Opus_96K")
    print(f"  Loaded model: {llm.model}", flush=True)
    print(f"  Base URL: {llm.base_url}", flush=True)

    # 3. Create Agent and LocalConversation
    print("\n[Step 3] Initializing Agent and LocalConversation...", flush=True)
    agent = Agent(llm=llm, tools=tools)
    workspace = LocalWorkspace(working_dir=WORKSPACE_DIR)
    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        persistence_dir=PERSISTENCE_DIR,
        callbacks=[event_callback],
        max_iteration_per_run=35,
        stuck_detection=True
    )
    
    session_id = str(conversation.id)
    print(f"  Session ID: {session_id}", flush=True)
    print(f"  Workspace: {WORKSPACE_DIR}", flush=True)

    # 4. Construct Prompt
    prompt = (
        "Task: Implement and verify a Python URL normalization module `url_normalizer.py` with pytest suite `test_url_normalizer.py`.\n\n"
        "Requirements for `url_normalizer.py`:\n"
        "1. `normalize_url(url: str) -> str`:\n"
        "   - Lowercase the scheme and host (e.g. 'HTTP://Example.COM/path' -> 'http://example.com/path').\n"
        "   - Remove default ports: port 80 for 'http', port 443 for 'https' (e.g. 'http://example.com:80/path' -> 'http://example.com/path', 'https://example.com:443/path' -> 'https://example.com/path'). Non-default ports must be preserved.\n"
        "   - Alphabetically sort query parameters by key (e.g. '?b=2&a=1' -> '?a=1&b=2').\n"
        "   - Remove trailing slash from the path unless the path is just '/' (e.g. '/path/to/' -> '/path/to', but '/' remains '/').\n"
        "   - Drop empty query parameters (e.g. '?a=1&b=&c=3' -> '?a=1&c=3', or '?empty=' dropped).\n"
        "2. `parse_url(url: str) -> dict`:\n"
        "   - Return a dictionary with keys: 'scheme', 'host', 'port' (int or None), 'path', 'query_params' (dict mapping param name to value).\n\n"
        "Requirements for `test_url_normalizer.py`:\n"
        "   - At least 5 pytest test cases verifying normalization, default port removal, query parameter sorting and empty param dropping, trailing slash handling, and URL parsing.\n"
        "   - Run tests via the terminal tool: `pytest test_url_normalizer.py`.\n"
        "   - Ensure all tests pass with exit code 0.\n\n"
        "MANDATORY ROLE & WORKFLOW PROTOCOL:\n"
        "You are operating under a multi-model specialization protocol using the `switch_llm` tool.\n\n"
        "PHASE 1 (CURRENT ROLE: Qwen38_Opus_96K - ARCHITECT & PLANNER):\n"
        "- You are Qwen, the Architect.\n"
        "- Analyze the requirements and establish a concrete, concise implementation and test plan.\n"
        "- CRITICAL: DO NOT write code to disk or edit files in Phase 1.\n"
        "- Immediately after formulating your plan, call the tool `switch_llm` with:\n"
        "  profile_name: 'Ornith-Coding'\n"
        "  reason: 'Handing off to Ornith for implementation and pytest verification.'\n\n"
        "PHASE 2 (ROLE: Ornith-Coding - CODER & TEST ENGINEER):\n"
        "- You are Ornith, the Coder and Test Engineer.\n"
        "- When you receive control after the switch, inspect Qwen's plan.\n"
        "- Use `file_editor` or `terminal` to implement `url_normalizer.py` and `test_url_normalizer.py`.\n"
        "- Execute `pytest test_url_normalizer.py` using the `terminal` tool.\n"
        "- If any test fails, fix the code or tests until all pass.\n"
        "- CRITICAL: DO NOT call the `finish` tool.\n"
        "- Once all pytest tests pass with exit code 0, call the tool `switch_llm` with:\n"
        "  profile_name: 'Qwen38_Opus_96K'\n"
        "  reason: 'All pytest tests passed with exit code 0; handing off to Qwen for architectural review.'\n\n"
        "PHASE 3 (ROLE: Qwen38_Opus_96K - REVIEWER & LEAD):\n"
        "- You are Qwen, returned for final review.\n"
        "- Inspect the git status / git diff and review the test execution output.\n"
        "- Provide your final assessment of the implementation and test coverage.\n"
        "- Call the `finish` tool with a summary of the completed task."
    )

    print("\n[Step 4] Submitting task prompt to conversation...", flush=True)
    conversation.send_message(prompt)

    # 5. Execute Conversation
    print("\n[Step 5] Running conversation.run() via authentic OpenHands engine...", flush=True)
    t_start = time.perf_counter()
    try:
        conversation.run()
    except Exception as e:
        print(f"\n[Warning / Exception during run] {e}", flush=True)
    
    total_time = time.perf_counter() - t_start
    print(f"\n[Step 5 Finished] Execution time: {total_time:.2f}s", flush=True)

    # 6. Post-Run Analysis & Gate Checking
    print("\n" + "=" * 80, flush=True)
    print("STAGE 2 GATES EVALUATION", flush=True)
    print("=" * 80, flush=True)

    # Inspect wire models timeline
    model_timeline = [e.get("model_requested") for e in captured_wire_timeline if e.get("model_requested")]
    print(f"Model Wire Requests Sequence: {model_timeline}", flush=True)

    # Gate 1: QWEN_PLAN
    # Check if Qwen produced a plan before switching
    qwen_plan_found = False
    for ev in collected_events:
        if ev.get("type") == "ActionEvent":
            d = ev.get("details", {})
            if d.get("action_type") == "SwitchLLMAction":
                # Check thought or reasoning content
                reasoning = d.get("reasoning_content") or d.get("thought") or ""
                if len(reasoning) > 50 or "plan" in reasoning.lower() or "architect" in reasoning.lower() or "normalizer" in reasoning.lower():
                    qwen_plan_found = True
                    break
    # Also check wire responses for Qwen
    if not qwen_plan_found:
        for req in captured_wire_timeline:
            if req.get("model_requested") in ["openai/qwen", "qwen"]:
                content = req.get("content_preview") or ""
                reasoning = req.get("reasoning_preview") or ""
                if len(reasoning) > 50 or len(content) > 50:
                    qwen_plan_found = True
                    break
    gate_1 = "PASS" if qwen_plan_found else "FAIL"
    print(f"GATE 1: QWEN_PLAN = {gate_1}", flush=True)

    # Gate 2: QWEN_TO_ORNITH_SWITCH
    qwen_to_ornith_switch = False
    for ev in collected_events:
        if ev.get("type") == "ActionEvent":
            d = ev.get("details", {})
            if d.get("action_type") == "SwitchLLMAction":
                action_data = d.get("action_data", {})
                if isinstance(action_data, dict) and action_data.get("profile_name") == "Ornith-Coding":
                    qwen_to_ornith_switch = True
                    break
    gate_2 = "PASS" if qwen_to_ornith_switch else "FAIL"
    print(f"GATE 2: QWEN_TO_ORNITH_SWITCH = {gate_2}", flush=True)

    # Gate 3: ORNITH_REAL_TOOL_EXECUTION
    ornith_tool_exec = False
    tools_executed = set()
    for ev in collected_events:
        if ev.get("type") == "ActionEvent":
            d = ev.get("details", {})
            tool = d.get("tool_name")
            if tool in ["file_editor", "terminal"]:
                tools_executed.add(tool)
                ornith_tool_exec = True
    gate_3 = "PASS" if ornith_tool_exec else "FAIL"
    print(f"GATE 3: ORNITH_REAL_TOOL_EXECUTION = {gate_3} (Tools used: {list(tools_executed)})", flush=True)

    # Gate 4: ORNITH_CODE_CHANGE
    code_path = os.path.join(WORKSPACE_DIR, "url_normalizer.py")
    test_path = os.path.join(WORKSPACE_DIR, "test_url_normalizer.py")
    code_exists = os.path.isfile(code_path) and os.path.getsize(code_path) > 50
    test_exists = os.path.isfile(test_path) and os.path.getsize(test_path) > 50
    gate_4 = "PASS" if (code_exists and test_exists) else "FAIL"
    print(f"GATE 4: ORNITH_CODE_CHANGE = {gate_4} (url_normalizer.py: {code_exists}, test_url_normalizer.py: {test_exists})", flush=True)

    # Gate 5: REAL_TEST_EXECUTION
    # Check if pytest was run via terminal tool
    pytest_command_run = None
    pytest_output_captured = ""
    for ev in collected_events:
        if ev.get("type") == "ActionEvent":
            d = ev.get("details", {})
            if d.get("tool_name") == "terminal":
                action_data = d.get("action_data", {})
                cmd = action_data.get("command") if isinstance(action_data, dict) else str(action_data)
                if cmd and "pytest" in cmd:
                    pytest_command_run = cmd
        elif ev.get("type") == "ObservationBaseEvent":
            d = ev.get("details", {})
            if d.get("tool_name") == "terminal":
                obs_data = d.get("obs_data", {})
                content = str(obs_data)
                if "passed" in content or "test session starts" in content:
                    pytest_output_captured = content
    gate_5 = "PASS" if pytest_command_run is not None else "FAIL"
    print(f"GATE 5: REAL_TEST_EXECUTION = {gate_5} (Command: {pytest_command_run})", flush=True)

    # Gate 6: TEST_EXIT_CODE
    # Run pytest directly to independently verify exit code 0
    direct_pytest = subprocess.run(
        ["pytest", "test_url_normalizer.py"],
        cwd=WORKSPACE_DIR,
        capture_output=True,
        text=True
    )
    test_exit_code = direct_pytest.returncode
    gate_6 = "PASS" if test_exit_code == 0 else "FAIL"
    print(f"GATE 6: TEST_EXIT_CODE = {gate_6} (Exit code: {test_exit_code})", flush=True)

    # Gate 7: ORNITH_TO_QWEN_AUTONOMOUS_SWITCH
    ornith_to_qwen_switch = False
    switch_count = 0
    for ev in collected_events:
        if ev.get("type") == "ActionEvent":
            d = ev.get("details", {})
            if d.get("action_type") == "SwitchLLMAction":
                switch_count += 1
                action_data = d.get("action_data", {})
                if isinstance(action_data, dict) and action_data.get("profile_name") == "Qwen38_Opus_96K" and switch_count >= 2:
                    ornith_to_qwen_switch = True
    gate_7 = "PASS" if ornith_to_qwen_switch else "FAIL"
    print(f"GATE 7: ORNITH_TO_QWEN_AUTONOMOUS_SWITCH = {gate_7}", flush=True)

    # Gate 8: QWEN_EVIDENCE_REVIEW
    qwen_reviewed = False
    final_response = ""
    try:
        final_response = get_agent_final_response(conversation.state.events) or ""
    except Exception:
        pass
    
    # Check if finish was called
    finish_called = False
    for ev in collected_events:
        if ev.get("type") == "ActionEvent":
            d = ev.get("details", {})
            if d.get("tool_name") == "finish" or d.get("action_type") == "FinishAction":
                finish_called = True
                action_data = d.get("action_data", {})
                msg = action_data.get("message") if isinstance(action_data, dict) else str(action_data)
                if msg:
                    final_response = msg
    
    if finish_called and (len(final_response) > 50 or "review" in final_response.lower() or "test" in final_response.lower() or "pass" in final_response.lower()):
        qwen_reviewed = True
    
    gate_8 = "PASS" if qwen_reviewed else "FAIL"
    print(f"GATE 8: QWEN_EVIDENCE_REVIEW = {gate_8}", flush=True)

    all_gates_pass = all(g == "PASS" for g in [gate_1, gate_2, gate_3, gate_4, gate_5, gate_6, gate_7, gate_8])
    overall_status = "PASS" if all_gates_pass else "FAIL"

    # Git diff and log
    git_diff_out = subprocess.run(["git", "diff", "HEAD"], cwd=WORKSPACE_DIR, capture_output=True, text=True).stdout
    git_status_out = subprocess.run(["git", "status"], cwd=WORKSPACE_DIR, capture_output=True, text=True).stdout
    git_log_out = subprocess.run(["git", "log", "-n", "5"], cwd=WORKSPACE_DIR, capture_output=True, text=True).stdout

    # 7. Persist Evidence Dossier
    print("\n[Step 7] Persisting Evidence Dossier...", flush=True)
    
    # Save copies of code and test files
    if os.path.exists(code_path):
        shutil.copy2(code_path, os.path.join(EVIDENCE_DIR_K, "url_normalizer.py"))
        shutil.copy2(code_path, os.path.join(EVIDENCE_DIR_BRAIN, "url_normalizer.py"))
    if os.path.exists(test_path):
        shutil.copy2(test_path, os.path.join(EVIDENCE_DIR_K, "test_url_normalizer.py"))
        shutil.copy2(test_path, os.path.join(EVIDENCE_DIR_BRAIN, "test_url_normalizer.py"))
    
    with open(os.path.join(EVIDENCE_DIR_K, "git_diff.txt"), "w", encoding="utf-8") as f:
        f.write(git_diff_out)
    with open(os.path.join(EVIDENCE_DIR_BRAIN, "git_diff.txt"), "w", encoding="utf-8") as f:
        f.write(git_diff_out)

    with open(os.path.join(EVIDENCE_DIR_K, "git_status.txt"), "w", encoding="utf-8") as f:
        f.write(git_status_out)
    with open(os.path.join(EVIDENCE_DIR_BRAIN, "git_status.txt"), "w", encoding="utf-8") as f:
        f.write(git_status_out)

    with open(os.path.join(EVIDENCE_DIR_K, "pytest_output.txt"), "w", encoding="utf-8") as f:
        f.write(direct_pytest.stdout + "\n" + direct_pytest.stderr)
    with open(os.path.join(EVIDENCE_DIR_BRAIN, "pytest_output.txt"), "w", encoding="utf-8") as f:
        f.write(direct_pytest.stdout + "\n" + direct_pytest.stderr)

    with open(os.path.join(EVIDENCE_DIR_K, "wire_timeline.json"), "w", encoding="utf-8") as f:
        json.dump(captured_wire_timeline, f, indent=2, ensure_ascii=False, default=str)
    with open(os.path.join(EVIDENCE_DIR_BRAIN, "wire_timeline.json"), "w", encoding="utf-8") as f:
        json.dump(captured_wire_timeline, f, indent=2, ensure_ascii=False, default=str)

    with open(os.path.join(EVIDENCE_DIR_K, "event_log.json"), "w", encoding="utf-8") as f:
        json.dump(collected_events, f, indent=2, ensure_ascii=False, default=str)
    with open(os.path.join(EVIDENCE_DIR_BRAIN, "event_log.json"), "w", encoding="utf-8") as f:
        json.dump(collected_events, f, indent=2, ensure_ascii=False, default=str)

    # Master evidence summary JSON
    master_evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "STAGE_2_QWEN_ORNITH_QWEN_WORKFLOW",
        "status": overall_status,
        "session_id": session_id,
        "model_timeline": model_timeline,
        "total_elapsed_seconds": round(total_time, 2),
        "gates": {
            "QWEN_PLAN": gate_1,
            "QWEN_TO_ORNITH_SWITCH": gate_2,
            "ORNITH_REAL_TOOL_EXECUTION": gate_3,
            "ORNITH_CODE_CHANGE": gate_4,
            "REAL_TEST_EXECUTION": gate_5,
            "TEST_EXIT_CODE": gate_6,
            "ORNITH_TO_QWEN_AUTONOMOUS_SWITCH": gate_7,
            "QWEN_EVIDENCE_REVIEW": gate_8
        },
        "tools_executed": list(tools_executed),
        "pytest_command": pytest_command_run,
        "pytest_exit_code": test_exit_code,
        "final_response": final_response,
        "wire_requests_count": len(captured_wire_timeline),
        "events_count": len(collected_events)
    }

    evidence_json = json.dumps(master_evidence, indent=2, ensure_ascii=False)
    with open(os.path.join(EVIDENCE_DIR_K, "stage_2_evidence.json"), "w", encoding="utf-8") as f:
        f.write(evidence_json)
    with open(os.path.join(EVIDENCE_DIR_BRAIN, "stage_2_evidence.json"), "w", encoding="utf-8") as f:
        f.write(evidence_json)

    print(f"\nEvidence written to: {os.path.join(EVIDENCE_DIR_K, 'stage_2_evidence.json')}", flush=True)
    print(f"Evidence mirrored to: {os.path.join(EVIDENCE_DIR_BRAIN, 'stage_2_evidence.json')}", flush=True)

    # 8. Output Final Report
    print("\n" + "=" * 80, flush=True)
    print(f"STAGE_2 = {overall_status}", flush=True)
    print(f"SESSION_ID = {session_id}", flush=True)
    print(f"MODEL_TIMELINE = {model_timeline}", flush=True)
    print(f"QWEN_TO_ORNITH_SWITCH = {gate_2}", flush=True)
    print(f"ORNITH_TOOL_EXECUTION = {gate_3}", flush=True)
    print(f"TEST_COMMAND = {pytest_command_run or 'pytest test_url_normalizer.py'}", flush=True)
    print(f"TEST_EXIT_CODE = {test_exit_code}", flush=True)
    print(f"ORNITH_TO_QWEN_SWITCH = {gate_7}", flush=True)
    print(f"QWEN_FINAL_REVIEW = {gate_8}", flush=True)
    print(f"EVIDENCE_PATH = {EVIDENCE_DIR_K}", flush=True)
    print(f"UNRESOLVED = {'None' if all_gates_pass else 'One or more gates failed'}", flush=True)
    print("=" * 80, flush=True)

    if not all_gates_pass:
        sys.exit(1)

if __name__ == "__main__":
    main()
