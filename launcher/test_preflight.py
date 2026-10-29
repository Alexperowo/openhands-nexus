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
    def test_folder_path_with_a_space_stops_the_install_at_once(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "Мои программы/OpenHands-Nexus"
            folder.mkdir(parents=True)
            shutil.copy2(root / "install", folder)
            steps = "system,driver,cuda,tools,engine,binaries,apps,keys,models,cards,wifi,services,agent"
            result = subprocess.run(["bash", folder / "install", "--yes", "--skip", steps], capture_output=True,
                                    text=True, env={**os.environ, "HOME": temp}, stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("в пути к папке есть пробел", result.stdout)
        self.assertNotIn("Шаг 1", result.stdout)

if __name__ == "__main__":
    unittest.main()
