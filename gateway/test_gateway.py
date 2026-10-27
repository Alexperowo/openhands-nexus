"""The real Caddyfile's page site on a loopback port, with a stand-in UI build and stand-in
services: cache headers and where each request goes (routes.json, shared with the UI dev proxy)."""
import http.server
import json
import os
import pathlib
import re
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
CADDY = HERE / "caddy"
ROUTES = json.loads((HERE / "routes.json").read_text())


def page_site(port, upstreams):
    """The 8443 site of the real Caddyfile, on plain HTTP at the given loopback port;
    upstreams maps each service port to the port of its stand-in."""
    text = (HERE / "Caddyfile").read_text()
    site = text[text.index("https://{$LAN_IP}:8443"):]
    body = site[site.index(" {\n") + 2:]
    body = re.sub(r"\n\tbind [^\n]*\n\ttls internal\n", "\n", body, count=1)
    body = re.sub(r"127\.0\.0\.1:(\d+)", lambda m: f"127.0.0.1:{upstreams[int(m[1])]}", body)
    return "{\n\tadmin off\n\tauto_https off\n}\n" + f"http://127.0.0.1:{port} {{" + body


def stand_in(name):
    """A service that answers with its name, the path it got and the session key it was given."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"upstream": name, "path": self.path,
                               "key": self.headers.get("X-Session-API-Key")}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        do_POST = do_GET

        def log_message(self, *_):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@unittest.skipUnless(CADDY.exists(), "gateway/caddy is not installed")
class GatewayTests(unittest.TestCase):
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
        cls.services = {name: stand_in(name) for name in ROUTES["ports"]}
        upstreams = {ROUTES["ports"][name]: server.server_port for name, server in cls.services.items()}
        (root / "Caddyfile").write_text(page_site(port, upstreams))
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
        for server in cls.services.values():
            server.shutdown()
            server.server_close()
        cls.temp.cleanup()

    def open(self, path, method="GET"):
        request = urllib.request.Request(self.origin + path, method=method)
        try:
            return urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            return error

    def get(self, path):
        response = self.open(path)
        return response.status, response.headers.get("Cache-Control"), response.headers.get("Content-Type")

    def test_requests_reach_the_service_in_the_routes_table(self):
        for route in ROUTES["routes"]:
            with self.subTest(route["path"]):
                response = self.open(route["path"])
                if route["upstream"] is None:
                    # Not proxied: /slots and the like of llama-server hold prompt text.
                    self.assertIn("text/html", response.headers.get("Content-Type"))
                    continue
                got = json.loads(response.read())
                self.assertEqual(got, {"upstream": route["upstream"], "path": route.get("to", route["path"]),
                                       "key": "test" if route["key"] else None})

    def test_only_reads_reach_the_agent_root(self):
        # Falls through to the page's file server, which only reads.
        self.assertEqual(self.open("/server_info", "POST").status, 405)

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
