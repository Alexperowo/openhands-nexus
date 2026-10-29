#!/usr/bin/env python3
"""PreToolUse hook: stops agent commands that break the desktop session, Nexus or the network.

The agent runs unsandboxed on Aleksandr's PC and nobody confirms its actions (his
decision), so a blocked action must teach the right way instead of asking him.
Contract (openhands-sdk hooks): the HookEvent JSON comes on stdin; exit 2 with
{"decision": "deny", "reason": ...} on stdout blocks the action, and the agent gets
the reason as a rejection. Any other outcome lets the action run; input that cannot
be read is blocked too.

Nothing here names a desktop environment: session components are recognised by where
systemd keeps them (the login session scope, the user session.slice, system services),
so the same rules hold for Cinnamon, KDE or GNOME on any systemd distribution.
Rules are deliberately narrow: they are a net under recoverable mistakes, not a judge.
Whole personal folders go to the trash instead of being removed; inline scripts
(python -c, heredocs) are searched for the same removals and writes.
"""
import itertools
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
REPO = GUARD_DIR.parent
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

# Command lines of the Nexus services (launcher/run.sh is the main process of ohn-agent).
NEXUS = re.compile(r"llama-server|llama-swap|agent-server|agent-canvas|openhands[-.]automation|caddy|"
                   r"service:app|launcher/(run\.sh|watch\.py)|^ohn[-.]", re.I)
# Canvas, agent-server, voice, llama-swap, gateway, CA, Canvas and Caddy internals; 18040+ — model servers.
NEXUS_PORTS = {"18010", "18011", "18020", "18030", "3011", "8443", "8081", "2029", "8010"} | \
    {str(port) for port in range(18040, 18050)}
NETWORK_UNITS = re.compile(r"^(systemd-resolved|NetworkManager|wpa_supplicant|happd)")
SESSION_UNITS = re.compile(r"^(display-manager|lightdm|gdm3?|sddm|systemd-logind|dbus|graphical\.target)")
NETWORK_FILES = {"/etc/resolv.conf", "/etc/systemd/resolved.conf"}  # a copy next to them is fine
NETWORK_DIRS = ("/etc/systemd/resolved.conf.d/", "/etc/NetworkManager/", "/etc/netplan/")
# Nexus itself and its keys too: settings and secrets are encrypted with OHN_SECRET_KEY.
PROTECTED_DIRS = {"/", "/home", HOME, f"{HOME}/Agents", f"{HOME}/.config", f"{HOME}/.local",
                  f"{HOME}/.local/share", "/usr", "/etc", "/boot", "/var", "/opt", "/bin", "/sbin",
                  "/lib", "/lib64", "/srv", "/root", str(REPO), str(REPO / "agent"),
                  str(REPO / "agent/state"), f"{HOME}/.config/openhands-nexus"}
# XDG folders whose subfolders are the user's own files (downloads are not: they are cleaned up).
XDG_PERSONAL = {"DESKTOP", "DOCUMENTS", "MUSIC", "PICTURES", "VIDEOS"}
READERS = {"cat", "less", "more", "head", "tail", "grep", "rg", "ls", "stat", "readlink", "file", "wc",
           "diff", "md5sum", "sha256sum", "python3", "python", "cd", "pushd", "find", "tree", "du",
           "realpath", "dirname", "basename", "echo", "test", "[", "nl", "jq", "awk", "bat", "xxd",
           "git", "pytest"}
COPIERS = {"cp", "rsync", "install", "ln", "scp"}  # only the last path is written
REDIRECTS = {">", ">>", ">|", "&>"}
# Prefix programs and their options that take a value; the real command follows them.
WRAPPERS = {"sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"},
            "env": {"-u", "-C", "-S"}, "nice": {"-n"}, "ionice": {"-c", "-n", "-p"},
            "timeout": {"-s", "-k", "--signal", "--kill-after"},
            "xargs": {"-n", "-I", "-P", "-L", "-d", "-s", "-a", "-E"},
            "nohup": set(), "setsid": set(), "exec": set(), "command": set(), "stdbuf": set(),
            "time": set(), "doas": {"-u"}, "pkexec": {"-u", "--user"}}
