import os
import sys
import time
import wave
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

os.environ["PYTHONPATH"] = r"D:\Project\futo-keyboard-gigaam\third_party\transcribe.cpp\bindings\python\src"
os.environ["TRANSCRIBE_LIBRARY"] = r"K:\Project\transcribe-build-shared\bin\Release\transcribe.dll"
sys.path.insert(0, r"D:\Project\futo-keyboard-gigaam\third_party\transcribe.cpp\bindings\python\src")

import transcribe_cpp

model_path = r"D:\Project\futo-keyboard-gigaam\voiceinput-shared\models\cache\assets\voice-models\gigaam-v3-e2e-rnnt-Q8_0.gguf"
wav_path = r"D:\Project\futo-keyboard-gigaam\third_party\transcribe.cpp\samples\ru.wav"

print("Loading GigaAM v3 model once into memory...", flush=True)
t0 = time.perf_counter()
model = transcribe_cpp.Model(model_path)
load_time = time.perf_counter() - t0
print(f"Model loaded into memory in {load_time:.3f} s!", flush=True)

with wave.open(wav_path, "rb") as wf:
    frames = wf.readframes(wf.getnframes())
    pcm_int16 = np.frombuffer(frames, dtype=np.int16)
    pcm_float32 = pcm_int16.astype(np.float32) / 32768.0

print(f"Audio loaded: {len(pcm_float32)/16000:.2f} s", flush=True)

# Run cold inference
t1 = time.perf_counter()
with model.session() as session:
    res1 = session.run(pcm_float32)
cold_latency = time.perf_counter() - t1
print(f"Cold inference: '{res1.text}' in {cold_latency:.3f} s!", flush=True)

# Run warm inference 1
t2 = time.perf_counter()
with model.session() as session:
    res2 = session.run(pcm_float32)
warm_latency_1 = time.perf_counter() - t2
print(f"Warm inference 1: '{res2.text}' in {warm_latency_1:.3f} s!", flush=True)

# Run warm inference 2
t3 = time.perf_counter()
with model.session() as session:
    res3 = session.run(pcm_float32)
warm_latency_2 = time.perf_counter() - t3
print(f"Warm inference 2: '{res3.text}' in {warm_latency_2:.3f} s!", flush=True)