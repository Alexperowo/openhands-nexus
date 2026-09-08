import os
import sys
import time
import json
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

text = "Голосовой интерфейс OpenHands работает локально. Распознавание и синтез речи выполняются на этом компьютере."
req_body = json.dumps({"text": text, "voice": "M1"}).encode("utf-8")

req = urllib.request.Request(
    "http://127.0.0.1:18002/tts",
    data=req_body,
    headers={"Content-Type": "application/json"},
    method="POST"
)

t0 = time.perf_counter()
with urllib.request.urlopen(req) as resp:
    audio_data = resp.read()
    headers = dict(resp.headers)
elapsed_ms = (time.perf_counter() - t0) * 1000.0

dur = float(headers.get("X-Duration-Seconds", 0.0))
server_lat = float(headers.get("X-Latency-Ms", 0.0))

print(f"TTS Output Audio Bytes: {len(audio_data)} bytes")
print(f"Reported Audio Duration: {dur} s")
print(f"Server Synthesis Latency: {server_lat} ms")
print(f"Full Round-trip HTTP Latency: {elapsed_ms:.1f} ms")
print(f"Real-Time Factor (RTF): {server_lat / (dur * 1000):.3f}")

out_path = r"K:\Project\local-voice\test-audio\e2e_tts_result.wav"
with open(out_path, "wb") as f:
    f.write(audio_data)

print(f"Saved audio output to {out_path}")