SYSTEMD_RUN_VALUED = {"-u", "--unit", "-p", "--property", "--description", "--slice", "-E", "--setenv",
                      "-M", "--machine", "-H", "--host", "--working-directory", "--uid", "--gid", "--nice"}
KILLERS = {"kill", "pkill", "killall"}
FINDERS = {"pgrep", "pidof"}
TRASHERS = {"gio", "trash-put", "trash", "gvfs-trash"}
# find tests that pick some files; without one, -delete takes the whole tree.
FIND_TESTS = {"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex",
              "-mtime", "-mmin", "-atime", "-amin", "-ctime", "-cmin", "-newer", "-size", "-empty",
              "-user", "-inum", "-samefile"}
MATCH_ALL = {"*": {"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename"}, ".*": {"-regex", "-iregex"}}
# $NAME, ${NAME} and ${NAME<op>word}: groups name, op, word for braces; name alone otherwise.
VARIABLE = re.compile(r"\$(?:\{(\w+)(?:(:?[-=?+])([^}]*))?\}|(\w+))")
DECLARERS = {"export", "declare", "local", "readonly", "typeset"}
# Words that open a compound command: the command after them runs as usual.
KEYWORDS = {"if", "then", "else", "elif", "while", "until", "do", "!", "{", "}"}
SCRIPTERS = {"python", "python3", "perl", "ruby", "node", "php"}
TREE_REMOVAL = re.compile(r"""\b(?:rmtree|remove_tree|rmSync|rimraf|fs\.(?:promises\.)?rm)\s*\(\s*"""
                          r"""(?:[\w.]+\(\s*)*[rbuf]?(['"])([^'"\n]+)\1""")
CODE_WRITES = re.compile(r"""\bopen\([^()]*,\s*(?:mode\s*=\s*)?[rbuf]?['"][^'"]*[wax+]|"""
                         r"""\.open\(\s*(?:mode\s*=\s*)?['"][^'"]*[wax+]|write_(?:text|bytes)|"""
                         r"""(?:write|append)File|\b(?:unlink|remove|rename|copy\w*|move|symlink|truncate)\s*\(""")
CODE_LITERAL = re.compile(r"""(['"])([^'"\s]*[/.][^'"\s]*)\1""")

# The shell's own restart, the same for every desktop: a D-Bus method, found and checked.
DBUS_RESTART = (
    "Оболочку рабочего стола перезапускай её собственным методом D-Bus: найди его (busctl --user list, "
    "затем gdbus introspect --session --dest <имя> --object-path <путь>; окружение — в "
    "$XDG_CURRENT_DESKTOP), вызови и проверь результат снимком экрана. Если такого метода нет — не "
    "перезапускай: продолжай остальную работу и в итоге напиши пользователю, что нужен перезапуск.")
REASON_SESSION_PROC = (
    "Страж Nexus: {what} — часть сеанса рабочего стола или системная служба ({unit}). "
    "Не убивай её из терминала. Службу systemd перезапускай её командой: systemctl --user restart "
    "<служба> (системную — sudo systemctl restart <служба>). " + DBUS_RESTART)
REASON_START = (
    "Страж Nexus: {what} — компонент сеанса рабочего стола. Запущенный из терминала агента, "
    "он погибнет, когда терминал закроется (так уже погибла оболочка рабочего стола). "
    "Упавший компонент поднимай отдельно от агента: " + DETACHED + ". " + DBUS_RESTART)
REASON_REPLACE = (
    "Страж Nexus: {what} — замена оболочки или оконного менеджера на ходу: новая копия оказывается вне "
    "менеджера сеанса, и он может завершить сеанс или запустить вторую копию. " + DBUS_RESTART +
    " Если оболочка не работает совсем — запусти её без --replace отдельно от агента: " + DETACHED + ".")
REASON_ALL = ("Страж Nexus: эта команда убьёт все процессы пользователя — весь сеанс и сам ассистент. "
              "Называй конкретный процесс.")
