"""The weights list matches llama-swap.yaml; downloads are checked before they take their name."""
import hashlib
import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("weights", HERE / "weights.py")
weights = importlib.util.module_from_spec(spec)
spec.loader.exec_module(weights)
spec = importlib.util.spec_from_file_location("preflight", HERE.parent / "launcher/preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def fake(folder, body=b"weights"):
    source = Path(folder) / "source.bin"
    source.write_bytes(body)
    return {"files": {"A/a.gguf": {"url": source.as_uri(), "size": len(body),
                                   "sha256": hashlib.sha256(body).hexdigest()}},
            "groups": [{"id": "a", "name": "A", "files": ["A/a.gguf"]}]}


def quiet(*args, **kwargs):
    with redirect_stdout(io.StringIO()):
        return weights.main(*args, **kwargs)


class WeightsTests(unittest.TestCase):
    def test_list_covers_every_weight_of_the_menu(self):
        menu = {str(p.relative_to(HERE / "weights")) for p in preflight.model_files(HERE / "llama-swap.yaml")
                if HERE / "weights" in p.parents}
        data = weights.load()
        self.assertEqual(menu, set(data["files"]))
        self.assertEqual(menu, {f for g in data["groups"] for f in g["files"]})
        for entry in data["files"].values():
            self.assertRegex(entry["url"], r"^https://huggingface\.co/[\w.-]+/[\w.-]+/resolve/[0-9a-f]{40}/")
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")

    def test_download_checked_then_named(self):
        with tempfile.TemporaryDirectory() as temp:
            data, folder = fake(temp), Path(temp) / "store"
            self.assertEqual(quiet(["missing", str(folder)], data), 0)
            self.assertEqual(weights.missing_groups(folder, data), data["groups"])
            self.assertEqual(quiet(["get", str(folder), "a"], data), 0)
            self.assertEqual((folder / "A/a.gguf").read_bytes(), b"weights")
            self.assertEqual(quiet(["status", str(folder)], data), 0)

    def test_wrong_checksum_never_takes_the_name(self):
        with tempfile.TemporaryDirectory() as temp:
            data, folder = fake(temp), Path(temp) / "store"
            data["files"]["A/a.gguf"]["sha256"] = "0" * 64
            self.assertEqual(quiet(["get", str(folder), "a"], data), 1)
            self.assertFalse((folder / "A/a.gguf").exists())
            self.assertFalse((folder / "A/a.gguf.part").exists())
            self.assertEqual(quiet(["status", str(folder)], data), 1)


if __name__ == "__main__":
    unittest.main()
