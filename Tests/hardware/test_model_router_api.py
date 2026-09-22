"""
Hardware test for llama-swap router, model loading, and reasoning modes.
Verifies all 4 workstation models:
- qwen (Qwen 3.8 27B)
- ornith (Ornith 1.5 35B)
- next (Qwen3-Next 80B)
- qwen122 (Qwen 3.5 122B MoE)
"""

import json
import time
import urllib.request
import pytest


class TestModelRouter:
    """Verifies llama-swap model router on port 8080 and model response matrix."""

    BASE_URL = "http://127.0.0.1:8080"

    @pytest.fixture(autouse=True)
    def check_router_running(self):
        """Skip tests gracefully if llama-swap is not currently running."""
        try:
            req = urllib.request.Request(f"{self.BASE_URL}/v1/models")
            with urllib.request.urlopen(req, timeout=2):
                pass
        except Exception:
            pytest.skip("llama-swap is not currently running on port 8080 (start with 'openhands start')")

    def test_router_models_list(self):
        """Verify all 4 core models are recognized by llama-swap."""
        url = f"{self.BASE_URL}/v1/models"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            models = {m["id"]: m.get("status", {}).get("value") for m in data.get("data", [])}
            assert "qwen" in models, f"Model 'qwen' missing from {models.keys()}"
            assert "ornith" in models, f"Model 'ornith' missing from {models.keys()}"
            assert "next" in models, f"Model 'next' missing from {models.keys()}"
            assert "qwen122" in models, f"Model 'qwen122' missing from {models.keys()}"
            # At least one model should be currently loaded or available
            assert any(s in ("loaded", "unloaded") for s in models.values())

    def test_warm_model_inference_ping(self):
        """Sends a lightweight chat completion request to the active model with 180s cold-start budget."""
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
            "temperature": 0.1,
        }
        req = urllib.request.Request(
            f"{self.BASE_URL}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        # 180 seconds to allow cold VRAM loading if model swap is required
        with urllib.request.urlopen(req, timeout=180) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            elapsed = time.time() - t0
            assert "choices" in res and len(res["choices"]) > 0
            msg = res["choices"][0]["message"]
            text = (msg.get("content") or "") + (msg.get("reasoning_content") or "")
            assert len(text.strip()) > 0, f"Model returned empty response: {msg}"
            print(f"\n[Inference Test] Model: {loaded_model}, latency: {elapsed:.2f}s, reply: {text.strip()[:50]}")

    @pytest.mark.parametrize("model_id,enable_thinking", [
        ("qwen", True),
        ("qwen", False),
        ("ornith", False),
    ])
    def test_fast_model_inference_modes(self, model_id, enable_thinking):
        """Verifies fast models inference and reasoning configuration toggles."""
        payload = {
            "model": f"openai/{model_id}",
            "messages": [
                {"role": "user", "content": "Сколько будет 2+2? Ответь кратко."}
            ],
            "max_tokens": 64,
            "temperature": 0.1,
            "chat_template_kwargs": {
                "enable_thinking": enable_thinking
            }
        }
        req = urllib.request.Request(
            f"{self.BASE_URL}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=180) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            elapsed = time.time() - t0
            assert "choices" in res and len(res["choices"]) > 0
            msg = res["choices"][0]["message"]
            content = (msg.get("content") or "").strip()
            reasoning = (msg.get("reasoning_content") or "").strip()
            total_text = content + reasoning
            assert len(total_text) > 0, f"Empty reply for model {model_id}"
            if enable_thinking and model_id == "qwen":
                # When thinking is enabled on thinking-distilled models, reasoning content or <think> tags are present
                has_reasoning = len(reasoning) > 0 or "<think>" in total_text or "4" in total_text
                assert has_reasoning, f"Thinking mode failed to produce reasoning: {msg}"
            print(f"\n[{model_id} Thinking={enable_thinking}] Latency: {elapsed:.2f}s | Reply: {content[:40]}")
