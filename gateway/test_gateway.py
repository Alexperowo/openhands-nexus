"""The real Caddyfile's page site on a loopback port, serving a stand-in UI build: cache headers."""
import os
import pathlib
import re
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
CADDY = HERE / "caddy"


def page_site(port):
    """The 8443 site of the real Caddyfile, on plain HTTP at the given loopback port."""
    text = (HERE / "Caddyfile").read_text()
    site = text[text.index("https://{$LAN_IP}:8443"):]
    body = site[site.index(" {\n") + 2:]
    body = re.sub(r"\n\tbind [^\n]*\n\ttls internal\n", "\n", body, count=1)
    return "{\n\tadmin off\n\tauto_https off\n}\n" + f"http://127.0.0.1:{port} {{" + body


@unittest.skipUnless(CADDY.exists(), "gateway/caddy is not installed")
class CacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.temp.name)
        (root / "dist/assets").mkdir(parents=True)
        (root / "dist/index.html").write_text('<script src="/assets/index-AbC123.js"></script>')
        (root / "dist/assets/index-AbC123.js").write_text("console.log(1);")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        (root / "Caddyfile").write_text(page_site(port))
        env = {**os.environ, "SHELL_DIST": str(root / "dist"), "OHN_SESSION_KEY": "test",
               "XDG_DATA_HOME": str(root / "data"), "XDG_CONFIG_HOME": str(root / "config")}
        cls.caddy = subprocess.Popen([CADDY, "run", "--config", root / "Caddyfile", "--adapter", "caddyfile"],
                                     env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.origin = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.origin, timeout=1)
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.caddy.terminate()
        cls.caddy.wait(10)
        cls.temp.cleanup()

    def get(self, path):
        try:
            response = urllib.request.urlopen(self.origin + path, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        return response.status, response.headers.get("Cache-Control"), response.headers.get("Content-Type")

    def test_page_is_checked_every_time_so_a_rebuild_is_seen_at_once(self):
        for path in ("/", "/conversations/abc", "/settings"):
            status, cache, kind = self.get(path)
            self.assertEqual((status, cache), (200, "no-cache"), path)
            self.assertIn("text/html", kind)

    def test_hashed_files_are_kept_for_good(self):
        self.assertEqual(self.get("/assets/index-AbC123.js")[:2], (200, "public, max-age=31536000, immutable"))

    def test_missing_file_is_a_plain_404_not_the_page_and_not_cached(self):
        # An old page asking for a removed file, or a file not yet written during a rebuild.
        for path in ("/assets/index-Old999.js", "/assets/"):
            self.assertEqual(self.get(path)[:2], (404, None), path)


if __name__ == "__main__":
    unittest.main()
