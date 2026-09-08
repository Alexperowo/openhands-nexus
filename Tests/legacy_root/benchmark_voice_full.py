import os
import sys
import time
import json
import wave
import urllib.request
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

os.environ["PYTHONPATH"] = r"D:\Project\futo-keyboard-gigaam\third_party\transcribe.cpp\bindings\python\src"
os.environ["TRANSCRIBE_LIBRARY"] = r"K:\Project\transcribe-build-shared\bin\Release\transcribe.dll"
sys.path.insert(0, r"D:\Project\futo-keyboard-gigaam\third_party\transcribe.cpp\bindings\python\src")

import transcribe_cpp
from supertonic import TTS

print("=== STARTING FULL VOICE BENCHMARK ===", flush=True)

# 1. STT Model Load Time
t0 = time.perf_counter()
stt_model = transcribe_cpp.Model(r"D:\Project\futo-keyboard-gigaam\voiceinput-shared\models\cache\assets\voice-models\gigaam-v3-e2e-rnnt-Q8_0.gguf")
stt_load_time = time.perf_counter() - t0
print(f"STT Model Load Time: {stt_load_time:.4f} s", flush=True)

# 2. STT Cold Latency
wav_path = r"D:\Project\futo-keyboard-gigaam\third_party\transcribe.cpp\samples\ru.wav"
with wave.open(wav_path, "rb") as wf:
    pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

t1 = time.perf_counter()
with stt_model.session() as s:
    res_cold = s.run(pcm)
stt_cold_latency = time.perf_counter() - t1
print(f"STT Cold Latency: {stt_cold_latency*1000:.1f} ms ('{res_cold.text}')", flush=True)

# 3. STT Warm Inference Latency (3 iterations)
warm_times = []
for i in range(3):
    t_start = time.perf_counter()
    with stt_model.session() as s:
        res_warm = s.run(pcm)
    warm_times.append(time.perf_counter() - t_start)
stt_warm_latency = sum(warm_times) / len(warm_times)
print(f"STT Warm Inference Latency: {stt_warm_latency*1000:.1f} ms (avg of 3)", flush=True)

# 4. TTS Model Load Time
t2 = time.perf_counter()
tts_model = TTS(model="supertonic-3", model_dir=r"D:\AI\Models\Speech\supertonic", auto_download=False)
tts_load_time = time.perf_counter() - t2
print(f"TTS Model Load Time: {tts_load_time:.4f} s", flush=True)

# 5. TTS Time-to-first-audio & Total Generation Speed / RTF
style = tts_model.get_voice_style("M1")
test_text = "Голосовой интерфейс OpenHands работает локально. Распознавание и синтез речи выполняются на этом компьютере."

t3 = time.perf_counter()
wav, dur = tts_model.synthesize(test_text, voice_style=style, lang="ru")
tts_total_time = time.perf_counter() - t3
audio_duration = float(dur[0])
rtf = tts_total_time / audio_duration
print(f"TTS Text: '{test_text}' ({len(test_text)} chars)")
print(f"TTS Audio Duration: {audio_duration:.2f} s")
print(f"TTS Total Generation Time: {tts_total_time:.3f} s")
print(f"TTS Realtime Factor (RTF): {rtf:.3f}")
print(f"TTS Time-to-First-Audio (TTFA): {tts_total_time*1000:.1f} ms")

benchmark_results = {
    "stt_model_load_time_s": round(stt_load_time, 4),
    "stt_cold_latency_ms": round(stt_cold_latency * 1000, 1),
    "stt_warm_latency_ms": round(stt_warm_latency * 1000, 1),
    "tts_model_load_time_s": round(tts_load_time, 4),
    "tts_ttfa_ms": round(tts_total_time * 1000, 1),
    "tts_total_gen_time_s": round(tts_total_time, 3),
    "tts_audio_duration_s": round(audio_duration, 2),
    "tts_rtf": round(rtf, 3),
}

with open(r"K:\Project\local-voice\benchmark_results.json", "w", encoding="utf-8") as f:
    json.dump(benchmark_results, f, ensure_ascii=False, indent=2)

print("\nSaved benchmark results to local-voice/benchmark_results.json", flush=True)