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


def terminal(command):
    return {"event_type": "PreToolUse", "tool_name": "terminal", "tool_input": {"command": command}}


def decide(command):
    guard.process_table.cache_clear()
    return guard.decide(terminal(command))


def session_process():
    """A process of the login session scope, as (name, pid)."""
    for p in guard._scan():
        if guard.AUTOSTART_CGROUP.search(p.cgroup) and p.comm not in guard.INTERPRETERS and len(p.comm) < 15:
            return p.comm, p.pid
    return None


DANGEROUS = {
    "cinnamon --replace &": guard.REASON_START,
    "nohup setsid kwin_x11 --replace >/dev/null 2>&1 &": guard.REASON_START,
    "sudo -u user plasmashell --replace": guard.REASON_START,
    "echo ok\nmuffin --replace": guard.REASON_START,
    'bash -lc "xfwm4 --replace"': guard.REASON_START,
    "systemd-run --user --scope cinnamon --replace": guard.REASON_START,
    "kill -9 -1": guard.REASON_ALL,
    "pkill -u user": guard.REASON_ALL,
    "kill $(lsof -t -i:18030)": guard.REASON_NEXUS,
    "fuser -k 8443/tcp": guard.REASON_NEXUS,
    "systemctl --user stop openhands-agent-server": guard.REASON_NEXUS,
    "systemctl --user restart llama-server": guard.REASON_NEXUS,
    "systemctl --user stop ohn.target": guard.REASON_NEXUS,
    "systemctl --user restart ohn-models.service": guard.REASON_NEXUS,
    "kill $(lsof -t -i:18011)": guard.REASON_NEXUS,
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
    f"echo x > {GUARD}": guard.REASON_SELF,
    f"sed -i s/a/b/ {GUARD}": guard.REASON_SELF,
}

ORDINARY = [
    "ls -la /usr/share/icons/",
    "grep -r cinnamon ~/.config/cinnamon/spices | head",
    "gsettings set org.cinnamon.desktop.interface icon-theme 'Mint-Y'",
    "gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon --method org.Cinnamon.RestartCinnamon true",
    "systemd-run --user --collect --service-type=exec cinnamon --replace",
    "systemctl --user restart pipewire",
    "cinnamon --version",
    "command -v nm-applet",
    "kill 999999",
    "kill -0 999999",
    "pkill -f 'python my_script.py'",
    "killall firefox-nonexistent",
    "rm -rf /tmp/build-cache ~/Downloads/old",
    "systemctl --user status openhands-agent-server",
    "cat /etc/resolv.conf",
    "cp /etc/resolv.conf /tmp/resolv.copy",
    "nmcli -f ipv4.dns connection show office",
    "nmcli device status",
    "curl -s http://127.0.0.1:18030/health",
    "ps aux | grep llama-server",
    "python3 -m http.server 9000",
    f"cd {GUARD.parent} && cat {GUARD.name}",
    "sudo apt install -y htop",
    "ls \\\n  /tmp",
]


class GuardRules(unittest.TestCase):
    def test_dangerous_commands_are_blocked_with_advice(self):
        for command, reason in DANGEROUS.items():
            with self.subTest(command=command):
                self.assertTrue((decide(command) or "").startswith(reason.split("{")[0]), decide(command))

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
        with mock.patch.object(guard, "processes", return_value=(server, voice)):
            for command in ("sudo pkill -f llama-server", "killall llama-server", "kill -9 4242", "pkill python"):
                with self.subTest(command=command):
                    self.assertEqual(guard.decide(terminal(command)), guard.REASON_NEXUS)
            self.assertIsNone(guard.decide(terminal("pkill -f some-other-tool")))

    def test_ordinary_commands_pass(self):
        for command in ORDINARY:
            with self.subTest(command=command):
                self.assertIsNone(decide(command))

    def test_session_components_found_by_systemd_not_by_name(self):
        found = session_process()
        if found is None:
            self.skipTest("no login session scope here")
        name, pid = found
        stop = guard.REASON_SESSION_PROC.split("{")[0]
        for command in (f"killall {name}", f"kill -9 {pid}", f"kill $(pgrep -x {name})",
                        f"pgrep -x {name} | xargs kill", f"sudo pkill -x {name}"):
            with self.subTest(command=command):
                self.assertTrue((decide(command) or "").startswith(stop), decide(command))
        start = guard.REASON_START.split("{")[0]
        for command in (f"{name} &", f"setsid {name} >/dev/null 2>&1 &", f"bash -c '{name} &'"):
            with self.subTest(command=command):
                self.assertTrue((decide(command) or "").startswith(start), decide(command))

    def test_session_service_stop_blocked_restart_allowed(self):
        if guard.unit_slice("pipewire.service") != "session.slice":
            self.skipTest("pipewire is not a user session service here")
        self.assertIn("session.slice", decide("systemctl --user stop pipewire.service") or "")
        self.assertIsNone(decide("systemctl --user restart pipewire.service"))

    def test_advice_is_desktop_neutral(self):
        for reason in (guard.REASON_SESSION_PROC, guard.REASON_START):
            self.assertIn("XDG_CURRENT_DESKTOP", reason)
            self.assertNotIn("Cinnamon", reason)
        self.assertIn("systemd-run --user --collect --service-type=exec", guard.REASON_START)

    def test_terminal_input_and_other_tools_pass(self):
        event = {"tool_name": "terminal", "tool_input": {"command": "kill -9 -1", "is_input": True}}
        self.assertIsNone(guard.decide(event))
        self.assertIsNone(guard.decide({"tool_name": "file_editor",
                                        "tool_input": {"command": "view", "path": str(GUARD)}}))
        self.assertIsNone(guard.decide({"tool_name": "file_editor",
                                        "tool_input": {"command": "create", "path": "/tmp/notes.txt"}}))

    def test_protected_files_are_not_editable_by_the_agent(self):
        edit = lambda path: {"tool_name": "file_editor", "tool_input": {"command": "str_replace", "path": path}}
        self.assertEqual(guard.decide(edit(str(GUARD))), guard.REASON_SELF)
        self.assertEqual(guard.decide(edit("/etc/systemd/resolved.conf")), guard.REASON_NETWORK)
        patch = {"tool_name": "apply_patch", "tool_input": {"patch": f"*** Update File: {GUARD}\n"}}
        self.assertEqual(guard.decide(patch), guard.REASON_SELF)

    def test_hook_contract(self):
        """Exit 2 and a JSON deny on stdout block; exit 0 and no output allow; a crash blocks visibly."""
        run = lambda data: subprocess.run([sys.executable, str(GUARD)], input=data,
                                          capture_output=True, text=True, timeout=10)
        blocked = run(json.dumps(terminal("kill -9 -1")))
        self.assertEqual(blocked.returncode, 2)
        self.assertEqual(json.loads(blocked.stdout), {"decision": "deny", "reason": guard.REASON_ALL})
        allowed = run(json.dumps(terminal("ls")))
        self.assertEqual((allowed.returncode, allowed.stdout), (0, ""))
        self.assertEqual(run("not json").returncode, 0)
        broken = run(json.dumps({"tool_name": "terminal", "tool_input": {"command": 42}}))
        self.assertEqual((broken.returncode, json.loads(broken.stdout)["reason"]), (2, guard.REASON_ERROR))


if __name__ == "__main__":
    unittest.main()
