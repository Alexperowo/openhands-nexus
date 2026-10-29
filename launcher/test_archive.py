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
                             ("home/Nexus", "notes.md"), ("repo/agent/state/w/.venv/bin", "python")]:
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


if __name__ == "__main__":
    unittest.main()
