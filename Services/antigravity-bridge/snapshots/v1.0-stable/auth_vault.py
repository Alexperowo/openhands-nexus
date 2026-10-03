import os
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("antigravity-bridge.auth_vault")

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

DEFAULT_LOAD_CODE_ASSIST: Dict[str, Any] = {
    "userTier": "PAID",
    "tierDisplayName": "Google AI Pro",
    "isGcpTos": True,
    "allowedProjects": ["aicode-consumers"],
    "cloudaicompanionProject": "aicode-consumers",
    "currentTier": {
        "id": "tier-paid-pro",
        "name": "Google AI Pro",
        "description": "Full Station Pro Access"
    },
    "appState": {
        "status": "STATUS_ACTIVE"
    }
}

DEFAULT_USER_INFO: Dict[str, Any] = {
    "userEmail": "alex17loginov96@gmail.com",
    "userTier": "PAID",
    "tierDisplayName": "Google AI Pro",
    "project": "aicode-consumers"
}

def _get_cache_path(endpoint_name: str) -> str:
    safe_name = endpoint_name.replace("/", "").replace(":", "_") + ".json"
    return os.path.join(CACHE_DIR, safe_name)

def save_auth_cache(endpoint: str, data: Dict[str, Any]):
    path = _get_cache_path(endpoint)
    try:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        logger.debug("[AUTH_VAULT] Saved fresh auth cache for %s", endpoint)
    except Exception as e:
        logger.warning("[AUTH_VAULT] Failed to persist auth cache for %s: %s", endpoint, e)

def get_auth_fallback(endpoint: str) -> Dict[str, Any]:
    path = _get_cache_path(endpoint)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info("[AUTH_VAULT] Serving persisted auth cache for %s", endpoint)
                return data
        except Exception as e:
            logger.warning("[AUTH_VAULT] Corrupt cache file for %s: %s", endpoint, e)

    if "loadCodeAssist" in endpoint:
        logger.info("[AUTH_VAULT] Serving built-in seed profile for loadCodeAssist")
        return DEFAULT_LOAD_CODE_ASSIST
    elif "fetchUserInfo" in endpoint:
        logger.info("[AUTH_VAULT] Serving built-in seed profile for fetchUserInfo")
        return DEFAULT_USER_INFO

    return {}
