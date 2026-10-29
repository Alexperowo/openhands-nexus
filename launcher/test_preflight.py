"""The readiness check reads the model files from llama-swap.yaml and names what is missing."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import preflight

CONFIG = """macros:
  server: /opt/ik/llama-server
  dir: /models/a
  pair: -m ${dir}/a.gguf --mmproj ${dir}/mmproj.gguf

models:
  a:
    cmd: |
      ${server}
      ${pair}
      --chat-template-file a.jinja --port ${PORT}
"""


class PreflightTests(unittest.TestCase):
    def test_model_files_expand_macros_and_resolve_relative_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "llama-swap.yaml"
            config.write_text(CONFIG)
            self.assertEqual(preflight.model_files(config), sorted([
                Path("/opt/ik/llama-server"), Path("/models/a/a.gguf"),
                Path("/models/a/mmproj.gguf"), Path(temp) / "a.jinja"]))

    def test_empty_install_names_what_to_get(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "models").mkdir()
            (Path(temp) / "models/llama-swap.yaml").write_text(CONFIG)
            with patch.object(preflight, "ROOT", Path(temp)), patch.object(preflight, "FFMPEG", Path(temp) / "ffmpeg"):
                found = "\n".join(preflight.missing())
        for item in ("сборка ui/dist", "gateway/caddy", "gateway/ca/openhands-ca.key",
                     "voice/models/v3_e2e_rnnt.ckpt", "/models/a/a.gguf", "/opt/ik/llama-server", "apt install ffmpeg"):
            self.assertIn(item, found)


class InstallTests(unittest.TestCase):
    """./install in a temporary home with only the steps named run (the others are --skip)."""
    STEPS = ("system", "driver", "cuda", "tools", "engine", "binaries", "apps", "keys", "models", "cards", "wifi",
             "services", "agent")

    def install(self, home, folder, run=()):
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(__file__).resolve().parent.parent / "install", folder)
        skip = ",".join(step for step in self.STEPS if step not in run)
        env = {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}
        return subprocess.run(["bash", folder / "install", "--yes", "--skip", skip], capture_output=True, text=True,
                              env=env, stdin=subprocess.DEVNULL)

    def test_folder_path_with_a_space_stops_the_install_at_once(self):
        with tempfile.TemporaryDirectory() as temp:
            result = self.install(Path(temp), Path(temp) / "Мои программы/OpenHands-Nexus")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("в пути к папке есть пробел", result.stdout)
        self.assertNotIn("Шаг 1", result.stdout)

    def test_key_left_without_its_certificate_gets_one(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "OpenHands-Nexus"
            ca = folder / "gateway/ca"
            ca.mkdir(parents=True)
            key = ca / "openhands-ca.key"
            subprocess.run(["openssl", "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256",
                            "-out", key], check=True, capture_output=True)
            before = key.read_bytes()
            result = self.install(Path(temp), folder, run=("keys",))
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(key.read_bytes(), before)
            public = [subprocess.run(command, capture_output=True, text=True).stdout for command in (
                ["openssl", "pkey", "-in", key, "-pubout"],
                ["openssl", "x509", "-in", ca / "openhands-ca.crt", "-noout", "-pubkey"])]
            self.assertTrue(public[0].startswith("-----BEGIN PUBLIC KEY"))
            self.assertEqual(public[0], public[1])

if __name__ == "__main__":
    unittest.main()
