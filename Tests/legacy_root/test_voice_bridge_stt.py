import os
import sys
import time
import json
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

test_files = [
    ("test1.wav", "Открой папку проекта и покажи последние изменённые файлы."),
    ("test2.wav", "Проверь, подключён ли планшет по беспроводному ADB."),
    ("test3.wav", "Создай текстовый файл тест голосового ввода.")
]

work_dir = r"K:\Project\local-voice\test-audio"

print("Testing Voice Bridge POST /stt endpoint with 3 test phrases...\n", flush=True)

results = []
for fname, orig in test_files:
    fpath = os.path.join(work_dir, fname)
    with open(fpath, "rb") as f:
        audio_bytes = f.read()

    req = urllib.request.Request(
        "http://127.0.0.1:18002/stt",
        data=audio_bytes,
        headers={"Content-Type": "audio/wav"},
        method="POST"
    )

    t0 = time.perf_counter()
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    rec = data.get("text", "")
    print(f"Original:   '{orig}'", flush=True)
    print(f"Recognized: '{rec}'", flush=True)
    print(f"Latency:    {elapsed_ms:.1f} ms (server reported: {data.get('latency_ms', 0)} ms)", flush=True)
    print("-" * 60, flush=True)
    results.append({
        "original": orig,
        "recognized": rec,
        "latency_ms": elapsed_ms,
        "server_latency_ms": data.get("latency_ms", 0)
    })

with open(r"K:\Project\local-voice\stt_test_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)