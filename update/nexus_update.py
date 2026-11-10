#!/usr/bin/env python3
"""Component updates; no LLM requests, model downloads or secret-file reads."""
import argparse
import ast
import concurrent.futures
import contextlib
import fcntl
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from pathlib import Path


PACKAGE = "@openhands/agent-canvas"
# Our page wraps Canvas components: React, the router and i18n must be the one copy Canvas also uses,
# or its hooks find no context and the page stays blank.
SHARED = ("react", "react-dom", "react-router", "i18next", "react-i18next", "lucide-react")
COMPONENTS = ("canvas", "ik-llama", "caddy", "llama-swap", "voice")
UNKNOWN = "unknown (неизвестно)"
GITHUB = "https://api.github.com/repos"
FORBIDDEN = {".env", "session.env", "secrets.json", "settings.json"}


class UpdateError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise UpdateError(message)


def read_json(path):
    return json.loads(Path(path).read_text())


def atomic_json(path, data):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


def copy_tree(source, target):
    require(not Path(target).is_symlink(), f"Символическая ссылка вместо каталога: {target}")
    if Path(target).exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, symlinks=True,
                    ignore=shutil.ignore_patterns(*FORBIDDEN, ".env.*", "*.bak*"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest_like(path, expected):
    """Сумма файла тем же алгоритмом, каким записана ожидаемая: Caddy 2.11.9 публикует SHA-512, остальные SHA-256."""
    algorithm = {64: hashlib.sha256, 128: hashlib.sha512}.get(len(expected))
    return algorithm(Path(path).read_bytes()).hexdigest() if algorithm else ""


class Updater:
    def __init__(self, args):
        self.args = args
        self.root = Path(__file__).resolve().parent.parent
        self.backend = Path.home() / "backend/ik_llama-fresh"
        self.state = Path.home() / ".local/state/ohn"
        self.backups = Path.home() / "Agents/Backups"
        if args.sandbox:
            root = Path(args.sandbox).resolve()
            require(root.parent == Path("/tmp") and root.name.startswith("nexus-update-test."),
                    "--sandbox допускает только /tmp/nexus-update-test.*")
            require(args.command == "canvas" or
                    (args.command == "rollback" and args.target == "canvas"),
                    "--sandbox предназначен только для canvas и его отката")
            self.root, self.state, self.backups = root, root / "update-state", root / "backups"
        self.log = None
        self.found = {}  # service → its state before this run first stopped or restarted it

    def emit(self, message):
        # A closed terminal or pipe must not stop an update halfway or skip its rollback: the journal goes on.
        try:
            print(message, flush=True)
        except OSError:
            sys.stdout = open(os.devnull, "w")
        if self.log:
            self.log.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(message) + "\n")
            self.log.flush()

    def run(self, command, *, cwd=None, env=None, timeout=1800, capture=False, include_stderr=False):
        if not capture:
            self.emit("$ " + shlex.join(map(str, command)))
        child_env = os.environ.copy()
        child_env.update(env or {})
        with tempfile.TemporaryFile(mode="w+b") as output, tempfile.TemporaryFile(mode="w+b") as errors:
            process = subprocess.Popen(list(map(str, command)), cwd=cwd, env=child_env,
                                       stdout=output, stderr=errors if capture else subprocess.STDOUT,
                                       start_new_session=True)
            offset = 0
            began = time.monotonic()
            # A separate open description: reading must not seek the child's stdout.
            with open(f"/proc/self/fd/{output.fileno()}", "rb") as reader:
                try:
                    while process.poll() is None:
                        if time.monotonic() - began > timeout:
                            raise UpdateError("Превышено время выполнения: " + str(command[0]))
                        if not capture:
                            chunk = reader.read()
                            offset += len(chunk)
                            if chunk:
                                self.emit(chunk.decode(errors="replace").rstrip())
                        time.sleep(0.1)
                except BaseException:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    raise
            output.seek(0)
            text = output.read().decode(errors="replace")
            if include_stderr:
                errors.seek(0)
                text += errors.read().decode(errors="replace")
            if not capture and len(text.encode()) > offset:
                self.emit(text.encode()[offset:].decode(errors="replace").rstrip())
            require(process.returncode == 0,
                    f"Команда {Path(str(command[0])).name} завершилась с кодом {process.returncode}")
            return text.strip()

    def installed_canvas(self):
        values = []
        for name in ("agent", "ui"):
            base = self.root / name
            installed = read_json(base / "node_modules" / PACKAGE / "package.json")["version"]
            declared = read_json(base / "package.json")["dependencies"][PACKAGE]
            locked = read_json(base / "package-lock.json")["packages"]["node_modules/" + PACKAGE]["version"]
            require(installed == declared == locked,
                    f"{name}: package.json, lock и установленный canvas не совпадают")
            values.append(installed)
        require(values[0] == values[1], "Версии canvas в двух проектах различаются")
        return values[0]

    def fetch_json(self, url):
        require(not self.args.offline, "Сеть отключена флагом --offline")
        headers = {"User-Agent": "nexus-update", "Accept": "application/json"}
        if url.startswith(GITHUB) and (token := self.github_token()):
            # The anonymous limit is 60 requests an hour per address, shared by everyone behind the VPN exit.
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)

    def github_token(self):
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token and shutil.which("gh"):
            result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
            token = result.stdout.strip() if result.returncode == 0 else ""
        return token

    def npm_metadata(self, version="latest"):
        require(not self.args.offline, "Сеть отключена флагом --offline")
        with tempfile.TemporaryDirectory(prefix="nexus-update-npm.") as cache:
            text = self.run(["npm", "view", f"{PACKAGE}@{version}", "version", "dist.tarball", "--json",
                             "--fetch-timeout=15000", "--fetch-retries=0"],
                            env={"npm_config_cache": cache}, capture=True, timeout=25)
        data = json.loads(text)
        require(isinstance(data, dict) and re.fullmatch(r"\d+\.\d+\.\d+(?:-[\w.-]+)?", data["version"]),
                "npm не вернул единственную точную версию")
        return data

    def canvas_pins(self, version):
        base = self.root / "agent/node_modules" / PACKAGE
        if version == read_json(base / "package.json")["version"]:
            return read_json(base / "config/defaults.json")["versions"]
        meta = self.npm_metadata(version)
        require(meta["dist.tarball"].startswith("https://registry.npmjs.org/"), "Неожиданный адрес npm tarball")
        with urllib.request.urlopen(meta["dist.tarball"], timeout=20) as stream:
            with tarfile.open(fileobj=stream, mode="r|gz") as archive:
                for member in archive:
                    if member.name == "package/config/defaults.json":
                        require(member.size < 1024 * 1024, "Слишком большой defaults.json")
                        return json.load(archive.extractfile(member))["versions"]
        raise UpdateError("В пакете нет config/defaults.json")

    def check(self):
        def canvas():
            try:
                installed = self.installed_canvas()
                current = self.canvas_pins(installed)
            except (OSError, KeyError, ValueError, UpdateError):
                installed, current = "несогласовано/не установлен", {}
            available, pins = UNKNOWN, {}
            with contextlib.suppress(Exception):
                available = self.npm_metadata()["version"]
                pins = self.canvas_pins(available)
            return [("canvas (оба проекта)", installed, available),
                    ("agent-server (pin)", current.get("agentServer", UNKNOWN), pins.get("agentServer", UNKNOWN)),
                    ("automation (pin)", current.get("automation", UNKNOWN), pins.get("automation", UNKNOWN))]

        def ik():
            installed = self.run(["git", "rev-parse", "HEAD"], cwd=self.backend, capture=True, timeout=5)
            require(not self.args.offline, "offline")
            remote = self.run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=self.backend,
                              env={"GIT_TERMINAL_PROMPT": "0"}, capture=True, timeout=20).split()[0]
            behind = UNKNOWN
            try:
                behind = self.run(["git", "rev-list", "--count", f"{installed}..{remote}"],
                                  cwd=self.backend, capture=True, timeout=5)
            except UpdateError:
                with contextlib.suppress(Exception):
                    data = self.fetch_json(f"{GITHUB}/ikawrakow/ik_llama.cpp/compare/{installed}...{remote}")
                    behind = str(data["ahead_by"]) if not data["behind_by"] else "ветки разошлись"
            return [("ik_llama", installed[:12], f"{remote[:12]}; отставание: {behind}")]

        def caddy():
            installed = self.run([self.root / "gateway/caddy", "version"], capture=True, timeout=10).split()[0]
            available = UNKNOWN
            with contextlib.suppress(Exception):
                available = self.fetch_json(f"{GITHUB}/caddyserver/caddy/releases/latest")["tag_name"]
            return [("Caddy", installed, available)]

        def llama_swap():
            output = self.run([self.root / "models/llama-swap", "--version"], capture=True, timeout=10)
            installed = re.search(r"v\d+", output)[0]
            available = UNKNOWN
            with contextlib.suppress(Exception):
                available = self.fetch_json(f"{GITHUB}/mostlygeek/llama-swap/releases/latest")["tag_name"]
            return [("llama-swap", installed, available)]

        def voice():
            project = self.root / "voice"
            lock = tomllib.loads((project / "uv.lock").read_text())
            packages = {p["name"]: p["version"] for p in lock["package"]}
            environment = "uv.lock"
            with contextlib.suppress(Exception):
                installed = self.run([project / ".venv/bin/python", "-I", "-B", "-c",
                    'import importlib.metadata as m,json; print(json.dumps({n:m.version(n) for n in ("torch","gigaam","fastapi")}))'],
                    capture=True, timeout=10)
                packages = json.loads(installed)
                environment = ".venv"
            installed = ", ".join(f"{n}={packages.get(n, '?')}" for n in ("torch", "gigaam", "fastapi"))
            available = UNKNOWN
            if not self.args.offline:
                before = digest(project / "uv.lock")
                with contextlib.suppress(Exception):
                    output = self.run(["uv", "lock", "--upgrade", "--dry-run", "--no-python-downloads",
                                       "--python", project / ".venv/bin/python"], cwd=project, capture=True,
                                      include_stderr=True, timeout=45)
                    changes = [s.strip() for s in output.splitlines() if re.match(r"(?:Would |Update[d]? |Add(?:ed)? |Remove[d]? )", s)]
                    available = "; ".join(changes) or "resolver завершился; изменений не сообщил"
                require(digest(project / "uv.lock") == before, "Проверка неожиданно изменила uv.lock")
            return [(f"Voice ({environment})", installed, available)]

        def screen():
            # Pinned in screen/pyproject.toml: a new version is a deliberate pin change.
            installed = self.run([self.root / "screen/.venv/bin/desk", "--version"], capture=True, timeout=10).split()[-1]
            available = UNKNOWN
            if not self.args.offline:
                with contextlib.suppress(Exception):
                    available = self.fetch_json("https://pypi.org/pypi/hai-drivers/json")["info"]["version"]
            return [("Screen (hai-drivers)", installed, available)]

        def safe(label, function):
            try:
                return function()
            except Exception:
                if label == "ik_llama":
                    with contextlib.suppress(Exception):
                        return [(label, self.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.backend,
                                                capture=True, timeout=5), UNKNOWN)]
                return [(label, UNKNOWN, UNKNOWN)]

        tasks = [("canvas", canvas), ("ik_llama", ik), ("Caddy", caddy), ("llama-swap", llama_swap), ("Voice", voice),
                 ("Screen", screen)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda pair: safe(*pair), tasks))
        self.emit("Компонент | Установлено | Доступно")
        for rows in results:
            for row in rows:
                self.emit(" | ".join(row))
        self.emit("agent-server/automation следуют canvas; модель и GGUF не проверяются.")
        for kind in COMPONENTS:
            if self.pending(kind).is_file():
                self.emit(f"ВНИМАНИЕ: обновление {kind} оборвалось на полпути. Вернуть прежнее состояние: "
                          f"nexus-update rollback {kind}")

    def snapshot(self, kind, items):
        self.backups.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix=time.strftime(f"update-%Y%m%d-%H%M%S-{kind}-"), dir=self.backups))
        self.emit(f"Резервная копия: {backup}")
        manifest = {"owner": "nexus-update-v1", "component": kind, "root": str(self.root), "items": []}
        try:
            for source, name in items:
                source = Path(source)
                require(not source.is_symlink(), f"Недопустимая ссылка: {source}")
                exists = source.exists()
                manifest["items"].append({"path": str(source), "name": name, "exists": exists, "directory": source.is_dir()})
                if exists:
                    if source.is_dir():
                        shutil.copytree(source, backup / name, symlinks=True,
                                        ignore=shutil.ignore_patterns(*FORBIDDEN, ".env.*", "*.bak*"))
                    else:
                        shutil.copy2(source, backup / name)
            atomic_json(backup / "manifest.json", manifest)
        except BaseException:
            shutil.rmtree(backup, ignore_errors=True)  # half a copy (a full disk) restores nothing
            raise
        return backup

    def pending(self, kind):
        return self.state / f"update-{kind}.pending.json"

    def begin(self, kind, backup):
        """From here to `finish` the component may be half changed. The mark outlives a kill and a power
        cut: `rollback` then returns the files from this copy, and a new update waits for that."""
        atomic_json(self.pending(kind), {"backup": str(backup)})

    def finish(self, kind):
        self.pending(kind).unlink(missing_ok=True)

    def remember(self, kind, backup):
        path = self.state / f"update-{kind}.json"
        stale = read_json(path)["backup"] if path.is_file() else None
        atomic_json(path, {"backup": str(backup)})
        # Rollback only ever uses the remembered copy: the one it replaces is dead weight.
        if stale and Path(stale) != Path(backup):
            self.discard(stale)

    def discard(self, backup):
        backup = Path(backup).resolve()
        if backup.parent == self.backups.resolve() and backup.name.startswith("update-"):
            shutil.rmtree(backup, ignore_errors=True)

    def previous(self, kind):
        """The copy `rollback` restores: of an update that stopped halfway, else of the last finished one."""
        path = self.pending(kind) if self.pending(kind).is_file() else self.state / f"update-{kind}.json"
        require(path.is_file(), f"Нет сохранённого обновления {kind} для отката")
        backup = Path(read_json(path)["backup"]).resolve()
        require(backup.parent == self.backups.resolve() and backup.name.startswith("update-"), "Некорректная копия")
        require((backup / "manifest.json").is_file(), f"Копии {backup} нет; запись о ней: {path}")
        manifest = read_json(backup / "manifest.json")
        require(manifest["owner"] == "nexus-update-v1" and manifest["component"] == kind and
                manifest["root"] == str(self.root), "Резервная копия относится к другой установке")
        return backup

    def restore_files(self, backup):
        for item in read_json(backup / "manifest.json")["items"]:
            path = Path(item["path"])
            require(not path.is_symlink(), f"Недопустимая ссылка: {path}")
            if item["exists"]:
                if item["directory"]:
                    copy_tree(backup / item["name"], path)
                else:
                    # Replacing an inode also works while Caddy executes the old binary.
                    temporary = path.with_name(path.name + ".restore-" + uuid.uuid4().hex)
                    try:
                        shutil.copy2(backup / item["name"], temporary)
                        os.replace(temporary, path)
                    finally:
                        temporary.unlink(missing_ok=True)
            elif path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)

    def transaction(self, kind, backup, action, restore):
        self.begin(kind, backup)
        try:
            action()
            self.remember(kind, backup)
        except BaseException:
            self.emit(f"Ошибка {kind}; восстанавливаю предыдущую версию.")
            try:
                restore(backup)
                self.emit("Автоматический откат завершён; обновление НЕ выполнено.")
                self.finish(kind)
                self.discard(backup)
            except BaseException as error:
                self.emit(f"ОШИБКА ОТКАТА: {error}. Копия цела: {backup}. Повторить откат: nexus-update rollback {kind}")
            raise
        self.finish(kind)
        self.emit(f"Обновление {kind} завершено.")

    def unit_state(self, unit):
        return self.run(["systemctl", "--user", "show", "--property=ActiveState", "--value", unit],
                        capture=True, timeout=10)

    def note(self, unit):
        """Called before a service is first stopped or restarted: `settle` needs the state it was found in."""
        if unit not in self.found:
            self.found[unit] = self.unit_state(unit)

    def settle(self):
        """An update starts services only for its checks: what it found stopped does not stay running
        (the GPUs and the PC may be busy with something else; Nexus starts by its shortcut)."""
        for unit, state in self.found.items():
            if state in {"inactive", "failed"}:
                self.emit(f"{unit} до обновления не работал: останавливаю снова.")
                try:
                    self.run(["systemctl", "--user", "stop", unit], timeout=120)
                except UpdateError as error:
                    self.emit(f"Не удалось остановить {unit}: {error}")
        self.found = {}

    def restart(self, *units):
        if self.args.sandbox:
            self.emit("Песочница: службы, health и API smoke пропущены.")
            return
        for unit in units:
            require(unit in {"ohn-agent", "ohn-gateway", "ohn-voice", "ohn-models"}, "Недопустимая служба")
            self.note(unit)
            # Quick update + rollback restarts can trip systemd's start limit.
            try:
                self.run(["systemctl", "--user", "reset-failed", unit], timeout=30)
            except UpdateError:  # служба ещё ни разу не загружалась (Nexus не запускали) — сбрасывать нечего
                pass
            self.run(["systemctl", "--user", "restart", unit], timeout=120)

    def curl(self, url, *, body=None, method=None, missing_ok=False):
        # No headers/response bodies enter the update log; settings may contain keys.
        command = ["curl", "--noproxy", "*", "--silent", "--show-error",
                   "--connect-timeout", "3", "--max-time", "15", "--insecure", "--write-out", "\n%{http_code}"]
        if method:
            command += ["--request", method]
        if body is not None:
            command += ["--header", "Content-Type: application/json", "--data-binary", "@-"]
        command.append(url)
        result = subprocess.run(command, input=json.dumps(body).encode() if body is not None else None,
                                capture_output=True, timeout=20)
        require(result.returncode == 0, f"HTTP smoke: ошибка curl {result.returncode}; тело ответа скрыто")
        data, _, code = result.stdout.rpartition(b"\n")
        require(code.startswith(b"2") or (missing_ok and code == b"404"),
                f"HTTP smoke: статус {code.decode(errors='replace')}; тело ответа скрыто")
        return data

    def health(self, agent=False, voice=False):
        if self.args.sandbox:
            return
        urls = ["http://127.0.0.1:18010/ready", "https://localhost:8443/"] if agent else ["https://localhost:8443/"]
        if voice:
            urls = ["http://127.0.0.1:18020/health"]
        for url in urls:
            deadline = time.monotonic() + (300 if agent or voice else 60)
            while True:
                try:
                    data = self.curl(url)
                    if voice:
                        require(json.loads(data).get("ready") is True, "Голосовые модели ещё не готовы")
                    break
                except (UpdateError, ValueError, subprocess.TimeoutExpired):
                    if time.monotonic() >= deadline:
                        raise UpdateError(f"Health не прошёл: {url}") from None
                    time.sleep(2)
            self.emit(f"Health OK: {url}")

    def guard_hooks(self):
        # The server owns the guard; the UI no longer embeds hooks in conversations.ts.
        # Read the declaration without importing sitecustomize (which patches Python imports).
        source = self.root / "agent/sdk-patch/sitecustomize.py"
        tree = ast.parse(source.read_text())
        matcher = next((ast.literal_eval(node.value) for node in tree.body
                        if isinstance(node, ast.Assign) and any(
                            isinstance(target, ast.Name) and target.id == "GUARD_TOOLS"
                            for target in node.targets)), None)
        require(isinstance(matcher, str) and "terminal" in matcher.split("|"),
                "Контракт GUARD_TOOLS сервера изменён; нужна проверка smoke")
        guard = self.root / "guard/guard.py"
        require(guard.is_file(), "Нет guard.py")
        return {"pre_tool_use": [{"matcher": matcher, "hooks": [{"type": "command",
                "command": "/usr/bin/python3 -I " + shlex.quote(str(guard)), "timeout": 10}]}]}

    def canvas_smoke(self):
        if self.args.sandbox:
            return
        base = "https://localhost:8443/api"
        settings = json.loads(self.curl(base + "/settings")).get("agent_settings")
        require(isinstance(settings, dict) and isinstance(settings.get("llm"), dict), "Нет agent_settings.llm")
        llm = settings["llm"]
        require(urllib.parse.urlparse(llm.get("base_url", "")).hostname in {"localhost", "127.0.0.1", "::1"},
                "Smoke допускает только локальный LLM URL; вызовов LLM не будет")
        if not llm.get("api_key") or "*" in llm["api_key"]:
            llm["api_key"] = "not-needed"
        hooks = self.guard_hooks()
        ident = str(uuid.uuid4())
        with tempfile.TemporaryDirectory(prefix="nexus-update-smoke.") as workspace:
            try:
                created = json.loads(self.curl(base + "/conversations", body={
                    "conversation_id": ident, "agent_settings": settings,
                    "workspace": {"working_dir": workspace}, "hook_config": hooks, "autotitle": False}))
                require(created.get("id") == ident, "API не подтвердил ID тестовой беседы")
                saved = json.loads(self.curl(base + "/conversations/" + ident))
                # The API shows hook_config only for a running conversation; the stored copy is meta.json.
                meta = Path(created.get("persistence_dir") or "/nonexistent") / "meta.json"
                require(meta.resolve().is_relative_to((self.root / "agent/state").resolve()) and meta.is_file(),
                        "Нет meta.json тестовой беседы")
                actual = (read_json(meta).get("hook_config") or {}).get("pre_tool_use", [])
                for expected in hooks["pre_tool_use"]:
                    require(any(rule.get("matcher") == expected["matcher"] and
                                all(any(all(saved_hook.get(key) == value for key, value in hook.items())
                                            for saved_hook in rule.get("hooks", [])) for hook in expected["hooks"])
                                for rule in actual), "Сервер не сохранил guard hook_config")
                require(saved.get("execution_status") in {None, "idle"}, "Тестовая беседа неожиданно запущена")
                self.emit("Smoke OK: беседа создана, guard hook_config сохранён; сообщения/LLM не отправлялись.")
            finally:
                self.curl(base + "/conversations/" + ident, method="DELETE", missing_ok=True)
                self.emit("Тестовая беседа удалена.")

    def locale_report(self):
        try:
            en = read_json(self.root / "ui/node_modules" / PACKAGE / "dist/locales/en/openhands.json")
            ru = read_json(self.root / "ui/src/locales/ru.json")
        except (OSError, ValueError):
            self.emit("Предупреждение: формат/путь словарей изменился; пробелы локали неизвестны.")
            return
        missing = sorted(set(en) - set(ru))
        self.emit(f"Русская локаль: отсутствует {len(missing)} ключей из текущего canvas.")
        for key in missing:
            self.emit("  " + key)

    def canvas_restore(self, backup):
        self.canvas_paths()
        if not self.args.sandbox:
            # The running server holds the automation database open.
            self.note("ohn-agent")
            self.run(["systemctl", "--user", "stop", "ohn-agent"], timeout=120)
        self.restore_files(backup)
        self.installed_canvas()
        try:
            self.run(["npm", "run", "build"], cwd=self.root / "ui")
        except BaseException:
            # Vite empties dist before building; leave the last known working assets.
            if (backup / "ui-dist").is_dir():
                copy_tree(backup / "ui-dist", self.root / "ui/dist")
            self.restart("ohn-agent", "ohn-gateway")
            self.health(agent=True)
            raise
        self.restart("ohn-agent", "ohn-gateway")
        self.health(agent=True)

    def canvas(self):
        self.canvas_paths()
        self.installed_canvas()
        self.guard_hooks()  # Fail before installing anything if the local contract is broken.
        version = self.npm_metadata(self.args.target or "latest")["version"]
        items = []
        for project in ("agent", "ui"):
            for name in ("package.json", "package-lock.json", "node_modules"):
                items.append((self.root / project / name, project + "-" + name))
        items.append((self.root / "ui/dist", "ui-dist"))
        # automation migrates its SQLite schema on start; the old version refuses the new schema.
        items.append((self.root / "agent/state/automation", "state-automation"))
        backup = self.canvas_snapshot(items)

        def action():
            for project in ("agent", "ui"):
                self.run(["npm", "install", "--save-exact", "--ignore-scripts", "--no-audit", "--no-fund",
                          f"{PACKAGE}@{version}"], cwd=self.root / project)
            self.canvas_shared()
            require(self.installed_canvas() == version, "Установлена неожиданная версия canvas")
            self.run(["npm", "run", "build"], cwd=self.root / "ui")
            self.locale_report()
            self.restart("ohn-agent", "ohn-gateway")
            self.health(agent=True)
            self.canvas_smoke()

        self.transaction("canvas", backup, action, self.canvas_restore)

    def canvas_shared(self):
        ui = self.root / "ui"
        wanted = read_json(ui / "node_modules" / PACKAGE / "package.json").get("dependencies", {})
        ours = read_json(ui / "package.json").get("dependencies", {})
        stale = [f"{name}@{wanted[name]}" for name in SHARED if name in wanted and ours.get(name, wanted[name]) != wanted[name]]
        if stale:
            self.run(["npm", "install", "--save-exact", "--ignore-scripts", "--no-audit", "--no-fund", *stale], cwd=ui)
        nested = [name for name in SHARED if (ui / "node_modules" / PACKAGE / "node_modules" / name).exists()]
        require(not nested, "Canvas держит свою копию " + ", ".join(nested) + ": страница не заработает")

    def canvas_snapshot(self, items):
        # Copying a live SQLite DB and its WAL separately can produce an invalid rollback.
        # Stop the writer before the snapshot, not only before restoring it.
        was_active = False
        if not self.args.sandbox:
            self.note("ohn-agent")
            state = self.found["ohn-agent"]
            require(state in {"active", "inactive", "failed"}, "ohn-agent меняет состояние; повторите обновление позже")
            was_active = state == "active"
            self.run(["systemctl", "--user", "stop", "ohn-agent"], timeout=120)
        try:
            return self.snapshot("canvas", items)
        except BaseException:
            if was_active:
                self.restart("ohn-agent")
            raise

    def canvas_paths(self):
        for name in ("agent", "ui"):
            directory = self.root / name
            require(directory.is_dir() and not directory.is_symlink() and directory.resolve().is_relative_to(self.root),
                    f"Нужна независимая рабочая копия {name}, без ссылки на живое дерево")
        # Stopping ohn-agent kills everything started from the agent's terminal, this update included.
        require(self.args.sandbox or "/ohn-agent.service" not in Path("/proc/self/cgroup").read_text(),
                "Canvas обновляется с остановкой агента, а команда запущена из его терминала и оборвётся на полпути. "
                f"Запустите её отдельно: systemd-run --user --collect {self.root}/launcher/when-idle "
                f"{self.root}/update/nexus-update {self.args.command} {self.args.target or ''}".rstrip())

    def models_idle(self, bench=False):
        require(self.unit_state("ohn-models") in {"inactive", "failed"},
                "ohn-models активен или его состояние неизвестно; отказ")
        sockets = self.run(["ss", "-H", "-lntu", "( sport = :18030 )"], capture=True, timeout=10)
        require(not sockets, "Порт 18030 занят; отказ")
        processes = self.run(["nvidia-smi", "--query-compute-apps=pid,process_name", "--format=csv,noheader,nounits"],
                             capture=True, timeout=15)
        for line in processes.splitlines():
            pid, _, name = line.partition(",")
            if "llama-server" in name:
                # Only our engine is swapped; another program's own llama-server copy keeps running untouched.
                try:
                    exe = Path(os.readlink(f"/proc/{pid.strip()}/exe")).resolve()
                except (OSError, ValueError):
                    exe = None
                require(exe is not None and not exe.is_relative_to(self.backend.resolve()),
                        "На видеокарте работает llama-server этого движка; отказ")
        if bench:
            require(not processes.strip(), "GPU заняты вычислениями; benchmark запрещён")
            load = self.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                            capture=True, timeout=15)
            rows = [list(map(int, line.split(","))) for line in load.splitlines()]
            require(rows and all(util <= 5 and memory <= 1024 for util, memory in rows),
                    "GPU заняты: загрузка >5% или память >1024 МиБ; benchmark запрещён")

    def cmake_flags(self):
        cache = (self.backend / "build/CMakeCache.txt").read_text()
        values = {}
        for line in cache.splitlines():
            match = re.match(r"([^:#/]+):([^=]+)=(.*)", line)
            if not match:
                continue
            key, kind, value = match.groups()
            if kind not in {"BOOL", "STRING", "FILEPATH", "PATH", "UNINITIALIZED"}:
                continue
            if key.startswith(("GGML_", "LLAMA_", "CMAKE_C_FLAGS", "CMAKE_CXX_FLAGS", "CMAKE_CUDA_FLAGS",
                               "CMAKE_EXE_LINKER_FLAGS", "CMAKE_SHARED_LINKER_FLAGS")) or key in {
                    "BUILD_SHARED_LIBS", "CMAKE_BUILD_TYPE", "CMAKE_C_COMPILER", "CMAKE_CXX_COMPILER",
                    "CMAKE_CUDA_COMPILER", "CMAKE_CUDA_ARCHITECTURES", "CMAKE_CUDA_HOST_COMPILER",
                    "CMAKE_C_FLAGS", "CMAKE_CXX_FLAGS", "CMAKE_CUDA_FLAGS", "CMAKE_INSTALL_PREFIX"}:
                if key.endswith("_FOUND"):
                    continue
                values[key] = (kind, value)
        require(values.get("GGML_CUDA", (None, None))[1] == "ON", "В текущем cache не включена CUDA")
        generator = re.search(r"^CMAKE_GENERATOR:INTERNAL=(.*)$", cache, re.M)
        require(generator, "В cache нет CMAKE_GENERATOR")
        # Absolute RUNPATHs in the old build break when the directory is renamed.
        values["CMAKE_BUILD_RPATH_USE_ORIGIN"] = ("BOOL", "ON")
        return ["-G", generator[1]] + [f"-D{key}:{kind}={value}" for key, (kind, value) in values.items()]

    def ik_llama(self):
        self.models_idle(bench=bool(self.args.bench))
        require(not self.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=self.backend, capture=True),
                "Есть изменения tracked-файлов ik_llama; обновление запрещено")
        old = self.run(["git", "rev-parse", "HEAD"], cwd=self.backend, capture=True)
        flags = self.cmake_flags()
        size = int(self.run(["du", "-sk", self.backend / "build"], capture=True).split()[0]) * 1024
        need = max(4 * 1024**3, 2 * size + 1024**3)
        require(shutil.disk_usage(self.backend).free >= need, f"Для сборки нужно свободно не менее {need // 1024**3} ГиБ")
        bench = Path(self.args.bench).resolve() if self.args.bench else None
        if bench:
            require(bench.is_file() and bench.suffix.lower() == ".gguf", "--bench требует существующий MODEL.gguf")
        previous_commit = self.backend.with_name(self.backend.name + ".prev-commit")
        backup = self.snapshot("ik-llama", [(previous_commit, "previous-commit-file")])
        atomic_json(backup / "ik.json", {"commit": old, "binary_sha256": digest(self.backend / "build/bin/llama-server"),
                                          "cmake_flags": flags})
        stage = self.backend / ("build.next-" + uuid.uuid4().hex)
        previous = self.backend / "build.prev"
        retired = self.backend / ("build.retired-" + uuid.uuid4().hex)
        self.begin("ik-llama", backup)
        try:
            previous_commit.write_text(old + "\n")
            self.run(["git", "fetch", "--no-tags", "origin", (self.args.target or "main").removeprefix("origin/")], cwd=self.backend)
            target = self.run(["git", "rev-parse", "--verify", "FETCH_HEAD^{commit}"], cwd=self.backend, capture=True)
            self.run(["git", "checkout", "--detach", target], cwd=self.backend)
            self.run(["cmake", "-S", self.backend, "-B", stage, *flags])
            # All threads at the lowest priority: fast build, the desktop stays responsive.
            self.run(["nice", "-n", "19", "cmake", "--build", stage, "--parallel", str(os.cpu_count() or 2)],
                     timeout=14400)
            self.models_idle(bench=bool(bench))
            self.run([stage / "bin/llama-server", "--version"], timeout=30,
                     env={"NCCL_SOCKET_IFNAME": "lo"})
            self.models_idle(bench=bool(bench))
            if previous.exists():
                require(not any(previous.rglob("*.gguf")), "GGUF найден в build.prev; удаление запрещено")
                previous.rename(retired)
            (self.backend / "build").rename(previous)
            stage.rename(self.backend / "build")
            self.run([self.backend / "build/bin/llama-server", "--version"], timeout=30,
                     env={"NCCL_SOCKET_IFNAME": "lo"})
            if bench:
                self.models_idle(bench=True)
                self.run([self.backend / "build/bin/llama-bench", "-m", bench, "-p", "64", "-n", "16", "-r", "1"],
                         timeout=300, env={"NCCL_SOCKET_IFNAME": "lo"})
            self.remember("ik-llama", backup)
        except BaseException:
            self.emit("Ошибка ik_llama; возвращаю исходный commit и build.")
            self.ik_llama_undo(backup)
            raise
        self.finish("ik-llama")
        if retired.exists():
            shutil.rmtree(retired)
        self.emit("ik_llama собран и заменён; build.prev сохранён. Модель НЕ запускалась.")

    def ik_llama_undo(self, backup):
        """Back to the commit and the build an unfinished update started from. Where it stopped is read
        from the disk, so this also works after a kill or a power cut (`rollback`)."""
        metadata = read_json(backup / "ik.json")
        build, previous = self.backend / "build", self.backend / "build.prev"

        def original(directory):
            binary = directory / "bin/llama-server"
            return binary.is_file() and digest(binary) == metadata["binary_sha256"]

        for stage in self.backend.glob("build.next-*"):
            shutil.rmtree(stage)
        if not original(build):
            # The swap began: build.prev is the build to return, build (if there) the new, unchecked one.
            require(original(previous), "Прежний llama-server не найден ни в build, ни в build.prev")
            if build.exists():
                require(not any(build.rglob("*.gguf")), "GGUF найден в build; удаление запрещено")
                shutil.rmtree(build)
            previous.rename(build)
        retired = sorted(self.backend.glob("build.retired-*"))
        if retired and not previous.exists():
            retired[0].rename(previous)
        self.run(["git", "checkout", "--detach", metadata["commit"]], cwd=self.backend)
        self.restore_files(backup)
        self.finish("ik-llama")
        self.discard(backup)

    def caddy_environment(self):
        lan = os.environ.get("OHN_LAN_IP")
        published = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "ohn-lan-ip"
        if not lan and published.is_file():
            # launcher publishes this non-secret value after applying its own override.
            lan = published.read_text().strip()
        if not lan:
            addresses = self.run(["ip", "-4", "-o", "addr", "show", "scope", "global"], capture=True)
            for line in addresses.splitlines():
                fields = line.split()
                if len(fields) > 3 and not re.match(r"^(tun|tap|wg|docker|br-|virbr|veth)", fields[1]):
                    ip = fields[3].split("/")[0]
                    if re.match(r"^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)", ip):
                        lan = ip
                        break
        require(lan, "Нет LAN IP; задайте OHN_LAN_IP")
        require(re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", lan), "Некорректный опубликованный LAN IP")
        base = self.root / "gateway"
        return {"LAN_IP": lan, "XDG_DATA_HOME": str(base / "data"), "XDG_CONFIG_HOME": str(base / "config"),
                "CA_DIR": str(base / "ca"), "LOG_DIR": str(base), "SHELL_DIST": str(self.root / "ui/dist"),
                # Validation needs the placeholder, not the actual session credential.
                "OHN_SESSION_KEY": "nexus-update-validation-placeholder"}

    def caddy_restore(self, backup):
        self.restore_files(backup)
        self.restart("ohn-gateway")
        self.health()

    def release_binary(self, repo, binary, base, version_pattern):
        """linux_amd64 archive of a GitHub release, checked against the release checksums.
        Returns the unpacked binary next to the working one; the caller removes it."""
        if self.args.target:
            version = self.args.target.removeprefix("v")
            require(re.fullmatch(version_pattern, version), f"Нужна точная версия {binary}")
            release = self.fetch_json(f"{GITHUB}/{repo}/releases/tags/v{version}")
        else:
            release = self.fetch_json(f"{GITHUB}/{repo}/releases/latest")
            version = release["tag_name"].removeprefix("v")
        archive_name = f"{binary}_{version}_linux_amd64.tar.gz"
        checksum_name = f"{binary}_{version}_checksums.txt"
        assets = {asset["name"]: asset["browser_download_url"] for asset in release["assets"]}
        require(archive_name in assets and checksum_name in assets, "В релизе нет архива/контрольных сумм")
        candidate = base / f"{binary}.next-{uuid.uuid4().hex}"
        try:
            with tempfile.TemporaryDirectory(prefix=f"nexus-update-{binary}.") as temp:
                archive = Path(temp) / archive_name
                checksums = Path(temp) / checksum_name
                for name, destination in [(archive_name, archive), (checksum_name, checksums)]:
                    require(assets[name].startswith(f"https://github.com/{repo}/releases/"), "Неожиданный URL релиза")
                    self.run(["curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
                              "--connect-timeout", "10", "--max-time", "600", "--output", destination, assets[name]], timeout=610)
                expected = [line.split()[0] for line in checksums.read_text().splitlines()
                            if len(line.split()) == 2 and line.split()[1].lstrip("*") == archive_name]
                require(len(expected) == 1 and digest_like(archive, expected[0]) == expected[0], f"SHA-256 архива {binary} не совпал")
                self.emit(f"Контрольная сумма {binary} подтверждена файлом контрольных сумм релиза.")
                with tarfile.open(archive) as tar:
                    member = tar.getmember(binary)
                    require(member.isfile(), f"В архиве {binary} не обычный файл")
                    with candidate.open("wb") as output:
                        shutil.copyfileobj(tar.extractfile(member), output)
            candidate.chmod(0o755)
        except BaseException:
            candidate.unlink(missing_ok=True)
            raise
        return candidate

    def caddy(self):
        base = self.root / "gateway"
        candidate = self.release_binary("caddyserver/caddy", "caddy", base, r"\d+\.\d+\.\d+")
        try:
            self.run([candidate, "validate", "--config", base / "Caddyfile", "--adapter", "caddyfile"],
                     env=self.caddy_environment(), timeout=60)
            backup = self.snapshot("caddy", [(base / "caddy", "caddy"), (base / "caddy.prev", "caddy.prev")])

            def action():
                shutil.copy2(base / "caddy", base / "caddy.prev")
                os.replace(candidate, base / "caddy")
                self.restart("ohn-gateway")
                self.health()

            self.transaction("caddy", backup, action, self.caddy_restore)
        finally:
            candidate.unlink(missing_ok=True)

    def models_active(self):
        return self.unit_state("ohn-models") == "active"

    def models_health(self):
        if self.args.sandbox:
            return
        deadline = time.monotonic() + 60
        while True:
            try:
                self.curl("http://127.0.0.1:18030/health")
                return
            except UpdateError:
                require(time.monotonic() < deadline, "llama-swap не ответил на /health за 60 с")
                time.sleep(2)

    def llama_swap_restore(self, backup):
        self.restore_files(backup)
        # Never start the models just for a rollback: the GPUs may belong to another task.
        if self.models_active():
            self.restart("ohn-models")
            self.models_health()

    def llama_swap(self):
        base = self.root / "models"
        candidate = self.release_binary("mostlygeek/llama-swap", "llama-swap", base, r"\d+")
        try:
            self.run([candidate, "--version"], timeout=30)
            backup = self.snapshot("llama-swap", [(base / "llama-swap", "llama-swap"),
                                                  (base / "llama-swap.prev", "llama-swap.prev")])

            def action():
                shutil.copy2(base / "llama-swap", base / "llama-swap.prev")
                os.replace(candidate, base / "llama-swap")
                if self.models_active():
                    self.restart("ohn-models")
                    self.models_health()
                else:
                    self.emit("ohn-models не запущен; новая версия заработает при следующем запуске Nexus.")

            self.transaction("llama-swap", backup, action, self.llama_swap_restore)
        finally:
            candidate.unlink(missing_ok=True)

    def torch_pin(self):
        data = tomllib.loads((self.root / "voice/pyproject.toml").read_text())
        for name in ("torch", "torchaudio"):
            dependencies = [s for s in data["project"]["dependencies"] if re.match(name + r"\s*[<>=]", s)]
            require(len(dependencies) == 1 and re.search(r"<=\s*2\.5\.1(?:\s|,|$)", dependencies[0]),
                    f"Требуется существующий верхний pin {name} <=2.5.1")

    def voice_smoke(self):
        base = "http://127.0.0.1:18020/v1/audio"
        audio = self.curl(base + "/speech", body={"input": "Проверка обновления голосовой службы.",
                                                "voice": "xenia", "response_format": "wav"})
        with wave.open(io.BytesIO(audio)) as wav:
            require(wav.getnframes() / wav.getframerate() > 0.2, "TTS вернул слишком короткий WAV")
        boundary = "nexus-" + uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"smoke.wav\"\r\n"
                "Content-Type: audio/wav\r\n\r\n").encode() + audio + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(base + "/transcriptions", data=body,
                                        headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=60) as response:
            text = json.load(response).get("text", "")
        require(isinstance(text, str) and any(part in text.lower() for part in ("проверк", "обновлен", "голос")),
                "STT не распознал проверочную фразу")
        self.emit("Smoke OK: TTS WAV и распознавание STT проверены.")

    def voice_restore(self, backup):
        self.restore_files(backup)
        self.torch_pin()
        self.run(["uv", "sync", "--frozen", "--no-python-downloads"], cwd=self.root / "voice")
        self.restart("ohn-voice")
        self.health(voice=True)
        self.voice_smoke()

    def voice(self):
        self.torch_pin()
        base = self.root / "voice"
        original = digest(base / "pyproject.toml")
        backup = self.snapshot("voice", [(base / "uv.lock", "uv.lock")])

        def action():
            self.run(["uv", "lock", "--upgrade", "--no-python-downloads"], cwd=base)
            require(digest(base / "pyproject.toml") == original, "pyproject.toml неожиданно изменён")
            self.torch_pin()
            self.run(["uv", "sync", "--frozen", "--no-python-downloads"], cwd=base)
            self.restart("ohn-voice")
            self.health(voice=True)
            self.voice_smoke()

        self.transaction("voice", backup, action, self.voice_restore)

    def rollback(self):
        kind = self.args.target
        backup = self.previous(kind)
        if self.pending(kind).is_file():
            self.emit(f"Обновление {kind} оборвалось на полпути; возвращаю состояние до него.")
        if kind == "ik-llama" and self.pending(kind).is_file():
            self.models_idle()
            self.ik_llama_undo(backup)
        elif kind == "canvas":
            self.canvas_restore(backup)
            self.canvas_smoke()
        elif kind == "caddy":
            self.caddy_restore(backup)
        elif kind == "llama-swap":
            self.llama_swap_restore(backup)
        elif kind == "voice":
            self.voice_restore(backup)
        elif kind == "ik-llama":
            self.models_idle()
            metadata = read_json(backup / "ik.json")
            previous, current = self.backend / "build.prev", self.backend / "build"
            require(previous.is_dir() and digest(previous / "bin/llama-server") == metadata["binary_sha256"],
                    "build.prev не соответствует последнему обновлению")
            require(not self.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=self.backend, capture=True),
                    "Есть изменения tracked-файлов ik_llama; откат запрещён")
            displaced_commit = self.run(["git", "rev-parse", "HEAD"], cwd=self.backend, capture=True)
            self.run(["git", "checkout", "--detach", metadata["commit"]], cwd=self.backend)
            displaced = self.backend / ("build.reverted-" + uuid.uuid4().hex)
            current.rename(displaced)
            try:
                previous.rename(current)
            except BaseException:
                displaced.rename(current)
                raise
            displaced.rename(previous)
            self.run([current / "bin/llama-server", "--version"], timeout=30, env={"NCCL_SOCKET_IFNAME": "lo"})
            self.backend.with_name(self.backend.name + ".prev-commit").write_text(displaced_commit + "\n")
        # Spent: the mark of the unfinished update, and the record of a finished one if it names this copy.
        for record in (self.pending(kind), self.state / f"update-{kind}.json"):
            if record.is_file() and Path(read_json(record)["backup"]).resolve() == backup:
                record.unlink()
        self.discard(backup)
        self.emit(f"Откат {kind} завершён.")

    def dry_run(self):
        command = self.args.command
        plans = {
            "check": "npm view; pins canvas; git ls-remote + отставание; GitHub Caddy и llama-swap; uv lock --upgrade --dry-run.",
            "canvas": "Копия обоих manifest/lock/node_modules и dist → установка одной точной версии → build UI → отчёт локали → restart ohn-agent, затем ohn-gateway → health → беседа/guard без LLM → удаление беседы. При ошибке восстановление/build/restart/health.",
            "ik-llama": "Отказ при активном ohn-models, слушателе 18030 или llama-server на GPU → проверка диска → сохранение commit → fetch/checkout → новый build с флагами cache и относительным RUNPATH → --version → повторная проверка занятости → swap build/build.prev. ohn-models НЕ запускается.",
            "caddy": "GitHub linux_amd64 + SHA-256 → validate текущего Caddyfile с окружением launcher (ключ-заглушка) → caddy.prev/swap → restart ohn-gateway → HTTPS health. При ошибке восстановление/restart/health.",
            "llama-swap": "GitHub linux_amd64 + SHA-256 → --version → llama-swap.prev/swap → restart ohn-models и /health, только если он уже запущен. При ошибке восстановление.",
            "voice": "Проверка torch/torchaudio <=2.5.1 → копия uv.lock → uv lock --upgrade → uv sync --frozen → restart ohn-voice → health, TTS и STT. При ошибке старый lock/sync/restart/smoke.",
            "rollback": "Вернуть состояние до оборванного обновления компонента, а если такого нет — до последнего удачного; для ik_llama сначала проверить занятость. Модели не запускать.",
        }
        self.emit(f"Сухой запуск: {command} {self.args.target or ''}; дерево {self.root}")
        self.emit(plans[command])
        if self.args.bench:
            self.emit(f"Явно запрошен короткий benchmark, только при свободных GPU: {self.args.bench}")
        self.emit("Файлы, журнал, службы и сеть не изменены; команды плана не выполнялись.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="nexus-update", add_help=False,
                                     description="Обновление движков Nexus; по умолчанию только проверка.")
    parser.add_argument("-h", "--help", action="help", help="Показать справку")
    parser.add_argument("command", nargs="?", default="check", choices=["check", *COMPONENTS, "rollback"])
    parser.add_argument("target", nargs="?", help="Версия/commit либо компонент для rollback")
    parser.add_argument("--dry-run", action="store_true", help="Показать план без изменений, включая журнал")
    parser.add_argument("--offline", action="store_true", help="check без сетевых запросов")
    parser.add_argument("--bench", metavar="MODEL.gguf", help="Явно разрешённое чтение модели для короткого benchmark ik_llama")
    parser.add_argument("--sandbox", metavar="DIR", help="Только canvas: независимая копия /tmp/nexus-update-test.*, без служб/API")
    args = parser.parse_args(argv)
    if args.command == "rollback" and args.target not in COMPONENTS:
        parser.error("rollback требует " + "|".join(COMPONENTS))
    if args.command in {"check", "voice"} and args.target:
        parser.error("Эта команда не принимает версию")
    if args.offline and args.command != "check":
        parser.error("--offline предназначен для check")
    if args.bench and args.command != "ik-llama":
        parser.error("--bench допустим только с ik-llama")
    if args.target and args.command in {"canvas", "caddy", "llama-swap", "ik-llama"}:
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", args.target), "Недопустимая версия/commit")
    return args


