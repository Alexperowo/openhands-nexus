"""
Local Voice Bridge Service for OpenHands Local
Port: 127.0.0.1:18002

Integrates:
- STT: FUTO Keyboard GigaAM v3 e2e-RNN-T (GGML/transcribe.cpp, 261 MB, in-memory)
- TTS: Supertonic 3 Russian ONNX (Supertone, 99M, in-memory)
Zero cloud dependencies. 100% offline.
"""

import os
import sys
import io
import time
import json
import wave
import re
import threading
import subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
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

# Setup paths for transcribe_cpp
PYTHONPATH_TRANSCRIBE = r"D:\Project\futo-keyboard-gigaam\third_party\transcribe.cpp\bindings\python\src"
TRANSCRIBE_DLL = r"K:\Project\transcribe-build-shared\bin\Release\transcribe.dll"
GIGAAM_MODEL_PATH = r"D:\Project\futo-keyboard-gigaam\voiceinput-shared\models\cache\assets\voice-models\gigaam-v3-e2e-rnnt-Q8_0.gguf"
SUPERTONIC_DIR = r"D:\AI\Models\Speech\supertonic"

os.environ["PYTHONPATH"] = PYTHONPATH_TRANSCRIBE
os.environ["TRANSCRIBE_LIBRARY"] = TRANSCRIBE_DLL
if PYTHONPATH_TRANSCRIBE not in sys.path:
    sys.path.insert(0, PYTHONPATH_TRANSCRIBE)

import transcribe_cpp
import av
from supertonic import TTS
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Config"))
import working_profiles

# Global state
START_TIME = time.time()
stt_model = None
tts_model = None
voice_styles = {}
stt_lock = threading.Lock()
tts_lock = threading.Lock()
cancel_event = threading.Event()

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
    METRICS["stt_load_time_s"] = round(time.perf_counter() - t0, 3)
    print(f"[Voice Bridge] GigaAM v3 STT loaded in {METRICS['stt_load_time_s']} s", flush=True)

    print("[Voice Bridge] Loading Supertonic 3 TTS into memory...", flush=True)
    t1 = time.perf_counter()
    tts_model = TTS(model="supertonic-3", model_dir=SUPERTONIC_DIR, auto_download=False)
    voice_styles["M1"] = tts_model.get_voice_style("M1")
    voice_styles["F1"] = tts_model.get_voice_style("F1")
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
    
    out_io = io.BytesIO()
    with wave.open(out_io, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(pcm_int16.tobytes())
        
    return out_io.getvalue(), duration, latency


class VoiceBridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Concise logging
        print(f"[HTTP] {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}", flush=True)

    def _set_cors(self, content_type="application/json"):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range, Authorization, X-Session-API-Key")
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
            self.end_headers()
            self.wfile.write(body)
            return

        elif clean_path == "/working-profile-ui.js":
            js_path = r"K:\Project\openhands-working-profile\working-profile-ui.js"
            with open(js_path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self._set_cors("application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(body)
            return

        elif clean_path == "/working-profile-ui.css":
            css_path = r"K:\Project\openhands-working-profile\working-profile-ui.css"
            with open(css_path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self._set_cors("text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache, must-revalidate")
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

        elif self.path in ("/health", "/status"):
            ram = get_process_ram_mb()
            resp = {
                "status": "ok",
                "uptime_s": round(time.time() - START_TIME, 1),
                "stt_engine": "gigaam-v3-e2e-rnnt (FUTO transcribe.cpp)",
                "tts_engine": "supertonic-3 (Supertone ONNX)",
                "voices": list(voice_styles.keys()),
                "ram_mb": ram,
                "metrics": METRICS
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
        content_length = int(self.headers.get("Content-Length", 0))
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
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
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

                with stt_lock:
                    with stt_model.session() as session:
                        result = session.run(pcm)
                        text = result.text.strip()

                latency = round((time.perf_counter() - t0) * 1000.0, 1)
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
                err_resp = json.dumps({"error": str(e)}).encode("utf-8")
                self.wfile.write(err_resp)

        elif self.path == "/tts":
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                raw_text = data.get("text", "")
                voice = data.get("voice", "M1")
                clean_text = clean_text_for_speech(raw_text)

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
                err_resp = json.dumps({"error": str(e)}).encode("utf-8")
                self.wfile.write(err_resp)

        elif self.path == "/shutdown":
            self.send_response(200)
            self._set_cors()
            self.end_headers()
            self.wfile.write(b'{"status": "shutting_down"}')
            threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0))).start()

        else:
            self.send_response(404)
            self._set_cors()
            self.end_headers()
            self.wfile.write(b'{"error": "Not Found"}')


def run_server(port: int = 18002):
    init_models()
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, VoiceBridgeHandler)
    print(f"\n=======================================================", flush=True)
    print(f" Voice Bridge Server RUNNING at http://127.0.0.1:{port}", flush=True)
    print(f" Endpoints: /health, /stt, /tts, /stop, /shutdown", flush=True)
    print(f" Initial RAM: {get_process_ram_mb()} MB", flush=True)
    print(f"=======================================================\n", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[Voice Bridge] Stopping server...", flush=True)
    finally:
        httpd.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18002
    run_server(port)