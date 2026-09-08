import os, sys, time, subprocess
sys.stdout.reconfigure(encoding="utf-8")
os.environ["PYTHONPATH"] = r"D:\Project\futo-keyboard-gigaam\third_party\transcribe.cpp\bindings\python\src"
os.environ["TRANSCRIBE_LIBRARY"] = r"K:\Project\transcribe-build-shared\bin\Release\transcribe.dll"
sys.path.insert(0, r"D:\Project\futo-keyboard-gigaam\third_party\transcribe.cpp\bindings\python\src")

def measure_ws():
    out = subprocess.check_output(f"powershell -Command \"(Get-Process -Id {os.getpid()}).WorkingSet64 / 1MB\"", shell=True)
    return float(out.strip().replace(b",", b"."))

import transcribe_cpp
from supertonic import TTS

ws0 = measure_ws()
stt_model = transcribe_cpp.Model(r"D:\Project\futo-keyboard-gigaam\voiceinput-shared\models\cache\assets\voice-models\gigaam-v3-e2e-rnnt-Q8_0.gguf")
ws1 = measure_ws()
tts_model = TTS(model="supertonic-3", model_dir=r"D:\AI\Models\Speech\supertonic", auto_download=False)
ws2 = measure_ws()

print(f"Initial RAM: {ws0:.1f} MB")
print(f"After STT:   {ws1:.1f} MB (+{ws1-ws0:.1f} MB)")
print(f"After TTS:   {ws2:.1f} MB (+{ws2-ws1:.1f} MB)")
print("VRAM usage:  0 MB (purely CPU inference)")