def main(argv=None):
    updater = None
    try:
        updater = Updater(parse_args(argv))
        if updater.args.dry_run:
            updater.dry_run()
            return 0
        updater.state.mkdir(parents=True, exist_ok=True)
        with (updater.state / "update.log").open("a") as log:
            updater.log = log
            with contextlib.ExitStack() as stack:
                if updater.args.command != "check":
                    lock = stack.enter_context((updater.state / "update.lock").open("a"))
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        raise UpdateError("Другое обновление уже выполняется") from None
                command = updater.args.command
                updater.emit("Nexus update: " + command)
                require(command in {"check", "rollback"} or not updater.pending(command).is_file(),
                        f"Прошлое обновление {command} оборвалось на полпути. Сначала верните прежнее состояние: "
                        f"nexus-update rollback {command}")
                try:
                    getattr(updater, command.replace("-", "_"))()
                finally:
                    updater.settle()
        updater.log = None
        return 0
    except (UpdateError, OSError, ValueError, KeyError, EOFError, urllib.error.URLError, subprocess.SubprocessError,
            tarfile.TarError, wave.Error) as error:
        # API response bodies and settings never appear in exception text.
        if updater:
            updater.log = None
            if not updater.args.dry_run and updater.state.is_dir():
                with (updater.state / "update.log").open("a") as log:
                    log.write(time.strftime("%Y-%m-%d %H:%M:%S ") + f"Ошибка: {error}\n")
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1


def unheard(signum, frame):
    """A handler, not SIG_IGN: the commands the update starts keep their own, default reactions."""


def interrupted(signum, frame):
    # The first Ctrl+C or kill stops the update and starts its rollback; a second one must not stop the rollback.
    signal.signal(signal.SIGTERM, unheard)
    signal.signal(signal.SIGINT, unheard)
    raise UpdateError("Выполнение прервано")


def handle_signals():
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    # A closed terminal stops nothing: the update goes on into the journal (see emit).
    signal.signal(signal.SIGHUP, unheard)


if __name__ == "__main__":
    handle_signals()
    sys.exit(main())
