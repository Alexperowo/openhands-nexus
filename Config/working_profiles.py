r"""
OpenHands Local - Working Profile Manager (Python Module)
Location: K:\Project\Config\working_profiles.py

Zero external dependencies (pure Python standard library: os, json, urllib.request).
Maintains persistent server-side active state and synchronizes with OpenHands Agent Server.
"""

import os
import json
import urllib.request
import urllib.error
from datetime import datetime

WORKING_PROFILES_DIR = r"C:\Users\User\.openhands\working-profiles"
STATE_FILE = r"C:\Users\User\.openhands\working-profile-state.json"
API_KEY_FILE = r"C:\Users\User\.openhands\agent-canvas\api-key.txt"
AGENT_SERVER_URL = "http://127.0.0.1:18000/api/settings"


def get_session_api_key() -> str:
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


def load_working_profiles() -> list:
    profiles = []
    if not os.path.exists(WORKING_PROFILES_DIR):
        return profiles
    for filename in sorted(os.listdir(WORKING_PROFILES_DIR)):
        if filename.endswith(".json"):
            filepath = os.path.join(WORKING_PROFILES_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    profiles.append(json.load(f))
            except Exception as e:
                print(f"[WorkingProfiles] Error loading {filename}: {e}")
    return profiles


def get_working_profile_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WorkingProfiles] Error loading state: {e}")

    # Safe default
    return {
        "active_working_profile_id": "team-full",
        "active_reasoning_mode_id": "standard_team",
        "resolved_agent_profile_id": "ba66f66f-f9fb-4764-b5b9-22f27bf84b3a",
        "resolved_llm_profile_name": "Qwen3.8-Medium",
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "updated_by": "default_fallback",
    }


def save_working_profile_state(state: dict):
    state["updated_at"] = datetime.utcnow().isoformat() + "Z"
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def sync_to_agent_server(agent_profile_id: str, llm_profile_name: str) -> bool:
    api_key = get_session_api_key()
    payload = json.dumps({
        "active_agent_profile_id": agent_profile_id,
        "active_profile": llm_profile_name
    }).encode("utf-8")

    req = urllib.request.Request(
        AGENT_SERVER_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-session-api-key": api_key
        },
        method="PATCH"
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return 200 <= res.status < 300
    except Exception as e:
        print(f"[WorkingProfiles] Agent Server sync error: {e}")
        return False


def switch_working_profile(working_profile_id: str, reasoning_mode_id: str = None, updated_by: str = "api") -> dict:
    profiles = load_working_profiles()
    target_wp = next((p for p in profiles if p.get("id") == working_profile_id), None)
    if not target_wp:
        raise ValueError(f"Working profile '{working_profile_id}' not found.")

    resolved_agent_profile_id = target_wp.get("default_agent_profile_id")
    resolved_llm_profile_name = target_wp.get("default_llm_profile_name")
    active_reasoning_mode_id = reasoning_mode_id or target_wp.get("reasoning", {}).get("default_mode_id", "direct")

    reasoning = target_wp.get("reasoning", {})
    if reasoning.get("supported") and reasoning.get("modes"):
        mode = next((m for m in reasoning["modes"] if m.get("id") == active_reasoning_mode_id), None)
        if mode:
            if mode.get("target_agent_profile_id"):
                resolved_agent_profile_id = mode["target_agent_profile_id"]
            if mode.get("target_llm_profile_name"):
                resolved_llm_profile_name = mode["target_llm_profile_name"]
        else:
            active_reasoning_mode_id = reasoning.get("default_mode_id") or reasoning["modes"][0]["id"]

    new_state = {
        "active_working_profile_id": target_wp["id"],
        "active_reasoning_mode_id": active_reasoning_mode_id,
        "resolved_agent_profile_id": resolved_agent_profile_id,
        "resolved_llm_profile_name": resolved_llm_profile_name,
        "updated_by": updated_by,
    }

    # Persist state
    save_working_profile_state(new_state)

    # Synchronize to Agent Server
    synced = sync_to_agent_server(resolved_agent_profile_id, resolved_llm_profile_name)

    return {
        "state": new_state,
        "agent_server_synced": synced
    }
