"""./pack: the clean archive check catches what must not leave this PC; the private copy goes back intact."""
import importlib.util
import io
import os
import subprocess
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("archive", HERE / "archive.py")
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)

KEY = "3f" * 32


def build(folder, extra=(), mode=0o755):
    """A project tar: the required files plus extra (name, body); body None or str makes a link."""
    path = Path(folder) / "project.tar"
    with tarfile.open(path, "w") as tar:
        for name, body in [(n, b"ok\n") for n in archive.REQUIRED] + list(extra):
            info = tarfile.TarInfo("OpenHands-Nexus/" + name)
            if not isinstance(body, bytes):
                info.type, info.linkname = tarfile.SYMTYPE, body or "/etc/passwd"
                tar.addfile(info)
                continue
            info.size, info.mode = len(body), mode if name in archive.EXECUTABLE else 0o644
            tar.addfile(info, io.BytesIO(body))
    return path


class ScanTests(unittest.TestCase):
    def scan(self, extra=(), **kwargs):
        with tempfile.TemporaryDirectory() as temp:
            return archive.scan(build(temp, extra, **kwargs), keys=[KEY.encode()])

    def test_clean_project_passes(self):
        self.assertEqual(self.scan([("agent/main.py", b"print('hi')\n")]), [])

    def test_personal_and_heavy_files_are_caught(self):
        names = ["agent/state/settings.json", "gateway/ca/root.crt", ".env", "x/session.env",
                 "models/Nex.gguf", "voice/models/vad.pt", "ui/node_modules/a.js", "a.py.bak", "voice.log"]
        problems = self.scan([(n, b"x") for n in names])
        self.assertEqual(sorted(p.split(":")[0] for p in problems), sorted(names))

    def test_secrets_are_named_by_file_never_shown(self):
        token = "hf_" + "A1b2" * 9
        problems = self.scan([("notes.md", f"token {token}\n".encode()),
                              ("cfg.txt", f"key={KEY}\n".encode())])
        self.assertEqual(len(problems), 2)
        self.assertFalse(any(token in p or KEY in p for p in problems))

    def test_programs_links_and_big_files_are_caught(self):
        problems = self.scan([("tool", b"\x7fELF" + b"\0" * 10), ("link", None),
                              ("big.json", b"0" * (archive.LIMIT + 1))])
        self.assertEqual(sorted(p.split(":")[0] for p in problems), ["big.json", "link", "tool"])
        self.assertEqual(self.scan([("bin/inner", "../lib/tool")]), [])
        self.assertEqual(len(self.scan([("bin/outer", "../../home/x")])), 1)

    def test_missing_and_not_executable(self):
        problems = self.scan(mode=0o644)
        self.assertIn("install: не исполняемый", problems)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "empty.tar"
            with tarfile.open(path, "w") as tar:
                info = tarfile.TarInfo("OpenHands-Nexus/README.md")
                tar.addfile(info, io.BytesIO(b""))
            self.assertIn("install: нет в архиве", archive.scan(path, keys=[]))

    def test_this_project_passes(self):
        """What ./pack would take after a commit: tracked and new files, not the ignored ones."""
        root = HERE.parent
        listed = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                                cwd=root, capture_output=True)
        if listed.returncode != 0:
            self.skipTest("не git-копия проекта")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "project.tar"
            with tarfile.open(path, "w") as tar:
                for name in filter(None, listed.stdout.decode().split("\0")):
                    if os.path.lexists(root / name):  # a deletion not committed yet
                        tar.add(root / name, "OpenHands-Nexus/" + name, recursive=False)
                tar.addfile(tarfile.TarInfo("OpenHands-Nexus/VERSION"))
            self.assertEqual(archive.scan(path), [])


