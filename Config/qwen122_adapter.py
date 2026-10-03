r"""
Qwen 122B Outgoing Translation Adapter (Nexus Shim)
Location: K:\Project\Config\qwen122_adapter.py

Purpose:
- Acts as a local reverse proxy specifically and exclusively for Qwen 122B (208E).
- Ingests prompts (native Russian or multilingual), prompts Qwen 122B to think and respond in English.
- Protects code blocks, markdown syntax, and tool calls.
- Translates outgoing English response (content) to natural Russian via in-memory CPU MarianMT + domain glossary.
- Uses Windows Job Object with KILL_ON_JOB_CLOSE to guarantee zero orphaned llama-server processes.
- Runs on CPU with ~300 MB RAM and 0 MB VRAM, keeping GPU pool dedicated to Qwen 122B.
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

import torch
from transformers import MarianMTModel, MarianTokenizer

# Windows Job Object support for clean child process management
try:
    import win32api
    import win32job
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# Global State
child_proc = None
upstream_port = None
translator_model = None
translator_tokenizer = None
translator_lock = threading.Lock()
translator_ready = threading.Event()
job_handle = None

# Domain Glossary for software engineering terms
DOMAIN_REPLACEMENTS = [
    (r"\bМолчаливые повешения\b", "Зависания без ошибок в логах"),
    (r"\bмолчаливые повешения\b", "зависания без ошибок в логах"),
    (r"\bпроизводственных пожаров\b", "аварий на проде"),
    (r"\bпроизводственном пожаре\b", "аварии на проде"),
    (r"\bпроизводственные пожары\b", "аварии на проде"),
    (r"\bзамерзает\b", "зависает"),
    (r"\bтупиком\b", "дедлоком"),
    (r"\bтупика\b", "дедлока"),
    (r"\bтупики\b", "дедлоки"),
    (r"\bтупик\b", "дедлок"),
    (r"\bвременем внешней зависимости\b", "таймаутом внешних сервисов"),
    (r"\bпопадает под ваш текущий прибор\b", "отслеживается вашей телеметрией"),
    (r"\bтекущий прибор\b", "текущий инструментарий мониторинга"),
    (r"\bне жучок\b", "не баг"),
    (r"\bжучок\b", "баг"),
    (r"\bпартнёр\b", "напарник"),
    (r"\bПартнёр\b", "Напарник"),
    (r"\bбревнах\b", "логах"),
    (r"\bбревнами\b", "логами"),
    (r"\bбревнам\b", "логам"),
    (r"\bбревен\b", "логов"),
    (r"\bбревна\b", "логи"),
    (r"\bбревно\b", "лог"),
    (r"\bКоллекция Гарбаджа\b", "Сборка мусора (GC)"),
    (r"\bколлекция гарбаджа\b", "сборка мусора (GC)"),
    (r"\bСердцебит\b", "Heartbeat (проверка пульса)"),
    (r"\bсердцебит\b", "heartbeat (проверка пульса)"),
    (r"\bСтайджинге\b", "стейджинге"),
    (r"\bстайджинге\b", "стейджинге"),
    (r"\bСтайджинг\b", "Стейджинг"),
    (r"\bстайджинг\b", "стейджинг"),
    (r"\bТрубопровода\b", "пайплайна"),
    (r"\bтрубопровода\b", "пайплайна"),
    (r"\bЦЕЛОЕ ЧИСЛО\b", "ЦЕЛИ (Goals)"),
    (r"\bцелое число\b", "цели"),
    (r"\bДОБАВЛЕНИЕ\b", "TODO (Задачи к выполнению)"),
    (r"\bдобавление\b", "TODO"),
    (r"\bПЛЕНАРНОЕ ЗАСЕДАНИЕ\b", "ПЛАН (Plan)"),
    (r"\bпленарное заседание\b", "план"),
]


def setup_job_object():
    """Binds current process to a Windows Job Object with KILL_ON_JOB_CLOSE."""
    global job_handle
    if not HAS_WIN32:
        return
    try:
        hJob = win32job.CreateJobObject(None, "")
        info = win32job.QueryInformationJobObject(hJob, win32job.JobObjectExtendedLimitInformation)
        info["BasicLimitInformation"]["LimitFlags"] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(hJob, win32job.JobObjectExtendedLimitInformation, info)
        win32job.AssignProcessToJobObject(hJob, win32api.GetCurrentProcess())
        job_handle = hJob
        print("[Qwen122-Adapter] Job Object initialized with KILL_ON_JOB_CLOSE", flush=True)
    except Exception as e:
        print(f"[Qwen122-Adapter] Warning: Failed to set up Job Object: {e}", flush=True)


def init_translator():
    """Initializes the lightweight MarianMT translation engine on CPU."""
    global translator_model, translator_tokenizer
    try:
        t0 = time.time()
        torch.set_num_threads(8)
        model_name = "Helsinki-NLP/opus-mt-en-ru"
        translator_tokenizer = MarianTokenizer.from_pretrained(model_name)
        translator_model = MarianMTModel.from_pretrained(model_name)
        translator_model.eval()
        dt = time.time() - t0
        print(f"[Qwen122-Adapter] Translation engine loaded on CPU in {dt:.2f}s", flush=True)
    except Exception as e:
        print(f"[Qwen122-Adapter] Error loading translation engine: {e}", flush=True)
    finally:
        translator_ready.set()


def translate_text_fragment(fragment: str) -> str:
    """Translates a single pure-text string from EN to RU."""
    if not fragment or not fragment.strip():
        return fragment

    try:
        inputs = translator_tokenizer([fragment], return_tensors="pt", truncation=True, max_length=512)
        out = translator_model.generate(**inputs, max_length=512)
        ru = translator_tokenizer.decode(out[0], skip_special_tokens=True)
        for pat, repl in DOMAIN_REPLACEMENTS:
            ru = re.sub(pat, repl, ru)
        return ru
    except Exception as err:
        print(f"[Qwen122-Adapter] Translation fragment error: {err}", flush=True)
        return fragment


def translate_text(text: str) -> str:
    """Translates text from English to Russian while strictly preserving code blocks and inline code."""
    if not text or not text.strip():
        return text

    translator_ready.wait(timeout=30)
    if translator_model is None or translator_tokenizer is None:
        return text

    # Step 1: Split into protected blocks (code blocks, tool calls, think blocks, XML tags) and prose
    protected_pattern = r"(```[\s\S]*?```|<tool_call[\s\S]*?</tool_call>|<action[\s\S]*?</action>|<think[\s\S]*?</think>|<[^>\n]+>)"
    block_parts = re.split(protected_pattern, text)
    result_blocks = []

    with translator_lock:
        with torch.inference_mode():
            for block in block_parts:
                if not block:
                    continue

                # Check if block is protected
                if ((block.startswith("```") and block.endswith("```")) or
                    (block.startswith("<tool_call") and block.endswith("</tool_call>")) or
                    (block.startswith("<action") and block.endswith("</action>")) or
                    (block.startswith("<think") and block.endswith("</think>")) or
                    (block.startswith("<") and block.endswith(">"))):
                    result_blocks.append(block)
                    continue

                # Step 2: Split block into lines
                lines = block.split("\n")
                trans_lines = []
                for line in lines:
                    if not line.strip():
                        trans_lines.append(line)
                        continue

                    # Preserve leading bullet / number formatting (*, -, 1., ##)
                    prefix = ""
                    m_pref = re.match(r"^(\s*#{1,6}\s*|\s*[-*+]\s+|\s*\d+\.\s+)", line)
                    if m_pref:
                        prefix = m_pref.group(1)
                        content_line = line[len(prefix):]
                    else:
                        content_line = line

                    # Step 3: Split line by inline code (`...`) or tags (<...>)
                    inline_parts = re.split(r"(`[^`\n]+`|<[^>\n]+>)", content_line)
                    trans_inline = []
                    for part in inline_parts:
                        if not part:
                            continue
                        if ((part.startswith("`") and part.endswith("`")) or
                            (part.startswith("<") and part.endswith(">"))):
                            trans_inline.append(part)
                        else:
                            trans_inline.append(translate_text_fragment(part))

                    trans_lines.append(prefix + "".join(trans_inline))

                result_blocks.append("\n".join(trans_lines))

    final_result = "".join(result_blocks)
    return final_result


def extract_tool_calls_from_content(content: str):
    """Parses raw XML or JSON tool calls generated inside content and returns OpenAI-format tool_calls."""
    if not content or not isinstance(content, str):
        return []

    tool_calls = []

    # Pattern 1: XML syntax <tool_call><function = NAME><parameter = KEY>VAL</parameter>...</function></tool_call>
    tc_matches = list(re.finditer(r'<tool_call>\s*<function\s*=\s*([\w\-]+)>(.*?)</function>\s*(?:</tool_call>)?', content, re.DOTALL))
    for m in tc_matches:
        fn_name = m.group(1).strip()
        params_body = m.group(2)
        params = {}
        for p in re.finditer(r'<parameter\s*=\s*([\w\-]+)>(.*?)</parameter>', params_body, re.DOTALL):
            params[p.group(1).strip()] = p.group(2).strip()
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
            name = parsed.get("name")
            args = parsed.get("arguments", {})
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
        print("[Qwen122-Adapter] Terminating child llama-server process...", flush=True)
        try:
            subprocess.run(f"taskkill /F /T /PID {child_proc.pid}", shell=True, capture_output=True)
        except Exception:
            try:
                child_proc.kill()
            except Exception:
                pass


atexit.register(cleanup)


class Qwen122ProxyHandler(BaseHTTPRequestHandler):
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

        # Intercept chat completions: append 'Answer in English.' to the last user message
        if method == "POST" and "/v1/chat/completions" in self.path and body:
            try:
                req_data = json.loads(body.decode("utf-8"))
                messages = req_data.get("messages", [])
                
                for m in reversed(messages):
                    if m.get("role") == "user":
                        u_content = m.get("content", "")
                        if isinstance(u_content, str) and "Answer in English" not in u_content:
                            m["content"] = u_content.rstrip() + "\n\nAnswer in English."
                        break
                
                req_data["messages"] = messages
                body = json.dumps(req_data).encode("utf-8")
            except Exception as e:
                print(f"[Qwen122-Adapter] Request transform warning: {e}", flush=True)

        headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")}
        if body is not None:
            headers["Content-Length"] = str(len(body))

        req = urllib.request.Request(target_url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=7200) as resp:
                resp_data = resp.read()
                resp_headers = resp.headers

                # If non-streaming chat completions response, translate content to Russian
                if "/v1/chat/completions" in self.path and resp.status == 200:
                    try:
                        res_json = json.loads(resp_data.decode("utf-8"))
                        choices = res_json.get("choices", [])
                        if choices and isinstance(choices, list):
                            msg = choices[0].get("message", {})
                            content = msg.get("content")

                            # 1. Recover any raw tool calls from content (XML or JSON)
                            if content and isinstance(content, str):
                                extracted_calls = extract_tool_calls_from_content(content)
                                if extracted_calls:
                                    existing = msg.get("tool_calls") or []
                                    msg["tool_calls"] = existing + extracted_calls
                                    # Strip tool_call blocks from content
                                    cleaned = re.sub(r'<tool_call[\s\S]*?(?:</tool_call>|$)', '', content).strip()
                                    cleaned = re.sub(r'^\s*</think>\s*', '', cleaned).strip()
                                    cleaned = re.sub(r'^\s*<think>[\s\S]*?</think>\s*', '', cleaned).strip()
                                    content = cleaned if cleaned else ""
                                    msg["content"] = content
                                    print(f"[Qwen122-Adapter] Recovered {len(extracted_calls)} tool call(s) from content!", flush=True)

                                # 2. If text content remains, translate it to Russian
                                if content:
                                    t0 = time.time()
                                    translated_content = translate_text(content)
                                    dt = time.time() - t0
                                    print(f"[Qwen122-Adapter] Output translation: {len(content)} -> {len(translated_content)} chars ({dt:.3f}s)", flush=True)
                                    msg["content"] = translated_content

                            resp_data = json.dumps(res_json, ensure_ascii=False).encode("utf-8")
                    except Exception as e:
                        print(f"[Qwen122-Adapter] Response translation warning: {e}", flush=True)

                self.send_response(resp.status)
                for k, v in resp_headers.items():
                    if k.lower() not in ("transfer-encoding", "content-length"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(resp_data)))
                self.end_headers()
                self.wfile.write(resp_data)

        except urllib.error.HTTPError as e:
            err_body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as e:
            err_msg = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_msg)))
            self.end_headers()
            self.wfile.write(err_msg)


def main():
    global child_proc, upstream_port

    setup_job_object()

    if "--listen-port" not in sys.argv:
        print("Usage: python qwen122_adapter.py --listen-port <PORT> -- <COMMAND_ARGS...>")
        sys.exit(1)

    lp_idx = sys.argv.index("--listen-port")
    listen_port = int(sys.argv[lp_idx + 1])

    dash_idx = sys.argv.index("--") if "--" in sys.argv else -1
    if dash_idx == -1 or dash_idx == len(sys.argv) - 1:
        print("Error: Command arguments separator '--' missing or empty.")
        sys.exit(1)

    cmd_args = sys.argv[dash_idx + 1:]
    upstream_port = find_free_port()

    cmd_args.extend(["--host", "127.0.0.1", "--port", str(upstream_port)])

    print(f"[Qwen122-Adapter] Launching llama-server on internal port {upstream_port}...", flush=True)
    child_proc = subprocess.Popen(cmd_args)

    threading.Thread(target=init_translator, daemon=True).start()

    print(f"[Qwen122-Adapter] Listening on port {listen_port} (proxies to {upstream_port})...", flush=True)
    server = ThreadingHTTPServer(("127.0.0.1", listen_port), Qwen122ProxyHandler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
