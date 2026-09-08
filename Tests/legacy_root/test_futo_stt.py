import torch
import wave
import numpy as np
import scipy.signal
import subprocess
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

model_path = os.environ.get("SILERO_MODEL_PATH", os.path.expanduser(r"~/.cache/silero/v5_ru.pt"))
model = torch.package.PackageImporter(model_path).load_pickle("tts_models", "model")
model.to("cpu")

test_phrases = [
    ("test1.wav", "Открой папку проекта и покажи последние изменённые файлы."),
    ("test2.wav", "Проверь, подключён ли планшет по беспроводному ADB."),
    ("test3.wav", "Создай текстовый файл тест голосового ввода.")
]

work_dir = r"K:\Project\local-voice\test-audio"
os.makedirs(work_dir, exist_ok=True)

cli_path = r"K:\Project\local-voice\bin\transcribe-cli.exe"
model_gguf = r"D:\Project\futo-keyboard-gigaam\voiceinput-shared\models\cache\assets\voice-models\gigaam-v3-e2e-rnnt-Q8_0.gguf"

print("Generating test audio and transcribing with FUTO GigaAM STT...\n", flush=True)

for filename, text in test_phrases:
    wav_path = os.path.join(work_dir, filename)
    # Generate 48 kHz audio and resample to 16 kHz
    audio_tensor = model.apply_tts(text=text, speaker="aidar", sample_rate=48000)
    audio_48k = audio_tensor.numpy()
    
    # Resample 48000 -> 16000 (factor of 3)
    num_samples = int(len(audio_48k) * 16000 / 48000)
    audio_16k = scipy.signal.resample(audio_48k, num_samples)
    audio_np = (np.clip(audio_16k, -1.0, 1.0) * 32767).astype(np.int16)
    
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_np.tobytes())
        
    # Run transcribe-cli
    cmd = [cli_path, "-m", model_gguf, "-q", wav_path]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    
    recognized_text = ""
    for line in res.stdout.splitlines():
        if line.startswith("text: "):
            recognized_text = line[6:].strip()
            break
            
    print(f"Original:   '{text}'", flush=True)
    print(f"Recognized: '{recognized_text}'", flush=True)
    print("-" * 60, flush=True)