"""Guard rules: dangerous commands are stopped with advice, ordinary work passes.

Session rules read the live process table and systemd units, so the session cases use
components that run on this PC and are skipped where they are absent.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import guard

GUARD = Path(guard.__file__).resolve()


def terminal(command, working_dir="/tmp"):
    return {"event_type": "PreToolUse", "tool_name": "terminal", "tool_input": {"command": command},
            "working_dir": working_dir}


def decide(command, working_dir="/tmp"):
    guard.process_table.cache_clear()
    return guard.decide(terminal(command, working_dir))


def matches(result, reason):
    """The reason itself, or for a template its fixed start and end around the placeholders."""
    if "{" not in reason:
        return result == reason
    return result.startswith(reason.split("{")[0]) and result.endswith(reason.rsplit("}", 1)[-1])


def session_process():
    """A process of the login session scope, as (name, pid)."""
    for p in guard._scan():
        if guard.AUTOSTART_CGROUP.search(p.cgroup) and p.comm not in guard.INTERPRETERS and len(p.comm) < 15:
            return p.comm, p.pid
    return None


HOME = guard.HOME
DANGEROUS = {
    "cinnamon --replace &": guard.REASON_REPLACE,
    "nohup setsid kwin_x11 --replace >/dev/null 2>&1 &": guard.REASON_REPLACE,
    "sudo -u user plasmashell --replace": guard.REASON_REPLACE,
    "echo ok\nmuffin --replace": guard.REASON_REPLACE,
    'bash -lc "xfwm4 --replace"': guard.REASON_REPLACE,
    "systemd-run --user --scope cinnamon --replace": guard.REASON_REPLACE,
    # Detached by systemd, but the replaced shell still leaves the session manager.
    "systemd-run --user --collect --service-type=exec cinnamon --replace": guard.REASON_REPLACE,
    "kill -9 -1": guard.REASON_ALL,
    "pkill -u user": guard.REASON_ALL,
    "kill $(lsof -t -i:18030)": guard.REASON_NEXUS,
    "fuser -k 8443/tcp": guard.REASON_NEXUS,
    "systemctl --user stop openhands-agent-server": guard.REASON_NEXUS,
    "systemctl --user restart llama-server": guard.REASON_NEXUS,
    "systemctl --user stop ohn.target": guard.REASON_NEXUS,
    "systemctl --user stop ohn-watch": guard.REASON_NEXUS,
    "systemctl --user restart ohn-models.service": guard.REASON_NEXUS,
    "systemctl --user reload-or-try-restart ohn-models": guard.REASON_NEXUS,
    "pkexec systemctl --user stop ohn-models": guard.REASON_NEXUS,
    "pkexec --user root systemctl restart NetworkManager": guard.REASON_NETWORK,
    "kill $(lsof -t -i:18011)": guard.REASON_NEXUS,
    "kill -9 $(lsof -t -i:18043)": guard.REASON_NEXUS,
    "fuser -k 18041/tcp": guard.REASON_NEXUS,
    "ip link set wlan0 down": guard.REASON_NETWORK,
    "sudo ip route flush default": guard.REASON_NETWORK,
    "kwriteconfig6 --file kioslaverc --group 'Proxy Settings' --key ProxyType 0": guard.REASON_NETWORK,
    "sudo rm -rf /": guard.REASON_RM,
    "rm -rf ~/": guard.REASON_RM,
    "rm -r --force /home/user/*": guard.REASON_RM,
    "rm -rf /tmp/../home/user": guard.REASON_RM,
    "rm -rf ~/.config": guard.REASON_RM,
    f"rm -rf {GUARD.parent.parent}/": guard.REASON_RM,
    f"rm -r {GUARD.parent.parent}/agent/state": guard.REASON_RM,
    "rm -rf ~/.config/openhands-nexus": guard.REASON_RM,
    "gio trash ~/.config": guard.REASON_RM,
    "find ~ -mindepth 1 -delete": guard.REASON_RM,
    f"python3 -c \"import shutil; shutil.rmtree('{HOME}')\"": guard.REASON_RM,
    f"rm -rf {HOME}/Documents": guard.REASON_TRASH,
    "rm -rf ~/Agents/Backups": guard.REASON_TRASH,
    "rm -rf ~/.cache": guard.REASON_TRASH,
    f"python3 -c \"import shutil; shutil.rmtree('{HOME}/Documents')\"": guard.REASON_TRASH,
    "python3 - <<'EOF'\nimport shutil, os\nshutil.rmtree(os.path.expanduser('~/Agents/Backups'))\nEOF":
        guard.REASON_TRASH,
    "find ~/Agents/Backups -type f -delete": guard.REASON_TRASH,
    "find ~/Agents/Backups -exec rm -rf {} +": guard.REASON_TRASH,
    "find ~/Agents/Backups | xargs rm -rf": guard.REASON_TRASH,
    "find ~/Agents/Backups -name '*' -delete": guard.REASON_TRASH,  # a test that lets everything through
    "find ~ -regex '.*' -delete": guard.REASON_RM,
    "D=~/Agents; rm -rf $D": guard.REASON_RM,
    'export TARGET="$HOME/.config" && rm -rf "$TARGET"': guard.REASON_RM,
    "base=/home; sub=$base/user; rm -rf ${sub}/": guard.REASON_RM,
    'rm -rf "$BUILD_DIR/"*': guard.REASON_EMPTY_VAR,  # BUILD_DIR unset: rm -rf /*
    "rm -rf ~/$PROJECT": guard.REASON_EMPTY_VAR,
    'rm -rf "${OUT:-$HOME}"': guard.REASON_EMPTY_VAR,
    "find $ROOT/ -delete": guard.REASON_EMPTY_VAR,
    # Variables as the shell has them, command by command (acceptance A4).
    'D=; rm -rf "${D:-$HOME}"': guard.REASON_RM,  # empty: the default
    'D=x; rm -rf "${D:+$HOME}"': guard.REASON_RM,
    'D=~/Agents; rm -rf "$D"; D=/tmp/cache': guard.REASON_RM,  # a later value does not count
    f'cd {HOME}/Documents; rm -rf "$PWD"': guard.REASON_TRASH,
    'cd ~ && rm -rf "$PWD"/*': guard.REASON_RM,
    'D=/tmp/x; unset D; rm -rf "$D"/*': guard.REASON_RM,
    'read D; rm -rf "$D"/*': guard.REASON_EMPTY_VAR,
    '[ -d /tmp/x ] && D=/tmp/x || D=~/Agents; rm -rf "$D"': guard.REASON_RM,  # either value
    'D=~/Agents; true && D=/tmp/x; rm -rf "$D"': guard.REASON_RM,  # the && chain may stop before D=
    'D=~/Agents; test -d /tmp/x || D=/tmp/x && rm -rf "$D"': guard.REASON_RM,
    """D=~/Agents bash -c 'rm -rf "$D"'""": guard.REASON_RM,
    'for d in /tmp/a ~/Documents; do rm -rf "$d"; done': guard.REASON_TRASH,
    # Commands after shell keywords are commands too.
    "for d in x; do rm -rf ~/Agents; done": guard.REASON_RM,
    "if true; then rm -rf ~; fi": guard.REASON_RM,
    "{ rm -rf ~/.config; }": guard.REASON_RM,
    "f() { rm -rf ~/.local; }; f": guard.REASON_RM,
    "kill 0": guard.REASON_OWN_GROUP,
    "kill -9 0": guard.REASON_OWN_GROUP,
    "kill -s KILL 0": guard.REASON_OWN_GROUP,
    "kill -- -0": guard.REASON_OWN_GROUP,
    "pkill -g 0 python": guard.REASON_OWN_GROUP,
    "cd ~ && rm -rf Agents": guard.REASON_RM,
    "cd ~/Agents && rm -rf Backups": guard.REASON_TRASH,
    "sudo systemctl restart lightdm": guard.REASON_SESSION,
    "sudo systemctl restart display-manager": guard.REASON_SESSION,
    "cinnamon-session-quit --logout --no-prompt": guard.REASON_SESSION,
    "loginctl terminate-user user": guard.REASON_SESSION,
    "sudo reboot": guard.REASON_SESSION,
    "systemctl poweroff": guard.REASON_SESSION,
    "echo nameserver 1.1.1.1 | sudo tee /etc/resolv.conf": guard.REASON_NETWORK,
    "cat > /etc/resolv.conf": guard.REASON_NETWORK,
    "sudo systemctl stop systemd-resolved": guard.REASON_NETWORK,
    "gsettings set org.gnome.system.proxy mode 'none'": guard.REASON_NETWORK,
    "nmcli connection modify office ipv4.dns 1.1.1.1": guard.REASON_NETWORK,
    "nmcli networking off": guard.REASON_NETWORK,
    "echo '[main]' | sudo tee /etc/NetworkManager/conf.d/dns.conf": guard.REASON_NETWORK,
    "sudo cp /tmp/x /etc/NetworkManager/dispatcher.d/99-x": guard.REASON_NETWORK,
    "cd /etc && echo nameserver 1.1.1.1 | sudo tee resolv.conf": guard.REASON_NETWORK,
    "sudo dd if=/tmp/r of=/etc/resolv.conf": guard.REASON_NETWORK,
    "python3 -c \"open('/etc/resolv.conf', 'w').write('nameserver 1.1.1.1')\"": guard.REASON_NETWORK,
    f"echo x > {GUARD}": guard.REASON_SELF,
    f"sed -i s/a/b/ {GUARD}": guard.REASON_SELF,
    f"cd {GUARD.parent} && sed -i s/a/b/ {GUARD.name}": guard.REASON_SELF,
    f"cd {GUARD.parent.parent} && echo x >> guard/test_guard.py": guard.REASON_SELF,
    "sed -i s/a/b/ guard.py": guard.REASON_SELF,  # the terminal may be in the guard folder already
    f"python3 -c \"open('{GUARD}', 'a').write('x')\"": guard.REASON_SELF,
    f"python3 -c \"import pathlib; pathlib.Path('{GUARD}').write_text('')\"": guard.REASON_SELF,
}

ORDINARY = [
    "ls -la /usr/share/icons/",
    "grep -r cinnamon ~/.config/cinnamon/spices | head",
    "gsettings set org.cinnamon.desktop.interface icon-theme 'Mint-Y'",
    "gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon --method org.Cinnamon.RestartCinnamon true",
    "systemd-run --user --collect --service-type=exec cinnamon",  # brings back a shell that died
    "podman run --replace --name web nginx",
    "systemctl --user restart pipewire",
    "cinnamon --version",
    "command -v nm-applet",
    "kill 999999",
    "kill -0 999999",
    "kill -0 1",
    "kill -s 0 1",
    "pkill -0 -x systemd",
    "kill -0 $(lsof -t -i:18030)",
    "pkill -f vite",
    "pkill -f 'python my_script.py'",
    "killall firefox-nonexistent",
    "rm -rf /tmp/build-cache ~/Downloads/old",
    "rm -rf ~/Загрузки/YAAS",
    "gio trash ~/Agents/Backups",
    "find ~/Agents/Backups -name '*.tmp' -delete",
    'rm -rf "${BUILD_DIR:?}/"*',  # the shell stops if it is empty
    "rm -rf $BUILD_DIR/cache /tmp/$JOB",
    'rm -rf "$TMPDIR"',  # empty: rm -rf "" removes nothing
    "D=/tmp/x; rm -rf $D",
    "D=$(mktemp -d); rm -rf $D/*",
    'echo "D=/"; rm -rf $D/build',
    'D=; rm -rf "${D-$HOME}"',  # set though empty: no default, rm -rf "" removes nothing
    'D=/tmp/x; rm -rf "$D"; D=~/Agents',
    'cd /tmp/x && D=build && rm -rf "$D"/*',  # the && chain ran up to rm
    'D=$(mktemp -d) && cd "$D" && rm -rf ./*',
    'for d in /tmp/a /tmp/b; do rm -rf "$d"; done',
    "if [ -d /tmp/x ]; then rm -rf /tmp/x; fi",
    "kill -0 0",
    "kill 0123456",
    "pgrep -g 0",
    "python3 -c \"import shutil; shutil.rmtree('/tmp/build')\"",
    "cd /tmp && rm -rf *",
    "systemctl --user status openhands-agent-server",
    "cat /etc/resolv.conf",
    "cp /etc/resolv.conf /tmp/resolv.copy",
    "sudo cp /etc/resolv.conf /etc/resolv.conf.backup",
    "python3 -c \"print(open('/etc/resolv.conf').read())\"",
    "nmcli -f ipv4.dns connection show office",
    "nmcli device status",
    "curl -s http://127.0.0.1:18030/health",
    "ps aux | grep llama-server",
    "python3 -m http.server 9000",
    f"cd {GUARD.parent} && cat {GUARD.name}",
    f"cd {GUARD.parent} && python3 test_guard.py",
    f"cd {GUARD.parent.parent} && git diff guard/guard.py",
    "sudo apt install -y htop",
    "ls \\\n  /tmp",
]


class GuardRules(unittest.TestCase):
    def test_dangerous_commands_are_blocked_with_advice(self):
        for command, reason in DANGEROUS.items():
            with self.subTest(command=command):
                self.assertTrue(matches(decide(command) or "", reason), decide(command))

    def test_killing_a_running_nexus_service_is_blocked(self):
        """pkill reaches only live processes, so the model server is faked: the test must not need it running."""
        argv = ["/opt/llama/bin/llama-server", "-m", "model.gguf", "--port", "18040"]
        server = SimpleNamespace(pid="4242", comm="llama-server", argv=argv, line=" ".join(argv),
                                 cgroup="/user.slice/user-1000.slice/user@1000.service/app.slice/ohn-models.service",
                                 pgrp="4242", unit="ohn-models.service")
        voice_argv = ["/opt/nexus/voice/.venv/bin/python3", "-m", "uvicorn", "service:app", "--port", "18020"]
        voice = SimpleNamespace(pid="4343", comm="python3", argv=voice_argv, line=" ".join(voice_argv),
                                cgroup="/user.slice/user-1000.slice/user@1000.service/app.slice/ohn-voice.service",
                                pgrp="4343", unit="ohn-voice.service")
        watch_argv = ["python3", "-I", "/opt/nexus/launcher/watch.py"]
        watcher = SimpleNamespace(pid="4444", comm="python3", argv=watch_argv, line=" ".join(watch_argv),
                                  cgroup="/user.slice/user-1000.slice/user@1000.service/app.slice/ohn-watch.service",
                                  pgrp="4444", unit="ohn-watch.service")
        with mock.patch.object(guard, "processes", return_value=(server, voice, watcher)):
            for command in ("sudo pkill -f llama-server", "killall llama-server", "kill -9 4242", "pkill python",
                            "pkill -n llama-server", "pkill -o llama-server", "pkill -nf llama-server",
                            "kill 4444", "pkill -f watch.py"):
                with self.subTest(command=command):
                    self.assertEqual(guard.decide(terminal(command)), guard.REASON_NEXUS)
            self.assertIsNone(guard.decide(terminal("pkill -f some-other-tool")))
            self.assertIsNone(guard.decide(terminal("kill -0 4242")))

    def test_ordinary_commands_pass(self):
        for command in ORDINARY:
            with self.subTest(command=command):
                self.assertIsNone(decide(command))

    def test_editor_relative_protected_paths(self):
        for tool in ("file_editor", "planning_file_editor"):
            for directory, path, reason in ((str(GUARD.parent), "guard.py", guard.REASON_SELF),
                                             ("/etc", "resolv.conf", guard.REASON_NETWORK),
                                             ("/etc", "NetworkManager/new.conf", guard.REASON_NETWORK)):
                with self.subTest(tool=tool, path=path):
                    self.assertEqual(guard.decide({"tool_name": tool, "working_dir": directory,
                        "tool_input": {"command": "create", "path": path}}), reason)

    def test_session_components_found_by_systemd_not_by_name(self):
        found = session_process()
        if found is None:
            self.skipTest("no login session scope here")
        name, pid = found
        for command in (f"killall {name}", f"kill -9 {pid}", f"kill $(pgrep -x {name})",
                        f"pgrep -x {name} | xargs kill", f"sudo pkill -x {name}"):
            with self.subTest(command=command):
                self.assertTrue(matches(decide(command) or "", guard.REASON_SESSION_PROC), decide(command))
        for command in (f"{name} &", f"setsid {name} >/dev/null 2>&1 &", f"bash -c '{name} &'"):
            with self.subTest(command=command):
                self.assertTrue(matches(decide(command) or "", guard.REASON_START), decide(command))

    def test_session_service_stop_blocked_restart_allowed(self):
        if guard.unit_slice("pipewire.service") != "session.slice":
            self.skipTest("pipewire is not a user session service here")
        self.assertIn("session.slice", decide("systemctl --user stop pipewire.service") or "")
        self.assertIsNone(decide("systemctl --user restart pipewire.service"))

    def test_advice_is_desktop_neutral(self):
        for reason in (guard.REASON_SESSION_PROC, guard.REASON_START, guard.REASON_REPLACE):
            self.assertIn("XDG_CURRENT_DESKTOP", reason)
            self.assertIn("gdbus introspect", reason)
            self.assertNotIn("Cinnamon", reason)
        for reason in (guard.REASON_START, guard.REASON_REPLACE):
            self.assertIn("systemd-run --user --collect --service-type=exec", reason)

    def test_terminal_input_is_checked_other_tools_pass(self):
        """Text sent to a running program reaches the shell when the program has finished."""
        typed = lambda text: {"tool_name": "terminal", "tool_input": {"command": text, "is_input": True}}
        self.assertEqual(guard.decide(typed("kill -9 -1")), guard.REASON_ALL)
        self.assertIsNone(guard.decide(typed("y")))
        self.assertIsNone(guard.decide(typed("C-c")))
        self.assertIsNone(guard.decide({"tool_name": "file_editor",
                                        "tool_input": {"command": "view", "path": str(GUARD)}}))
        self.assertIsNone(guard.decide({"tool_name": "file_editor",
                                        "tool_input": {"command": "create", "path": "/tmp/notes.txt"}}))

    def test_whole_disks_homes_and_models_are_never_removed(self):
        for path in sorted(guard.mount_points() | guard.homes()):
            with self.subTest(path=path):
                self.assertEqual(decide(f"sudo rm -rf {path}"), guard.REASON_RM)
        for path in guard.nexus_paths():
            with self.subTest(path=path):
                self.assertEqual(decide(f"rm -rf {Path(path).parent}"), guard.REASON_RM)
        self.assertEqual(decide("rm -rf *", working_dir=HOME), guard.REASON_RM)
        self.assertEqual(decide("rm -rf .*", working_dir=HOME), guard.REASON_RM)

    def test_protected_files_are_not_editable_by_the_agent(self):
        edit = lambda path: {"tool_name": "file_editor", "tool_input": {"command": "str_replace", "path": path}}
        self.assertEqual(guard.decide(edit(str(GUARD))), guard.REASON_SELF)
        self.assertEqual(guard.decide(edit("/etc/systemd/resolved.conf")), guard.REASON_NETWORK)
        patch = {"tool_name": "apply_patch", "tool_input": {"patch": f"*** Update File: {GUARD}\n"}}
        self.assertEqual(guard.decide(patch), guard.REASON_SELF)

    def test_hook_contract(self):
        """Exit 2 and a JSON deny on stdout block; exit 0 and no output allow; bad input or a crash blocks visibly."""
        run = lambda data: subprocess.run([sys.executable, str(GUARD)], input=data,
                                          capture_output=True, text=True, timeout=10)
        blocked = run(json.dumps(terminal("kill -9 -1")))
        self.assertEqual(blocked.returncode, 2)
        self.assertEqual(json.loads(blocked.stdout), {"decision": "deny", "reason": guard.REASON_ALL})
        allowed = run(json.dumps(terminal("ls")))
        self.assertEqual((allowed.returncode, allowed.stdout), (0, ""))
        unreadable = run("not json")
        self.assertEqual((unreadable.returncode, json.loads(unreadable.stdout)["reason"]), (2, guard.REASON_ERROR))
        broken = run(json.dumps({"tool_name": "terminal", "tool_input": {"command": 42}}))
        self.assertEqual((broken.returncode, json.loads(broken.stdout)["reason"]), (2, guard.REASON_ERROR))


if __name__ == "__main__":
    unittest.main()
