import http.server
import socketserver
import urllib.request
import urllib.error
import json
import gzip
import os
import sys
import logging
from typing import Any, Dict, Optional

from upstream_detector import get_upstream_proxy, invalidate_proxy
from auth_vault import save_auth_cache, get_auth_fallback
from model_catalog import inject_local_model, get_models_fallback, LOCAL_MODEL_ID, resolve_station_model, STATION_MODELS
from converter import (
    gemini_to_openai_messages,
    format_gemini_sse_thought_chunk,
    format_gemini_sse_text_chunk,
    format_gemini_sse_function_call,
    format_gemini_sse_finish,
    repair_json_string,
    validate_and_fill_tool_args,
    is_tool_call_operable,
    extract_generation_params,
    emergency_compact_messages
)

TARGET_HOST = "https://daily-cloudcode-pa.googleapis.com"
LLAMA_SWAP_URL = "http://127.0.0.1:8080/v1/chat/completions"
DEFAULT_LOCAL_MODEL = "qwen"
PORT = 18005

CLIENT_DISCONNECT_EXCEPTIONS = (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)

AUXILIARY_ENDPOINTS = {
    "/v1internal:recordTrajectoryAnalytics",
    "/v1internal:listExperiments",
    "/v1internal:fetchAdminControls",
    "/v1internal:writeTrajectoryAcls"
}

