import subprocess
import time
import urllib.request
import json
import os
import socket

SWAP_DIR = r"K:\Project\llama-swap"
SESSION_FILE = os.path.join(SWAP_DIR, "session.json")

# Start a lightweight HTTP listener pretending to be an external / foreign process
import http.server
import socketserver
import threading

class ForeignHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, format, *args):
        pass

server = socketserver.TCPServer(("127.0.0.1", 8089), ForeignHandler)
th = threading.Thread(target=server.serve_forever, daemon=True)
th.start()
print("Foreign service listening on 127.0.0.1:8089")

# Test 1: start-swap on port 8089 -> should detect already running, mark owned = false
res_start = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(SWAP_DIR, "start-swap.ps1"), "8089"], capture_output=True, text=True)
print("start-swap output:")
print(res_start.stdout)

assert "owned = false" in res_start.stdout, "start-swap did not mark owned = false for foreign service!"
with open(SESSION_FILE, "r", encoding="utf-8-sig") as f:
    sess = json.load(f)
assert sess.get("owned") is False, "session.json owned is not False!"
print("Verified session.json owned == False.")

# Test 2: stop-swap on port 8089 -> should SKIP stopping foreign service
res_stop = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(SWAP_DIR, "stop-swap.ps1")], capture_output=True, text=True)
print("stop-swap output:")
print(res_stop.stdout)

assert "Keeping it running" in res_stop.stdout, "stop-swap did not skip stopping foreign service!"

# Test 3: verify foreign service is still alive
with urllib.request.urlopen("http://127.0.0.1:8089/health", timeout=2) as r:
    assert r.read().decode() == "OK", "Foreign service was killed!"

print("\nFOREIGN SERVICE SURVIVED! TEST PASSED!")
server.shutdown()
server.server_close()
