#!/usr/bin/env python3
"""The model weights of models/llama-swap.yaml (list: models/weights.json): which are already in a folder,
and downloading the missing ones from Hugging Face. Downloads resume (curl -C -) and are checked by
SHA-256 before they take their name, so a broken or substituted file never reaches llama-server.

  python3 -I models/weights.py status FOLDER        what is there; exit 1 if something is missing
  python3 -I models/weights.py missing FOLDER       ids of incomplete groups, one per line
  python3 -I models/weights.py get FOLDER ID...     download those groups into FOLDER
"""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent / "weights.json"
GiB = 1024 ** 3


def load(manifest=MANIFEST):
    return json.loads(Path(manifest).read_text())


def present(folder, name, entry):
    """Same size as the published file: hashing 80 GB on every check would take minutes."""
    path = Path(folder) / name
    return path.is_file() and path.stat().st_size == entry["size"]


def missing_groups(folder, data):
    return [g for g in data["groups"] if not all(present(folder, f, data["files"][f]) for f in g["files"])]


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(folder, name, entry):
    """One file: resume into NAME.part, check size and SHA-256, then rename. False on failure."""
    target = Path(folder) / name
    part = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n{name} ({entry['size'] / GiB:.1f} ГБ)", flush=True)
    result = subprocess.run(["curl", "-fL", "--retry", "5", "--retry-delay", "5", "--progress-bar",
                             "-C", "-", "-o", str(part), entry["url"]])
    if result.returncode != 0 and not (part.exists() and part.stat().st_size == entry["size"]):
        print(f"Скачивание прервалось (curl {result.returncode}). Повторный запуск продолжит с того же места.")
        return False
    if part.stat().st_size != entry["size"]:
        print("Размер не совпал с опубликованным: файл удалён, скачайте заново.")
        part.unlink()
        return False
    print("Проверка SHA-256…", flush=True)
    if sha256(part) != entry["sha256"]:
        print("Контрольная сумма не совпала: файл удалён, скачайте заново.")
        part.unlink()
        return False
    part.rename(target)
    return True


def get(folder, ids, data):
    groups = {g["id"]: g for g in data["groups"]}
    unknown = [i for i in ids if i not in groups]
    if unknown:
        print("Неизвестные группы: " + ", ".join(unknown))
        return 2
    names = list(dict.fromkeys(f for i in ids for f in groups[i]["files"]))
    todo = [n for n in names if not present(folder, n, data["files"][n])]
    Path(folder).mkdir(parents=True, exist_ok=True)
    started = sum((Path(folder) / (n + ".part")).stat().st_size for n in todo
                  if (Path(folder) / (n + ".part")).exists())
    need = sum(data["files"][n]["size"] for n in todo) - started
    free = shutil.disk_usage(folder).free
    if need + GiB > free:
        print(f"Мало места: нужно {need / GiB:.0f} ГБ, свободно {free / GiB:.0f} ГБ.")
        return 1
    failed = [n for n in todo if not fetch(folder, n, data["files"][n])]
    if failed:
        print("\nНе скачано: " + ", ".join(failed))
        return 1
    print("\nВсе выбранные модели на месте.")
    return 0


def main(argv=None, data=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2 or argv[0] not in ("status", "missing", "get"):
        print(__doc__.strip())
        return 2
    data = data or load()
    command, folder = argv[0], argv[1]
    if command == "get":
        return get(folder, argv[2:], data)
    absent = missing_groups(folder, data)
    if command == "missing":
        print("\n".join(g["id"] for g in absent))
        return 0
    for group in data["groups"]:
        size = sum(data["files"][f]["size"] for f in group["files"]) / GiB
        print(f"{'нет ' if group in absent else 'есть'}  {group['id']}: {group['name']} ({size:.0f} ГБ)")
    return 1 if absent else 0


if __name__ == "__main__":
    sys.exit(main())
