import http.server
import sys

port = int(sys.argv[1])

class MockHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"choices":[{"message":{"content":"mock_response"}}]}')

    def log_message(self, format, *args):
        pass

server = http.server.HTTPServer(("127.0.0.1", port), MockHandler)
server.serve_forever()
