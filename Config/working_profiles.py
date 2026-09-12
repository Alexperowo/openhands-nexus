r"""
OpenHands Local - Working Profile Manager (Python Module)
Location: Config/working_profiles.py

Zero external dependencies (pure Python standard library: os, json, urllib.request).
Maintains persistent server-side active state and synchronizes with OpenHands Agent Server.
"""

import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone

ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

USER_HOME = os.environ.get("USERPROFILE") or os.environ.get("HOME") or os.path.expanduser("~")
OPENHANDS_HOME = os.environ.get("OPENHANDS_HOME") or os.path.join(USER_HOME, ".openhands")
WORKING_PROFILES_DIR = os.path.join(OPENHANDS_HOME, "working-profiles")
STATE_FILE = os.path.join(OPENHANDS_HOME, "working-profile-state.json")
API_KEY_FILE = os.path.join(OPENHANDS_HOME, "agent-canvas", "api-key.txt")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "working-profile-templates")
AGENT_SERVER_URL = "http://127.0.0.1:18000/api/settings"


def get_session_api_key() -> str:
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


def seed_templates_if_missing():
    try:
        os.makedirs(WORKING_PROFILES_DIR, exist_ok=True)
        existing = [f for f in os.listdir(WORKING_PROFILES_DIR) if f.endswith(".json")]
        if not existing and os.path.exists(TEMPLATES_DIR):
            template_files = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith(".json")]
            for tf in template_files:
                shutil.copyfile(os.path.join(TEMPLATES_DIR, tf), os.path.join(WORKING_PROFILES_DIR, tf))
            print(f"[WorkingProfiles] Auto-seeded {len(template_files)} working profile templates to {WORKING_PROFILES_DIR}")
    except Exception as e:
        print(f"[WorkingProfiles] Template auto-seeding warning: {e}")


def load_working_profiles() -> list:
    seed_templates_if_missing()
    profiles = []
    if not os.path.exists(WORKING_PROFILES_DIR):
        return profiles
    for filename in sorted(os.listdir(WORKING_PROFILES_DIR)):
        if filename.endswith(".json"):
            filepath = os.path.join(WORKING_PROFILES_DIR, filename)
            try:
                with open(filepath, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and isinstance(data.get("id"), str) and isinstance(data.get("name"), str):
                        profiles.append(data)
                    else:
                        print(f"[WorkingProfiles] Skipping invalid profile {filename}: missing id or name")
            except Exception as e:
                print(f"[WorkingProfiles] Error loading {filename}: {e}")
    return profiles


def get_working_profile_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WorkingProfiles] Error loading state: {e}")

    # Safe default
    return {
        "active_working_profile_id": "team-full",
        "active_reasoning_mode_id": "standard_team",
        "resolved_agent_profile_id": "ba66f66f-f9fb-4764-b5b9-22f27bf84b3a",
        "resolved_llm_profile_name": "Qwen3.8-Medium",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "updated_by": "default_fallback",
    }


