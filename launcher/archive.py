#!/usr/bin/env python3
"""Archives of ./pack.

  archive.py scan TAR          the clean project archive holds no keys, personal data, weights, builds
                               or leftovers; prints each problem by path, never the matched text
  archive.py scan-own TAR      the own archive holds this PC's Nexus ready to start and nothing else
  archive.py backup FOLDER     the personal copy: keys, tablet certificate, conversations, ~/Nexus
  archive.py restore FILE      put a personal copy back where it was; existing files stay untouched
"""
import os
import re
import shutil
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "openhands-nexus"
REBUILT = {".venv", "node_modules", "__pycache__"}
LIMIT = 1024 * 1024  # the largest tracked file, ui/package-lock.json, is 440 KB

# Never in the project archive: runtime state, keys, builds, weights, leftovers.
FORBIDDEN = re.compile(
    r"(^|/)(agent/state|gateway/(ca|data|config)|node_modules|\.venv|__pycache__|voice/models|ui/dist)(/|$)"
    r"|(^|/)(\.env|session\.env|secrets?\.json)$"
    r"|\.(key|pem|p12|pfx|gguf|pt|ckpt|safetensors|bin|so|pyc|log|pid|part|tmp|orig|rej|swp)$"
    r"|\.bak|~$")
SECRETS = re.compile(
    rb"sk-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{30,}|ghp_[A-Za-z0-9]{30,}|github_pat_\w{20,}|AKIA[0-9A-Z]{16}"
    rb"|BEGIN [A-Z ]*PRIVATE KEY|xox[bp]-[\w-]{10,}|AIza[\w-]{30,}"
    rb"|OHN_(SESSION|SECRET)_KEY=[0-9a-f]{16,}")
REQUIRED = ("install", "pack", "check", "README.md", "docs/first-run.md", "docs/user-guide.md",
            "models/llama-swap.yaml", "models/weights.json", "launcher/install.sh", "VERSION")
EXECUTABLE = ("install", "pack", "check", "launcher/install.sh")

# The own archive (./pack own), paths from the home folder: the project as a fresh clone of the last
# commit plus what ./install would otherwise build or download, and the engine as a fresh checkout of
# its commit with the built server.
ENGINE = "backend/ik_llama-fresh"  # BACKEND in install
ENGINE_BUILD = ("build/bin/llama-server", "build/src/libllama.so", "build/ggml/src/libggml.so",
                "build/examples/mtmd/libmtmd.so", "build/CMakeCache.txt")  # the cache: cmake flags for nexus-update
PROGRAMS = ("models/llama-swap", "gateway/caddy")
CA_KEY = "gateway/ca/openhands-ca.key"
OWN_REQUIRED = (*PROGRAMS, CA_KEY, "gateway/ca/openhands-ca.crt", ".git/HEAD", ".git/shallow")
PC_LINKS = ("models/llama-server", "models/weights")  # absolute: the engine and the model folder of this PC
VOICE_MODELS = re.compile(r"^voice/models/[\w.-]+\.(pt|ckpt|model)$")
GARBAGE = re.compile(
    r"(^|/)(__pycache__|node_modules|\.venv|\.\w+_cache|evidence|agent/state|gateway/(data|config)|ui/dist)(/|$)"
    r"|^\.git/(logs|hooks|info|description|FETCH_HEAD|ORIG_HEAD)(/|$)"
    r"|(^|/)(\.env|session\.env|secrets?\.json)$"
    r"|\.(pyc|log|pid|part|tmp|orig|rej|swp|restore)$|\.(prev|old|next|retired)[\w-]*(/|$)|\.bak|~$")


def own_keys():
    """This PC's key values: none of them may appear in the archive (compared, never printed)."""
    try:
        text = (CONFIG / "session.env").read_text()
    except OSError:
        return []
    return [v.encode() for v in re.findall(r"^OHN_\w+=(\S{16,})$", text, re.M)]


