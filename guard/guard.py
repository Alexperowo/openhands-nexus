#!/usr/bin/env python3
"""PreToolUse hook: stops agent commands that break the desktop session, Nexus or the network.

The agent runs unsandboxed on Aleksandr's PC and nobody confirms its actions (his
decision), so a blocked action must teach the right way instead of asking him.
Contract (openhands-sdk hooks): the HookEvent JSON comes on stdin; exit 2 with
{"decision": "deny", "reason": ...} on stdout blocks the action, and the agent gets
the reason as a rejection. Any other outcome lets the action run.

Nothing here names a desktop environment: session components are recognised by where
systemd keeps them (the login session scope, the user session.slice, system services),
so the same rules hold for Cinnamon, KDE or GNOME on any systemd distribution.
Rules are deliberately narrow: they are a net under recoverable mistakes, not a judge.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import traceback
from functools import lru_cache
from pathlib import Path

GUARD_DIR = Path(__file__).resolve().parent
HOME = os.path.expanduser("~")

# The agent's terminal is a process group of agent-server, killed when the terminal closes.
DETACHED = "systemd-run --user --collect --service-type=exec <команда>"

# Login session scope, user session services (shell, audio, portals), system services, managers.
SESSION_CGROUP = re.compile(r"/session-\d+\.scope$|/session\.slice/|^/system\.slice/|/init\.scope$")
# Only the session itself counts when a program is started: system services run helpers like `sleep`.
AUTOSTART_CGROUP = re.compile(r"/session-\d+\.scope$|/session\.slice/")
INTERPRETERS = {"python", "python3", "perl", "ruby", "node", "bash", "sh", "dash", "zsh", "env",
                "sleep", "cat", "tail", "timeout"}
INFO_ONLY = {"--version", "--help", "-h", "-V"}

NEXUS = re.compile(r"llama-server|agent-server|agent-canvas|caddy|llama-swap|service:app|vite|openhands|^ohn[-.]", re.I)
NEXUS_PORTS = {"18010", "18011", "18020", "18030", "3011", "8443", "8081", "2029", "8010"}
NETWORK_UNITS = re.compile(r"^(systemd-resolved|NetworkManager|wpa_supplicant|happd)")
SESSION_UNITS = re.compile(r"^(display-manager|lightdm|gdm3?|sddm|systemd-logind|dbus|graphical\.target)")
NETWORK_FILES = ("/etc/resolv.conf", "/etc/systemd/resolved.conf", "/etc/NetworkManager/")
# Nexus itself and its keys too: settings and secrets are encrypted with OHN_SECRET_KEY.
PROTECTED_DIRS = {"/", "/home", HOME, f"{HOME}/Agents", f"{HOME}/.config", f"{HOME}/.local",
                  f"{HOME}/.local/share", "/usr", "/etc", "/boot", "/var", "/opt", "/bin", "/sbin",
                  "/lib", "/lib64", "/srv", "/root", str(GUARD_DIR.parent), str(GUARD_DIR.parent / "agent"),
                  str(GUARD_DIR.parent / "agent/state"), f"{HOME}/.config/openhands-nexus"}
READERS = {"cat", "less", "more", "head", "tail", "grep", "rg", "ls", "stat", "readlink", "file", "wc",
           "diff", "md5sum", "sha256sum", "python3", "python", "cd", "pushd", "find", "tree", "du",
           "realpath", "dirname", "basename", "echo", "test", "[", "nl", "jq", "awk", "bat", "xxd"}
COPIERS = {"cp", "rsync", "install", "ln", "scp"}  # only the last path is written
REDIRECTS = {">", ">>", ">|", "&>"}
# Prefix programs and their options that take a value; the real command follows them.
WRAPPERS = {"sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"},
            "env": {"-u", "-C", "-S"}, "nice": {"-n"}, "ionice": {"-c", "-n", "-p"},
            "timeout": {"-s", "-k", "--signal", "--kill-after"},
            "xargs": {"-n", "-I", "-P", "-L", "-d", "-s", "-a", "-E"},
            "nohup": set(), "setsid": set(), "exec": set(), "command": set(), "stdbuf": set(),
            "time": set(), "doas": {"-u"}}
SYSTEMD_RUN_VALUED = {"-u", "--unit", "-p", "--property", "--description", "--slice", "-E", "--setenv",
                      "-M", "--machine", "-H", "--host", "--working-directory", "--uid", "--gid", "--nice"}
KILLERS = {"kill", "pkill", "killall"}
FINDERS = {"pgrep", "pidof"}

REASON_SESSION_PROC = (
    "Страж Nexus: {what} — часть сеанса рабочего стола или системная служба ({unit}). "
    "Не убивай её из терминала. Службу systemd перезапускает её же команда "
    "(systemctl --user restart <служба> или sudo systemctl restart <служба>); оболочку рабочего "
    "стола — её штатный способ (окружение в $XDG_CURRENT_DESKTOP; найди официальный способ, "
    "обычно вызов D-Bus), а не kill или --replace.")
REASON_START = (
    "Страж Nexus: {what} — компонент сеанса рабочего стола. Запущенный из терминала агента, "
    "он погибнет, когда терминал закроется (так уже погибла оболочка рабочего стола). "
    f"Запускай отдельно от агента: {DETACHED}; оболочку рабочего стола перезапускай её "
    "штатным способом (окружение в $XDG_CURRENT_DESKTOP).")
REASON_ALL = ("Страж Nexus: эта команда убьёт все процессы пользователя — весь сеанс и сам ассистент. "
              "Называй конкретный процесс.")
REASON_NEXUS = (
    "Страж Nexus: это службы, на которых работает сам ассистент (модель, голос, агент, шлюз, "
    "интерфейс) или прежняя установка. Их остановка оборвёт текущую работу. "
    "Не останавливай их. Если служба мешает — обойди это, а в итоге напиши пользователю, какую службу и почему нужно проверить.")
REASON_RM = ("Страж Nexus: рекурсивное удаление системного, домашнего, каталога настроек или самого Nexus целиком "
             "запрещено. Удаляй конкретные файлы или подкаталоги по полному пути.")
REASON_SESSION = ("Страж Nexus: это завершит сеанс или выключит компьютер и выкинет пользователя из системы "
                  "посреди работы. Не делай этого; если перезапуск действительно нужен — закончи остальное и в итоге напиши, зачем он нужен.")
REASON_NETWORK = ("Страж Nexus: DNS, VPN, прокси и сеть настроены вручную (обход региональных ограничений, "
                  "связь с планшетом) и не меняются агентом. Если сеть не работает — собери диагностику только чтением "
                  "(ip addr, resolvectl status, ping) и в итоге передай её пользователю.")
REASON_SELF = "Страж Nexus: файлы стража меняет только пользователь."
REASON_ERROR = ("Страж Nexus: не смог разобрать команду (внутренняя ошибка стража), поэтому не пропустил её. "
                "Разбей её на простые шаги.")


def tokens(command: str):
    """Shell words and operators, quotes respected; falls back to plain words on bad quoting."""
    command = command.replace("\\\n", " ").replace("`", " ; ").replace("\n", " ; ")
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        return list(lexer)
    except ValueError:
        return re.split(r"\s+|(?=[;|&()])|(?<=[;|&()])", command)


def unwrap(argv: list[str]):
    """The command behind prefix programs, VAR=value and their options."""
    while argv:
        program = os.path.basename(argv[0])
        if re.match(r"^\w+=", argv[0]):
            argv = argv[1:]
        elif program in WRAPPERS:
            argv = argv[1:]
            while argv and argv[0].startswith("-"):
                argv = argv[2:] if argv[0] in WRAPPERS[program] else argv[1:]
            if program == "timeout" and argv:
                argv = argv[1:]  # the duration
        else:
            break
        if program == "command" and argv and argv[0] in ("-v", "-V"):
            return []  # a lookup, nothing runs
    return argv


def segments(command: str):
    """Simple commands of a shell line; `bash -c '...'` bodies are opened recursively."""
    argv: list[str] = []
    for token in tokens(command) + [";"]:
        if token and not set(token) <= set(";|&()"):
            # `$(` arrives as a lone "$" or glued to the word before it ("a=$").
            word = token[:-1] if token.endswith("$") else token
            if word:
                argv.append(word)
            continue
        argv = unwrap(argv)
        shell_c = next((i for i, a in enumerate(argv[1:3], 1) if re.fullmatch(r"-\w*c\w*", a)), None)
        if argv and os.path.basename(argv[0]) in ("bash", "sh", "dash", "zsh") and shell_c \
                and len(argv) > shell_c + 1:
            yield from segments(argv[shell_c + 1])
        elif argv:
            yield argv
        argv = []


class Process:
    def __init__(self, pid: str):
        base = Path("/proc", pid)
        self.pid = pid
        self.comm = (base / "comm").read_text().strip()
        self.argv = (base / "cmdline").read_bytes().decode(errors="replace").split("\0")[:-1]
        self.cgroup = (base / "cgroup").read_text().strip().split("::", 1)[-1]
        self.pgrp = (base / "stat").read_text().rsplit(")", 1)[1].split()[2]

    @property
    def line(self):
        return " ".join(self.argv)

    @property
    def unit(self):
        return self.cgroup.rsplit("/", 1)[-1]


@lru_cache(maxsize=1)
def process_table():
    return tuple(_scan())


def processes():
    return process_table()


def _scan():
    own = {str(os.getpid()), str(os.getppid())}
    for entry in os.listdir("/proc"):
        if entry.isdigit() and entry not in own:
            try:
                yield Process(entry)
            except (OSError, IndexError):
                continue  # gone or a kernel thread


def matching(program: str, args: list[str]):
    """Processes a kill/pkill/killall/pgrep/pidof call would reach, or None for "all of them"."""
    if program == "kill":
        rest = args[:]
        if rest and rest[0] in ("-s", "-n"):
            rest = rest[2:]
        elif rest and rest[0] in ("-l", "-L"):
            return []
        elif rest and re.fullmatch(r"-\w+", rest[0]) and not re.fullmatch(r"-\d+", rest[0]) or \
                len(rest) > 1 and re.fullmatch(r"-\d+", rest[0]):
            rest = rest[1:]  # the signal
        if rest and rest[0] == "--":
            rest = rest[1:]
        pids = {a for a in rest if a.isdigit()}
        groups = {a[1:] for a in rest if re.fullmatch(r"-\d+", a)}
        if "1" in groups:
            return None
        return [p for p in processes() if p.pid in pids or p.pgrp in groups] if pids | groups else []
    flags, patterns, i = set(), [], 0
    valued = {"-u", "-U", "-g", "-G", "-P", "-s", "-t", "-F", "--signal", "-n", "-o"} \
        if program in ("pkill", "pgrep") else {"-u", "-s", "--signal", "-o", "-y"}
    while i < len(args):
        arg = args[i]
        if arg in valued:
            flags.add(arg)
            i += 2
            continue
        if arg.startswith("-") and len(arg) > 1:
            flags.update("-" + c for c in arg[1:]) if not arg.startswith("--") else flags.add(arg)
        else:
            patterns.append(arg)
        i += 1
    if not patterns:
        return None if "-u" in flags or "-U" in flags else []
    found = []
    for p in processes():
        name = os.path.basename(p.argv[0]) if p.argv else ""
        for pattern in patterns:
            if program in ("pkill", "pgrep"):
                subject = p.line if "-f" in flags else p.comm
                try:
                    rx = re.compile(pattern, re.I if "-i" in flags else 0)
                except re.error:
                    continue
                hit = rx.fullmatch(subject) if "-x" in flags else rx.search(subject)
            elif "-r" in flags:
                hit = re.search(pattern, p.comm)
            else:
                hit = pattern[:15] == p.comm or pattern == name
            if hit:
                found.append(p)
                break
    return found


def check_targets(targets):
    if targets is None:
        return REASON_ALL
    if any(NEXUS.search(p.line) for p in targets):
        return REASON_NEXUS
    for p in targets:
        if SESSION_CGROUP.search(p.cgroup):
            return REASON_SESSION_PROC.format(what=f"процесс {p.comm} ({p.pid})", unit=p.unit)
    return None


def inside(path: str, root: Path):
    try:
        resolved = Path(os.path.expanduser(path)).resolve()
    except (OSError, RuntimeError):
        return False
    return resolved == root or root in resolved.parents


def normalized(path: str):
    path = re.sub(r"^\$\{?HOME\}?", HOME, os.path.expanduser(path))
    path = re.sub(r"/\*$", "", path) or "/"
    return os.path.normpath(path) if path.startswith("/") else path


def writes_to(argv: list[str], match):
    """True when the command changes a file that `match(path)` accepts."""
    program = os.path.basename(argv[0])
    paths = [i for i, word in enumerate(argv) if i and word[:1] in ("/", "~")]
    for i in paths:
        written = argv[i - 1] in REDIRECTS or program not in READERS | COPIERS or \
            program in COPIERS and i == len(argv) - 1
        if written and match(argv[i]):
            return True
    return False


def check_systemctl(args: list[str]):
    stopping = {"stop", "kill", "disable", "mask", "freeze"}
    restarting = {"restart", "try-restart", "reload-or-restart", "condrestart"}
    if set(args) & {"isolate", "poweroff", "reboot", "halt", "suspend", "hibernate", "kexec",
                    "soft-reboot", "rescue", "emergency"}:
        return REASON_SESSION
    verbs = (stopping | restarting) & set(args)
    if not verbs:
        return None
    user = "--user" in args
    units = [a for a in args if not a.startswith("-") and a not in stopping | restarting]
    for unit in units:
        if NEXUS.search(unit):
            return REASON_NEXUS
        if not user and NETWORK_UNITS.match(unit):
            return REASON_NETWORK
        if not user and SESSION_UNITS.match(unit) or not user and unit in system_names("display-manager"):
            return REASON_SESSION
        # A session service restarted by systemd stays systemd's; stopping it leaves the session broken.
        if user and verbs & stopping and unit_slice(unit) == "session.slice":
            return REASON_SESSION_PROC.format(what=f"служба {unit}", unit="session.slice")
    return None


def system_names(unit: str):
    return systemctl_show([], unit, "Names").split()


def unit_slice(unit: str):
    return systemctl_show(["--user"], unit, "Slice")


def systemctl_show(scope: list[str], unit: str, prop: str):
    try:
        return subprocess.run(["systemctl", *scope, "show", "-p", prop, "--value", unit],
                              capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def without_redirects(argv: list[str]):
    words, target = [], False
    for word in argv:
        if target:
            target = False
        elif re.fullmatch(r"\d*[<>][<>&|]*|&>>?", word):
            target = True
            if words and words[-1].isdigit():
                words.pop()  # `2>` arrives as "2" and ">"
        else:
            words.append(word)
    return words


def check_start(program: str, argv: list[str]):
    """Starting a session component from the agent's terminal ties it to the terminal."""
    argv = without_redirects(argv)
    args = set(argv[1:])
    if args & INFO_ONLY:
        return None
    if program == "systemd-run":
        if "--scope" not in args:
            return None  # the right way: a transient service owned by systemd
        i = 1
        while i < len(argv) and argv[i].startswith("-"):
            i += 2 if argv[i] in SYSTEMD_RUN_VALUED else 1
        if i >= len(argv):
            return None
        program, args = os.path.basename(argv[i]), set(argv[i + 1:])
    if "--replace" in args:
        return REASON_START.format(what=f"{program} --replace (замена оконного менеджера или оболочки)")
    if program in INTERPRETERS or any(not a.startswith("-") for a in args):
        return None  # daemons and applets start with options only; a positional means a CLI call
    for p in processes():
        if p.comm == program[:15] and AUTOSTART_CGROUP.search(p.cgroup):
            return REASON_START.format(what=f"{program} (уже работает в {p.unit})")
    return None


