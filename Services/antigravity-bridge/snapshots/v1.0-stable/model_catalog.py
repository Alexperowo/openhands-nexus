import os
import json
import logging
from typing import Any, Dict

logger = logging.getLogger("antigravity-bridge.models")

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
MODELS_CACHE_FILE = os.path.join(CACHE_DIR, "models.json")

LOCAL_MODEL_ID = "station-local"
LOCAL_MODEL_SPEC: Dict[str, Any] = {
    "displayName": "Локальная модель",
    "tagTitle": "Station Local",
    "tagDescription": "Dual-GPU (5060Ti + 2080Ti) / llama-swap",
    "supportsImages": True,
    "supportsThinking": True,
    "thinkingBudget": 1000,
    "minThinkingBudget": 32,
    "maxTokens": 131072,
    "maxOutputTokens": 8192,
    "model": "MODEL_PLACEHOLDER_M71",
    "apiProvider": "API_PROVIDER_GOOGLE_GEMINI",
    "modelProvider": "MODEL_PROVIDER_GOOGLE",
    "supportedMimeTypes": {
        "text/plain": True,
        "text/x-python": True,
        "text/javascript": True,
        "text/x-typescript": True,
        "text/html": True,
        "text/css": True,
        "text/markdown": True,
        "application/json": True,
        "image/png": True,
        "image/jpeg": True,
        "image/webp": True
    },
    "quotaInfo": {
        "remainingFraction": 1.0,
        "resetTime": "2099-01-01T00:00:00Z"
    }
}

STANDALONE_MODELS_FALLBACK: Dict[str, Any] = {
    "models": {
        LOCAL_MODEL_ID: LOCAL_MODEL_SPEC,
        "gemini-3.8-flash": {
            "displayName": "Gemini 3.8 Flash (Cloud)",
            "supportsImages": True,
            "supportsThinking": True,
            "maxTokens": 1048576,
            "maxOutputTokens": 8192,
            "quotaInfo": {"remainingFraction": 0.0, "resetTime": "2099-01-01T00:00:00Z"}
        }
    },
    "agentModelSorts": [
        {
            "groups": [
                {
                    "modelIds": [LOCAL_MODEL_ID, "gemini-3.8-flash"]
                }
            ]
        }
    ]
}

def inject_local_model(catalog_data: Dict[str, Any]) -> Dict[str, Any]:
    """Injects station-local into models dictionary and prepends to agentModelSorts."""
    models_dict = catalog_data.setdefault("models", {})
    models_dict[LOCAL_MODEL_ID] = LOCAL_MODEL_SPEC

    sorts = catalog_data.setdefault("agentModelSorts", [])
    if sorts and isinstance(sorts, list) and "groups" in sorts[0] and sorts[0]["groups"]:
        model_ids = sorts[0]["groups"][0].setdefault("modelIds", [])
        if LOCAL_MODEL_ID in model_ids:
            model_ids.remove(LOCAL_MODEL_ID)
        model_ids.insert(0, LOCAL_MODEL_ID)
    else:
        catalog_data["agentModelSorts"] = [{"groups": [{"modelIds": [LOCAL_MODEL_ID]}]}]

    # Persist cache
    try:
        tmp = f"{MODELS_CACHE_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(catalog_data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, MODELS_CACHE_FILE)
    except Exception as e:
        logger.debug("Failed to cache models catalog: %s", e)

    return catalog_data

def get_models_fallback() -> Dict[str, Any]:
    """Returns cached models catalog or standalone fallback with local model."""
    if os.path.exists(MODELS_CACHE_FILE):
        try:
            with open(MODELS_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info("[MODELS] Serving persisted models cache")
                return data
        except Exception as e:
            logger.warning("[MODELS] Corrupt models cache: %s", e)

    logger.info("[MODELS] Serving standalone fallback model catalog")
    return STANDALONE_MODELS_FALLBACK