class OwnArchiveTests(unittest.TestCase):
    """./pack own: this PC's Nexus ready to start; garbage, foreign files and keys are caught by path."""
    PROJECT = "Agents/OpenHands-Nexus"

    def scan(self, extra=(), drop=()):
        project = [n for n in archive.REQUIRED if n != "VERSION"] + list(archive.OWN_REQUIRED)
        files = {f"{self.PROJECT}/{n}": b"ok\n" for n in project}
        files.update({f"{self.PROJECT}/{n}": b"\x7fELF" for n in archive.PROGRAMS})
        files.update({f"{self.PROJECT}/voice/models/m{n}.pt": b"\x80" for n in range(3)})
        files.update({f"{archive.ENGINE}/{n}": b"\x7fELF" for n in archive.ENGINE_BUILD[:4]})
        files.update({f"{archive.ENGINE}/{n}": b"ok\n" for n in (archive.ENGINE_BUILD[4], ".git/HEAD", ".git/shallow")})
        files.update({f"{self.PROJECT}/{n}": "/abs/" + n for n in archive.PC_LINKS})
        files.update(extra)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "own.tar"
            with tarfile.open(path, "w") as tar:
                for folder in ("Agents", "backend"):
                    info = tarfile.TarInfo(folder)
                    info.type = tarfile.DIRTYPE
                    tar.addfile(info)
                for name, body in files.items():
                    if any(name.endswith("/" + d) for d in drop):
                        continue
                    info = tarfile.TarInfo(name)
                    if isinstance(body, str):
                        info.type, info.linkname = tarfile.SYMTYPE, body
                        tar.addfile(info)
                        continue
                    executable = name.endswith(("/install", "/pack", "/check", "/install.sh", "/caddy",
                                                "/llama-swap", "/llama-server"))
                    info.size = len(body)
                    info.mode = 0o600 if name.endswith(".key") else 0o755 if executable else 0o644
                    tar.addfile(info, io.BytesIO(body))
            return archive.scan_own(path, self.PROJECT, keys=[KEY.encode()])

    def test_ready_archive_passes(self):
        self.assertEqual(self.scan({f"{self.PROJECT}/screen/bin/click": "../.venv/bin/desk",
                                    f"{archive.ENGINE}/src/llama.cpp": b"int x;\n"}), [])

    def test_garbage_and_foreign_files_are_caught(self):
        names = [f"{self.PROJECT}/{n}" for n in ("voice/__pycache__/s.pyc", "agent/state/base_state.json",
                                                   "models/llama-swap.prev", "ui/dist/index.html", ".git/logs/HEAD",
                                                   "ui/dev/evidence/a.png", ".ruff_cache/x", "ui/.env", "a.bak")]
        names += [f"{archive.ENGINE}/build.prev/bin/x", f"{archive.ENGINE}/build/ggml/src/x.o", "Documents/x.txt"]
        problems = self.scan({n: b"x" for n in names})
        self.assertEqual(len(problems), len(names), problems)

    def test_keys_programs_and_links_are_caught(self):
        token = "hf_" + "A1b2" * 9
        problems = self.scan({f"{self.PROJECT}/notes.md": f"{token}\n".encode(),
                              f"{archive.ENGINE}/cfg.txt": f"key={KEY}\n".encode(),
                              f"{self.PROJECT}/tool": b"\x7fELF..",
                              f"{self.PROJECT}/agent/link": "/etc/passwd",
                              f"{self.PROJECT}/voice/models/notes.txt": b"x"})
        self.assertEqual(len(problems), 5, problems)
        self.assertFalse(any(token in p or KEY in p for p in problems))

    def test_missing_parts_and_open_key_are_caught(self):
        problems = self.scan(drop=("libggml.so", "openhands-ca.crt", "llama-server"))
        self.assertEqual(len(problems), 4, problems)  # the server binary and the link to it
        problems = self.scan({f"{self.PROJECT}/voice/models/m2.pt": "x"})
        self.assertIn("voice/models: нет моделей голоса", problems)

    def test_open_ca_key_is_caught(self):
        with patch.object(archive, "CA_KEY", "gateway/ca/openhands-ca.crt"):
            self.assertIn("gateway/ca/openhands-ca.crt: ключ сертификата открыт другим пользователям", self.scan())


class PersonalCopyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.saved = archive.CONFIG, archive.ROOT, archive.HOME
        archive.CONFIG, archive.ROOT, archive.HOME = base / "config", base / "repo", base / "home"

    def tearDown(self):
        archive.CONFIG, archive.ROOT, archive.HOME = self.saved
        self.temp.cleanup()

    def quiet(self, *args):
        with redirect_stdout(io.StringIO()) as out:
            return archive.main(list(args)), out.getvalue()

    def fill(self):
        archive.CONFIG.mkdir(parents=True)
        (archive.CONFIG / "session.env").write_text(f"OHN_SESSION_KEY={KEY}\n")
        os.chmod(archive.CONFIG / "session.env", 0o600)
        for folder, name in [("repo/gateway/ca", "root.crt"), ("repo/agent/state", "settings.json"),
                             ("home/Nexus", "notes.md"), ("home/Nexus", "a.md"), ("repo/agent/state/w/.venv/bin", "python")]:
            (Path(self.temp.name) / folder).mkdir(parents=True, exist_ok=True)
            (Path(self.temp.name) / folder / name).write_text(name)

    def backup(self):
        code, out = self.quiet("backup", str(Path(self.temp.name) / "copies"))
        self.assertEqual(code, 0)
        self.assertNotIn(KEY, out)
        (copy,) = (Path(self.temp.name) / "copies").glob("nexus-personal-*.tar.gz")
        self.assertEqual(copy.stat().st_mode & 0o777, 0o600)
        return copy

    def test_copy_goes_back_where_it_was_without_rebuilt_folders(self):
        self.fill()
        copy = self.backup()
        for path, _ in archive.personal_items():
            os.system(f"rm -rf '{path}'")
        self.assertEqual(self.quiet("restore", str(copy))[0], 0)
        self.assertEqual((archive.CONFIG / "session.env").stat().st_mode & 0o777, 0o600)
        self.assertEqual((archive.HOME / "Nexus/notes.md").read_text(), "notes.md")
        self.assertTrue((archive.ROOT / "gateway/ca/root.crt").is_file())
        self.assertTrue((archive.ROOT / "agent/state/settings.json").is_file())
        self.assertFalse((archive.ROOT / "agent/state/w/.venv").exists())

    def test_existing_files_are_never_overwritten(self):
        self.fill()
        copy = self.backup()
        (archive.HOME / "Nexus/notes.md").write_text("newer")
        code, out = self.quiet("restore", str(copy))
        self.assertEqual(code, 0)
        self.assertEqual((archive.HOME / "Nexus/notes.md").read_text(), "newer")
        self.assertIn("не тронуто: workspace", out)

    def test_interrupted_restore_is_finished_by_the_next_one(self):
        self.fill()
        copy = self.backup()
        for path, _ in archive.personal_items():
            os.system(f"rm -rf '{path}'")
        real = tarfile.data_filter

        def interrupted(member, destination):
            if member.name.endswith("notes.md"):  # after a.md: the folder already has a file
                raise KeyboardInterrupt
            return real(member, destination)
        with patch.object(archive.tarfile, "data_filter", interrupted), self.assertRaises(KeyboardInterrupt):
            self.quiet("restore", str(copy))
        self.assertFalse((archive.CONFIG / "session.env").exists())  # ./install will offer the copy again
        self.assertEqual(self.quiet("restore", str(copy))[0], 0)
        self.assertEqual(sorted(os.listdir(archive.HOME / "Nexus")), ["a.md", "notes.md"])
        self.assertTrue((archive.CONFIG / "session.env").is_file())
        self.assertEqual([p for p in Path(self.temp.name).rglob(".*.restore")], [])

    def test_copies_in_a_row_are_both_kept_and_a_failed_one_leaves_nothing(self):
        self.fill()
        folder = Path(self.temp.name) / "copies"
        self.quiet("backup", str(folder))
        self.quiet("backup", str(folder))
        self.assertEqual(len(list(folder.glob("nexus-personal-*.tar.gz"))), 2)
        kept = sorted(os.listdir(folder))

        def broken(info):
            raise OSError("диск отключён")
        with patch.object(archive, "lean", broken), self.assertRaises(OSError):
            self.quiet("backup", str(folder))
        self.assertEqual(sorted(os.listdir(folder)), kept)
        for name in kept:
            with tarfile.open(folder / name) as tar:
                self.assertIn("workspace/notes.md", tar.getnames())

    def test_foreign_or_escaping_members_are_refused(self):
        path = Path(self.temp.name) / "bad.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            tar.addfile(tarfile.TarInfo("../outside"), io.BytesIO(b""))
        self.assertEqual(self.quiet("restore", str(path))[0], 1)
        with tarfile.open(path, "w:gz") as tar:
            info = tarfile.TarInfo("workspace/link")
            info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            tar.addfile(info)
        code, out = self.quiet("restore", str(path))
        self.assertEqual(code, 0)
        self.assertFalse(os.path.lexists(archive.HOME / "Nexus/link"))
        self.assertIn("пропущено ссылок наружу: 1", out)


