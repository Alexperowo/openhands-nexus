"""
Local Voice Bridge Service for OpenHands Local
Port: 127.0.0.1:18002

Integrates:
- STT: FUTO Keyboard GigaAM v3 e2e-RNN-T (GGML/transcribe.cpp, 261 MB, in-memory)
- TTS: Supertonic 3 Russian ONNX (Supertone, 99M, in-memory)
Zero cloud dependencies. 100% offline.
"""

import glob
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

# Ensure UTF-8 output and safety under pythonw (where stdout/stderr can be None)
if sys.stdout is None:
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "..", "Logs", "Voice")
        os.makedirs(log_dir, exist_ok=True)
        log_file = open(os.path.join(log_dir, "voice-bridge.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
    except Exception:
        pass
else:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if sys.stderr is not None:
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Setup portable paths for transcribe_cpp and speech models
VOICE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(VOICE_DIR, ".."))

candidate_transcribe_paths = [
    os.environ.get("FUTO_TRANSCRIBE_PATH"),
    VOICE_DIR,
    os.path.join(PROJECT_ROOT, "local-voice"),
    os.path.join(PROJECT_ROOT, "futo-keyboard-gigaam", "third_party", "transcribe.cpp", "bindings", "python", "src"),
]
PYTHONPATH_TRANSCRIBE = next(
    (p for p in candidate_transcribe_paths if p and os.path.isdir(os.path.join(p, "transcribe_cpp"))),
    VOICE_DIR
)

candidate_dll_paths = [
    os.environ.get("TRANSCRIBE_LIBRARY"),
    os.path.join(PROJECT_ROOT, "transcribe-build-shared", "bin", "Release", "transcribe.dll"),
    os.path.join(VOICE_DIR, "bin", "transcribe.dll"),
]
TRANSCRIBE_DLL = next((p for p in candidate_dll_paths if p and os.path.isfile(p)), candidate_dll_paths[1])

candidate_gigaam_paths = [
    os.environ.get("GIGAAM_MODEL_PATH"),
    os.path.join(PROJECT_ROOT, "Models", "Speech", "gigaam-v3-e2e-rnnt-Q8_0.gguf"),
    os.path.join(PROJECT_ROOT, "Models", "gigaam-v3-e2e-rnnt-Q8_0.gguf"),
]
GIGAAM_MODEL_PATH = next((p for p in candidate_gigaam_paths if p and os.path.isfile(p)), candidate_gigaam_paths[1])

candidate_supertonic_paths = [
    os.environ.get("SUPERTONIC_MODEL_DIR"),
    os.path.join(PROJECT_ROOT, "Models", "Speech", "supertonic"),
    os.path.join(PROJECT_ROOT, "Models", "supertonic"),
]
SUPERTONIC_DIR = next((p for p in candidate_supertonic_paths if p and os.path.isdir(p)), candidate_supertonic_paths[1])

os.environ["PYTHONPATH"] = PYTHONPATH_TRANSCRIBE
os.environ["TRANSCRIBE_LIBRARY"] = TRANSCRIBE_DLL
if PYTHONPATH_TRANSCRIBE not in sys.path:
    sys.path.insert(0, PYTHONPATH_TRANSCRIBE)

import av
import transcribe_cpp
from supertonic import TTS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Config"))
import slot_cache_manager
import working_profiles

# Global state
START_TIME = time.time()
stt_model = None
tts_model = None
voice_styles = {}
stt_lock = threading.Lock()
tts_lock = threading.Lock()
metrics_lock = threading.Lock()
cancel_event = threading.Event()
_httpd_ref = None
_telemetry_cache = None
_telemetry_cache_time = 0.0
_telemetry_lock = threading.Lock()
_prev_telemetry_sample = {}
_prefill_tracker = {}
_slot_prefill_tracker = {}
_gen_tracker = {}
_last_known_gen_speed = 0.0
_last_known_prefill_speed = 0.0


def _shutdown_server():
    """Gracefully shut down the HTTP server."""
    global _httpd_ref
    try:
        slot_cache_manager.stop_slot_restorer_daemon()
    except Exception:
        pass
    if _httpd_ref:
        _httpd_ref.shutdown()

# Metrics
METRICS = {
    "stt_load_time_s": 0.0,
    "tts_load_time_s": 0.0,
    "stt_count": 0,
    "tts_count": 0,
    "last_stt_latency_ms": 0.0,
    "last_tts_latency_ms": 0.0,
    "last_tts_rtf": 0.0,
}


def init_models():
    global stt_model, tts_model, voice_styles

    print("[Voice Bridge] Loading FUTO GigaAM v3 STT into memory...", flush=True)
    t0 = time.perf_counter()
    stt_model = transcribe_cpp.Model(GIGAAM_MODEL_PATH)
    with metrics_lock:
        METRICS["stt_load_time_s"] = round(time.perf_counter() - t0, 3)
    print(f"[Voice Bridge] GigaAM v3 STT loaded in {METRICS['stt_load_time_s']} s", flush=True)

    print("[Voice Bridge] Loading Supertonic 3 TTS into memory...", flush=True)
    t1 = time.perf_counter()
    tts_model = TTS(model="supertonic-3", model_dir=SUPERTONIC_DIR, auto_download=False)
    voice_styles["M1"] = tts_model.get_voice_style("M1")
    voice_styles["F1"] = tts_model.get_voice_style("F1")
    with metrics_lock:
        METRICS["tts_load_time_s"] = round(time.perf_counter() - t1, 3)
    print(f"[Voice Bridge] Supertonic 3 TTS loaded in {METRICS['tts_load_time_s']} s", flush=True)


def get_process_ram_mb():
    try:
        out = subprocess.check_output(
            f'powershell -NoProfile -Command "(Get-Process -Id {os.getpid()}).WorkingSet64 / 1MB"',
            shell=True,
            timeout=2
        )
        return round(float(out.strip().replace(b",", b".")), 1)
    except Exception:
        return 0.0


def decode_audio_to_16k_mono(audio_bytes: bytes) -> np.ndarray:
    """Decode incoming audio buffer (WebM, Opus, WAV, etc.) to 16kHz float32 mono."""
    container = None
    try:
        input_file = io.BytesIO(audio_bytes)
        container = av.open(input_file)
        resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
        samples = []
        for frame in container.decode(audio=0):
            for resampled_frame in resampler.resample(frame):
                samples.append(resampled_frame.to_ndarray())
        if not samples:
            return np.array([], dtype=np.float32)
        pcm = np.concatenate(samples, axis=1).squeeze(0)
        return pcm.astype(np.float32)
    except Exception as err:
        print(f"[Voice Bridge] Audio decode error: {err}", flush=True)
        return np.array([], dtype=np.float32)
    finally:
        if container is not None:
            try:
                container.close()
            except Exception:
                pass


def clean_text_for_speech(text: str) -> str:
    """Clean LLM output for natural Russian text-to-speech synthesis."""
    if not text:
        return ""
    # Strip <think> ... </think> or reasoning tags if present
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```.*?```", " Код опущен. ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove markdown links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove markdown headers and bullet markers
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\*\-\+]\s+", "", text, flags=re.MULTILINE)
    # Remove excessive punctuation or symbols
    text = re.sub(r"[~*_|\\]", "", text)
    # Collapse multiple whitespace/newlines into single space
    text = re.sub(r"\s+", " ", text).strip()
    return text