LOG_FILE = os.path.join(os.path.dirname(__file__), "bridge.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("antigravity-bridge")

def _make_upstream_opener() -> urllib.request.OpenerDirector:
    """Builds a urllib opener using the live agy-unlock proxy if available."""
    proxy_url = get_upstream_proxy()
    if proxy_url:
        proxy_handler = urllib.request.ProxyHandler({
            "http": proxy_url,
            "https": proxy_url
        })
        return urllib.request.build_opener(proxy_handler)
    return urllib.request.build_opener()

STRIP_REQUEST_HEADERS = {
    "host",
    "content-length",
    "transfer-encoding",
    "content-encoding",
    "accept-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "upgrade"
}

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class AntigravityBridgeHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.debug("%s - - %s", self.address_string(), format % args)

    def _read_body(self) -> bytes:
        """
        Reads HTTP request body supporting both Content-Length and Transfer-Encoding: chunked.
        Automatically decompresses gzip / deflate bodies if compressed.
        """
        te = self.headers.get("Transfer-Encoding", "").lower()
        if "chunked" in te:
            chunks = []
            while True:
                line = self.rfile.readline()
                if not line:
                    break
                chunk_header = line.split(b";")[0].strip()
                if not chunk_header:
                    continue
                try:
                    chunk_len = int(chunk_header, 16)
                except ValueError:
                    logger.error("Invalid chunk header: %r", chunk_header)
                    break
                if chunk_len == 0:
                    # Consume trailer headers until empty line
                    while True:
                        trailer = self.rfile.readline()
                        if not trailer or trailer.strip() == b"":
                            break
                    break
                chunk_data = self.rfile.read(chunk_len)
                chunks.append(chunk_data)
                # Consume trailing CRLF
                self.rfile.readline()
            raw_body = b"".join(chunks)
        else:
            try:
                cl = int(self.headers.get("Content-Length", 0))
            except (ValueError, TypeError):
                cl = 0
            raw_body = self.rfile.read(cl) if cl > 0 else b""

        ce = self.headers.get("Content-Encoding", "").lower()
        if ce == "gzip":
            try:
                return gzip.decompress(raw_body)
            except Exception as e:
                logger.warning("Failed to decompress gzip request body: %s", e)
                return raw_body
        elif ce in ("deflate", "zlib"):
            import zlib
            try:
                return zlib.decompress(raw_body)
            except Exception as e:
                logger.warning("Failed to decompress deflate request body: %s", e)
                return raw_body

        return raw_body

    def do_POST(self):
        try:
            req_body = self._read_body()
            path = self.path
            logger.info("[POST] %s (body_len=%d, TE=%s, CE=%s)",
                        path, len(req_body),
                        self.headers.get("Transfer-Encoding", "none"),
                        self.headers.get("Content-Encoding", "none"))

            if "/v1internal:loadCodeAssist" in path or "/v1internal:fetchUserInfo" in path:
                self._handle_auth_endpoints(req_body)
            elif "/v1internal:fetchAvailableModels" in path:
                self._handle_fetch_models(req_body)
            elif "/v1internal:streamGenerateContent" in path:
                self._handle_stream_generate(req_body)
            else:
                self._proxy_generic("POST", req_body)
        except CLIENT_DISCONNECT_EXCEPTIONS:
            logger.debug("Client closed connection on %s", self.path)
            return
        except Exception as e:
            logger.exception("Unhandled error in do_POST on %s: %s", self.path, e)
            try:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))
            except Exception:
                pass

    def do_GET(self):
        clean_path = self.path.split("?")[0].rstrip("/")
        if clean_path in ("/health", "/status"):
            resp = {
                "status": "ok",
                "service": "antigravity-bridge",
                "port": PORT,
                "default_model": DEFAULT_LOCAL_MODEL
            }
            body = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._proxy_generic("GET", b"")

    def _handle_auth_endpoints(self, req_body: bytes):
        """
        Handles /v1internal:loadCodeAssist and /v1internal:fetchUserInfo.
        Tries upstream with live proxy. If successful, updates cache.
        If upstream fails (error, timeout, offline), serves auth vault fallback (200 OK).
        NEVER returns 502 to protect Antigravity from session wipes.
        """
        target_url = TARGET_HOST + self.path
        headers = {k: v for k, v in self.headers.items() if k.lower() not in STRIP_REQUEST_HEADERS}
        if "content-type" not in [k.lower() for k in headers]:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(target_url, data=req_body, headers=headers, method="POST")
        opener = _make_upstream_opener()

        try:
            with opener.open(req, timeout=10) as resp:
                resp_body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    decomp = gzip.decompress(resp_body)
                    parsed = json.loads(decomp.decode("utf-8"))
                else:
                    parsed = json.loads(resp_body.decode("utf-8"))

                # Persist fresh auth cache
                save_auth_cache(self.path, parsed)

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                out_bytes = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
                self.send_header("Content-Length", str(len(out_bytes)))
                self.end_headers()
                self.wfile.write(out_bytes)
                logger.info("[AUTH] Successfully proxied and refreshed cache for %s", self.path)
                return
        except Exception as e:
            logger.warning("[AUTH] Upstream %s failed (%s). Triggering zero-logout fallback.", self.path, e)
            invalidate_proxy()

        # Offline / failure fallback: always return 200 OK with valid profile
        fallback_data = get_auth_fallback(self.path)
        out_bytes = json.dumps(fallback_data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(out_bytes)))
        self.end_headers()
        self.wfile.write(out_bytes)
        logger.info("[AUTH] Served guaranteed 200 OK fallback for %s", self.path)

    def _handle_fetch_models(self, req_body: bytes):
        """
        Handles /v1internal:fetchAvailableModels.
        Queries upstream, injects station-local into models and sorts, and returns.
        Falls back to model_catalog fallback if offline.
        """
        target_url = TARGET_HOST + self.path
        headers = {k: v for k, v in self.headers.items() if k.lower() not in STRIP_REQUEST_HEADERS}
        if "content-type" not in [k.lower() for k in headers]:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(target_url, data=req_body, headers=headers, method="POST")
        opener = _make_upstream_opener()

        try:
            with opener.open(req, timeout=30) as resp:
                resp_body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    resp_body = gzip.decompress(resp_body)
                data = json.loads(resp_body.decode("utf-8"))

                merged_data = inject_local_model(data)
                out_bytes = json.dumps(merged_data, ensure_ascii=False).encode("utf-8")

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(out_bytes)))
                self.end_headers()
                self.wfile.write(out_bytes)
                logger.info("[MODELS] Successfully injected '%s' into live cloud models.", LOCAL_MODEL_ID)
                return
        except Exception as e:
            logger.warning("[MODELS] Upstream fetchAvailableModels failed (%s). Serving catalog fallback.", e)
            invalidate_proxy()

        fallback_data = get_models_fallback()
        out_bytes = json.dumps(fallback_data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(out_bytes)))
        self.end_headers()
        self.wfile.write(out_bytes)
        logger.info("[MODELS] Served offline fallback models catalog.")

    def _handle_stream_generate(self, req_body: bytes):
        """
        Handles /v1internal:streamGenerateContent.
        Routes station-local to llama-swap (:8080) with full reasoning/thinking and tools support.
        Routes all other models upstream to Google Cloud as streaming SSE.
        """
        try:
            req_json = json.loads(req_body.decode("utf-8"))
        except Exception as e:
            logger.warning("Failed to parse streamGenerateContent JSON (len=%d): %s. Streaming directly to upstream.", len(req_body), e)
            self._proxy_stream_upstream(req_body)
            return

        model_name = req_json.get("model") or (req_json.get("request") or {}).get("model") or ""
        target_swap_model = resolve_station_model(model_name)
        if not target_swap_model:
            logger.info("[INFERENCE] Cloud model requested ('%s'). Proxying stream to Google Cloud.", model_name)
            self._proxy_stream_upstream(req_body)
            return

        logger.info("[INFERENCE] Intercepted streamGenerateContent for '%s' -> routing to llama-swap ('%s')", model_name, target_swap_model)
        gemini_req = req_json.get("request") or req_json
        messages, tools, tool_schemas = gemini_to_openai_messages(gemini_req)
        
        gen_params = extract_generation_params(gemini_req)
        openai_payload = {
            "model": target_swap_model,
            "messages": messages,
            "stream": True,
            "temperature": gen_params.get("temperature", 0.2)
        }
        if "max_tokens" in gen_params:
            openai_payload["max_tokens"] = min(gen_params["max_tokens"], 8192)
        if "top_p" in gen_params:
            openai_payload["top_p"] = gen_params["top_p"]
        if tools:
            openai_payload["tools"] = tools

        logger.info("[INFERENCE] Sending %d messages (%d tools) to llama-swap (%s)", len(messages), len(tools), DEFAULT_LOCAL_MODEL)
        try:
            with open(os.path.join(os.path.dirname(__file__), "last_payload.json"), "w", encoding="utf-8") as f:
                json.dump(openai_payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def _request_llama_swap(payload: Dict[str, Any]):
            openai_req = urllib.request.Request(
                LLAMA_SWAP_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            return urllib.request.urlopen(openai_req, timeout=7200)

        try:
            resp = None
            try:
                resp = _request_llama_swap(openai_payload)
            except urllib.error.HTTPError as e:
                err_data = e.read().decode("utf-8", errors="ignore")
                if e.code == 400 and ("exceed" in err_data.lower() or "context" in err_data.lower()):
                    logger.warning("[INFERENCE] Context limit exceeded on llama-swap (%s). Performing emergency compaction and retrying...", err_data)
                    openai_payload["messages"] = emergency_compact_messages(messages, keep_recent=10)
                    logger.info("[INFERENCE] Emergency retry with %d messages", len(openai_payload["messages"]))
                    resp = _request_llama_swap(openai_payload)
                else:
                    raise

            with resp:
                streamed_tools: Dict[int, Dict[str, str]] = {}
                has_text = False
                has_thought = False
                
                for line in resp:
                    line_str = line.decode("utf-8").strip()
                    if not line_str.startswith("data:"):
                        continue
                    payload_str = line_str[5:].strip()
                    if payload_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload_str)
                    except Exception:
                        continue

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    
                    # 1. Native Reasoning / Thinking chunk -> collapsible UI Thinking block!
                    if "reasoning_content" in delta and delta["reasoning_content"]:
                        has_thought = True
                        sse_thought = format_gemini_sse_thought_chunk(delta["reasoning_content"])
                        self.wfile.write(sse_thought.encode("utf-8"))
                        self.wfile.flush()

                    # 2. Main content text delta
                    if "content" in delta and delta["content"]:
                        has_text = True
                        sse_chunk = format_gemini_sse_text_chunk(delta["content"])
                        self.wfile.write(sse_chunk.encode("utf-8"))
                        self.wfile.flush()
                        
                    # 3. Tool calls delta
                    if "tool_calls" in delta and delta["tool_calls"]:
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            if idx not in streamed_tools:
                                streamed_tools[idx] = {"name": "", "arguments": ""}
                            fn = tc.get("function") or {}
                            if "name" in fn and fn["name"]:
                                streamed_tools[idx]["name"] = fn["name"]
                            if "arguments" in fn and fn["arguments"]:
                                streamed_tools[idx]["arguments"] += fn["arguments"]

                # Yield all accumulated and repaired tool calls with anti-hollow filtering
                valid_tool_count = 0
                for idx, t_info in sorted(streamed_tools.items()):
                    t_name = t_info["name"]
                    t_args_str = t_info["arguments"]
                    if not t_name:
                        continue
                    repaired_args = repair_json_string(t_args_str)
                    validated_args = validate_and_fill_tool_args(t_name, repaired_args, tool_schemas)
                    
                    # Strictly filter out hollow / inoperable tool calls
                    if not is_tool_call_operable(t_name, validated_args):
                        logger.warning("[INFERENCE] Discarding inoperable hollow tool call [%d]: %s(%s)", idx, t_name, validated_args)
                        continue

                    logger.info("[INFERENCE] Yielding validated functionCall [%d]: %s(%s)", idx, t_name, validated_args)
                    sse_tc = format_gemini_sse_function_call(t_name, validated_args)
                    self.wfile.write(sse_tc.encode("utf-8"))
                    self.wfile.flush()
                    valid_tool_count += 1

                # If no text was sent and all tool calls were discarded as hollow, emit a fallback explanation
                if not has_text and valid_tool_count == 0:
                    logger.warning("[INFERENCE] Model generated no text and no valid tool calls. Emitting fallback clarification text.")
                    fallback_text = "Локальная модель завершила шаг без действия. Пожалуйста, уточните или повторите запрос."
                    sse_fallback = format_gemini_sse_text_chunk(fallback_text)
                    self.wfile.write(sse_fallback.encode("utf-8"))
                    self.wfile.flush()

                sse_finish = format_gemini_sse_finish("STOP")
                self.wfile.write(sse_finish.encode("utf-8"))
                self.wfile.flush()
                self.close_connection = True
                logger.info("[INFERENCE] Generation completed successfully (tools=%d, text=%s, thought=%s).",
                            valid_tool_count, has_text, has_thought)

        except CLIENT_DISCONNECT_EXCEPTIONS:
            logger.debug("Client disconnected during streamGenerateContent on %s", self.path)
            return
        except urllib.error.HTTPError as e:
            err_data = e.read().decode("utf-8", errors="ignore")
            logger.error("[INFERENCE] HTTP Error %d from llama-swap: %s | Body: %s", e.code, e, err_data)
            err_msg = f"Ошибка локальной модели рабочей станции: HTTP {e.code} - {err_data}"
            err_chunk = format_gemini_sse_text_chunk(err_msg)
            self.wfile.write(err_chunk.encode("utf-8"))
            sse_finish = format_gemini_sse_finish("STOP")
            self.wfile.write(sse_finish.encode("utf-8"))
            self.wfile.flush()
        except Exception as e:
            logger.error("[INFERENCE] Error communicating with llama-swap: %s", e)
            err_msg = f"Ошибка локальной модели рабочей станции: {str(e)}"
            err_chunk = format_gemini_sse_text_chunk(err_msg)
            self.wfile.write(err_chunk.encode("utf-8"))
            sse_finish = format_gemini_sse_finish("STOP")
            self.wfile.write(sse_finish.encode("utf-8"))
            self.wfile.flush()

    def _proxy_stream_upstream(self, req_body: bytes):
        target_url = TARGET_HOST + self.path
        headers = {k: v for k, v in self.headers.items() if k.lower() not in STRIP_REQUEST_HEADERS}
        if "content-type" not in [k.lower() for k in headers]:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(target_url, data=req_body, headers=headers, method="POST")
        opener = _make_upstream_opener()
        try:
            with opener.open(req, timeout=300) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ["transfer-encoding", "content-length", "connection"]:
                        self.send_header(k, v)
                self.send_header("Connection", "close")
                self.close_connection = True
                self.end_headers()
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
                logger.info("[STREAM_UPSTREAM] Completed stream for %s (status %d)", self.path, resp.status)
        except CLIENT_DISCONNECT_EXCEPTIONS:
            logger.debug("Client disconnected during stream on %s", self.path)
            return
        except urllib.error.HTTPError as e:
            logger.warning("[STREAM_UPSTREAM] Upstream HTTP %d on %s", e.code, self.path)
            try:
                self.send_response(e.code)
                for k, v in e.headers.items():
                    if k.lower() not in ["transfer-encoding", "content-length", "connection"]:
                        self.send_header(k, v)
                resp_body = e.read()
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                self.wfile.write(resp_body)
            except CLIENT_DISCONNECT_EXCEPTIONS:
                logger.debug("Client disconnected while forwarding stream HTTPError on %s", self.path)
        except Exception as e:
            logger.error("Error streaming from upstream: %s", e)
            invalidate_proxy()
            try:
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"error": "{str(e)}"}}'.encode("utf-8"))
            except Exception:
                pass

    def _proxy_generic(self, method: str, req_body: bytes):
        is_auxiliary = any(ep in self.path for ep in AUXILIARY_ENDPOINTS)
        target_url = TARGET_HOST + self.path
        headers = {k: v for k, v in self.headers.items() if k.lower() not in STRIP_REQUEST_HEADERS}
        if method == "POST" and "content-type" not in [k.lower() for k in headers]:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(target_url, data=req_body if method == "POST" else None, headers=headers, method=method)
        opener = _make_upstream_opener()
        req_timeout = 5 if is_auxiliary else 30
        try:
            with opener.open(req, timeout=req_timeout) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ["transfer-encoding", "content-length", "connection"]:
                        self.send_header(k, v)
                resp_body = resp.read()
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                self.wfile.write(resp_body)
        except CLIENT_DISCONNECT_EXCEPTIONS:
            logger.debug("Client disconnected during _proxy_generic on %s", self.path)
            return
        except urllib.error.HTTPError as e:
            if is_auxiliary:
                logger.debug("[AUXILIARY] Upstream HTTP %d on %s. Serving 200 OK fast-path.", e.code, self.path)
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"{}")
                except Exception:
                    pass
                return

            logger.warning("[GENERIC] Upstream HTTP %d on %s", e.code, self.path)
            try:
                self.send_response(e.code)
                for k, v in e.headers.items():
                    if k.lower() not in ["transfer-encoding", "content-length", "connection"]:
                        self.send_header(k, v)
                resp_body = e.read()
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                self.wfile.write(resp_body)
            except CLIENT_DISCONNECT_EXCEPTIONS:
                logger.debug("Client disconnected while forwarding HTTPError on %s", self.path)
        except Exception as e:
            if is_auxiliary:
                logger.debug("[AUXILIARY] Upstream error (%s) on %s. Serving 200 OK fast-path.", e, self.path)
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"{}")
                except Exception:
                    pass
                return

            logger.warning("Generic proxy error on %s: %s", self.path, e)
            invalidate_proxy()
            try:
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"error": "{str(e)}"}}'.encode("utf-8"))
            except Exception:
                pass

def main():
    server = ThreadedHTTPServer(("127.0.0.1", PORT), AntigravityBridgeHandler)
    logger.info("Antigravity Bridge service listening on http://127.0.0.1:%d", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down bridge service...")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