def check_argv(argv: list[str]):
    program = os.path.basename(argv[0])
    args = argv[1:]
    words = " ".join(argv)
    if program in KILLERS:
        return check_targets(matching(program, args))
    if program == "fuser" and any(re.fullmatch(r"-\w*k\w*", a) for a in args) and nexus_port(words):
        return REASON_NEXUS
    if program == "rm" and any(re.fullmatch(r"-\w*[rR]\w*|--recursive", a) for a in args):
        if any(normalized(a) in PROTECTED_DIRS for a in args if not a.startswith("-")):
            return REASON_RM
    if program == "systemctl":
        return check_systemctl(args)
    if program in ("reboot", "poweroff", "shutdown", "halt") and not set(args) & INFO_ONLY \
            or re.search(r"session-quit$|^logout$", program) \
            or program == "loginctl" and set(args) & {"terminate-session", "terminate-user", "kill-session",
                                                       "kill-user", "poweroff", "reboot"} \
            or program in ("init", "telinit") and set(args) & {"0", "1", "2", "3", "6"}:
        return REASON_SESSION
    if program == "resolvectl" and set(args) & {"dns", "domain", "revert", "default-route", "dnsovertls"}:
        return REASON_NETWORK
    if program == "nmcli" and (re.search(r"\b(dns|vpn)\b", words) and
                               set(args) & {"modify", "mod", "m", "add", "a", "delete", "del", "edit",
                                            "import", "up", "down"}
                               or re.search(r"\bnetworking off\b|\bradio \w+ off\b|\bdevice disconnect\b|"
                                            r"\bconnection down\b|\bcon down\b", words)):
        return REASON_NETWORK
    if program == "gsettings" and "set" in args and "org.gnome.system.proxy" in words \
            or re.fullmatch(r"kwriteconfig\d*", program) and "kioslaverc" in words \
            or program == "ip" and re.search(r"\blink set\b.*\bdown\b|\baddr(ess)? (flush|del)|"
                                             r"\broute (flush|del)", words):
        return REASON_NETWORK
    if writes_to(argv, lambda path: normalized(path).startswith(NETWORK_FILES)):
        return REASON_NETWORK
    if writes_to(argv, lambda path: inside(path, GUARD_DIR)):
        return REASON_SELF
    return check_start(program, argv)


