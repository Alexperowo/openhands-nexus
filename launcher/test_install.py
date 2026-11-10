"""launcher/install.sh writes units that start nothing by themselves and hand the keys only to
the two services that work with them; launcher/run.sh does not pass the keys further on."""
import subprocess
import tempfile
import unittest
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parent
SERVICES = ("models", "voice", "agent", "gateway", "watch")


class UnitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        home, tools = Path(cls.temp.name, "home"), Path(cls.temp.name, "tools")
        home.mkdir()
        tools.mkdir()
        # The real commands would reload the user's systemd and rewrite the desktop shortcuts.
        for name, body in (("systemctl", ""), ("gio", ""), ("xdg-user-dir", 'echo "$HOME/Desktop"'),
                           ("python3", ""), ("openssl", "echo 0123abcd")):
            (tools / name).write_text(f"#!/bin/sh\n{body}\n")
            (tools / name).chmod(0o755)
        env = {"HOME": str(home), "PATH": f"{tools}:/usr/bin:/bin"}
        subprocess.run(["bash", str(LAUNCHER / "install.sh")], env=env, check=True, capture_output=True, timeout=60)
        cls.config = home / ".config"
        cls.units = {path.name: path.read_text() for path in (cls.config / "systemd/user").iterdir()}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_every_service_has_a_unit_under_the_target(self):
        self.assertEqual(set(self.units), {f"ohn-{name}.service" for name in SERVICES} | {"ohn.target"})
        for name in SERVICES:
            self.assertIn(f"ohn-{name}.service", self.units["ohn.target"])
            self.assertIn(f"launcher/run.sh {name}\n", self.units[f"ohn-{name}.service"])

    def test_nothing_can_start_with_the_session(self):
        for name, text in self.units.items():
            self.assertNotIn("[Install]", text, name)
            self.assertNotIn("WantedBy", text, name)

    def test_only_the_agent_and_the_gateway_get_the_keys(self):
        keys = f"EnvironmentFile={self.config}/openhands-nexus/session.env\n"
        for name in SERVICES:
            self.assertEqual(keys in self.units[f"ohn-{name}.service"], name in ("agent", "gateway"), name)
        self.assertNotIn("EnvironmentFile", self.units["ohn.target"])

    def test_keys_are_private_and_kept(self):
        session = self.config / "openhands-nexus/session.env"
        self.assertEqual(session.stat().st_mode & 0o777, 0o600)
        self.assertEqual(session.read_text(), "OHN_SESSION_KEY=0123abcd\nOHN_SECRET_KEY=0123abcd\n")


class RunTests(unittest.TestCase):
    def started(self, service, files=()):
        """The environment and arguments the service's program gets from run.sh, in a copy of the tree
        where that program only prints them."""
        with tempfile.TemporaryDirectory() as temp:
            work, tools = Path(temp, "nexus"), Path(temp, "tools")
            (work / "launcher").mkdir(parents=True)
            (work / "launcher/run.sh").write_text((LAUNCHER / "run.sh").read_text())
            tools.mkdir()
            show = "#!/bin/sh\nenv\n"
            for name in ("node", "curl", "sleep", *files):
                target = tools / name if "/" not in name else work / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(show if name in ("node", *files) else "#!/bin/sh\nexit 0\n")
                target.chmod(0o755)
            (work / "agent/skills").mkdir(parents=True, exist_ok=True)
            env = {"HOME": temp, "PATH": f"{tools}:/usr/bin:/bin", "XDG_RUNTIME_DIR": temp, "OHN_LAN_IP": "192.168.1.5",
                   "OHN_SESSION_KEY": "session-value", "OHN_SECRET_KEY": "secret-value"}
            result = subprocess.run(["bash", str(work / "launcher/run.sh"), service], env=env, capture_output=True,
                                    text=True, timeout=60)
            return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)

    def test_canvas_gets_the_keys_under_its_own_names_only(self):
        env = self.started("agent")
        self.assertEqual(env["LOCAL_BACKEND_API_KEY"], "session-value")
        self.assertEqual(env["OH_SECRET_KEY"], "secret-value")  # the SDK keeps this name out of the terminal
        self.assertNotIn("OHN_SESSION_KEY", env)
        self.assertNotIn("OHN_SECRET_KEY", env)

    def test_the_gateway_gets_the_session_key_alone(self):
        env = self.started("gateway", files=("gateway/caddy", "ui/dist/index.html"))
        self.assertEqual(env["OHN_SESSION_KEY"], "session-value")
        self.assertNotIn("OHN_SECRET_KEY", env)


if __name__ == "__main__":
    unittest.main()