def synthesize_to_wav_bytes(text: str, voice_style_name: str = "M1") -> tuple[bytes, float, float]:
    """Synthesize text to WAV bytes. Returns (wav_bytes, duration_s, latency_s)."""
    cancel_event.clear()
    style = voice_styles.get(voice_style_name, voice_styles.get("M1"))

    t0 = time.perf_counter()
    with tts_lock:
        if cancel_event.is_set():
            return b"", 0.0, 0.0
        wav, dur = tts_model.synthesize(text, voice_style=style, lang="ru")

    latency = time.perf_counter() - t0
    duration = float(dur[0]) if len(dur) > 0 else 0.0

    # Convert numpy float32 waveform (shape 1, N) to 16-bit PCM WAV bytes
    waveform = np.clip(wav[0], -1.0, 1.0)
    pcm_int16 = (waveform * 32767).astype(np.int16)

    # Safely determine native sample rate (from model attribute or waveform / duration)
    sample_rate = getattr(tts_model, "sample_rate", None)
    if not sample_rate and duration > 0 and len(waveform) > 0:
        sample_rate = int(round(len(waveform) / duration))
    if not sample_rate or sample_rate <= 0:
        sample_rate = 44100

    out_io = io.BytesIO()
    with wave.open(out_io, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_int16.tobytes())

    return out_io.getvalue(), duration, latency