def scan(tar_path, keys=None):
    keys = own_keys() if keys is None else keys
    problems, names = [], set()
    with tarfile.open(tar_path) as archive:
        members = archive.getmembers()
        top = {m.name.split("/", 1)[0] for m in members}
        if len(top) != 1:
            return ["в архиве не одна корневая папка"]
        for member in members:
            name = member.name.split("/", 1)[1] if "/" in member.name else ""
            if not name:
                continue
            names.add(name)
            if member.issym() or member.islnk():
                # screen/bin/click -> ../.venv/bin/desk is fine: it stays inside the project
                target = os.path.normpath(os.path.join(os.path.dirname(name), member.linkname))
                if member.islnk() or member.linkname.startswith("/") or target.startswith(".."):
                    problems.append(f"{name}: ссылка за пределы проекта")
                continue
            if not member.isfile():
                continue
            if FORBIDDEN.search(name):
                problems.append(f"{name}: такому файлу не место в архиве")
            if member.size > LIMIT:
                problems.append(f"{name}: больше {LIMIT // 1024} КБ")
                continue
            body = archive.extractfile(member).read()
            if body.startswith(b"\x7fELF"):
                problems.append(f"{name}: программа (ELF)")
            if SECRETS.search(body):
                problems.append(f"{name}: похоже на ключ или пароль")
            if any(key in body for key in keys):
                problems.append(f"{name}: содержит ключ этого ПК из session.env")
        modes = {m.name.split("/", 1)[1]: m.mode for m in members if "/" in m.name}
    problems += [f"{n}: нет в архиве" for n in REQUIRED if n not in names]
    problems += [f"{n}: не исполняемый" for n in EXECUTABLE if n in modes and not modes[n] & 0o100]
    return problems


def scan_own(tar_path, project, keys=None):
    """project: the project folder from the home folder, Agents/OpenHands-Nexus on this PC."""
    keys = own_keys() if keys is None else keys
    roots = {project: "", ENGINE: "движок: "}
    problems, found, voice = [], set(), 0
    with tarfile.open(tar_path) as archive:
        for member in archive:
            root = next((r for r in roots if member.name == r or member.name.startswith(r + "/")), None)
            if root is None:
                if not (member.isdir() and any(r.startswith(member.name + "/") for r in roots)):
                    problems.append(f"{member.name}: чужой файл")
                continue
            name, label = member.name[len(root) + 1:], roots[root]
            path = label + name
            if not name:
                continue
            found.add(path)
            if member.issym() or member.islnk():
                target = os.path.normpath(os.path.join(os.path.dirname(name), member.linkname))
                if not (root == project and name in PC_LINKS) and (
                        member.islnk() or member.linkname.startswith("/") or target.startswith("..")):
                    problems.append(f"{path}: ссылка за пределы своей папки")
                continue
            if not member.isfile():
                if not member.isdir():
                    problems.append(f"{path}: не файл и не папка")
                continue
            if GARBAGE.search(name):
                problems.append(f"{path}: мусор")
            binary = (root == project and name in PROGRAMS) or (root == ENGINE and name in ENGINE_BUILD[:4])
            if root == ENGINE and name.startswith("build/") and name not in ENGINE_BUILD:
                problems.append(f"{path}: лишний файл сборки")
            elif root == project and name.startswith("voice/models/"):
                if VOICE_MODELS.match(name):
                    voice += 1
                else:
                    problems.append(f"{path}: лишний файл в voice/models")
            elif binary or name.startswith(".git/objects/") or name == ".git/index":
                if binary and archive.extractfile(member).read(4) != b"\x7fELF":
                    problems.append(f"{path}: не программа")
            elif member.size > 64 * LIMIT:
                problems.append(f"{path}: неожиданно большой файл")
            else:
                body = archive.extractfile(member).read()
                if body.startswith(b"\x7fELF"):
                    problems.append(f"{path}: программа (ELF)")
                if root == project and name != CA_KEY and SECRETS.search(body):
                    problems.append(f"{path}: похоже на ключ или пароль")
                if any(key in body for key in keys):
                    problems.append(f"{path}: содержит ключ этого ПК из session.env")
            if root == project and name == CA_KEY and member.mode & 0o077:
                problems.append(f"{path}: ключ сертификата открыт другим пользователям")
            executable = (root == project and name in (*PROGRAMS, *EXECUTABLE)) or (
                root == ENGINE and name == ENGINE_BUILD[0])
            if executable and not member.mode & 0o100:
                problems.append(f"{path}: не исполняемый")
    required = [n for n in (*REQUIRED, *OWN_REQUIRED, *PC_LINKS) if n != "VERSION"]
    required += [roots[ENGINE] + n for n in (*ENGINE_BUILD, ".git/HEAD", ".git/shallow")]
    problems += [f"{n}: нет в архиве" for n in required if n not in found]
    if voice < 3:
        problems.append("voice/models: нет моделей голоса")
    return problems