class SecondDiskTests(unittest.TestCase):
    """./pack mirror: the second disk gets the archives; only Nexus archives beyond the kept ones go."""
    MIRROR = 'source <(sed -n "/^prune()/,/^}/p;/^mirror()/,/^}/p" "$1"); mirror'

    def test_archives_are_copied_and_rotated_other_files_stay(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            out, copy, home, here = base / "out", base / "disk", base / "home", base / "here"
            for folder in (out / "личное", copy / "личное", home / ".config/openhands-nexus", here):
                folder.mkdir(parents=True)
            (home / ".config/openhands-nexus/archive-copy").write_text(str(copy))
            (here / "stays.txt").write_text("cwd")
            files = {copy: ["документ.odt", "личное/заметка.txt", "OpenHands-Nexus-linux-0.tar.gz",
                            "ik_llama-0.bundle", "ik_llama-1.bundle"]
                           + [f"личное/nexus-personal-{n}.tar.gz" for n in range(3)],
                     out: [f"OpenHands-Nexus-linux-{n}.tar.gz" for n in range(1, 6)]
                          + ["ik_llama-2.bundle", "личное/nexus-personal-3.tar.gz"]}
            moment = 1_700_000_000
            for folder, names in files.items():
                for name in names:  # later in the list = newer, copies older than the archives
                    moment += 60
                    for path in (folder / name, folder / f"{name}.sha256"):
                        path.write_text(name)
                        os.utime(path, (moment, moment))

            def mirror():
                result = subprocess.run(["bash", "-c", "set -euo pipefail; " + self.MIRROR, "bash", HERE.parent / "pack"],
                                        cwd=here, env={**os.environ, "HOME": str(home), "OUT": str(out)},
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return sorted(str(p.relative_to(copy)) for p in copy.rglob("*") if p.is_file()
                              and not p.name.endswith(".sha256"))

            self.assertEqual(mirror(), sorted(
                ["документ.odt", "личное/заметка.txt", "ik_llama-1.bundle", "ik_llama-2.bundle"]
                + [f"OpenHands-Nexus-linux-{n}.tar.gz" for n in range(1, 6)]
                + [f"личное/nexus-personal-{n}.tar.gz" for n in range(1, 4)]))
            self.assertFalse((copy / "OpenHands-Nexus-linux-0.tar.gz.sha256").exists())
            for path in (out / "личное").iterdir():
                path.unlink()
            for path in (copy / "личное").glob("nexus-personal-*"):
                path.unlink()
            self.assertIn("личное/заметка.txt", mirror())  # no personal copy at all is not an error
            self.assertTrue((here / "stays.txt").exists())


if __name__ == "__main__":
    unittest.main()
