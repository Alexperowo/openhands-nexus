"""Model downloads are checked against the expected SHA-256 before they land in models/."""
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import download_models
from download_models import ChecksumError, fetch

GOOD = b"model weights"


class Response(io.BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class DownloadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.models = Path(temp.name)
        expected = {"tts.pt": ("https://models.example", hashlib.sha256(GOOD).hexdigest())}
        for target, value in (("MODELS_DIR", self.models), ("EXPECTED", expected)):
            patcher = patch.object(download_models, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def serve(self, body):
        return patch.object(download_models.urllib.request, "urlopen", lambda request: Response(body))

    def test_matching_download_is_saved(self):
        with self.serve(GOOD):
            self.assertEqual(fetch("tts.pt").read_bytes(), GOOD)
        self.assertEqual(sorted(p.name for p in self.models.iterdir()), ["tts.pt"])

    def test_tampered_download_is_refused_and_leaves_nothing(self):
        with self.serve(b"model weights + code"), self.assertRaises(ChecksumError):
            fetch("tts.pt")
        self.assertEqual(list(self.models.iterdir()), [])

    def test_file_already_in_place_is_checked_too(self):
        (self.models / "tts.pt").write_bytes(b"swapped")
        with self.serve(GOOD), self.assertRaises(ChecksumError):
            fetch("tts.pt")
        (self.models / "tts.pt").write_bytes(GOOD)
        with self.serve(b"never fetched"):
            self.assertEqual(fetch("tts.pt").read_bytes(), GOOD)

    def test_model_without_an_expected_hash_is_refused(self):
        with self.serve(GOOD), self.assertRaises(ChecksumError):
            fetch("other.pt")


class InstalledModelsTests(unittest.TestCase):
    def test_installed_models_match_the_expected_hashes(self):
        from service import STT_MODEL
        names = {"v5_6_ru.pt", f"{STT_MODEL}.ckpt", f"{STT_MODEL}_tokenizer.model"}
        self.assertLessEqual(names, set(download_models.EXPECTED))
        for name in names:
            path = download_models.MODELS_DIR / name
            if not path.exists():
                self.skipTest(f"{path} is not downloaded")
            self.assertEqual(download_models.sha256(path), download_models.EXPECTED[name][1], name)


if __name__ == "__main__":
    unittest.main()
