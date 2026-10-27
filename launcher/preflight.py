#!/usr/bin/env python3
"""What Nexus still needs before it can start: programs, builds, binaries, certificates and the
files named in models/llama-swap.yaml. Prints each missing item with how to get it; exit 1 if any.

  python3 -I launcher/preflight.py
"""
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "voice/download_models.py"


def voice_models():
    """The model files voice/download_models.py fetches and checks."""
    spec = importlib.util.spec_from_file_location("download_models", DOWNLOADS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return sorted(module.EXPECTED)


def model_files(config):
    """llama-server and every file the model commands open (-m, --mmproj, templates), macros expanded."""
    text = config.read_text()
    macros = dict(re.findall(r"^  (\w+): (\S[^\n]*)$", text.split("\nmodels:", 1)[0], re.M))
    for _ in range(3):  # a macro may use another one
        text = re.sub(r"\$\{(\w+)\}", lambda m: macros.get(m[1], m[0]), text)
    files = {macros["server"]} if "server" in macros else set()
    files |= set(re.findall(r"(?:^|\s)(?:-m|--mmproj|--chat-template-file)\s+(\S+)", text))
    return sorted(config.parent / f for f in files)


def missing():
    found = []

    def need(ok, what, how):
        if not ok:
            found.append(f"{what} — {how}")

    for program, how in (("node", "Node 24"), ("npm", "Node 24"), ("uv", "https://docs.astral.sh/uv/"),
                         ("openssl", "apt install openssl"), ("curl", "apt install curl"),
                         ("xdotool", "apt install xdotool"), ("wmctrl", "apt install wmctrl"),
                         ("xclip", "apt install xclip")):
        need(shutil.which(program), program, how)
    libraries = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True).stdout
    need("libflite.so" in libraries, "libflite (произношение латиницы)", "apt install libflite1")

    need((ROOT / "agent/node_modules/@openhands/agent-canvas/package.json").exists(), "agent/node_modules", "(cd agent && npm ci)")
    need((ROOT / "ui/node_modules").exists(), "ui/node_modules", "(cd ui && npm ci)")
    need((ROOT / "ui/dist/index.html").exists(), "сборка ui/dist", "(cd ui && npm run build)")
    need((ROOT / "voice/.venv/bin/uvicorn").exists(), "voice/.venv", "(cd voice && uv sync --frozen)")
    for name in voice_models():
        need((ROOT / "voice/models" / name).exists(), f"voice/models/{name}", "(cd voice && .venv/bin/python download_models.py)")
    need((ROOT / "screen/.venv/bin/desk").exists(), "screen/.venv", "(cd screen && uv sync --frozen)")

    for binary, how in (("gateway/caddy", "Caddy с caddyserver.com, версия в README «Восстановление»"),
                        ("models/llama-swap", "llama-swap с github.com/mostlygeek/llama-swap")):
        path = ROOT / binary
        need(path.is_file() and path.stat().st_mode & 0o111, binary, how)
    for name in ("openhands-ca.crt", "openhands-ca.key"):
        need((ROOT / "gateway/ca" / name).exists(), f"gateway/ca/{name}", "корневой сертификат шлюза (README «Восстановление»)")

    config = ROOT / "models/llama-swap.yaml"
    for path in model_files(config):
        need(path.exists(), str(path), "путь в models/llama-swap.yaml: собрать ik_llama или положить веса")
    return found


def main():
    found = missing()
    if not found:
        print("Всё нужное для запуска на месте.")
        return 0
    print("Не хватает:")
    for line in found:
        print(f"  {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
