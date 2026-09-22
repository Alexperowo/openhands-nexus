"""
End-to-end multi-model benchmark script for OpenHands Nexus.
Sequentially exercises all 4 models:
1. qwen (27B)
2. ornith (35B)
3. next (80B)
4. qwen122 (122B MoE)
Measures swap/load time, prompt processing, and token generation speed.
"""

import json
import os
import sys
import time
import urllib.request

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROUTER_URL = "http://127.0.0.1:8080"
MODELS_TO_TEST = [
    ("qwen", "Соло / Ведущий (Qwen 27B)", 180),
    ("ornith", "Исполнитель кода (Ornith 35B)", 180),
    ("next", "Аудитор архитектуры (Next 80B)", 300),
    ("qwen122", "Флагманский архитектор (Qwen 122B MoE)", 360),
]


def test_model(model_key: str, desc: str, timeout_s: int):
    print(f"\n{'='*70}")
    print(f"[*] Testing Model: {model_key} — {desc}")
    print(f"    Timeout ceiling: {timeout_s}s")
    print(f"{'='*70}")

    payload = {
        "model": f"openai/{model_key}",
        "messages": [
            {"role": "system", "content": "You are OpenHands Nexus. Be concise and direct."},
            {"role": "user", "content": "Подтверди готовность к работе и назови свои параметры одной фразой."}
        ],
        "max_tokens": 50,
        "temperature": 0.2
    }

    req = urllib.request.Request(
        f"{ROUTER_URL}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            elapsed = time.time() - t0
            res = json.loads(resp.read().decode("utf-8"))
            choice = res["choices"][0]["message"]
            content = choice.get("content") or ""
            reasoning = choice.get("reasoning_content") or ""
            usage = res.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            comp_tokens = usage.get("completion_tokens", 0)

            print(f"[OK SUCCESS] Model '{model_key}' responded in {elapsed:.2f}s!")
            print(f"    Prompt tokens: {prompt_tokens} | Completion tokens: {comp_tokens}")
            if comp_tokens > 0 and elapsed > 0:
                print(f"    Total latency: {elapsed:.2f}s (load + prefill + {comp_tokens} tokens)")
            if reasoning:
                print(f"    Reasoning preview: {reasoning.strip()[:100]}...")
            print(f"    Answer: {content.strip()}")
            return True, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[FAIL ERROR] Model '{model_key}' failed after {elapsed:.2f}s: {e}")
        return False, elapsed


def main():
    print("\n" + "#"*70)
    print("      OPENHANDS NEXUS — FULL 4-MODEL VERIFICATION BATTERY")
    print("#"*70)

    # Check router
    try:
        req = urllib.request.Request(f"{ROUTER_URL}/v1/models")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"[OK] llama-swap online at {ROUTER_URL}. Registered models: {len(data.get('data', []))}")
    except Exception as e:
        print(f"[FAIL] llama-swap router unreachable: {e}")
        sys.exit(1)

    results = []
    for m_key, m_desc, m_timeout in MODELS_TO_TEST:
        ok, dur = test_model(m_key, m_desc, m_timeout)
        results.append((m_key, ok, dur))

    print("\n" + "="*70)
    print("                     VERIFICATION SUMMARY")
    print("="*70)
    all_ok = True
    for m_key, ok, dur in results:
        status_str = "[PASS]" if ok else "[FAIL]"
        print(f"  {status_str:7s} {m_key:15s} — {dur:6.2f}s")
        if not ok:
            all_ok = False
    print("="*70 + "\n")

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
