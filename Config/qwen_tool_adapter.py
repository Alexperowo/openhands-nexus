r"""
Universal Tool Call & Reasoning Recovery Adapter for llama-server
Location: K:\Project\Config\qwen_tool_adapter.py

Purpose:
- Acts as a transparent, high-performance reverse proxy for llama-server.
- Zero translation overhead (maintains native Russian / multilingual speed).
- Intercepts raw XML (<tool_call><function=...>) and JSON tool calls emitted by models.
- Normalizes them into standard OpenAI tool_calls objects with finish_reason: "tool_calls".
- Strips leakage of </think> and tool markup from user-visible content.
- Binds child llama-server to a Windows Job Object with KILL_ON_JOB_CLOSE to guarantee zero orphaned processes.
"""

import atexit
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Windows Job Object support for clean child process management
try:
    import win32api
    import win32job
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

child_proc = None
upstream_port = None
job_handle = None


def setup_job_object():
    """Binds current process to a Windows Job Object with KILL_ON_JOB_CLOSE."""
    global job_handle
    if not HAS_WIN32:
        return
    try:
        hJob = win32job.CreateJobObject(None, "")
        info = win32job.QueryInformationJobObject(hJob, win32job.JobObjectExtendedLimitInformation)
        info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(hJob, win32job.JobObjectExtendedLimitInformation, info)
        win32job.AssignProcessToJobObject(hJob, win32process.GetCurrentProcess())
        job_handle = hJob
        print("[ToolAdapter] Successfully bound to Windows Job Object (KILL_ON_JOB_CLOSE).", flush=True)
    except Exception as e:
        print(f"[ToolAdapter] Warning: Failed to set up Windows Job Object: {e}", flush=True)


def parse_val(val_str: str):
    v = val_str.strip()
    if v.isdigit():
        return int(v)
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    try:
        if "." in v:
            return float(v)
    except ValueError:
        pass
    return v


def extract_tool_calls_from_content(content: str):
    """Parses raw XML or JSON tool calls generated inside content and returns OpenAI-format tool_calls."""
    if not content or not isinstance(content, str):
        return []

    tool_calls = []

    # Pattern 1: XML syntax <tool_call><function=NAME><parameter=KEY>VAL</parameter>...</function></tool_call>
    tc_matches = list(re.finditer(r'<tool_call>\s*<function\s*=\s*([\w\-]+)>(.*?)</function>\s*(?:</tool_call>)?', content, re.DOTALL))
    for m in tc_matches:
        fn_name = m.group(1).strip()
        params_body = m.group(2)
        params = {}
        for p in re.finditer(r'<parameter\s*=\s*([\w\-]+)>(.*?)</parameter>', params_body, re.DOTALL):
            params[p.group(1).strip()] = parse_val(p.group(2))
        tool_calls.append({
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "type": "function",
            "function": {
                "name": fn_name,
                "arguments": json.dumps(params, ensure_ascii=False)
            }
        })

    # Pattern 2: JSON syntax <tool_call>{"name": "...", "arguments": {...}}</tool_call>
    json_matches = re.finditer(r'<tool_call>\s*(\{.*?\})\s*</tool_call>', content, re.DOTALL)
    for jm in json_matches:
        try:
            parsed = json.loads(jm.group(1))
            name = parsed.get("name") or parsed.get("function")
            args = parsed.get("arguments", parsed.get("parameters", {}))
            if name:
                args_str = json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args)
                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": args_str
                    }
                })
        except Exception:
            pass

    return tool_calls


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def cleanup():
    global child_proc
    if child_proc and child_proc.poll() is None:
        print("[ToolAdapter] Terminating child llama-server process...", flush=True)
        try:
            subprocess.run(f"taskkill /F /T /PID {child_proc.pid}", shell=True, capture_output=True)
        except Exception:
            try:
                child_proc.kill()
            except Exception:
                pass


atexit.register(cleanup)


class ToolProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self._proxy_request("GET")

    def do_POST(self):
        self._proxy_request("POST")

    def do_HEAD(self):
        self._proxy_request("HEAD")

    def _proxy_request(self, method: str):
        global upstream_port
        target_url = f"http://127.0.0.1:{upstream_port}{self.path}"

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")}
        if body is not None:
            headers["Content-Length"] = str(len(body))

        req = urllib.request.Request(target_url, data=body, headers=headers, method=method)

        # Handle streaming requests with immediate chunk pass-through
        is_stream = False
        if body:
            try:
                body_json = json.loads(body.decode("utf-8"))
                if body_json.get("stream") is True:
                    is_stream = True
            except Exception:
                pass

        if is_stream:
            try:
                with urllib.request.urlopen(req, timeout=7200) as resp:
                    self.send_response(resp.status)
                    for k, v in resp.headers.items():
                        if k.lower() not in ("content-length", "transfer-encoding", "connection"):
                            self.send_header(k, v)
                    self.send_header("Connection", "close")
                    self.end_headers()
                    while True:
                        chunk = resp.read(1024)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                return
            except urllib.error.HTTPError as e:
                err_data = e.read()
                self.send_response(e.code)
                for k, v in e.headers.items():
                    if k.lower() not in ("content-length", "transfer-encoding", "connection"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(err_data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(err_data)
                return

        try:
            with urllib.request.urlopen(req, timeout=7200) as resp:
                resp_data = resp.read()

                # Process /v1/chat/completions to intercept and recover tool calls
                if "/v1/chat/completions" in self.path and resp.status == 200:
                    try:
                        res_json = json.loads(resp_data.decode("utf-8"))
                        choices = res_json.get("choices", [])
                        if choices and isinstance(choices, list):
                            choice = choices[0]
                            msg = choice.get("message", {})
                            content = msg.get("content")

                            if content and isinstance(content, str):
                                extracted_calls = extract_tool_calls_from_content(content)
                                if extracted_calls:
                                    existing = msg.get("tool_calls") or []
                                    msg["tool_calls"] = existing + extracted_calls
                                    choice["finish_reason"] = "tool_calls"

                                    # Clean up tags from content
                                    cleaned = re.sub(r'<tool_call[\s\S]*?(?:</tool_call>|$)', '', content).strip()
                                    cleaned = re.sub(r'^\s*</think>\s*', '', cleaned).strip()
                                    cleaned = re.sub(r'^\s*<think>[\s\S]*?</think>\s*', '', cleaned).strip()
                                    msg["content"] = cleaned if cleaned else ""
                                    print(f"[ToolAdapter] Successfully recovered {len(extracted_calls)} parallel tool call(s)!", flush=True)

                                # Also clean orphan </think> if present without tool calls
                                elif "</think>" in content:
                                    msg["content"] = re.sub(r'^\s*</think>\s*', '', content).strip()

                        resp_data = json.dumps(res_json, ensure_ascii=False).encode("utf-8")
                    except Exception as e:
                        print(f"[ToolAdapter] Response parse error: {e}", flush=True)

                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ("content-length", "transfer-encoding", "connection"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(resp_data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(resp_data)
        except urllib.error.HTTPError as e:
            err_data = e.read()
            self.send_response(e.code)
            for k, v in e.headers.items():
                if k.lower() not in ("content-length", "transfer-encoding", "connection"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(err_data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(err_data)
        except Exception as e:
            self.send_response(502)
            msg = json.dumps({"error": f"Bad Gateway: {str(e)}"}).encode("utf-8")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(msg)


def main():
    global child_proc, upstream_port

    setup_job_object()

    args = sys.argv[1:]
    listen_port = None
    llama_cmd = []

    i = 0
    while i < len(args):
        if args[i] == "--listen-port":
            listen_port = int(args[i + 1])
            i += 2
        elif args[i] == "--":
            llama_cmd = args[i + 1:]
            break
        else:
            i += 1

    if not listen_port or not llama_cmd:
        print("Usage: python qwen_tool_adapter.py --listen-port <PORT> -- <llama-server args...>")
        sys.exit(1)

    upstream_port = find_free_port()

    # Replace --port in llama_cmd
    final_cmd = []
    skip = False
    for idx, token in enumerate(llama_cmd):
        if skip:
            skip = False
            continue
        if token == "--port":
            final_cmd.extend(["--port", str(upstream_port)])
            skip = True
        elif token.startswith("--port="):
            final_cmd.append(f"--port={upstream_port}")
        else:
            final_cmd.append(token)

    if "--port" not in llama_cmd and not any(t.startswith("--port=") for t in llama_cmd):
        final_cmd.extend(["--port", str(upstream_port)])

    print(f"[ToolAdapter] Spawning upstream llama-server on port {upstream_port}...")
    child_proc = subprocess.Popen(final_cmd)

    # Health check upstream
    print(f"[ToolAdapter] Waiting for upstream llama-server to be ready...")
    ready = False
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{upstream_port}/health", timeout=2) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            pass
        if child_proc.poll() is not None:
            print("[ToolAdapter] Child llama-server terminated unexpectedly!")
            sys.exit(1)
        time.sleep(1)

    if not ready:
        print("[ToolAdapter] Upstream llama-server failed to respond in time.")
        sys.exit(1)

    print(f"[ToolAdapter] Upstream is ready! Starting proxy on port {listen_port}...")
    server = ThreadingHTTPServer(("127.0.0.1", listen_port), ToolProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        cleanup()


if __name__ == "__main__":
    main()