def nexus_port(text: str):
    return any(port in NEXUS_PORTS for port in re.findall(r"(?<!\d)(\d{4,5})(?!\d)", text))


def check_terminal(command: str):
    parts = list(segments(command))
    programs = {os.path.basename(argv[0]) for argv in parts}
    if programs & KILLERS:
        # `kill $(lsof -t -i:PORT)` or `pgrep x | xargs kill` split into harmless-looking parts.
        if programs & {"lsof", "fuser", "ss", "netstat"} and nexus_port(command):
            return REASON_NEXUS
        for argv in parts:
            if os.path.basename(argv[0]) in FINDERS:
                reason = check_targets(matching(os.path.basename(argv[0]), argv[1:]))
                if reason:
                    return reason
    for argv in parts:
        reason = check_argv(argv)
        if reason:
            return reason
    return None


def decide(event: dict):
    tool = event.get("tool_name") or ""
    tool_input = event.get("tool_input") or {}
    if tool == "terminal":
        if tool_input.get("is_input"):
            return None
        return check_terminal(tool_input.get("command") or "")
    if tool in ("file_editor", "planning_file_editor") and tool_input.get("command") != "view":
        path = str(tool_input.get("path") or "")
        if path.startswith("/") and inside(path, GUARD_DIR):
            return REASON_SELF
        if path.startswith("/") and normalized(path).startswith(NETWORK_FILES):
            return REASON_NETWORK
    if tool == "apply_patch" and str(GUARD_DIR) in str(tool_input.get("patch") or ""):
        return REASON_SELF
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    try:
        reason = decide(event)
    except Exception:  # a broken rule must be visible, not a silent pass
        traceback.print_exc(file=sys.stderr)
        reason = REASON_ERROR
    if reason:
        print(json.dumps({"decision": "deny", "reason": reason}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
