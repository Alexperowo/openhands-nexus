import os
import sys
import json
import time
import subprocess
import httpx
from pathlib import Path
from datetime import datetime, timezone

# Ensure openhands is available
try:
    from openhands.sdk import Message, TextContent, Conversation, Agent
    from openhands.sdk.llm.llm_profile_store import LLMProfileStore
    from openhands.sdk.workspace import LocalWorkspace
    from openhands.sdk.conversation.response_utils import get_agent_final_response
except ImportError as e:
    print(f"Error: OpenHands SDK imports failed: {e}")
    sys.exit(1)

EVIDENCE_FILE_K = r"K:\Project\OpenHands-Tests\Production-Station\stage_1_agent_session_evidence.json"
EVIDENCE_FILE_BRAIN = r"C:\Users\User\.gemini\antigravity\brain\f2ece564-c6b9-4bcb-978c-aa86c97c4da5\stage_1_agent_session_evidence.json"
WORKSPACE_DIR = r"C:\Users\User\.gemini\antigravity\scratch\stage_1_agent_workspace"
PERSISTENCE_DIR = r"C:\Users\User\.gemini\antigravity\scratch\stage_1_agent_persistence"

# Intercept outgoing HTTP requests made by httpx (used by LiteLLM)
captured_wire_requests = []
captured_wire_responses = []
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
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": req_url,
            "method": request.method,
            "headers": dict(request.headers),
            "body_json": body_json,
            "body_raw": body_text
        }
        captured_wire_requests.append(entry)
    
    response = original_httpx_send(self, request, *args, **kwargs)
    
    if ":8080" in req_url:
        resp_text = None
        resp_json = None
        if response.content:
            try:
                resp_text = response.content.decode("utf-8", errors="ignore")
                resp_json = json.loads(resp_text)
            except Exception:
                pass
        captured_wire_responses.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status_code": response.status_code,
            "response_json": resp_json,
            "response_raw": resp_text
        })
    return response

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

