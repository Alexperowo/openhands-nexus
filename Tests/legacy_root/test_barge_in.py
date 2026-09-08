import os
import sys
import time
import json
import urllib.request
import threading

sys.stdout.reconfigure(encoding="utf-8")

# Long text to synthesize
long_text = "Тестируем немедленную остановку генерации и прерывание воспроизведения речи. " * 8

def send_tts():
    req_body = json.dumps({"text": long_text, "voice": "M1"}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:18002/tts",
        data=req_body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"[TTS Thread] Finished with status {resp.status}, bytes: {len(resp.read())}")
    except Exception as e:
        print(f"[TTS Thread] Exception: {e}")

t = threading.Thread(target=send_tts)
t.start()

# Wait 100 ms then send /stop
time.sleep(0.1)
print("[Main] Sending POST /stop (barge-in signal)...")
t0 = time.perf_counter()
req_stop = urllib.request.Request(
    "http://127.0.0.1:18002/stop",
    data=b"{}",
    headers={"Content-Type": "application/json"},
    method="POST"
)
with urllib.request.urlopen(req_stop) as resp:
    stop_data = json.loads(resp.read().decode("utf-8"))
stop_latency_ms = (time.perf_counter() - t0) * 1000.0

print(f"[Main] Stop acknowledged in {stop_latency_ms:.1f} ms: {stop_data}")
t.join()
print("[Main] Barge-in test completed successfully!")