def personal_items():
    """(path on this PC, name in the copy)."""
    return [(CONFIG / "session.env", "config/session.env"),
            (ROOT / "gateway/ca", "ca"),
            (ROOT / "agent/state", "state"),
            (HOME / "Nexus", "workspace")]


def lean(info):
    """Leave out what a task rebuilds by itself: the agent's .venv and node_modules are 0.5 GB."""
    return None if REBUILT & set(Path(info.name).parts) else info


def backup(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    for left in folder.glob(".nexus-personal-*.part"):  # from a copy that was interrupted
        left.unlink()
    while (target := folder / f"nexus-personal-{time.strftime('%Y-%m-%d-%H%M%S')}.tar.gz").exists():
        time.sleep(1)  # never over a copy made the same second
    part = folder / f".{target.name}.part"  # the copy gets its name only when it is whole
    old = os.umask(0o077)
    try:
        with tarfile.open(part, "w:gz") as archive:
            for path, name in personal_items():
                if path.exists():
                    archive.add(path, arcname=name, filter=lean)
                    print(f"  {name}")
                else:
                    print(f"  {name}: нет на этом ПК, пропущено")
        os.replace(part, target)
    finally:
        os.umask(old)
        part.unlink(missing_ok=True)  # still here only if the copy failed
    os.chmod(target, 0o600)
    copies = sorted(folder.glob("nexus-personal-*.tar.gz"))
    for stale in copies[:-3]:  # the three newest stay
        stale.unlink()
    print(f"Личная копия: {target} ({target.stat().st_size / 1024 / 1024:.0f} МБ). Хранить у себя, никому не отправлять.")
    return 0


def restore(file):
    # Keys last: once session.env is back, so is everything else (./install's keys step looks at it).
    places = {name: path for path, name in reversed(personal_items())}
    restored, kept, skipped = [], [], []

    def place(member):
        return next((n for n in places if member.name == n or member.name.startswith(n + "/")), None)

    def safe(member, destination):  # a link leading out of its place is left out, not followed
        try:
            return tarfile.data_filter(member, destination)
        except tarfile.FilterError:
            skipped.append(member.name)
            return None

    with tarfile.open(file) as archive:
        members = archive.getmembers()
        strangers = [m.name for m in members if place(m) is None or m.isdev()]
        if strangers:
            print(f"Чужой файл в копии: {strangers[0]}. Восстановление отменено.")
            return 1
        for name, path in places.items():
            mine = [m for m in members if place(m) == name]
            if not mine:
                continue
            temp = path.parent / f".{path.name}.restore"  # left by an interrupted restore: started again
            shutil.rmtree(temp, ignore_errors=True)
            if path.exists() and (not path.is_dir() or any(path.iterdir())):
                kept.append(name)
                continue
            temp.mkdir(parents=True)
            for member in mine:
                member = member.replace(name=str(Path(path.name) / Path(member.name).relative_to(name)))
                archive.extract(member, temp, filter=safe)
            if os.path.lexists(temp / path.name):
                os.replace(temp / path.name, path)  # whole or not at all: half a folder never looks restored
                restored.append(name)
            temp.rmdir()
    if (CONFIG / "session.env").exists():
        os.chmod(CONFIG / "session.env", 0o600)
    for name in restored:
        print(f"  восстановлено: {name}")
    for name in kept:
        print(f"  уже есть, не тронуто: {name}")
    if skipped:
        print(f"  пропущено ссылок наружу: {len(skipped)}")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("scan", "scan-own", "backup", "restore"):
        print(__doc__.strip())
        return 2
    if argv[0] in ("scan", "scan-own"):
        problems = scan(argv[1]) if argv[0] == "scan" else scan_own(argv[1], str(ROOT.relative_to(HOME)))
        for line in problems:
            print(f"  {line}")
        return 1 if problems else 0
    return backup(argv[1]) if argv[0] == "backup" else restore(argv[1])


if __name__ == "__main__":
    sys.exit(main())