def save_working_profile_state(state: dict):
    state["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    state_dir = os.path.dirname(STATE_FILE)
    fd, tmp_path = tempfile.mkstemp(dir=state_dir, suffix=".tmp", prefix="wp-state-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, STATE_FILE)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def sync_to_agent_server(agent_profile_id: str, llm_profile_name: str) -> tuple:
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
            if 200 <= res.status < 300:
                return True, ""
            return False, f"HTTP {res.status}"
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(65536).decode("utf-8", errors="ignore")
        except Exception:
            pass
        return False, f"HTTP {e.code}: {body or e.reason}"
    except Exception as e:
        return False, str(e)


def switch_working_profile(working_profile_id: str, reasoning_mode_id: str = None, updated_by: str = "api") -> dict:
    """
    Safely switches the global Working Profile with strict validation and Agent Server sync.
    Failure behavior:
    - Validates target profile and reasoning mode first (invalid mode raises ValueError, never silent fallback).
    - Synchronizes with Agent Server before touching disk state.
    - Only modifies disk state and reports success when Agent Server accepts.
    """
    if not working_profile_id or not isinstance(working_profile_id, str) or not ID_PATTERN.match(working_profile_id):
        raise ValueError(f"Invalid working_profile_id format: '{working_profile_id}'")
    if reasoning_mode_id and (not isinstance(reasoning_mode_id, str) or not ID_PATTERN.match(reasoning_mode_id)):
        raise ValueError(f"Invalid reasoning_mode_id format: '{reasoning_mode_id}'")

    # a) Validate target profile first
    profiles = load_working_profiles()
    target_wp = next((p for p in profiles if p.get("id") == working_profile_id), None)
    if not target_wp:
        raise ValueError(f"Working profile '{working_profile_id}' not found.")

    resolved_agent_profile_id = target_wp.get("default_agent_profile_id")
    resolved_llm_profile_name = target_wp.get("default_llm_profile_name")
    active_reasoning_mode_id = None

    reasoning = target_wp.get("reasoning") or {}
    supported = bool(reasoning.get("supported"))
    modes = reasoning.get("modes") or []

    if reasoning_mode_id:
        if not supported:
            # Profile does not support reasoning modes (e.g. Ornith)
            allowed_default = reasoning.get("default_mode_id") or "direct"
            if reasoning_mode_id != allowed_default and reasoning_mode_id != "direct":
                raise ValueError(
                    f"Working profile '{working_profile_id}' does not support reasoning modes (requested: '{reasoning_mode_id}')."
                )
            active_reasoning_mode_id = allowed_default
        else:
            # Explicit reasoning_mode_id must be valid for supported profiles; no silent fallback
            mode = next((m for m in modes if m.get("id") == reasoning_mode_id), None)
            if not mode:
                valid_modes = ", ".join(f"'{m.get('id')}'" for m in modes) if modes else "none"
                raise ValueError(
                    f"Invalid reasoning_mode_id '{reasoning_mode_id}' for working profile '{working_profile_id}'. "
                    f"Valid modes: [{valid_modes}]."
                )
            active_reasoning_mode_id = mode.get("id")
            if mode.get("target_agent_profile_id"):
                resolved_agent_profile_id = mode["target_agent_profile_id"]
            if mode.get("target_llm_profile_name"):
                resolved_llm_profile_name = mode["target_llm_profile_name"]
    else:
        # Default mode selection if none explicitly specified
        if supported and modes:
            active_reasoning_mode_id = reasoning.get("default_mode_id") or modes[0].get("id")
            mode = next((m for m in modes if m.get("id") == active_reasoning_mode_id), modes[0])
            if mode.get("target_agent_profile_id"):
                resolved_agent_profile_id = mode["target_agent_profile_id"]
            if mode.get("target_llm_profile_name"):
                resolved_llm_profile_name = mode["target_llm_profile_name"]
        else:
            active_reasoning_mode_id = reasoning.get("default_mode_id") or "direct"

    if not resolved_agent_profile_id or not resolved_llm_profile_name:
        raise ValueError(f"Working profile '{working_profile_id}' is missing resolved agent or LLM profile.")

    # b) Synchronize Agent Server before touching disk
    synced, error_detail = sync_to_agent_server(resolved_agent_profile_id, resolved_llm_profile_name)
    if not synced:
        raise RuntimeError(
            f"Agent Server synchronization failed: {error_detail}. Working profile state was NOT changed."
        )

    # c & d) Only update disk state after verified successful Agent Server sync
    new_state = {
        "active_working_profile_id": target_wp["id"],
        "active_reasoning_mode_id": active_reasoning_mode_id,
        "resolved_agent_profile_id": resolved_agent_profile_id,
        "resolved_llm_profile_name": resolved_llm_profile_name,
        "updated_by": updated_by,
    }

    save_working_profile_state(new_state)

    return {
        "ok": True,
        "state": new_state,
        "agent_server_synced": True
    }
