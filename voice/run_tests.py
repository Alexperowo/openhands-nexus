#!/usr/bin/env python3
"""
Скрипт проверки доказательств (proof of work) голосовой службы:
(1) TTS синтез фразы -> test_tts_output.wav, длительность, время синтеза
(2) STT распознавание wav обратно -> текст
(3) STT распознавание webm/opus (сконвертированного ffmpeg) -> текст
(4) Замеры времени ответа эндпоинтов и потребления RAM/VRAM
"""

import json
import subprocess
import time
import urllib.request
from pathlib import Path

import soundfile as sf

BASE_DIR = Path(__file__).resolve().parent
URL_BASE = "http://127.0.0.1:18020"
PHRASE = "Привет. Задача выполнена, жду следующую команду."
WAV_OUTPUT = BASE_DIR / "test_tts_output.wav"
WEBM_OUTPUT = BASE_DIR / "test_tts_output.webm"
FFMPEG_BIN = "/usr/bin/ffmpeg"


def post_json(url: str, data: dict, headers: dict = None) -> tuple[int, bytes, float]:
    body = json.dumps(data).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req) as resp:
        t1 = time.perf_counter()
        return resp.status, resp.read(), (t1 - t0)


def post_multipart(url: str, filepath: Path, model_name: str = "whisper-1", auth_token: str = "test-token") -> tuple[int, dict, float]:
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    filename = filepath.name
    with open(filepath, "rb") as f:
        file_bytes = f.read()

    lines = []
    lines.append(f"--{boundary}".encode("utf-8"))
    lines.append(f'Content-Disposition: form-data; name="model"'.encode("utf-8"))
    lines.append(b"")
    lines.append(model_name.encode("utf-8"))

    lines.append(f"--{boundary}".encode("utf-8"))
    lines.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode("utf-8"))
    lines.append(b"Content-Type: application/octet-stream")
    lines.append(b"")
    lines.append(file_bytes)
    lines.append(f"--{boundary}--".encode("utf-8"))
    lines.append(b"")

    body = b"\r\n".join(lines)
    req_headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {auth_token}"
    }
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req) as resp:
        t1 = time.perf_counter()
        res_json = json.loads(resp.read().decode("utf-8"))
        return resp.status, res_json, (t1 - t0)


def get_memory_stats():
    pid_file = BASE_DIR / "service.pid"
    ram_mb = 0.0
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            # Читаем VmRSS из /proc/<pid>/status
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        ram_mb = int(parts[1]) / 1024.0
                        break
        except Exception as e:
            print(f"Ошибка получения RAM: {e}")

    # Замер VRAM
    vram_info = "N/A"
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.used", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if res.returncode == 0:
            lines = res.stdout.strip().split("\n")
            vram_info = "; ".join([f"GPU {l.strip()}" for l in lines])
    except Exception as e:
        vram_info = f"nvidia-smi error: {e}"

    return ram_mb, vram_info


def main():
    print("=" * 60)
    print("СТАРТ ТЕСТОВ И СБОРА ДОКАЗАТЕЛЬСТВ ГОЛОСОВОЙ СЛУЖБЫ")
    print("=" * 60)

    # 0. Health check
    print("\n[0] Проверка GET /health...")
    t0 = time.perf_counter()
    req = urllib.request.Request(f"{URL_BASE}/health")
    with urllib.request.urlopen(req) as resp:
        t_health = time.perf_counter() - t0
        health_data = json.loads(resp.read().decode("utf-8"))
        print(f"  Код: {resp.status}, Время: {t_health*1000:.1f} мс")
        print(f"  Ответ: {health_data}")

    # 1. TTS
    print(f"\n[1] Синтез речи (TTS) POST /v1/audio/speech...")
    print(f"  Текст: «{PHRASE}»")
    status, audio_bytes, t_tts = post_json(
        f"{URL_BASE}/v1/audio/speech",
        {"input": PHRASE, "voice": "xenia", "response_format": "wav", "speed": 1.0}
    )
    with open(WAV_OUTPUT, "wb") as f:
        f.write(audio_bytes)
    
    # Замер параметров WAV
    info = sf.info(str(WAV_OUTPUT))
    print(f"  Код ответа: {status}")
    print(f"  Файл сохранён: {WAV_OUTPUT} ({WAV_OUTPUT.stat().st_size} байт)")
    print(f"  Время синтеза (latency): {t_tts:.3f} с ({t_tts*1000:.1f} мс)")
    print(f"  Длительность аудио: {info.duration:.2f} с ({info.samplerate} Гц, {info.channels} канал)")
    print(f"  RTF (Real-Time Factor): {t_tts / info.duration:.3f}")

    # 2. STT WAV
    print(f"\n[2] Распознавание речи (STT) POST /v1/audio/transcriptions (WAV)...")
    status, stt_res_wav, t_stt_wav = post_multipart(
        f"{URL_BASE}/v1/audio/transcriptions",
        WAV_OUTPUT,
        model_name="whisper-1",
        auth_token="Bearer test-token-openhands"
    )
    print(f"  Код ответа: {status}")
    print(f"  Время распознавания: {t_stt_wav:.3f} с ({t_stt_wav*1000:.1f} мс)")
    print(f"  Распознанный текст: «{stt_res_wav.get('text')}»")

    # 3. Конвертация в webm/opus и STT WEBM
    print(f"\n[3] Конвертация в WebM/Opus и STT POST /v1/audio/transcriptions (WebM)...")
    cmd_conv = [FFMPEG_BIN, "-y", "-i", str(WAV_OUTPUT), "-c:a", "libopus", str(WEBM_OUTPUT)]
    subprocess.run(cmd_conv, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(f"  Файл WebM создан: {WEBM_OUTPUT} ({WEBM_OUTPUT.stat().st_size} байт)")

    status, stt_res_webm, t_stt_webm = post_multipart(
        f"{URL_BASE}/v1/audio/transcriptions",
        WEBM_OUTPUT,
        model_name="whisper-1",
        auth_token="Bearer test-token-openhands"
    )
    print(f"  Код ответа: {status}")
    print(f"  Время распознавания (WebM): {t_stt_webm:.3f} с ({t_stt_webm*1000:.1f} мс)")
    print(f"  Распознанный текст: «{stt_res_webm.get('text')}»")

    # 4. Память RAM и VRAM
    ram_mb, vram_info = get_memory_stats()
    print(f"\n[4] Потребление ресурсов:")
    print(f"  Служба RAM (VmRSS): {ram_mb:.1f} МБ")
    print(f"  VRAM GPU: {vram_info}")

    print("\n" + "=" * 60)
    print("ВСЕ ПРОВЕРКИ УСПЕШНО ЗАВЕРШЕНЫ")
    print("=" * 60)


if __name__ == "__main__":
    main()