def get_station_telemetry() -> dict:
    global _telemetry_cache, _telemetry_cache_time
    now = time.time()
    with _telemetry_lock:
        if _telemetry_cache is not None and (now - _telemetry_cache_time) < 0.5:
            return dict(_telemetry_cache)
        res = _compute_station_telemetry()
        _telemetry_cache = res
        _telemetry_cache_time = now
        return dict(res)


def _compute_station_telemetry() -> dict:
    global _last_known_gen_speed, _last_known_prefill_speed, _gen_tracker, _prefill_tracker, _slot_prefill_tracker
    log_path = os.path.join(os.path.dirname(__file__), "..", "Logs", "llama-swap", "llama-swap.log")
    if not os.path.exists(log_path):
        log_path = os.path.join(os.path.dirname(__file__), "..", "llama-swap.log")

    active_profile = "Qwen 122B"
    try:
        st = working_profiles.get_working_profile_state()
        if st and st.get("active_working_profile_id"):
            profs = working_profiles.load_working_profiles()
            for p in profs:
                if p.get("id") == st.get("active_working_profile_id"):
                    active_profile = p.get("name", active_profile)
                    break
    except Exception:
        pass

    slot_status = None
    try:
        slot_status = slot_cache_manager.get_slot_status()
    except Exception:
        pass

    now = time.time()
    telemetry = {
        "status": "ok",
        "model": active_profile,
        "state": "idle",
        "progress_pct": 0,
        "tokens": 0,
        "total_tokens": 0,
        "speed_tok_s": 0.0,
        "last_gen_speed": _last_known_gen_speed,
        "last_prefill_speed": _last_known_prefill_speed,
        "eta_seconds": None,
        "eta_str": None,
        "active_tool": None,
        "is_active": False,
        "slot_cache": slot_status,
        "timestamp": now
    }

    # 1. Check if OpenHands is actively executing a tool
    try:
        conv_root = os.path.expanduser(r"~/.openhands/agent-canvas/dev_conversations")
        if os.path.exists(conv_root):
            conv_dirs = [os.path.join(conv_root, d) for d in os.listdir(conv_root) if os.path.isdir(os.path.join(conv_root, d))]
            if conv_dirs:
                latest_conv = max(conv_dirs, key=os.path.getmtime)
                events_dir = os.path.join(latest_conv, "events")
                if os.path.exists(events_dir):
                    event_files = sorted(glob.glob(os.path.join(events_dir, "event-*.json")))
                    if event_files:
                        last_f = event_files[-1]
                        if (now - os.path.getmtime(last_f)) < 30:
                            with open(last_f, encoding="utf-8-sig") as ef:
                                ev_data = json.load(ef)
                            if ev_data.get("kind") == "ActionEvent":
                                t_name = ev_data.get("tool_name") or ev_data.get("action", {}).get("kind") or "инструмент"
                                telemetry["state"] = "tool"
                                telemetry["active_tool"] = t_name
                                telemetry["is_active"] = True
                                return telemetry
    except Exception:
        pass

    # 2. Check running model info from llama-swap router
    running_info = {"model": None, "state": "none", "proxy": None}
    try:
        running_info = slot_cache_manager.get_running_model_info()
    except Exception:
        pass

    model_id = running_info.get("model")
    model_state = running_info.get("state", "none")
    proxy = running_info.get("proxy")

    if model_state in ("loading", "starting", "initializing", "swapping"):
        telemetry["state"] = "loading"
        telemetry["is_active"] = True
        return telemetry

    # 3. Query live llama-server slot for ground-truth hardware state
    slot_obj = None
    if model_id and model_state == "ready":
        s_url = f"{proxy.rstrip('/')}/slots" if proxy else f"http://127.0.0.1:8080/upstream/{model_id}/slots"
        try:
            s_req = urllib.request.Request(s_url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(s_req, timeout=0.35) as s_resp:
                data = json.loads(s_resp.read().decode("utf-8"))
                if isinstance(data, list) and len(data) > 0:
                    slot_obj = data[0]
        except Exception:
            pass

    # Read log tail to extract speeds (only from recently updated log files)
    log_task_active = False
    log_last_task = None
    log_prefill_tokens = 0
    log_prefill_done = False

    if os.path.exists(log_path):
        try:
            # Only consider log tail if log file was modified in the last 60 seconds
            if (now - os.path.getmtime(log_path)) < 60:
                with open(log_path, "rb") as f:
                    f_size = os.path.getsize(log_path)
                    f.seek(max(0, f_size - 65536))
                    lines = f.read().decode("utf-8", errors="ignore").splitlines()

                for line in lines:
                    m_launch = re.search(r'(?:slot is processing task.*?id_task=(\d+)|launch_slot_:.*?task\s*(\d+))', line)
                    if m_launch:
                        log_last_task = int(m_launch.group(1) or m_launch.group(2))
                        log_task_active = True
                        log_prefill_done = False

                    m_chk = re.search(r'(?:slot create_check:.*?task\s*(\d+).*?n_tokens\s*=\s*(\d+)|print_timing:.*?task\s*(\d+).*?prompt processing,\s*n_tokens\s*=\s*(\d+))', line)
                    if m_chk:
                        t_id = int(m_chk.group(1) or m_chk.group(3))
                        if log_last_task == t_id:
                            log_prefill_tokens = int(m_chk.group(2) or m_chk.group(4))

                    m_peval = re.search(r'prompt eval time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s*tokens\s*\(.*?([\d.]+)\s*tokens per second\)', line)
                    if m_peval:
                        log_prefill_done = True
                        p_spd = float(m_peval.group(3))
                        _last_known_prefill_speed = p_spd
                        telemetry["last_prefill_speed"] = p_spd

                    m_geval = re.search(r'^\s*eval time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s*tokens\s*\(.*?([\d.]+)\s*tokens per second\)', line)
                    if m_geval:
                        g_spd = float(m_geval.group(3))
                        _last_known_gen_speed = g_spd
                        telemetry["last_gen_speed"] = g_spd

                    if re.search(r'release_slots.*?id_task=(\d+)', line) or 'all slots are idle' in line:
                        log_task_active = False
        except Exception:
            pass

    # Ground Truth: If slot is present and says IDLE, model is definitely idle!
    if slot_obj and isinstance(slot_obj, dict):
        s_task_id = int(slot_obj.get("id_task", -1))
        s_state_code = int(slot_obj.get("state", 0))
        s_is_processing = bool(slot_obj.get("is_processing", False))

        if s_task_id == -1 or (s_state_code == 0 and not s_is_processing):
            telemetry["state"] = "idle"
            telemetry["is_active"] = False
            return telemetry

    has_next = False
    n_decoded = 0
    s_task = 0
    s_state = 0

    if slot_obj and isinstance(slot_obj, dict):
        s_task = int(slot_obj.get("id_task", 0))
        s_state = int(slot_obj.get("state", 0))
        next_tok = slot_obj.get("next_token", {})
        if isinstance(next_tok, list) and len(next_tok) > 0:
            next_tok = next_tok[0]
        elif not isinstance(next_tok, dict):
            next_tok = {}

        has_next = bool(next_tok.get("has_next_token", False))
        n_decoded = int(next_tok.get("n_decoded", 0))

    # Case A: Live token generation (decoding in progress)
    if has_next or (s_state == 1 and n_decoded > 0):
        telemetry["is_active"] = True
        telemetry["state"] = "generating"
        telemetry["tokens"] = n_decoded

        if _gen_tracker.get("task") != s_task:
            def_spd = 33.0 if "122" in str(model_id) else (70.0 if "35" in str(model_id) else 100.0)
            _gen_tracker.update({
                "task": s_task,
                "last_tokens": n_decoded,
                "last_time": now,
                "speed": _last_known_gen_speed or def_spd
            })
        else:
            dt = now - _gen_tracker.get("last_time", now)
            dn = n_decoded - _gen_tracker.get("last_tokens", 0)
            if dt >= 0.3 and dn > 0:
                calc_spd = round(dn / dt, 1)
                _gen_tracker["speed"] = calc_spd
                _last_known_gen_speed = calc_spd
                _gen_tracker["last_tokens"] = n_decoded
                _gen_tracker["last_time"] = now

        current_gen_speed = _gen_tracker.get("speed", _last_known_gen_speed or 30.0)
        telemetry["speed_tok_s"] = current_gen_speed
        telemetry["last_gen_speed"] = _last_known_gen_speed
        return telemetry

    # Case B: Live slot processing (active prefill or thinking when has_next is not yet true)
    if slot_obj and bool(slot_obj.get("is_processing")):
        telemetry["is_active"] = True
        n_prompt = int(slot_obj.get("n_prompt_tokens", 0))
        n_proc = int(slot_obj.get("n_prompt_tokens_processed", 0))
        n_cache = int(slot_obj.get("n_prompt_tokens_cache", 0))

        done_tokens = n_cache + n_proc
        total_tokens = max(n_prompt, done_tokens, 1)

        if total_tokens > 0 and done_tokens < total_tokens:
            telemetry["state"] = "prefill"
            p_spd = max(5.0, _last_known_prefill_speed or (20.0 if "122" in str(model_id) else 1000.0))

            # Smooth time-based interpolation between discrete batch updates
            s_task = int(slot_obj.get("id_task", 0))
            if _slot_prefill_tracker.get("task") != s_task or _slot_prefill_tracker.get("base_tokens") != done_tokens:
                _slot_prefill_tracker.update({
                    "task": s_task,
                    "base_tokens": done_tokens,
                    "base_time": now,
                    "total_tokens": total_tokens
                })

            dt_step = max(0.0, now - _slot_prefill_tracker.get("base_time", now))
            interp_tokens = min(total_tokens - 1, int(done_tokens + (dt_step * p_spd)))
            pct = min(99.0, max(1.0, round((interp_tokens / total_tokens) * 100, 1)))

            telemetry["tokens"] = interp_tokens
            telemetry["total_tokens"] = total_tokens
            telemetry["progress_pct"] = pct
            telemetry["speed_tok_s"] = p_spd
            rem = max(0, total_tokens - interp_tokens)
            eta_s = int(rem / p_spd)
            telemetry["eta_seconds"] = eta_s
            telemetry["eta_str"] = f"{eta_s // 60}м {eta_s % 60}с" if eta_s >= 60 else f"{eta_s}с"
            return telemetry
        else:
            telemetry["state"] = "thinking"
            telemetry["progress_pct"] = 100.0
            telemetry["speed_tok_s"] = 0.0
            return telemetry

    # Case C: Prefill complete, waiting for first token or thinking
    if log_task_active and log_prefill_done and not has_next:
        telemetry["is_active"] = True
        telemetry["state"] = "thinking"
        telemetry["progress_pct"] = 100.0
        telemetry["speed_tok_s"] = 0.0
        return telemetry

    # Case D: Completely idle
    telemetry["state"] = "idle"
    telemetry["is_active"] = False
    return telemetry



class VoiceBridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Concise logging
        print(f"[HTTP] {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}", flush=True)

    def _set_cors(self, content_type="application/json"):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range, Authorization, X-Session-API-Key, Cache-Control")
        self.send_header("Content-Type", content_type)

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors()
        self.end_headers()

    def do_GET(self):
        clean_path = self.path.split("?")[0].rstrip("/")
        if clean_path.startswith("/voice-api"):
            clean_path = clean_path[len("/voice-api"):]
            if not clean_path.startswith("/"):
                clean_path = "/" + clean_path

        if clean_path == "/voice-bridge.js":
            js_path = os.path.join(os.path.dirname(__file__), "voice-bridge.js")
            with open(js_path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self._set_cors("application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(body)
            return

        elif clean_path == "/voice-bridge.css":
            css_path = os.path.join(os.path.dirname(__file__), "voice-bridge.css")
            with open(css_path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self._set_cors("text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(body)
            return

        elif clean_path == "/working-profile-ui.js":
            js_path = os.path.join(os.path.dirname(__file__), "..", "openhands-working-profile", "working-profile-ui.js")
            with open(js_path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self._set_cors("application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(body)
            return

        elif clean_path == "/working-profile-ui.css":
            css_path = os.path.join(os.path.dirname(__file__), "..", "openhands-working-profile", "working-profile-ui.css")
            with open(css_path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self._set_cors("text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(body)
            return

        elif clean_path in ("/api/working-profiles", "/working-profiles"):
            try:
                profiles = working_profiles.load_working_profiles()
                state = working_profiles.get_working_profile_state()
                body = json.dumps({"profiles": profiles, "state": state}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self._set_cors("application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self._set_cors("application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        elif clean_path in ("/api/station-telemetry", "/telemetry"):
            try:
                data = get_station_telemetry()
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self._set_cors("application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self._set_cors("application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        elif clean_path in ("/api/slot-status", "/slot-status"):
            try:
                status_data = slot_cache_manager.get_slot_status()
                body = json.dumps(status_data, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(200)
                self._set_cors("application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self._set_cors("application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        elif self.path in ("/health", "/status"):
            ram = get_process_ram_mb()
            with metrics_lock:
                metrics_copy = dict(METRICS)
            resp = {
                "status": "ok",
                "uptime_s": round(time.time() - START_TIME, 1),
                "stt_engine": "gigaam-v3-e2e-rnnt (FUTO transcribe.cpp)",
                "tts_engine": "supertonic-3 (Supertone ONNX)",
                "voices": list(voice_styles.keys()),
                "ram_mb": ram,
                "metrics": metrics_copy
            }
            body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self._set_cors("application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self._set_cors()
            self.end_headers()
            self.wfile.write(b'{"error": "Not Found"}')

    def do_POST(self):
        clean_path = self.path.split("?")[0].rstrip("/")
        if clean_path.startswith("/voice-api"):
            clean_path = clean_path[len("/voice-api"):]
            if not clean_path.startswith("/"):
                clean_path = "/" + clean_path

        MAX_PAYLOAD_BYTES = 10 * 1024 * 1024  # 10 MB limit (DoS protection)
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > MAX_PAYLOAD_BYTES:
            self.send_response(413)
            self._set_cors()
            self.end_headers()
            self.wfile.write(b'{"error": "Payload Too Large"}')
            return

        body_bytes = self.rfile.read(content_length) if content_length > 0 else b""

        if clean_path in ("/api/working-profiles", "/working-profiles"):
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                wp_id = data.get("working_profile_id")
                rm_id = data.get("reasoning_mode_id")
                res = working_profiles.switch_working_profile(wp_id, rm_id, updated_by="voice_service")
                body = json.dumps(res, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self._set_cors("application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(400)
                self._set_cors("application/json; charset=utf-8")
                self.end_headers()
                err_msg = str(e).splitlines()[0][:200] if str(e) else "Profile switch error"
                self.wfile.write(json.dumps({"error": err_msg}).encode("utf-8"))
            return

        elif clean_path in ("/api/restore-prefix-slot", "/restore-prefix-slot"):
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                target_model = data.get("model")
                target_dump = data.get("dump")
                if target_model and target_dump:
                    res = slot_cache_manager.restore_slot_dump(target_model, target_dump)
                else:
                    res = slot_cache_manager.check_and_auto_restore()
                body = json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(200)
                self._set_cors("application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self._set_cors("application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        elif clean_path in ("/shutdown", "/voice-api/shutdown"):
            resp = {"status": "shutting_down"}
            body = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self._set_cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            print("[Voice Bridge] Graceful shutdown requested via HTTP POST", flush=True)
            threading.Thread(target=_shutdown_server).start()
            return

        if self.path == "/stop":
            cancel_event.set()
            resp = {"status": "stopped"}
            body = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self._set_cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            print("[Voice Bridge] STOP received -> cancelled active speech.", flush=True)

        elif self.path == "/stt":
            if not body_bytes:
                self.send_response(400)
                self._set_cors()
                self.end_headers()
                self.wfile.write(b'{"error": "Empty audio body"}')
                return

            try:
                t0 = time.perf_counter()
                pcm = decode_audio_to_16k_mono(body_bytes)
                audio_dur = len(pcm) / 16000.0

                if audio_dur < 0.2:
                    self.send_response(200)
                    self._set_cors()
                    self.end_headers()
                    self.wfile.write(b'{"text": ""}')
                    return

                with stt_lock, stt_model.session() as session:
                    result = session.run(pcm)
                    text = result.text.strip()

                latency = round((time.perf_counter() - t0) * 1000.0, 1)
                with metrics_lock:
                    METRICS["stt_count"] += 1
                    METRICS["last_stt_latency_ms"] = latency
                print(f"[STT] ({audio_dur:.2f}s audio) -> '{text}' ({latency} ms)", flush=True)

                resp = {
                    "text": text,
                    "audio_duration_s": round(audio_dur, 2),
                    "latency_ms": latency
                }
                body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self._set_cors("application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            except Exception as e:
                print(f"[STT Error] {e}", flush=True)
                self.send_response(500)
                self._set_cors()
                self.end_headers()
                err_msg = str(e).splitlines()[0][:200] if str(e) else "STT processing error"
                err_resp = json.dumps({"error": err_msg}).encode("utf-8")
                self.wfile.write(err_resp)

        elif self.path == "/tts":
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                raw_text = data.get("text", "")
                voice = data.get("voice", "M1")
                if voice not in voice_styles:
                    voice = "M1"

                # Guard against runaway raw text before regex operations
                if len(raw_text) > 8000:
                    raw_text = raw_text[:8000]

                clean_text = clean_text_for_speech(raw_text)

                # Safeguard against excessive text payloads (prevent runaway latency / memory)
                max_tts_chars = 4000
                if len(clean_text) > max_tts_chars:
                    print(f"[TTS Warning] Text exceeds {max_tts_chars} chars ({len(clean_text)} chars), truncating gracefully", flush=True)
                    clean_text = clean_text[:max_tts_chars] + "..."

                if not clean_text:
                    self.send_response(200)
                    self._set_cors("application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status": "empty_text"}')
                    return

                wav_bytes, dur, lat = synthesize_to_wav_bytes(clean_text, voice)
                if cancel_event.is_set() or not wav_bytes:
                    self.send_response(204)  # No content (cancelled)
                    self._set_cors()
                    self.end_headers()
                    return

                rtf = round(lat / dur, 2) if dur > 0 else 0.0
                with metrics_lock:
                    METRICS["tts_count"] += 1
                    METRICS["last_tts_latency_ms"] = round(lat * 1000.0, 1)
                    METRICS["last_tts_rtf"] = rtf
                print(f"[TTS] ({len(clean_text)} chars, {dur:.2f}s audio) -> generated in {lat:.3f}s (RTF {rtf})", flush=True)

                self.send_response(200)
                self._set_cors("audio/wav")
                self.send_header("Content-Length", str(len(wav_bytes)))
                self.send_header("X-Duration-Seconds", str(round(dur, 2)))
                self.send_header("X-Latency-Ms", str(round(lat * 1000.0, 1)))
                self.end_headers()
                self.wfile.write(wav_bytes)

            except Exception as e:
                print(f"[TTS Error] {e}", flush=True)
                self.send_response(500)
                self._set_cors()
                self.end_headers()
                err_msg = str(e).splitlines()[0][:200] if str(e) else "TTS synthesis error"
                err_resp = json.dumps({"error": err_msg}).encode("utf-8")
                self.wfile.write(err_resp)

        elif self.path == "/shutdown":
            self.send_response(200)
            self._set_cors()
            self.end_headers()
            self.wfile.write(b'{"status": "shutting_down"}')
            threading.Thread(target=lambda: (time.sleep(0.5), _shutdown_server()), daemon=True).start()

        else:
            self.send_response(404)
            self._set_cors()
            self.end_headers()
            self.wfile.write(b'{"error": "Not Found"}')


def run_server(port: int = 18002):
    global _httpd_ref
    init_models()
    try:
        slot_cache_manager.start_slot_restorer_daemon(1.0)
    except Exception as e:
        print(f"[Voice Bridge] Slot cache restorer warning: {e}", flush=True)
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, VoiceBridgeHandler)
    _httpd_ref = httpd
    print("\n=======================================================", flush=True)
    print(f" Voice Bridge Server RUNNING at http://127.0.0.1:{port}", flush=True)
    print(" Endpoints: /health, /stt, /tts, /stop, /shutdown, /api/slot-status, /api/restore-prefix-slot", flush=True)
    print(f" Initial RAM: {get_process_ram_mb()} MB", flush=True)
    print("=======================================================\n", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[Voice Bridge] Stopping server...", flush=True)
    finally:
        httpd.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18002
    run_server(port)
