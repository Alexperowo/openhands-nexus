import contextlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import nexus_update as update


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nexus-update-test.")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.u = update.Updater(update.parse_args(["canvas", "1.33.0", "--sandbox", str(self.root)]))
        self.u.emit = Mock()
        self.u.state.mkdir()
        for project in ("agent", "ui"):
            self.set_version(project, "1.30.1")
        (self.root / "ui/dist").mkdir()
        (self.root / "ui/dist/index.html").write_text("working assets")
        source = self.root / "ui/src"
        source.mkdir()
        (source / "conversations.ts").write_text('hook_config: guardHooks; __NEXUS_GUARD__; '
                                                'matcher: "terminal|file_editor|planning_file_editor", '
                                                'hooks: [{type: "command", timeout: 10}]')
        guard = self.root / "guard"
        guard.mkdir()
        (guard / "guard.py").write_text("# frozen fixture, never executed\n")
        self.u.npm_metadata = Mock(return_value={"version": "1.33.0"})
        self.u.locale_report = Mock()

    def set_version(self, project, version):
        base = self.root / project
        package = base / "node_modules" / update.PACKAGE
        package.mkdir(parents=True, exist_ok=True)
        update.atomic_json(package / "package.json", {"version": version})
        update.atomic_json(base / "package.json", {"dependencies": {update.PACKAGE: version}})
        update.atomic_json(base / "package-lock.json", {"packages": {
            "node_modules/" + update.PACKAGE: {"version": version}}})

    def install_runner(self, fail=None):
        counts = {"install": 0, "build": 0}

        def run(command, **kwargs):
            if command[:2] == ["npm", "install"]:
                counts["install"] += 1
                if fail == "second-install" and counts["install"] == 2:
                    raise update.UpdateError("injected install error")
                self.set_version(Path(kwargs["cwd"]).name, "1.33.0")
            if command == ["npm", "run", "build"]:
                counts["build"] += 1
                if fail == "first-build" and counts["build"] == 1:
                    (self.root / "ui/dist/index.html").unlink()
                    raise update.UpdateError("injected deep import error")
                (self.root / "ui/dist/index.html").write_text("rebuilt")
            return ""

        self.u.run = Mock(side_effect=run)
        return counts

    def assert_old_canvas(self):
        self.assertEqual(self.u.installed_canvas(), "1.30.1")
        self.assertTrue((self.root / "ui/dist/index.html").is_file())

    def test_all_dry_runs_have_no_effects(self):
        cases = [["canvas"], ["canvas", "1.33.0"], ["ik-llama"], ["ik-llama", "cea2d61", "--bench", "/no/model.gguf"],
                 ["caddy"], ["voice"], *[["rollback", x] for x in ("canvas", "ik-llama", "caddy", "voice")]]
        with patch.object(update.Updater, "run", side_effect=AssertionError("executed")), \
             patch.object(Path, "mkdir", side_effect=AssertionError("mkdir")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
             contextlib.redirect_stdout(io.StringIO()):
            for case in cases:
                with self.subTest(case=case):
                    self.assertEqual(update.main(case + ["--dry-run"]), 0)

    def test_second_install_failure_restores_both(self):
        counts = self.install_runner("second-install")
        with self.assertRaises(update.UpdateError):
            self.u.canvas()
        self.assert_old_canvas()
        self.assertEqual(counts, {"install": 2, "build": 1})
        self.assertFalse((self.u.state / "update-canvas.json").exists())

    def test_build_failure_restores_and_rebuilds(self):
        counts = self.install_runner("first-build")
        with self.assertRaises(update.UpdateError):
            self.u.canvas()
        self.assert_old_canvas()
        self.assertEqual(counts["build"], 2)

    def test_health_failure_restores(self):
        self.install_runner()
        self.u.health = Mock(side_effect=[update.UpdateError("health failed"), None])
        with self.assertRaises(update.UpdateError):
            self.u.canvas()
        self.assert_old_canvas()
        self.assertEqual(self.u.health.call_count, 2)

    def test_explicit_canvas_rollback(self):
        self.install_runner()
        before = update.digest(self.root / "ui/package-lock.json")
        self.u.canvas()
        self.assertEqual(self.u.installed_canvas(), "1.33.0")
        self.u.args.command, self.u.args.target = "rollback", "canvas"
        self.u.rollback()
        self.assert_old_canvas()
        self.assertEqual(before, update.digest(self.root / "ui/package-lock.json"))
        self.assertFalse((self.u.state / "update-canvas.json").exists())

    def test_mismatch_refuses_before_backup(self):
        self.set_version("ui", "1.31.0")
        with self.assertRaises(update.UpdateError):
            self.u.canvas()
        self.assertFalse(self.u.backups.exists())

    def test_sandbox_refuses_project_symlink(self):
        original = self.root / "ui"
        displaced = self.root / "independent-ui"
        original.rename(displaced)
        original.symlink_to(displaced, target_is_directory=True)
        with self.assertRaisesRegex(update.UpdateError, "независимая"):
            self.u.canvas()
        self.assertFalse(self.u.backups.exists())

    def test_models_gates_fail_closed(self):
        cases = [(["active"], False), (["inactive", "LISTEN 18030"], False),
                 (["inactive", "", "12, /bin/llama-server"], False),
                 (["inactive", "", "15, python"], True),
                 (["inactive", "", "", "90, 2048"], True), (["unknown"], False)]
        for responses, bench in cases:
            with self.subTest(responses=responses):
                self.u.run = Mock(side_effect=responses)
                with self.assertRaises(update.UpdateError):
                    self.u.models_idle(bench)
        self.u.run = Mock(side_effect=["inactive", "", "", "0, 300\n1, 400"])
        self.u.models_idle(True)

    def test_cmake_flags_preserved_and_relocatable(self):
        self.u.backend = self.root / "backend"
        (self.u.backend / "build").mkdir(parents=True)
        (self.u.backend / "build/CMakeCache.txt").write_text(
            "GGML_CUDA:BOOL=ON\nGGML_NCCL:BOOL=ON\nGGML_CUDA_FUSION:STRING=1\n"
            "CMAKE_CUDA_ARCHITECTURES:UNINITIALIZED=75;120\n"
            "CMAKE_CXX_FLAGS_RELEASE:STRING=-O3 -DNDEBUG\n"
            "CMAKE_GENERATOR:INTERNAL=Unix Makefiles\nCMAKE_HOME_DIRECTORY:INTERNAL=/old/source\n")
        flags = self.u.cmake_flags()
        self.assertIn("-DCMAKE_CUDA_ARCHITECTURES:UNINITIALIZED=75;120", flags)
        self.assertIn("-DCMAKE_CXX_FLAGS_RELEASE:STRING=-O3 -DNDEBUG", flags)
        self.assertIn("-DCMAKE_BUILD_RPATH_USE_ORIGIN:BOOL=ON", flags)
        self.assertFalse(any("HOME_DIRECTORY" in flag for flag in flags))

    def test_voice_failure_restores_lock_and_keeps_torch_pin(self):
        self.u.args.sandbox = None
        base = self.root / "voice"
        base.mkdir()
        (base / "uv.lock").write_text("old lock\n")
        (base / "pyproject.toml").write_text('[project]\ndependencies=["torch>=2.2.0,<=2.5.1", "torchaudio<=2.5.1"]\n')
        original = update.digest(base / "pyproject.toml")

        def run(command, **kwargs):
            if command[:3] == ["uv", "lock", "--upgrade"]:
                (base / "uv.lock").write_text("new lock\n")
            return ""

        self.u.run = Mock(side_effect=run)
        self.u.restart = Mock()
        self.u.health = Mock()
        self.u.voice_smoke = Mock(side_effect=[update.UpdateError("STT failed"), None])
        with self.assertRaises(update.UpdateError):
            self.u.voice()
        self.assertEqual((base / "uv.lock").read_text(), "old lock\n")
        self.assertEqual(update.digest(base / "pyproject.toml"), original)
        self.assertEqual(self.u.voice_smoke.call_count, 2)

    def test_caddy_bad_checksum_never_swaps_or_restarts(self):
        base = self.root / "gateway"
        base.mkdir()
        (base / "caddy").write_bytes(b"old caddy")
        self.u.args.target = "2.11.7"
        names = ["caddy_2.11.7_linux_amd64.tar.gz", "caddy_2.11.7_checksums.txt"]
        self.u.fetch_json = Mock(return_value={"assets": [{"name": name, "browser_download_url":
                    "https://github.com/caddyserver/caddy/releases/download/v2.11.7/" + name} for name in names]})

        def run(command, **kwargs):
            destination = Path(command[command.index("--output") + 1])
            destination.write_text("0" * 64 + "  caddy_2.11.7_linux_amd64.tar.gz\n" if destination.suffix == ".txt" else "bad")

        self.u.run = Mock(side_effect=run)
        self.u.restart = Mock()
        with self.assertRaisesRegex(update.UpdateError, "SHA-256"):
            self.u.caddy()
        self.assertEqual((base / "caddy").read_bytes(), b"old caddy")
        self.u.restart.assert_not_called()
        self.assertFalse(list(base.glob("caddy.next-*")))

    def test_caddy_health_failure_restores_binary_and_previous(self):
        base = self.root / "gateway"
        base.mkdir()
        (base / "caddy").write_bytes(b"old caddy")
        (base / "caddy.prev").write_bytes(b"older caddy")
        self.u.args.target = "2.11.7"
        names = ["caddy_2.11.7_linux_amd64.tar.gz", "caddy_2.11.7_checksums.txt"]
        self.u.fetch_json = Mock(return_value={"assets": [{"name": name, "browser_download_url":
                    "https://github.com/caddyserver/caddy/releases/download/v2.11.7/" + name} for name in names]})
        archive_hash = None

        def run(command, **kwargs):
            nonlocal archive_hash
            if command[0] != "curl":
                return ""
            destination = Path(command[command.index("--output") + 1])
            if destination.suffix == ".txt":
                destination.write_text(archive_hash + "  " + names[0] + "\n")
            else:
                payload = io.BytesIO(b"new caddy")
                with tarfile.open(destination, "w:gz") as tar:
                    member = tarfile.TarInfo("caddy");member.size = 9
                    tar.addfile(member, payload)
                archive_hash = update.digest(destination)
            return ""

        self.u.run = Mock(side_effect=run)
        self.u.caddy_environment = Mock(return_value={})
        self.u.restart = Mock()
        self.u.health = Mock(side_effect=[update.UpdateError("health failed"), None])
        with self.assertRaises(update.UpdateError):
            self.u.caddy()
        self.assertEqual((base / "caddy").read_bytes(), b"old caddy")
        self.assertEqual((base / "caddy.prev").read_bytes(), b"older caddy")
        self.assertEqual(self.u.restart.call_args_list[0].args, ("ohn-gateway",))
        self.assertEqual(self.u.restart.call_count, 2)

    def test_check_reports_uv_upgrade_output(self):
        self.u.args = update.parse_args(["check"])
        base = self.root / "voice"
        base.mkdir()
        (base / "uv.lock").write_text('[[package]]\nname="fastapi"\nversion="0.159.1"\n')
        self.u.canvas_pins = Mock(return_value={"agentServer": "1.58.1", "automation": "1.25.1"})
        self.u.fetch_json = Mock(return_value={"tag_name": "v2.11.7"})

        def run(command, **kwargs):
            if command[0] == "uv":
                self.assertTrue(kwargs["include_stderr"])
                return "Resolved 49 packages\nUpdate fastapi v0.159.1 -> v0.162.0"
            if "ls-remote" in command:
                return "a" * 40 + " refs/heads/main"
            if "rev-list" in command:
                return "0"
            if "git" == command[0]:
                return "a" * 40
            return "v2.11.7"

        self.u.run = Mock(side_effect=run)
        self.u.check()
        self.assertIn("Update fastapi", "\n".join(str(c.args[0]) for c in self.u.emit.call_args_list))

    def test_api_smoke_no_messages_and_hook_defaults_allowed(self):
        self.u.args.sandbox = None
        calls, created = [], {}

        def curl(url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith("/settings"):
                return json.dumps({"agent_settings": {"llm": {"base_url": "http://127.0.0.1:18030/v1", "api_key": "***"}}}).encode()
            if kwargs.get("body"):
                created.update(kwargs["body"])
                stored = self.u.root / "agent/state/agent-canvas/dev_conversations/x"
                stored.mkdir(parents=True, exist_ok=True)
                hook = json.loads(json.dumps(created["hook_config"]))
                hook["pre_tool_use"][0]["hooks"][0]["name"] = None
                (stored / "meta.json").write_text(json.dumps({"hook_config": hook}))
                return json.dumps({"id": created["conversation_id"], "persistence_dir": str(stored)}).encode()
            if kwargs.get("method") == "DELETE":
                return b"{}"
            # Like the real server: the API shows no hooks before the conversation runs.
            return json.dumps({"hook_config": None, "execution_status": "idle"}).encode()

        self.u.curl = Mock(side_effect=curl)
        self.u.canvas_smoke()
        self.assertNotIn("initial_message", created)
        self.assertIs(created["autotitle"], False)
        self.assertEqual(created["agent_settings"]["llm"]["api_key"], "not-needed")
        self.assertEqual(calls[-1][1]["method"], "DELETE")
        self.assertTrue(all(not url.endswith(("/run", "/events")) for url, _ in calls))

    def test_api_smoke_rejects_external_llm(self):
        self.u.args.sandbox = None
        self.u.curl = Mock(return_value=b'{"agent_settings":{"llm":{"base_url":"https://external.invalid/v1"}}}')
        with self.assertRaises(update.UpdateError):
            self.u.canvas_smoke()
        self.assertEqual(self.u.curl.call_count, 1)

    def test_ik_build_failure_and_swap_failure_restore(self):
        for failure in ("compile", "swapped-version"):
            with self.subTest(failure=failure):
                self.exercise_ik(failure)

    def exercise_ik(self, failure=None):
        backend = self.root / ("ik-" + str(failure))
        (backend / "build/bin").mkdir(parents=True)
        (backend / "build/bin/llama-server").write_bytes(b"old binary")
        (backend / "build.prev").mkdir()
        (backend / "build.prev/old-marker").write_text("previous previous")
        old_prev = backend.with_name(backend.name + ".prev-commit")
        old_prev.write_text("original pointer\n")
        self.u.backend = backend
        self.u.args.target, self.u.args.bench = "main", None
        self.u.cmake_flags = Mock(return_value=[])
        self.u.models_idle = Mock()

        def run(command, **kwargs):
            command = list(map(str, command))
            if command[:2] == ["git", "rev-parse"]:
                return "b" * 40 if "FETCH_HEAD^{commit}" in command else "a" * 40
            if command[0] == "du":
                return "1 build"
            if command[:2] == ["cmake", "-S"]:
                stage = Path(command[command.index("-B") + 1]);(stage / "bin").mkdir(parents=True)
                (stage / "bin/llama-server").write_bytes(b"new binary")
            if command[:2] == ["cmake", "--build"] and failure == "compile":
                raise update.UpdateError("injected compile failure")
            if command[0] == str(backend / "build/bin/llama-server") and failure == "swapped-version":
                raise update.UpdateError("injected relocated executable failure")
            return ""

        self.u.run = Mock(side_effect=run)
        if failure:
            with self.assertRaises(update.UpdateError):
                self.u.ik_llama()
            self.assertEqual((backend / "build/bin/llama-server").read_bytes(), b"old binary")
            self.assertTrue((backend / "build.prev/old-marker").exists())
            self.assertEqual(old_prev.read_text(), "original pointer\n")
        else:
            self.u.ik_llama()
            self.assertEqual((backend / "build/bin/llama-server").read_bytes(), b"new binary")
            self.assertEqual((backend / "build.prev/bin/llama-server").read_bytes(), b"old binary")
            self.u.args.command, self.u.args.target = "rollback", "ik-llama"
            self.u.rollback()
            self.assertEqual((backend / "build/bin/llama-server").read_bytes(), b"old binary")
        self.assertFalse(list(backend.glob("build.next-*")))

    def test_ik_swap_and_manual_rollback(self):
        self.exercise_ik()


if __name__ == "__main__":
    unittest.main()