REASON_OWN_GROUP = ("Страж Nexus: kill 0 шлёт сигнал всей группе процессов этого терминала — оборвётся всё, "
                    "что в нём запущено, а то и сам терминал беседы. Останавливай процесс по номеру: kill PID "
                    "(номер — из pgrep -a имя).")
REASON_NEXUS = (
    "Страж Nexus: это службы, на которых работает сам ассистент (модель, голос, агент, шлюз, "
    "интерфейс). Их остановка оборвёт текущую работу. Не останавливай их. Если служба мешает "
    "(занят порт или видеокарта) — обойди это другим портом или способом, а в итоге напиши пользователю, "
    "какую службу и почему нужно проверить.")
REASON_RM = ("Страж Nexus: рекурсивное удаление системного или домашнего каталога, каталога настроек, "
             "целого диска, самого Nexus или его моделей запрещено. Удаляй конкретные файлы или подкаталоги "
             "по полному пути.")
REASON_EMPTY_VAR = (
    "Страж Nexus: если переменная {name} в этом терминале пуста или не задана, команда удалит {path}. "
    "Пиши ${{{name}:?}} — тогда при пустой переменной оболочка остановится, — или полный путь.")
REASON_TRASH = (
    "Страж Nexus: {path} — личные данные пользователя (папка в домашнем каталоге, проект, каталог на диске); "
    "удаление необратимо. Если их действительно нужно убрать — перемести в корзину: gio trash {path} "
    "(пользователь сможет восстановить) и в итоге напиши, что отправил в корзину и зачем.")
REASON_SESSION = ("Страж Nexus: это завершит сеанс или выключит компьютер и выкинет пользователя из системы "
                  "посреди работы. Не делай этого; если перезапуск действительно нужен — закончи остальное и в итоге напиши, зачем он нужен.")
REASON_NETWORK = ("Страж Nexus: DNS, VPN, прокси и сеть настроены вручную (обход региональных ограничений, "
                  "связь с планшетом) и не меняются агентом. Если сеть не работает — собери диагностику только чтением "
                  "(ip addr, resolvectl status, ping) и в итоге передай её пользователю.")
REASON_SELF = ("Страж Nexus: файлы стража меняет только пользователь. Если правило мешает делу — обойди его "
               "другим способом, а в итоге напиши пользователю, какое правило и почему стоит пересмотреть.")
REASON_ERROR = ("Страж Nexus: не смог разобрать запрос (внутренняя ошибка стража), поэтому не пропустил его. "
                "Разбей команду на простые шаги.")


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
        if re.match(r"^\w+=", argv[0]) or argv[0] in KEYWORDS:
            argv = argv[1:]
        elif argv[0] == "function":
            argv = argv[2:]  # `function f { ...`
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
        if not token or not set(token) <= set(";|&()"):  # "" is an empty word, not an operator
            # `$(` arrives as a lone "$" or glued to the word before it ("a=$").
            word = token[:-1] if token.endswith("$") else token
            if word or not token:
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


def probe_only(program: str, args: list[str]):
    """Signal 0 (`kill -0 PID`) only asks whether a process exists."""
    if program == "kill":
        return args[:1] == ["-0"] or args[:2] in (["-s", "0"], ["-n", "0"])
    for i, arg in enumerate(args):
        if not arg.startswith("-"):
            break  # the patterns follow the options
        if arg in ("-0", "--signal=0") or arg in ("-s", "--signal") and args[i + 1:i + 2] == ["0"]:
            return True
    return False


def kill_targets(args: list[str]):
    """The PIDs and process groups a kill call names."""
    rest = args[:]
    if rest and rest[0] in ("-s", "-n"):
        rest = rest[2:]
    elif rest and rest[0] in ("-l", "-L"):
        return set(), set()  # lists signals
    elif rest and re.fullmatch(r"-\w+", rest[0]) and not re.fullmatch(r"-\d+", rest[0]) or \
            len(rest) > 1 and re.fullmatch(r"-\d+", rest[0]):
        rest = rest[1:]  # the signal
    if rest and rest[0] == "--":
        rest = rest[1:]
    return {a for a in rest if a.isdigit()}, {a[1:] for a in rest if re.fullmatch(r"-\d+", a)}