def main():
    print("=" * 70)
    print("STAGE 1 CLOSURE: REAL OPENHANDS AGENT/SESSION SMOKE TEST")
    print("=" * 70)

    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    os.makedirs(PERSISTENCE_DIR, exist_ok=True)

    # 1. Load established profile 'Next-Normal'
    print("\n[Step 1] Loading installed profile 'Next-Normal' via LLMProfileStore...")
    store = LLMProfileStore()
    llm = store.load("Next-Normal")
    print(f"  Loaded model: {llm.model}")
    print(f"  Base URL: {llm.base_url}")
    print(f"  litellm_extra_body: {llm.litellm_extra_body}")

    # Verify duplicate budget removal in loaded profile
    extra_body = llm.litellm_extra_body or {}
    budget_in_extra = extra_body.get("thinking_budget_tokens")
    has_chat_template_kwargs = "chat_template_kwargs" in extra_body
    chat_kwargs_budget = extra_body.get("chat_template_kwargs", {}).get("thinking_budget_tokens") if has_chat_template_kwargs else None

    duplicate_removed = (budget_in_extra == 2048) and (chat_kwargs_budget is None)
    print(f"  Duplicate budget removed check: {'YES' if duplicate_removed else 'NO'}")
    print(f"    - thinking_budget_tokens: {budget_in_extra}")
    print(f"    - chat_template_kwargs budget: {chat_kwargs_budget}")

    # 2. Construct authentic OpenHands Agent and Session
    print("\n[Step 2] Creating authentic OpenHands Agent and LocalConversation session...")
    agent = Agent(llm=llm, tools=[])
    workspace = LocalWorkspace(working_dir=WORKSPACE_DIR)
    
    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        persistence_dir=PERSISTENCE_DIR
    )
    
    session_id = str(conversation.id)
    print(f"  Session / Conversation ID: {session_id}")
    print(f"  Conversation Class: {conversation.__class__.__name__}")
    print(f"  Agent Class: {agent.__class__.__name__}")

    # 3. Send message and run through the Agent/Session loop
    prompt = "Solve: 12 * 12 = ? Return only the number."
    print(f"\n[Step 3] Submitting message to session: {prompt!r}...")
    conversation.send_message(prompt)

    req_count_before = len(captured_wire_requests)
    t0 = time.perf_counter()
    print("  Executing conversation.run() via authentic Agent.step engine...")
    conversation.run()
    elapsed = time.perf_counter() - t0
    print(f"  conversation.run() finished in {elapsed:.2f}s")

    # 4. Inspect wire capture and responses
    captured_req = captured_wire_requests[-1] if len(captured_wire_requests) > req_count_before else None
    captured_resp = captured_wire_responses[-1] if len(captured_wire_responses) > 0 else None

    wire_body = captured_req.get("body_json", {}) if captured_req else {}
    wire_budget = wire_body.get("thinking_budget_tokens")
    wire_chat_kwargs = wire_body.get("chat_template_kwargs")
    wire_chat_kwargs_budget = wire_chat_kwargs.get("thinking_budget_tokens") if isinstance(wire_chat_kwargs, dict) else None

    resp_json = captured_resp.get("response_json", {}) if captured_resp else {}
    choices = resp_json.get("choices", [])
    finish_reason = choices[0].get("finish_reason") if choices else None
    resp_message = choices[0].get("message", {}) if choices else {}
    reasoning_content = resp_message.get("reasoning_content", "")
    content = resp_message.get("content", "")

    # Extract final response from OpenHands conversation state events
    final_content = ""
    try:
        final_content = get_agent_final_response(conversation.state.events)
    except Exception:
        pass
    if not final_content and content:
        final_content = content

    backend_pid = get_llama_server_pid()

    # Evaluation
    wire_budget_ok = (wire_budget == 2048)
    no_chat_kwargs_budget = (wire_chat_kwargs_budget is None)
    finish_ok = (finish_reason == "stop")
    content_ok = ("144" in final_content) or ("144" in content)

    agent_session_pass = wire_budget_ok and no_chat_kwargs_budget and finish_ok and content_ok

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY:")
    print("=" * 70)
    print(f"  DUPLICATE_BUDGET_REMOVED    : {'YES' if duplicate_removed and no_chat_kwargs_budget else 'NO'}")
    print(f"  WIRE_BUDGET_AFTER_CLEANUP   : {wire_budget if wire_budget_ok else 'FAIL'}")
    print(f"  REAL_OPENHANDS_AGENT_SESSION: {'PASS' if agent_session_pass else 'FAIL'}")
    print(f"  SESSION_ID                  : {session_id}")
    print(f"  SELECTED_PROFILE            : Next-Normal")
    print(f"  BACKEND_PID                 : {backend_pid}")
    print(f"  FINISH_REASON               : {finish_reason}")
    print(f"  FINAL_CONTENT               : {final_content.strip()!r}")
    print(f"  REASONING_LENGTH            : {len(reasoning_content)} chars")
    print(f"  WIRE_BODY_KEYS              : {list(wire_body.keys())}")
    print("=" * 70)

    # Save evidence
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "STAGE_1_AGENT_SESSION_CLOSURE",
        "duplicate_budget_removed": "YES" if duplicate_removed and no_chat_kwargs_budget else "NO",
        "wire_budget_after_cleanup": wire_budget if wire_budget_ok else "FAIL",
        "real_openhands_agent_session": "PASS" if agent_session_pass else "FAIL",
        "finish_reason": finish_reason,
        "backend_pid": backend_pid,
        "session_id": session_id,
        "profile": "Next-Normal",
        "elapsed_seconds": round(elapsed, 2),
        "final_content": final_content,
        "reasoning_length": len(reasoning_content),
        "wire_request": {
            "url": captured_req.get("url") if captured_req else None,
            "body_keys": list(wire_body.keys()),
            "thinking_budget_tokens": wire_budget,
            "chat_template_kwargs_budget": wire_chat_kwargs_budget
        },
        "overall_status": "PASS" if agent_session_pass else "FAIL"
    }

    evidence_json = json.dumps(results, indent=2, ensure_ascii=False)
    with open(EVIDENCE_FILE_K, "w", encoding="utf-8") as f:
        f.write(evidence_json)
    with open(EVIDENCE_FILE_BRAIN, "w", encoding="utf-8") as f:
        f.write(evidence_json)

    print(f"\nEvidence written to: {EVIDENCE_FILE_K}")
    print(f"Evidence mirrored to: {EVIDENCE_FILE_BRAIN}")

    if not agent_session_pass:
        sys.exit(1)

if __name__ == "__main__":
    main()
