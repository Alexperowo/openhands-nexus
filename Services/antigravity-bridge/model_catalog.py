import os
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("antigravity-bridge.models")

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
MODELS_CACHE_FILE = os.path.join(CACHE_DIR, "models.json")
BASELINE_MODELS_FILE = os.path.join(CACHE_DIR, "baseline_models.json")

# Station named models as requested by the user, with 1M tokens context to satisfy checkpointer validation (>= 256K)
STATION_MODELS: Dict[str, Dict[str, Any]] = {
    "station-qwen": {
        "swap_target": "qwen",
        "displayName": "Локальная: Qwen 27B Coder (Vision)",
        "tagTitle": "Dual-GPU 38G",
        "tagDescription": "131k context / MTP / Multimodal",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI",
        "modelProvider": "MODEL_PROVIDER_GOOGLE",
        "supportedMimeTypes": {
            "text/plain": True, "text/x-python": True, "text/javascript": True, "text/x-typescript": True,
            "text/html": True, "text/css": True, "text/markdown": True, "application/json": True,
            "image/png": True, "image/jpeg": True, "image/webp": True
        },
        "quotaInfo": {"remainingFraction": 1.0, "resetTime": "2099-01-01T00:00:00Z"}
    },
    "station-next": {
        "swap_target": "next",
        "displayName": "Локальная: Next 80B MoE (Thinking)",
        "tagTitle": "Deep Thinking",
        "tagDescription": "Dual-GPU 38G / 8k reasoning budget",
        "supportsImages": False,
        "supportsThinking": True,
        "thinkingBudget": 2048,
        "minThinkingBudget": 64,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI",
        "modelProvider": "MODEL_PROVIDER_GOOGLE",
        "quotaInfo": {"remainingFraction": 1.0, "resetTime": "2099-01-01T00:00:00Z"}
    },
    "station-ornith": {
        "swap_target": "ornith",
        "displayName": "Локальная: Ornith 1.5 35B (Android & Big Dumps)",
        "tagTitle": "CUDA1 Specialist",
        "tagDescription": "19GB VRAM / Анализ дампов / Android MTP",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI",
        "modelProvider": "MODEL_PROVIDER_GOOGLE",
        "supportedMimeTypes": {
            "text/plain": True, "text/x-python": True, "text/javascript": True, "text/x-typescript": True,
            "text/html": True, "text/css": True, "text/markdown": True, "application/json": True,
            "image/png": True, "image/jpeg": True, "image/webp": True
        },
        "quotaInfo": {"remainingFraction": 1.0, "resetTime": "2099-01-01T00:00:00Z"}
    },
    "station-tinfield": {
        "swap_target": "tinfield",
        "displayName": "Локальная: Tinfield 177B (Titan MoE)",
        "tagTitle": "Heavyweight",
        "tagDescription": "177B MoE / 131k context / Глубокий синтез",
        "supportsImages": False,
        "supportsThinking": True,
        "thinkingBudget": 1000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI",
        "modelProvider": "MODEL_PROVIDER_GOOGLE",
        "quotaInfo": {"remainingFraction": 1.0, "resetTime": "2099-01-01T00:00:00Z"}
    },
    "station-qwen122": {
        "swap_target": "qwen122",
        "displayName": "Локальная: Qwen 122B MoE (208E)",
        "tagTitle": "Station Titan",
        "tagDescription": "35GB VRAM allocation / DeepSeek reasoning",
        "supportsImages": False,
        "supportsThinking": True,
        "thinkingBudget": 1536,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI",
        "modelProvider": "MODEL_PROVIDER_GOOGLE",
        "quotaInfo": {"remainingFraction": 1.0, "resetTime": "2099-01-01T00:00:00Z"}
    }
}

LOCAL_MODEL_ID = "station-qwen"

def resolve_station_model(model_name: str) -> Optional[str]:
    """Resolves incoming model request string to target llama-swap model name."""
    if not model_name:
        return None
    for sm_id, sm_info in sorted(STATION_MODELS.items(), key=lambda x: len(x[0]), reverse=True):
        if sm_id in model_name:
            return sm_info.get("swap_target", "qwen")
    if "station-local" in model_name:
        return "qwen"
    return None

def inject_local_model(catalog_data: Dict[str, Any]) -> Dict[str, Any]:
    """Injects all named station models into models dictionary and prepends to agentModelSorts."""
    models_dict = catalog_data.setdefault("models", {})
    
    # Remove generic station-local if present in catalog
    if "station-local" in models_dict:
        del models_dict["station-local"]

    for sm_id, sm_spec in STATION_MODELS.items():
        clean_spec = {k: v for k, v in sm_spec.items() if k != "swap_target"}
        models_dict[sm_id] = clean_spec

    sorts = catalog_data.setdefault("agentModelSorts", [])
    named_ids = list(STATION_MODELS.keys())
    if sorts and isinstance(sorts, list) and "groups" in sorts[0] and sorts[0]["groups"]:
        model_ids = sorts[0]["groups"][0].setdefault("modelIds", [])
        # Remove old station-local
        if "station-local" in model_ids:
            model_ids.remove("station-local")
        for sm_id in reversed(named_ids):
            if sm_id in model_ids:
                model_ids.remove(sm_id)
            model_ids.insert(0, sm_id)
    else:
        catalog_data["agentModelSorts"] = [{"groups": [{"modelIds": named_ids}]}]

    # Only persist if it contains core cloud models to avoid caching an accidentally truncated catalog
    if "gemini-3.8-flash-high" in models_dict:
        try:
            tmp = f"{MODELS_CACHE_FILE}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(catalog_data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, MODELS_CACHE_FILE)
        except Exception as e:
            logger.debug("Failed to cache models catalog: %s", e)

    return catalog_data

def get_models_fallback() -> Dict[str, Any]:
    """Returns cached models catalog with guaranteed Gemini models. Never returns a stripped catalog."""
    # 1. Try live cache
    if os.path.exists(MODELS_CACHE_FILE):
        try:
            with open(MODELS_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "gemini-3.8-flash-high" in data.get("models", {}):
                    logger.info("[MODELS] Serving valid persisted models cache (%d models)", len(data["models"]))
                    return inject_local_model(data)
        except Exception as e:
            logger.warning("[MODELS] Corrupt models cache: %s", e)

    # 2. Try baseline cache
    if os.path.exists(BASELINE_MODELS_FILE):
        try:
            with open(BASELINE_MODELS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info("[MODELS] Serving baseline models fallback (%d models)", len(data.get("models", {})))
                return inject_local_model(data)
        except Exception as e:
            logger.warning("[MODELS] Corrupt baseline models file: %s", e)

    logger.error("[MODELS] No valid model catalog found on disk!")
    return {"models": {}, "agentModelSorts": []}
