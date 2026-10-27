#!/usr/bin/env python3
"""
Скрипт загрузки моделей голосовой службы:
1. Silero TTS v5.6 ru (v5_6_ru.pt)
2. GigaAM v3_e2e_rnnt с токенизатором

Все модели сохраняются исключительно в папку voice/models/.
Каждый файл сверяется с ожидаемой SHA-256 до того, как попадёт в папку: модели читаются
через pickle (torch.package, torch.load), подменённый файл выполнил бы свой код.
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"

SILERO_URL = "https://models.silero.ai/models/tts/ru"
GIGAAM_URL = "https://cdn.chatwm.opensmodel.sberdevices.ru/GigaAM"  # как gigaam._URL_DIR
# Новая модель или версия: скачать, проверить в работе и только тогда вписать сюда её SHA-256.
EXPECTED = {
    "v5_6_ru.pt": (SILERO_URL, "04cc9b1d08ce38bcaa9d02c488d80d3e6806d17f7eaa7c95982f36a3cbf50b2e"),
    "v3_e2e_rnnt.ckpt": (GIGAAM_URL, "f60c62fe45902d967000770a12f260de7c5ac4d4b8e5e852f1df8c548e3958b5"),
    "v3_e2e_rnnt_tokenizer.model": (GIGAAM_URL, "828c12c991019eef952a960661f25a92d6ad279591e2ea466b4aeddf1d20a18a"),
}


class ChecksumError(Exception):
    pass


def sha256(filepath: Path) -> str:
    digest = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(name: str) -> Path:
    """Скачанный и сверенный файл модели; уже лежащий в папке файл тоже сверяется."""
    if name not in EXPECTED:
        raise ChecksumError(f"{name}: нет ожидаемой SHA-256 в EXPECTED.")
    base, expected = EXPECTED[name]
    dest = MODELS_DIR / name
    if dest.exists():
        if sha256(dest) != expected:
            raise ChecksumError(f"{dest}: SHA-256 не совпадает с ожидаемой. Удалите файл и запустите снова.")
        print(f"Файл на месте и сверен: {dest}")
        return dest
    url = f"{base}/{name}"
    print(f"Скачивание {url} -> {dest}...")
    temp_dest = dest.with_name(dest.name + ".tmp")
    req = urllib.request.Request(url, headers={"User-Agent": "OpenHands-Nexus-Voice/1.0"})
    try:
        with urllib.request.urlopen(req) as resp, open(temp_dest, "wb") as out:
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            while chunk := resp.read(64 * 1024):
                out.write(chunk)
                downloaded += len(chunk)
                if total > 0 and downloaded % (1024 * 1024 * 10) < 64 * 1024:
                    print(f"  Скачано {downloaded / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB...")
        actual = sha256(temp_dest)
        if actual != expected:
            raise ChecksumError(f"{url}: SHA-256 {actual}, ожидалась {expected}. Файл не сохранён.")
        temp_dest.rename(dest)
    finally:
        temp_dest.unlink(missing_ok=True)
    print(f"Скачивание завершено и сверено: {dest} ({dest.stat().st_size} байт)")
    return dest


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Папка моделей: {MODELS_DIR}")
    from service import STT_MODEL
    try:
        fetch("v5_6_ru.pt")
        # GigaAM качает сама, но без сверки токенизатора: файлы кладём заранее, она их берёт.
        fetch(f"{STT_MODEL}.ckpt")
        fetch(f"{STT_MODEL}_tokenizer.model")
    except (ChecksumError, OSError) as e:
        print(f"Ошибка: {e}")
        return 1

    print("\nПроверка GigaAM...")
    try:
        import gigaam
        gigaam.load_model(STT_MODEL, download_root=str(MODELS_DIR), device="cpu")
        print(f"GigaAM {STT_MODEL} успешно инициализирована на CPU!")
    except Exception as e:
        print(f"Ошибка инициализации GigaAM: {e}")
        return 1

    print("\nВсе модели проверены и готовы.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
