r"""
OpenHands Nexus - Autonomous Prefix Slot Cache Manager
Location: Config/slot_cache_manager.py

Automatically detects running llama-server models via llama-swap router (port 8080)
and restores the matching static prefix NVMe slot dump into slot 0:
- architect_prefix.bin (Qwen 122B Lead Architect / Team Chains)
- solo_full_prefix.bin (Qwen 122B Solo Autonomous / Qwen 27B)
- executor_prefix.bin (Ornith 35B Fast Coder / Implementer)
- auditor_prefix.bin (Qwen 80B / Next Security & Code Auditor)

Zero cloud dependencies. Non-invasive overlay. Safe and idempotent.
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CACHE_DIR = os.path.join(PROJECT_ROOT, "Cache", "slots")
LOGS_DIR = os.path.join(PROJECT_ROOT, "Logs", "llama-server")
RESTORE_LOG_FILE = os.path.join(LOGS_DIR, "slot-restore.log")
ROUTER_URL = os.environ.get("ROUTER_URL", "http://127.0.0.1:8080")

# Dump catalog
AVAILABLE_DUMPS = {
    "architect_prefix.bin": "Lead Architect & Planner (Qwen 122B / Team Chains)",
    "solo_full_prefix.bin": "Solo Autonomous Engineer (Qwen 122B / 27B)",
    "executor_prefix.bin": "Fast Coder & Implementer (Ornith 35B)",
    "auditor_prefix.bin": "Security & Code Auditor (Qwen 80B / Next)",
}

_state_lock = threading.Lock()
_last_restored_state = {
    "model": None,
    "dump": None,
    "proxy": None,
    "tokens": 0,
    "bytes": 0,
    "restore_ms": 0.0,
    "timestamp": 0.0,
    "status": "uninitialized",
}

_watcher_thread = None
_watcher_stop_event = threading.Event()
_trigger_event = threading.Event()


def _log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [SlotRestorer] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(RESTORE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def resolve_dump_for_model(model_id: str, working_profile_id: str = None, prefer_active_dialogue: bool = True) -> str:
    """Resolve the canonical prefix dump filename for a model and active profile."""
    if not model_id:
        return "architect_prefix.bin"

    m = model_id.lower()
    prof = (working_profile_id or "").lower()

    # 5th Dump: Prioritize dynamic active dialogue snapshot if fresh and available
    if prefer_active_dialogue:
        diag_dump = f"active_conversation_{model_id}.bin"
        diag_path = os.path.join(CACHE_DIR, diag_dump)
        if os.path.isfile(diag_path):
            try:
                # Use if created/modified within last 48 hours
                if (time.time() - os.path.getmtime(diag_path)) < 172800:
                    return diag_dump
            except Exception:
                pass

    if "ornith" in m:
        return "executor_prefix.bin"
    if "next" in m:
        return "auditor_prefix.bin"
    if "qwen122" in m or "gpt-5.6" in m:
        if "solo" in prof:
            return "solo_full_prefix.bin"
        return "architect_prefix.bin"
    if "qwen" in m:
        # Qwen 3.8 27B has separate architecture without 122B static dump
        return None

    return None


def get_active_profile_id() -> str:
    """Retrieve currently active working profile ID from persistent state."""
    try:
        sys_path_config = os.path.join(PROJECT_ROOT, "Config")
        if sys_path_config not in sys.path:
            sys.path.insert(0, sys_path_config)
        import working_profiles
        st = working_profiles.get_working_profile_state()
        return st.get("active_working_profile_id", "team-full")
    except Exception:
        return "team-full"


def get_running_model_info(router_url: str = ROUTER_URL) -> dict:
    """Query llama-swap /running endpoint for currently active model and proxy."""
    url = f"{router_url}/running"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            running = data.get("running", [])
            for item in running:
                if item.get("state") == "ready" and item.get("model"):
                    return {
                        "model": item["model"],
                        "state": item["state"],
                        "proxy": item.get("proxy", ""),
                    }
            if running:
                return {
                    "model": running[0].get("model", ""),
                    "state": running[0].get("state", "unknown"),
                    "proxy": running[0].get("proxy", ""),
                }
    except Exception:
        pass
    return {"model": None, "state": "none", "proxy": None}


def restore_slot_dump(model_id: str, dump_filename: str, router_url: str = ROUTER_URL) -> dict:
    """Send restore request to /upstream/{model_id}/slots/0?action=restore."""
    dump_path = os.path.join(CACHE_DIR, dump_filename)
    if not os.path.isfile(dump_path):
        err = f"Dump file '{dump_filename}' not found in {CACHE_DIR}"
        _log(f"ERROR: {err}")
        return {"ok": False, "error": err}

    url = f"{router_url}/upstream/{model_id}/slots/0?action=restore"
    payload = json.dumps({"filename": dump_filename}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            body = resp.read().decode("utf-8")
            dt_total_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            data = json.loads(body)
            n_restored = data.get("n_restored", 0)
            n_read = data.get("n_read", 0)
            restore_ms = data.get("timings", {}).get("restore_ms", dt_total_ms)

            res = {
                "ok": True,
                "model": model_id,
                "dump": dump_filename,
                "n_restored": n_restored,
                "n_read": n_read,
                "restore_ms": restore_ms,
                "total_latency_ms": dt_total_ms,
                "timestamp": time.time(),
            }

            with _state_lock:
                _last_restored_state.update({
                    "model": model_id,
                    "dump": dump_filename,
                    "tokens": n_restored,
                    "bytes": n_read,
                    "restore_ms": restore_ms,
                    "timestamp": time.time(),
                    "status": "restored",
                })

            mb = round(n_read / (1024 * 1024), 1)
            _log(
                f"[SUCCESS] Restored slot 0 for model '{model_id}' with '{dump_filename}' "
                f"({n_restored} tokens, {mb} MB) in {restore_ms:.1f} ms"
            )
            return res

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        err = f"HTTP {e.code}: {body or e.reason}"
        _log(f"[WARN] Failed to restore slot for '{model_id}': {err}")
        return {"ok": False, "error": err}
    except Exception as e:
        _log(f"[WARN] Error restoring slot for '{model_id}': {e}")
        return {"ok": False, "error": str(e)}


def save_slot_dump(model_id: str, dump_filename: str, router_url: str = ROUTER_URL) -> dict:
    """Send save request to /upstream/{model_id}/slots/0?action=save."""
    url = f"{router_url}/upstream/{model_id}/slots/0?action=save"
    payload = json.dumps({"filename": dump_filename}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            body = resp.read().decode("utf-8")
            dt_total_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            data = json.loads(body)
            n_saved = data.get("n_saved", 0)
            n_written = data.get("n_written", 0)
            save_ms = data.get("timings", {}).get("save_ms", dt_total_ms)

            mb = round(n_written / (1024 * 1024), 1)
            _log(
                f"[SUCCESS] Saved slot 0 for model '{model_id}' to '{dump_filename}' "
                f"({n_saved} tokens, {mb} MB) in {save_ms:.1f} ms"
            )
            return {
                "ok": True,
                "model": model_id,
                "dump": dump_filename,
                "n_saved": n_saved,
                "n_written": n_written,
                "save_ms": save_ms,
                "total_latency_ms": dt_total_ms,
                "timestamp": time.time(),
            }
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        err = f"HTTP {e.code}: {body or e.reason}"
        _log(f"[WARN] Failed to save slot for '{model_id}': {err}")
        return {"ok": False, "error": err}
    except Exception as e:
        _log(f"[WARN] Error saving slot for '{model_id}': {e}")
        return {"ok": False, "error": str(e)}


def check_and_auto_restore(router_url: str = ROUTER_URL) -> dict:
    """
    Check current router status and automatically restore slot 0 if needed.
    Idempotent: skips if model, proxy, and desired dump match last restored state.
    """
    running_info = get_running_model_info(router_url)
    model = running_info.get("model")
    state = running_info.get("state")
    proxy = running_info.get("proxy")

    if not model or state != "ready":
        return {
            "status": "idle",
            "model": model,
            "state": state,
            "synced": True
        }

    profile_id = get_active_profile_id()
    desired_dump = resolve_dump_for_model(model, profile_id)

    with _state_lock:
        already_processed = (
            _last_restored_state.get("model") == model
            and _last_restored_state.get("dump") == desired_dump
            and _last_restored_state.get("proxy") == proxy
            and _last_restored_state.get("status") in ("restored", "failed", "skipped_no_dump")
        )

    if already_processed:
        return {
            "status": "already_synced",
            "model": model,
            "dump": desired_dump,
            "synced": True
        }

    if not desired_dump:
        with _state_lock:
            _last_restored_state["model"] = model
            _last_restored_state["dump"] = None
            _last_restored_state["proxy"] = proxy
            _last_restored_state["status"] = "skipped_no_dump"
        return {
            "status": "skipped_no_dump",
            "model": model,
            "synced": True
        }

    # Never interrupt or block an ongoing inference session
    try:
        slots_url = f"{proxy.rstrip('/')}/slots" if proxy else f"{router_url}/upstream/{model}/slots"
        s_req = urllib.request.Request(slots_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(s_req, timeout=0.8) as s_resp:
            slots = json.loads(s_resp.read().decode("utf-8"))
            if slots and isinstance(slots, list) and slots[0].get("is_processing", False):
                return {
                    "status": "busy_processing",
                    "model": model,
                    "dump": desired_dump,
                    "synced": False
                }
    except Exception:
        pass

    # Perform restoration
    _log(f"Detected model '{model}' (profile '{profile_id}'). Restoring '{desired_dump}'...")
    res = restore_slot_dump(model, desired_dump, router_url)
    with _state_lock:
        _last_restored_state["model"] = model
        _last_restored_state["dump"] = desired_dump
        _last_restored_state["proxy"] = proxy
        _last_restored_state["status"] = "restored" if res.get("ok") else "failed"
    return res


def get_slot_status() -> dict:
    """Return live status of prefix slot cache for telemetry."""
    running_info = get_running_model_info()
    model = running_info.get("model")
    profile_id = get_active_profile_id()
    desired_dump = resolve_dump_for_model(model, profile_id) if model else None

    with _state_lock:
        state_copy = dict(_last_restored_state)

    is_synced = bool(
        model
        and desired_dump
        and state_copy.get("model") == model
        and state_copy.get("dump") == desired_dump
        and state_copy.get("status") == "restored"
    )

    return {
        "running_model": model,
        "running_state": running_info.get("state"),
        "active_profile": profile_id,
        "desired_dump": desired_dump,
        "restored_dump": state_copy.get("dump"),
        "restored_tokens": state_copy.get("tokens", 0),
        "restore_ms": state_copy.get("restore_ms", 0.0),
        "restored_timestamp": state_copy.get("timestamp", 0.0),
        "is_synced": is_synced,
        "watcher_active": _watcher_thread is not None and _watcher_thread.is_alive(),
    }


def trigger_restore_async():
    """Trigger an immediate restore check asynchronously."""
    _trigger_event.set()


_last_seen_processing = False


def _watcher_loop(interval_s: float = 1.0):
    global _last_seen_processing
    _log(f"Auto-Restore Watcher loop started (polling interval {interval_s}s)")
    while not _watcher_stop_event.is_set():
        try:
            check_and_auto_restore()

            # Dynamic 5th Dump: Auto-snapshot when model completes a turn
            running_info = get_running_model_info()
            model = running_info.get("model")
            proxy = running_info.get("proxy")
            if model and running_info.get("state") == "ready":
                slots_url = f"{proxy.rstrip('/')}/slots" if proxy else f"{ROUTER_URL}/upstream/{model}/slots"
                try:
                    s_req = urllib.request.Request(slots_url, headers={"Accept": "application/json"})
                    with urllib.request.urlopen(s_req, timeout=0.8) as s_resp:
                        slots = json.loads(s_resp.read().decode("utf-8"))
                        if slots and isinstance(slots, list):
                            is_proc = slots[0].get("is_processing", False)
                            n_prompt = slots[0].get("n_prompt_tokens", 0)

                            # Turn completion detected: True -> False with meaningful tokens
                            if _last_seen_processing and not is_proc and n_prompt > 200:
                                dump_name = f"active_conversation_{model}.bin"
                                _log(f"[DynamicSnapshot] Model '{model}' finished turn ({n_prompt} tokens). Auto-saving 5th dump '{dump_name}'...")
                                save_res = save_slot_dump(model, dump_name)
                                if save_res.get("ok"):
                                    with _state_lock:
                                        _last_restored_state["dump"] = dump_name
                                        _last_restored_state["tokens"] = save_res.get("n_saved", n_prompt)
                                        _last_restored_state["status"] = "restored"

                            _last_seen_processing = is_proc
                except Exception:
                    pass
        except Exception as e:
            _log(f"Watcher loop error: {e}")

        # Wait for either interval or trigger event
        triggered = _trigger_event.wait(timeout=interval_s)
        if triggered:
            _trigger_event.clear()
            try:
                check_and_auto_restore()
            except Exception as e:
                _log(f"Triggered restore error: {e}")


def start_slot_restorer_daemon(interval_s: float = 1.0):
    """Start background watcher thread if not already running."""
    global _watcher_thread
    if _watcher_thread is not None and _watcher_thread.is_alive():
        return
    _watcher_stop_event.clear()
    _trigger_event.clear()
    _watcher_thread = threading.Thread(
        target=_watcher_loop,
        args=(interval_s,),
        daemon=True,
        name="NexusPrefixSlotWatcher"
    )
    _watcher_thread.start()


def stop_slot_restorer_daemon():
    """Stop background watcher thread."""
    global _watcher_thread
    if _watcher_thread and _watcher_thread.is_alive():
        _watcher_stop_event.set()
        _trigger_event.set()
        _watcher_thread.join(timeout=2.0)
        _watcher_thread = None
        _log("Auto-Restore Watcher stopped.")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "status":
        print(json.dumps(get_slot_status(), indent=2))
    elif action == "restore":
        model_arg = sys.argv[2] if len(sys.argv) > 2 else None
        if model_arg:
            prof = get_active_profile_id()
            dump = resolve_dump_for_model(model_arg, prof)
            res = restore_slot_dump(model_arg, dump)
            print(json.dumps(res, indent=2))
        else:
            res = check_and_auto_restore()
            print(json.dumps(res, indent=2))
    elif action == "daemon":
        print("Starting slot restorer in foreground mode (Ctrl+C to stop)...")
        start_slot_restorer_daemon(1.0)
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            stop_slot_restorer_daemon()
