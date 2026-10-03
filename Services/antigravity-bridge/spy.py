import http.server
import socketserver
import urllib.request
import urllib.error
import json
import os
import sys

TARGET_HOST = "https://daily-cloudcode-pa.googleapis.com"
PORT = 18005
LOG_FILE = os.path.join(os.path.dirname(__file__), "traffic.jsonl")

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self._proxy_request("POST")

    def do_GET(self):
        self._proxy_request("GET")

    def _proxy_request(self, method):
        content_length = int(self.headers.get("Content-Length", 0))
        req_body = self.rfile.read(content_length) if content_length > 0 else b""
        
        target_url = TARGET_HOST + self.path
        headers = {}
        for k, v in self.headers.items():
            if k.lower() not in ["host", "content-length"]:
                headers[k] = v

        req = urllib.request.Request(target_url, data=req_body if method == "POST" else None, headers=headers, method=method)
        
        entry = {
            "method": method,
            "path": self.path,
            "req_headers": dict(self.headers),
            "req_body": req_body.decode("utf-8", errors="ignore")[:2000]
        }

        try:
            with urllib.request.urlopen(req) as resp:
                resp_status = resp.status
                resp_headers = dict(resp.headers)
                resp_body = resp.read()

                entry["resp_status"] = resp_status
                entry["resp_body"] = resp_body.decode("utf-8", errors="ignore")[:2000]
                
                self.send_response(resp_status)
                for hk, hv in resp_headers.items():
                    if hk.lower() not in ["transfer-encoding", "content-length"]:
                        self.send_header(hk, hv)
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            resp_body = e.read()
            entry["resp_status"] = e.code
            entry["resp_body"] = resp_body.decode("utf-8", errors="ignore")[:2000]
            
            self.send_response(e.code)
            for hk, hv in e.headers.items():
                if hk.lower() not in ["transfer-encoding", "content-length"]:
                    self.send_header(hk, hv)
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
        except Exception as e:
            entry["error"] = str(e)
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f'{{"error": "{str(e)}"}}'.encode("utf-8"))

        with open(LOG_FILE, "a", encoding="utf-8") as lf:
            lf.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"[{method}] {self.path} -> {entry.get('resp_status')}")

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), ProxyHandler) as httpd:
        print(f"Proxy spy running on http://127.0.0.1:{PORT}")
        sys.stdout.flush()
        httpd.serve_forever()
