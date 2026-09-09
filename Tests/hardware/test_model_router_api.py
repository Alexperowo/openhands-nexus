"""
Hardware test for llama-swap router and warm model inference.
"""

import urllib.request
import json
import time
import pytest


class TestModelRouter:
    """Verifies llama-swap model router on port 8080 and warm model response."""

    BASE_URL = "http://127.0.0.1:8080"

    def test_router_models_list(self):
        url = f"{self.BASE_URL}/v1/models"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            models = {m["id"]: m.get("status", {}).get("value") for m in data.get("data", [])}
            assert "qwen" in models
            assert "ornith" in models
            assert "next" in models
            # At least one model should be currently loaded or available
            assert any(s in ("loaded", "unloaded") for s in models.values())

    def test_warm_model_inference_ping(self):
        """Sends a lightweight chat completion request to the active model."""
        # Find which model is currently loaded
        url = f"{self.BASE_URL}/v1/models"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            loaded_model = next((m["id"] for m in data.get("data", []) if m.get("status", {}).get("value") == "loaded"), None)

        if not loaded_model:
            loaded_model = "qwen"

        payload = {
            "model": f"openai/{loaded_model}",
            "messages": [
                {"role": "user", "content": "Скажи одно слово: ПРОВЕРКА"}
            ],
            "max_tokens": 15,
            "temperature": 0.1
        }
        req = urllib.request.Request(
            f"{self.BASE_URL}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=30) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            elapsed = time.time() - t0
            assert "choices" in res and len(res["choices"]) > 0
            msg = res["choices"][0]["message"]
            text = (msg.get("content") or "") + (msg.get("reasoning_content") or "")
            assert len(text.strip()) > 0, f"Model returned empty response: {msg}"
            print(f"\n[Inference Test] Model: {loaded_model}, latency: {elapsed:.2f}s, reply len: {len(text)}")
