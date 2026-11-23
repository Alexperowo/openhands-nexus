"""The readiness check reads the model files from llama-swap.yaml and names what is missing."""
import os
import runpy
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
    def test_desk_skill_explains_the_configured_coordinates_and_keeps_aliases(self):
        with tempfile.TemporaryDirectory() as temp:
            screen = Path(temp)
            (screen / "bin").mkdir()
            (screen / ".venv/bin").mkdir(parents=True)
            wrapper = screen / "bin/desk"
            shutil.copy2(preflight.ROOT / "screen/bin/desk", wrapper)
            native = screen / ".venv/bin/desk"
            native.write_text("#!/bin/sh\nif [ \"$1\" = skill ]; then\n"
                              "  printf '%s\\n' '- Coordinates are screen pixels, (0,0) top-left.'\n"
                              "elif [ \"$1\" = zoom ]; then\n"
                              "  printf '%s\\n' 'shows=58,347-558,847' '@@attach /tmp/example.png'\n"
                              "else\n  printf '%s\\n' \"$*\"\nfi\n")
            native.chmod(0o755)
            click = screen / "bin/click"
            click.symlink_to("desk")
            for mode, expected in (("0-1000", "Nexus uses 0-1000"), ("px", "Coordinates are screen pixels")):
                env = {**os.environ, "COORDINATE_SYSTEM": mode}
                self.assertIn(expected, subprocess.check_output([wrapper, "skill"], env=env, text=True))
            self.assertEqual(subprocess.check_output([click, "310", "600"], text=True), "click 310 600\n")
            env = {**os.environ, "COORDINATE_SYSTEM": "0-1000"}
            zoom = screen / "bin/zoom"
            zoom.symlink_to("desk")
            output = subprocess.check_output([zoom, "308", "597"], env=env, text=True)
            self.assertIn("shows=58,347-558,847\n@@attach /tmp/example.png\n", output)
            self.assertIn("desk click-crop X Y", output)
            click_crop = screen / "bin/click-crop"
            click_crop.symlink_to("desk")
            self.assertEqual(subprocess.check_output(
                [click_crop, "493", "513", "shows=58,347-558,847"], env=env, text=True),
                "click 304.500 603.500\n")
            for x, y, expected in (("493", "513", "click 304.500 603.500\n"),
                                   ("647", "508", "click 381.500 601.000\n"),
                                   ("0000", "1000", "click 58.000 847.000\n")):
                self.assertEqual(subprocess.check_output(
                    [wrapper, "click-crop", x, y, "shows=58,347-558,847"], env=env, text=True), expected)
            for coordinate, box in (("1001", "58,347-558,847"), ("500", "558,347-58,847"),
                                    ("500", "58,347-558,1001"), ("500", "$(touch unexpected)")):
                result = subprocess.run([wrapper, "click-crop", coordinate, "500", box],
                                        env=env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_strict_check_rejects_a_skipped_group(self):
        main = runpy.run_path(str(preflight.ROOT / "check"))["main"]
        with tempfile.TemporaryDirectory() as temp, patch("builtins.print"):
            with patch.dict(main.__globals__, {
                "LOGS": Path(temp),
                "layers": lambda: iter([("агент", ".", [], "агент не запущен")]),
            }):
                self.assertEqual(main(), 0)
                self.assertEqual(main(strict=True), 1)

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
