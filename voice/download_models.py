#!/usr/bin/env python3
"""
Скрипт загрузки моделей голосовой службы:
1. Silero TTS v5.6 ru (v5_6_ru.pt)
2. GigaAM v3 (v3_ctc / v3_e2e_ctc)

Все модели сохраняются исключительно в папку voice/models/
"""

import os
import sys
import hashlib
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

SILERO_V5_6_URL = "https://models.silero.ai/models/tts/ru/v5_6_ru.pt"
SILERO_FILE = MODELS_DIR / "v5_6_ru.pt"


def get_hashes(filepath: Path):
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def download_file(url: str, dest: Path):
    if dest.exists() and dest.stat().st_size > 0:
        print(f"Файл уже существует: {dest} ({dest.stat().st_size} байт)")
        return
    print(f"Скачивание {url} -> {dest}...")
    temp_dest = dest.with_suffix(".tmp")
    req = urllib.request.Request(url, headers={"User-Agent": "OpenHands-Nexus-Voice/1.0"})
    with urllib.request.urlopen(req) as resp, open(temp_dest, "wb") as out:
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        while chunk := resp.read(64 * 1024):
            out.write(chunk)
            downloaded += len(chunk)
            if total > 0 and downloaded % (1024 * 1024 * 10) < 64 * 1024:
                print(f"  Скачано {downloaded / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB...")
    temp_dest.rename(dest)
    print(f"Скачивание завершено: {dest} ({dest.stat().st_size} байт)")


def main():
    print(f"Папка моделей: {MODELS_DIR}")
    # 1. Silero v5.6
    download_file(SILERO_V5_6_URL, SILERO_FILE)
    md5_silero, sha256_silero = get_hashes(SILERO_FILE)
    print(f"Silero v5.6 ru: MD5={md5_silero}, SHA256={sha256_silero}")

    # 2. GigaAM v3 через gigaam.load_model с download_root
    print("\nПроверка/скачивание GigaAM v3...")
    try:
        import gigaam
        print("Загрузка GigaAM v3_ctc в папку models/...")
        model_ctc = gigaam.load_model("v3_ctc", download_root=str(MODELS_DIR), device="cpu")
        print("GigaAM v3_ctc успешно инициализирована на CPU!")
        
        ctc_file = MODELS_DIR / "v3_ctc.ckpt"
        if ctc_file.exists():
            md5_giga, sha256_giga = get_hashes(ctc_file)
            print(f"GigaAM v3_ctc: MD5={md5_giga}, SHA256={sha256_giga}")
    except Exception as e:
        print(f"Ошибка инициализации GigaAM: {e}")
        return 1

    print("\nВсе модели проверены и готовы.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