def own_group(program: str, args: list[str]):
    """`kill 0` and `pkill -g 0` signal the caller's process group: the agent's own terminal."""
    if program == "kill":
        return "0" in set.union(*kill_targets(args))
    if program != "pkill":
        return False
    groups = [args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-g", "--pgroup")] + \
        [a.split("=", 1)[1] for a in args if a.startswith("--pgroup=")]
    return any("0" in value.split(",") for value in groups)


def matching(program: str, args: list[str]):
    """Processes a kill/pkill/killall/pgrep/pidof call would reach, or None for "all of them"."""
    if program == "kill":
        pids, groups = kill_targets(args)
        if "1" in groups:
            return None
        return [p for p in processes() if p.pid in pids or p.pgrp in groups] if pids | groups else []
    flags, patterns, i = set(), [], 0
    valued = {"-u", "-U", "-g", "-G", "-P", "-s", "-t", "-F", "--signal"} \
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


def absolute(word: str, dirs: list[str]):
    """Full paths a command word names: itself when absolute, else what exists under the current folders."""
    if not word or word.startswith("-"):
        return []
    path = normalized(word)
    if path.startswith("/"):
        return [path]
    if "$" in path:
        return []
    path = "." if path in ("*", ".*") else path  # everything in the current folder
    return [full for d in dirs if os.path.lexists(full := os.path.normpath(os.path.join(d, path)))]


def network_file(path: str):
    return path in NETWORK_FILES or (path + "/").startswith(NETWORK_DIRS)


@lru_cache(maxsize=1)
def mount_points():
    """Disk mounts: removing one whole wipes the disk."""
    try:
        lines = Path("/proc/self/mounts").read_text().splitlines()
    except OSError:
        return frozenset()
    return frozenset(fields[1].replace("\\040", " ") for fields in map(str.split, lines)
                     if fields[0].startswith("/dev/") and not fields[0].startswith("/dev/loop"))


@lru_cache(maxsize=1)
def homes():
    """The home folder and those of other systems on data disks (<disk>/home/<user>)."""
    found = {HOME}
    for mount in mount_points() - {"/"}:
        try:
            found.update(entry.path for entry in os.scandir(os.path.join(mount, "home")) if entry.is_dir())
        except OSError:
            continue
    return frozenset(found)


@lru_cache(maxsize=1)
def personal_roots():
    """Folders whose direct subfolders are the user's own data: removed only to the trash."""
    roots = set(homes()) | {f"{HOME}/Agents"} | {m for m in mount_points() if m != "/" and not m.startswith("/boot")}
    try:
        dirs = Path(HOME, ".config/user-dirs.dirs").read_text()
    except OSError:
        dirs = ""
    roots.update(os.path.normpath(value.replace("$HOME", HOME))
                 for name, value in re.findall(r'^XDG_(\w+)_DIR="(.+)"', dirs, re.M) if name in XDG_PERSONAL)
    return frozenset(roots)


@lru_cache(maxsize=1)
def nexus_paths():
    """What Nexus runs from: the clone, its keys, llama-server and the model files of models/llama-swap.yaml."""
    paths = {str(REPO), f"{HOME}/.config/openhands-nexus"}
    try:
        menu = (REPO / "models/llama-swap.yaml").read_text()
    except OSError:
        menu = ""
    for line in menu.splitlines():
        paths.update(re.findall(r"(?<![\w}$])(/[\w.+-]+(?:/[\w.+-]+)+)", line.split("#", 1)[0]))
    # The menu names llama-server and the weights relative to models/, through links the installer
    # makes (models/llama-server, models/weights): what counts is where they lead.
    macros = dict(re.findall(r"^  (\w+): (\S[^\n]*)$", menu.split("\nmodels:", 1)[0], re.M))
    for _ in range(3):  # a macro may use another one
        menu = re.sub(r"\$\{(\w+)\}", lambda m: macros.get(m[1], m[0]), menu)
    for name in {macros.get("server", "")} | set(re.findall(r"(?:^|\s)(?:-m|--mmproj)\s+(\S+)", menu)):
        if name and not name.startswith("/"):
            paths.add(os.path.realpath(REPO / "models" / name))
    return frozenset(paths)


def removal(word: str, dirs: list[str]):
    """Why removing this whole path is stopped, or None."""
    for path in absolute(word, dirs):
        if path in PROTECTED_DIRS or path in mount_points() or path in homes() or \
                any(p == path or p.startswith(path.rstrip("/") + "/") for p in nexus_paths()):
            return REASON_RM
        if os.path.dirname(path) in personal_roots():
            return REASON_TRASH.format(path=path)
    return None


# A variable the line does not set (the terminal's own, a loop's, read's): kept as written.
UNKNOWN = object()
VALUES = 8  # more values of one variable than this: one of them is UNKNOWN
VARIANTS = 512  # expansions of one command checked


def expand(word: str, known: dict):
    """What the word may become: each variable of `known` replaced by each value it may have there
    (None: unset); a variable the line does not set stays as written, its default expanded."""
    variants, end = [""], 0
    for m in VARIABLE.finditer(word):
        options = [text for value in known.get(m[1] or m[4], [UNKNOWN]) for text in substitute(m, value, known)]
        variants = [v + word[end:m.start()] + option for v in variants for option in options]
        end = m.end()
    return list(dict.fromkeys(v + word[end:] for v in variants))


def substitute(m, value, known):
    """One variable reference with one value, as the shell has it (`${D:-w}`, `${D-w}`, `${D:+w}`…)."""
    name, operator, rest = m[1] or m[4], m[2] or "", m[3] or ""
    kind = operator[-1:]
    if value is UNKNOWN:
        # `${OUT:-$HOME}`: the default is what an empty OUT gives, so it is expanded too.
        return [f"${{{name}{operator}{d}}}" for d in expand(rest, known)] if kind in ("-", "=") else [m[0]]
    missing = value is None or operator.startswith(":") and value == ""
    if kind in ("-", "="):
        return expand(rest, known) if missing else [value]
    if kind == "+":
        return [""] if missing else expand(rest, known)
    if kind == "?":
        return [m[0]] if missing else [value]  # the shell stops instead of running the command
    return [value or ""]


def merged(*lists):
    values = list(dict.fromkeys(v for values in lists for v in values))
    return values if len(values) <= VALUES else values[-VALUES + 1:] + [UNKNOWN]


def simple_commands(command: str, known: dict):
    """Each simple command of the line in order, with its words as the shell may expand them, and the
    folders it runs in (known["PWD"]). Assignments, export, unset, read, for and cd change `known`
    as they come. What may not run (after || or in a pipeline, or after && once the chain is over)
    adds its values to the earlier ones instead of replacing them. Subshells are not told apart."""
    argv: list[str] = []
    first, either, pending = True, False, {}

    def assign(name, values):
        before = known.get(name, [UNKNOWN])
        if not first:
            pending.setdefault(name, before)
        known[name] = merged(before, values) if either else values

    def settle():
        for name, before in pending.items():
            known[name] = merged(before, known[name])
        pending.clear()

    for token in tokens(command) + [";"]:
        if not token or not set(token) <= set(";|&()"):  # "" is an empty word, not an operator
            # `$(` arrives as a lone "$" or glued to the word before it ("a=$"): a variable set to
            # its output has an unknown value; elsewhere the worst case, an empty output, is checked.
            if re.fullmatch(r"[A-Za-z_]\w*=\$", token):
                argv.append(token + "(...)")
            elif token != "$":
                argv.append(token[:-1] if token.endswith("$") else token)
            continue
        yield from command_effects(argv, known, assign)
        argv = []
        if token == "&&":
            first = False
        elif "|" in token:
            first, either = False, True
            settle()
        else:
            settle()
            first, either = True, False


def command_effects(argv: list[str], known: dict, assign):
    """One simple command: what it changes in `known`, and its expanded words when it runs something."""
    names = [re.fullmatch(r"([A-Za-z_]\w*)=(.*)", word, re.S) for word in argv]
    leading = 0
    while leading < len(argv) and names[leading]:
        leading += 1
    values = {m[1]: expand(m[2], known) for m in names[:leading]}
    if leading == len(argv):  # `D=/x`: set for the rest of the line
        for name, value in values.items():
            assign(name, value)
        return
    # `D=/x cmd`: D only in cmd's environment; the shell expands cmd's words with the old D.
    argv = unwrap(argv[leading:])
    if not argv:
        return
    program = os.path.basename(argv[0])
    shell_c = next((i for i, a in enumerate(argv[1:3], 1) if re.fullmatch(r"-\w*c\w*", a)), None)
    if program in ("bash", "sh", "dash", "zsh") and shell_c and len(argv) > shell_c + 1:
        inner = {**known, **values}
        yield from simple_commands(argv[shell_c + 1], inner)
        return
    args = [a for a in argv[1:] if not a.startswith("-")]
    if program in DECLARERS:
        for m in filter(None, (re.fullmatch(r"([A-Za-z_]\w*)=(.*)", a, re.S) for a in args)):
            assign(m[1], expand(m[2], known))
    elif program == "unset" and "-f" not in argv:
        for name in args:
            assign(name, [None])
    elif program == "read":
        for name in args:
            assign(name, [UNKNOWN])
    elif program == "for" and len(argv) > 1:
        words = argv[3:] if argv[2:3] == ["in"] else None
        assign(argv[1], [v for w in words for v in expand(w, known)] if words is not None else [UNKNOWN])
        return
    elif program in ("cd", "pushd"):
        if argv[1:2] != ["-"]:
            targets = [v for w in args[:1] for v in expand(w, known)] or [HOME]
            # an absolute target replaces the folder
            assign("PWD", list(dict.fromkeys(os.path.normpath(os.path.join(d, normalized(t)))
                                             for d in folders(known) for t in targets)))
        return
    for variant in itertools.islice(itertools.product(*(expand(word, known) for word in argv)), VARIANTS):
        yield list(variant), folders(known)


def folders(known: dict):
    return [d for d in known["PWD"] if isinstance(d, str)]  # past VALUES folders one is UNKNOWN


def empty_variable(word: str, dirs: list[str]):
    """`rm -rf "$DIR/"*` with DIR empty or unset removes /*: the reason, or None (shellcheck SC2115)."""
    names = [m[1] or m[4] for m in VARIABLE.finditer(word) if not (m[2] and m[2][-1] == "?")]
    if not names:
        return None
    # As the shell has it with these variables unset; `${X:?}` stops the shell, `${X:-w}` gives w.
    worst = VARIABLE.sub(lambda m: m[0] if m[2] and m[2][-1] == "?" else
                         m[3] if m[2] and m[2][-1] in "-=" else "", word)
    if "$" in worst or not removal(worst, dirs):
        return None
    return REASON_EMPTY_VAR.format(name=names[0], path=(absolute(worst, dirs) or [worst])[0])


def check_find(args: list[str], dirs: list[str], fed_to_rm: bool):
    """`find DIR -delete`, `-exec rm` or `| xargs rm -r` without a test removes the whole tree."""
    deletes = fed_to_rm or "-delete" in args or any(
        a in ("-exec", "-execdir", "-ok", "-okdir") and os.path.basename(args[i + 1]) in ("rm", "shred")
        for i, a in enumerate(args[:-1]))
    narrows = any(a in FIND_TESTS and a not in MATCH_ALL.get(args[i + 1] if i + 1 < len(args) else "", ())
                  for i, a in enumerate(args))
    if not deletes or narrows:
        return None
    starts = []
    for arg in args:
        if arg.startswith("-") or arg in ("(", "!", ")"):
            break
        starts.append(arg)
    for start in starts or ["."]:
        reason = empty_variable(start, dirs) or removal(start, dirs)
        if reason:
            return reason
    return None


SED_WRITE = re.compile(r"(?:^|[^A-Za-z])[gpiImMe\d]*[wW]\s*(\S[^\n]*)")
RESOLVECTL_SETTINGS = {"dns", "domain", "default-route", "llmnr", "mdns", "dnssec", "dnsovertls", "nta"}


def resolvectl_changes(args: list[str]):
    """Only a link after dns, domain and the like shows its settings; values after it set them."""
    positional, link, value = [], False, False
    for arg in args:
        if value:
            value = False
        elif arg in ("-i", "--interface", "-p", "--protocol", "-t", "--type", "-c", "--class"):
            value = True
            link = link or arg in ("-i", "--interface")
        elif arg.startswith("-"):
            link = link or bool(re.match(r"-i.|--interface=", arg))
        else:
            positional.append(arg)
    verb, rest = positional[0] if positional else "", positional[1:]
    return verb == "revert" or verb in RESOLVECTL_SETTINGS and len(rest) > (0 if link else 1)


def written(argv: list[str]):
    """Words of a command that name what it changes."""
    program = os.path.basename(argv[0])
    # sed only prints unless told to edit in place (-i, -ni, --in-place) or its script writes a file
    # (w, W, the s///w flag). A script read from a file (-f) and the e command are not looked into.
    reader = program in READERS or program == "sed" and \
        not any(re.match(r"-[a-zA-Z]*i|--in-place", a) for a in argv[1:])
    words = []
    for i, word in enumerate(argv[1:], 1):
        if argv[i - 1] in REDIRECTS or not reader and program not in COPIERS or \
                program in COPIERS and i == len(argv) - 1:
            words.append(word[3:] if word.startswith("of=") else word)  # dd of=
        if program == "sed":
            # The file name runs to the end of the line. A stray match in a plain word names no network file.
            words += [name.rstrip() for name in SED_WRITE.findall(word)]
    return words


def changes_guard(words: list[str], dirs: list[str]):
    """A guard file by path, or by name when the terminal's folder is unknown and nothing else has that name."""
    scripts = {entry.name for entry in GUARD_DIR.glob("*.py")}
    for word in words:
        paths = absolute(word, dirs)
        if any(inside(p, GUARD_DIR) for p in paths) or not paths and "/" not in word and word in scripts:
            return True
    return False


def check_systemctl(args: list[str]):
    stopping = {"stop", "kill", "disable", "mask", "freeze"}
    restarting = {"restart", "try-restart", "reload-or-restart", "reload-or-try-restart", "condrestart"}
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
    detached = False
    if program == "systemd-run":
        i = 1
        while i < len(argv) and argv[i].startswith("-"):
            i += 2 if argv[i] in SYSTEMD_RUN_VALUED else 1
        inner = unwrap(argv[i:])
        if not inner:
            return None
        detached = "--scope" not in args  # a transient service owned by systemd, not by the terminal
        program, args = os.path.basename(inner[0]), set(inner[1:])
    # Window managers and shells take options only; `podman run --replace IMAGE` is a CLI call.
    if "--replace" in args and not any(not a.startswith(("-", ":")) for a in args):
        return REASON_REPLACE.format(what=f"{program} --replace")
    if detached or program in INTERPRETERS or any(not a.startswith("-") for a in args):
        return None  # daemons and applets start with options only; a positional means a CLI call
    for p in processes():
        if p.comm == program[:15] and AUTOSTART_CGROUP.search(p.cgroup):
            return REASON_START.format(what=f"{program} (уже работает в {p.unit})")
    return None


def check_argv(argv: list[str], dirs: list[str], fed_to_rm=False):
    program = os.path.basename(argv[0])
    args = argv[1:]
    words = " ".join(argv)
    if program in KILLERS:
        if probe_only(program, args):
            return None
        return REASON_OWN_GROUP if own_group(program, args) else check_targets(matching(program, args))
    if program == "fuser" and any(re.fullmatch(r"-\w*k\w*", a) for a in args) and nexus_port(words):
        return REASON_NEXUS
    if program == "rm" and any(re.fullmatch(r"-\w*[rR]\w*|--recursive", a) for a in args):
        for arg in args:
            reason = empty_variable(arg, dirs) or removal(arg, dirs)
            if reason:
                return reason
    if program == "find":
        reason = check_find(args, dirs, fed_to_rm)
        if reason:
            return reason
    if program in TRASHERS and (program != "gio" or args[:1] == ["trash"]):
        # The trash is the way for personal folders, not for the home, settings or Nexus.
        if any(removal(arg, dirs) == REASON_RM for arg in args[program == "gio":]):
            return REASON_RM
    if program == "systemctl":
        return check_systemctl(args)
    if program in ("reboot", "poweroff", "shutdown", "halt") and not set(args) & INFO_ONLY \
            or re.search(r"session-quit$|^logout$", program) \
            or program == "loginctl" and set(args) & {"terminate-session", "terminate-user", "kill-session",
                                                       "kill-user", "poweroff", "reboot"} \
            or program in ("init", "telinit") and set(args) & {"0", "1", "2", "3", "6"}:
        return REASON_SESSION
    if program == "resolvectl" and resolvectl_changes(args):
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
    changed = written(argv)
    if any(network_file(path) for word in changed for path in absolute(word, dirs)):
        return REASON_NETWORK
    if changes_guard(changed, dirs):
        return REASON_SELF
    return check_start(program, argv)


def check_code(command: str, dirs: list[str]):
    """Inline scripts that remove a tree or write a protected file by a literal path."""
    for match in TREE_REMOVAL.finditer(command):
        reason = removal(match[2], dirs)
        if reason:
            return reason
    if CODE_WRITES.search(command):
        for match in CODE_LITERAL.finditer(command):
            for path in absolute(match[2], dirs):
                if network_file(path):
                    return REASON_NETWORK
                if inside(path, GUARD_DIR):
                    return REASON_SELF
    return None


def nexus_port(text: str):
    return any(port in NEXUS_PORTS for port in re.findall(r"(?<!\d)(\d{4,5})(?!\d)", text))


def check_terminal(command: str, dirs: list[str]):
    parts = list(segments(command))
    programs = {os.path.basename(argv[0]) for argv in parts}
    if any(os.path.basename(argv[0]) in KILLERS and not probe_only(os.path.basename(argv[0]), argv[1:])
           for argv in parts):
        # `kill $(lsof -t -i:PORT)` or `pgrep x | xargs kill` split into harmless-looking parts.
        if programs & {"lsof", "fuser", "ss", "netstat"} and nexus_port(command):
            return REASON_NEXUS
        for argv in parts:
            if os.path.basename(argv[0]) in FINDERS:
                reason = check_targets(matching(os.path.basename(argv[0]), argv[1:]))
                if reason:
                    return reason
    if programs & SCRIPTERS:
        reason = check_code(command, dirs)
        if reason:
            return reason
    # `find DIR | xargs rm -rf`: the paths come from find.
    fed_to_rm = any(os.path.basename(argv[0]) == "rm" and all(a.startswith("-") for a in argv[1:])
                    for argv in parts)
    user = os.environ.get("USER") or os.path.basename(HOME)
    known = {"HOME": [HOME], "USER": [user], "LOGNAME": [user], "PWD": list(dirs)}
    for argv, folders in simple_commands(command, known):
        reason = check_argv(argv, folders, fed_to_rm)
        if reason:
            return reason
    return None


def decide(event: dict):
    tool = event.get("tool_name") or ""
    tool_input = event.get("tool_input") or {}
    # The hook runs in the conversation's folder; a `cd` earlier in the command line moves it.
    dirs = [event.get("working_dir") or os.getcwd()]
    if tool == "terminal":
        # Text sent with is_input goes to the running program, and at a shell prompt it runs as a command.
        return check_terminal(tool_input.get("command") or "", dirs)
    if tool in ("file_editor", "planning_file_editor") and tool_input.get("command") != "view":
        path = str(tool_input.get("path") or "")
        path = os.path.normpath(os.path.join(dirs[0], normalized(path)))
        if inside(path, GUARD_DIR):
            return REASON_SELF
        if network_file(path):
            return REASON_NETWORK
    if tool == "apply_patch" and str(GUARD_DIR) in str(tool_input.get("patch") or ""):
        return REASON_SELF
    return None


def main():
    try:
        reason = decide(json.load(sys.stdin))
    except Exception:  # unreadable input or a broken rule must be visible, not a silent pass
        traceback.print_exc(file=sys.stderr)
        reason = REASON_ERROR
    if reason:
        print(json.dumps({"decision": "deny", "reason": reason}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
