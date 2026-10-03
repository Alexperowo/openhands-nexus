"""
Antigravity Voice Companion
Push-to-Talk (PTT) and Voice Read-Aloud Bridge for Google Antigravity & Windows Host.

Integrates with Local Voice Bridge on port 18002:
- STT: FUTO GigaAM v3 RNN-T (offline, 16kHz mono)
- TTS: Supertonic 3 (Russian ONNX)

Key Features:
- Push-to-Talk via Global Hotkey (Default: F9, Hold or Toggle mode)
- Read Aloud Last Response / Selection via Global Hotkey (Default: F10, Toggle / Stop mode)
- Instant Speech Interrupt via Esc or F10
- Direct text injection into active Antigravity editor/prompt via Windows SendInput / Clipboard
- Smart markdown and code block filtering for natural Russian speech
- Audio feedback beeps (start/stop)
- Zero external GUI bloat, 100% stock Antigravity compatibility (clean sidecar)
"""

import argparse
import ctypes
import glob
import io
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.request
import urllib.error
import wave
import winsound
from typing import Optional

try:
    import numpy as np
    import sounddevice as sd
except ImportError as e:
    print(f"[FATAL] Missing required audio package: {e}")
    print("Run: python -m pip install sounddevice numpy")
    sys.exit(1)

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "Logs", "Voice")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "voice-companion.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("voice-companion")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "companion_config.json")
DEFAULT_CONFIG = {
    "voice_bridge_url": "http://127.0.0.1:18002",
    "hotkey": "F9",          # STT Push-to-Talk hotkey
    "read_hotkey": "F10",    # TTS Read Aloud hotkey
    "mode": "toggle",        # "hold" (press and hold) or "toggle" (press once to start, press again to stop)
    "audio_feedback": True,  # Beep on record/read start/stop
    "auto_paste": True,      # Paste text into focused window
    "sample_rate": 16000,
    "input_device": None,    # None = system default
    "voice": "M1",           # Default TTS voice ("M1" or "F1")
    "max_read_chars": 1800   # Max characters to synthesize for speech
}

VK_MAP = {
    "F9": 0x78,
    "F8": 0x77,
    "F10": 0x79,
    "F11": 0x7A,
    "F12": 0x7B,
    "SCROLL_LOCK": 0x91,
    "NUMPAD0": 0x60,
    "RCONTROL": 0xA3,
    "PAUSE": 0x13
}

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Explicit 64-bit ABI ctypes declarations
user32.OpenClipboard.restype = ctypes.c_int
user32.OpenClipboard.argtypes = [ctypes.c_void_p]

user32.CloseClipboard.restype = ctypes.c_int
user32.CloseClipboard.argtypes = []

user32.EmptyClipboard.restype = ctypes.c_int
user32.EmptyClipboard.argtypes = []

user32.GetClipboardData.restype = ctypes.c_void_p
user32.GetClipboardData.argtypes = [ctypes.c_uint]

user32.SetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]

user32.keybd_event.restype = None
user32.keybd_event.argtypes = [ctypes.c_byte, ctypes.c_byte, ctypes.c_ulong, ctypes.c_size_t]

user32.RegisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
user32.RegisterHotKey.restype = ctypes.c_bool

user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.UnregisterHotKey.restype = ctypes.c_bool

kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]

kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]

kernel32.GlobalUnlock.restype = ctypes.c_int
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]


def load_config() -> dict:
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                merged = dict(DEFAULT_CONFIG)
                merged.update(cfg)
                return merged
        except Exception as e:
            logger.warning("Failed to load %s (%s), using defaults", CONFIG_PATH, e)
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to save config: %s", e)


def is_key_down(vk_code: int) -> bool:
    """Returns True if the specified virtual key is currently pressed."""
    return bool(user32.GetAsyncKeyState(vk_code) & 0x8000)


def send_paste_command():
    """Simulates Ctrl+V using Windows keybd_event to paste text into the active window."""
    VK_CONTROL = 0x11
    VK_V = 0x56
    KEYEVENTF_KEYUP = 0x0002

    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def get_clipboard_text() -> Optional[str]:
    """Retrieves current Unicode text from Windows clipboard if available."""
    CF_UNICODETEXT = 13
    if not user32.OpenClipboard(0):
        return None
    try:
        h_mem = user32.GetClipboardData(CF_UNICODETEXT)
        if not h_mem:
            return None
        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            return None
        try:
            val = ctypes.wstring_at(p_mem)
            return val
        finally:
            kernel32.GlobalUnlock(h_mem)
    except Exception:
        return None
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str) -> bool:
    """Sets Unicode text into Windows clipboard."""
    GMEM_MOVEABLE = 0x0002
    CF_UNICODETEXT = 13

    if not user32.OpenClipboard(0):
        return False
    try:
        user32.EmptyClipboard()
        encoded = text.encode("utf-16le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            return False
        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            return False
        ctypes.memmove(p_mem, encoded, len(encoded))
        kernel32.GlobalUnlock(h_mem)
        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        return True
    finally:
        user32.CloseClipboard()


CLIPBOARD_PROPAGATION_SEC = 0.04
PASTE_SETTLE_SEC = 0.08


def paste_text_safely(text: str) -> bool:
    """
    Safely pastes text into active window preserving the user's previous clipboard content.
    """
    old_clip = get_clipboard_text()
    try:
        if not set_clipboard_text(text):
            return False
        time.sleep(CLIPBOARD_PROPAGATION_SEC)
        send_paste_command()
        time.sleep(PASTE_SETTLE_SEC)
        return True
    finally:
        if old_clip is not None:
            try:
                set_clipboard_text(old_clip)
            except Exception:
                pass


def get_selected_text_quick() -> Optional[str]:
    """
    Attempts to copy currently highlighted text in active window via Ctrl+C.
    Preserves and restores previous clipboard contents.
    Returns None if no text was highlighted.
    """
    old_clip = get_clipboard_text()
    VK_CONTROL = 0x11
    VK_C = 0x43
    KEYEVENTF_KEYUP = 0x0002

    if not set_clipboard_text(""):
        return None

    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_C, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)

    sel = get_clipboard_text()

    if old_clip is not None:
        try:
            set_clipboard_text(old_clip)
        except Exception:
            pass

    if sel and sel.strip():
        return sel.strip()
    return None


def get_latest_assistant_response() -> Optional[str]:
    """
    Finds the most recent conversation transcript in Antigravity brain directory
    and returns the latest assistant (MODEL / PLANNER_RESPONSE) text content.
    """
    brain_dir = os.path.expanduser("~/.gemini/antigravity-ide/brain")
    if not os.path.isdir(brain_dir):
        return None
    transcripts = glob.glob(os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript.jsonl"))
    if not transcripts:
        return None
    transcripts.sort(key=os.path.getmtime, reverse=True)
    latest_transcript = transcripts[0]

    last_content = None
    try:
        with open(latest_transcript, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("source") == "MODEL" and obj.get("type") == "PLANNER_RESPONSE":
                        content = obj.get("content")
                        if content and content.strip():
                            last_content = content
                except Exception:
                    pass
    except Exception as e:
        logger.warning("Error reading transcript %s: %s", latest_transcript, e)
    return last_content


def sanitize_markdown_for_speech(text: str, max_chars: int = 1800) -> str:
    """
    Cleans markdown formatting, links, code blocks, and symbols for natural Russian speech synthesis.
    """
    if not text:
        return ""

    # Remove thinking tags if present
    text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL)

    # Strip multi-line code blocks
    text = re.sub(r'```[\s\S]*?```', ' (блок кода) ', text)
    # Strip inline code
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Strip markdown links: [Text](url) -> Text
    text = re.sub(r'\[(.*?)\]\([^)]+\)', r'\1', text)

    # Strip image tags: ![Alt](url)
    text = re.sub(r'!\[.*?\]\([^)]+\)', '', text)

    # Strip HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Strip markdown headers (#, ##, ###)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Strip bold / italics
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)

    # Strip list markers and blockquotes
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*>\s+', '', text, flags=re.MULTILINE)

    # Strip table markup
    text = re.sub(r'\|[^\n]+\|', '', text)

    # Normalize whitespace
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    cleaned = " ".join(lines)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    if len(cleaned) > max_chars:
        cutoff = cleaned[:max_chars].rfind('.')
        if cutoff > 300:
            cleaned = cleaned[:cutoff + 1] + " (текст сокращён для озвучивания)"
        else:
            cleaned = cleaned[:max_chars] + "..."

    return cleaned


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, device: int | None = None, max_seconds: int = 120):
        self.sample_rate = sample_rate
        self.device = device
        self.max_seconds = max_seconds
        self.max_samples = max_seconds * sample_rate
        self.frames = []
        self.stream = None
        self.is_recording = False
        self._lock = threading.Lock()

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.debug("Audio status: %s", status)
        if self.is_recording:
            with self._lock:
                current_samples = sum(len(f) for f in self.frames)
                if current_samples < self.max_samples:
                    self.frames.append(indata.copy())

    def start(self):
        with self._lock:
            self.frames = []
            self.is_recording = True

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            device=self.device,
            callback=self._audio_callback
        )
        self.stream.start()

    def stop(self) -> bytes:
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        with self._lock:
            if not self.frames:
                return b""
            all_pcm = np.concatenate(self.frames, axis=0)

        out_io = io.BytesIO()
        with wave.open(out_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(all_pcm.tobytes())

        return out_io.getvalue()


class VoiceCompanion:
    def __init__(self, config: dict):
        self.config = config
        self.bridge_url = config.get("voice_bridge_url", "http://127.0.0.1:18002").rstrip("/")
        self.hotkey_name = config.get("hotkey", "F9").upper()
        self.vk_code = VK_MAP.get(self.hotkey_name, 0x78)
        self.read_hotkey_name = config.get("read_hotkey", "F10").upper()
        self.read_vk_code = VK_MAP.get(self.read_hotkey_name, 0x79)
        self.mode = config.get("mode", "toggle").lower()
        self.audio_feedback = config.get("audio_feedback", True)
        self.auto_paste = config.get("auto_paste", True)
        self.voice = config.get("voice", "M1")
        self.max_read_chars = config.get("max_read_chars", 1800)
        self.recorder = AudioRecorder(sample_rate=config.get("sample_rate", 16000),
                                     device=config.get("input_device"))
        self.running = False
        self.state_recording = False
        self.is_speaking = False
        self._tts_thread = None

    def beep_start(self):
        if self.audio_feedback:
            threading.Thread(target=lambda: winsound.Beep(900, 100), daemon=True).start()

    def beep_stop(self):
        if self.audio_feedback:
            threading.Thread(target=lambda: winsound.Beep(600, 120), daemon=True).start()

    def send_stt_request(self, wav_bytes: bytes) -> dict:
        url = f"{self.bridge_url}/stt"
        req = urllib.request.Request(
            url,
            data=wav_bytes,
            headers={"Content-Type": "audio/wav"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error("STT request failed: %s", e)
        return {"text": "", "error": "STT request failed"}

    def stop_speaking(self):
        """Immediately interrupts ongoing speech playback."""
        if self.is_speaking:
            self.is_speaking = False
            try:
                sd.stop()
            except Exception:
                pass
            if self.audio_feedback:
                threading.Thread(target=lambda: winsound.Beep(500, 80), daemon=True).start()
            logger.info("Speech playback stopped by user.")

    def speak(self, text: str, voice: str = "M1"):
        """Requests TTS synthesis and plays the resulting audio waveform (blocking)."""
        url = f"{self.bridge_url}/tts"
        payload = json.dumps({"text": text, "voice": voice, "mode": "summary"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status == 200:
                    wav_bytes = resp.read()
                    with io.BytesIO(wav_bytes) as bio, wave.open(bio, "rb") as wf:
                        data = wf.readframes(wf.getnframes())
                        sr = wf.getframerate()
                        arr = np.frombuffer(data, dtype=np.int16)
                        sd.play(arr, sr)
                        sd.wait()
        except Exception as e:
            logger.error("TTS playback error: %s", e)

    def speak_async(self, text: str, voice: str = "M1"):
        """Synthesizes and plays text asynchronously with interruptibility."""
        if self.is_speaking:
            self.stop_speaking()
            return

        def _worker():
            self.is_speaking = True
            logger.info("Synthesizing speech for %d characters...", len(text))
            url = f"{self.bridge_url}/tts"
            payload = json.dumps({"text": text, "voice": voice, "mode": "summary"}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    if resp.status == 200:
                        wav_bytes = resp.read()
                        with io.BytesIO(wav_bytes) as bio, wave.open(bio, "rb") as wf:
                            data = wf.readframes(wf.getnframes())
                            sr = wf.getframerate()
                            arr = np.frombuffer(data, dtype=np.int16)
                            if not self.is_speaking:
                                return
                            sd.play(arr, sr)
                            while self.is_speaking and sd.get_stream().active:
                                time.sleep(0.04)
            except Exception as e:
                logger.error("TTS synthesis/playback error: %s", e)
            finally:
                self.is_speaking = False

        if self.audio_feedback:
            threading.Thread(target=lambda: winsound.Beep(1100, 80), daemon=True).start()
        self._tts_thread = threading.Thread(target=_worker, daemon=True)
        self._tts_thread.start()

    def trigger_read_aloud(self):
        """Finds selection or latest assistant response, cleans it, and reads aloud."""
        text = get_selected_text_quick()
        source = "selection"
        if not text:
            text = get_latest_assistant_response()
            source = "last_assistant_response"

        if not text:
            logger.warning("No text found to read aloud.")
            if self.audio_feedback:
                threading.Thread(target=lambda: winsound.Beep(400, 150), daemon=True).start()
            return

        clean = sanitize_markdown_for_speech(text, max_chars=self.max_read_chars)
        if not clean:
            logger.warning("Sanitized text is empty.")
            return

        logger.info("Read-aloud from %s (%d chars clean): %s...", source, len(clean), clean[:60])
        self.speak_async(clean, voice=self.voice)

    def process_recording(self, wav_bytes: bytes):
        if not wav_bytes or len(wav_bytes) < 4000:
            logger.info("Recording too short or empty, discarded.")
            return

        logger.info("Transcribing audio payload (%d bytes)...", len(wav_bytes))
        t0 = time.perf_counter()
        result = self.send_stt_request(wav_bytes)
        lat = round((time.perf_counter() - t0) * 1000.0, 1)

        text = result.get("text", "").strip()
        if not text:
            logger.info("No speech detected.")
            return

        logger.info("[RECOGNIZED in %d ms] Transcribed %d characters", lat, len(text))
        logger.debug("[RECOGNIZED TEXT] %s", text)

        if self.auto_paste:
            if paste_text_safely(text):
                logger.info("Safely pasted recognized text into active window (clipboard preserved).")
            else:
                logger.warning("Failed to safely paste recognized text.")

    def handle_ptt_toggle(self):
        if not self.state_recording:
            logger.info("PTT [TOGGLE] Start recording...")
            self.beep_start()
            self.recorder.start()
            self.state_recording = True
        else:
            logger.info("PTT [TOGGLE] Stop recording...")
            self.beep_stop()
            wav = self.recorder.stop()
            self.state_recording = False
            threading.Thread(target=self.process_recording, args=(wav,), daemon=True).start()

    def run(self):
        self.running = True
        logger.info("==================================================")
        logger.info(" Antigravity Voice Companion ACTIVE (Win32 RegisterHotKey)")
        logger.info(" Target Voice Bridge: %s", self.bridge_url)
        logger.info(" PTT Hotkey (Mic): %s (ID: 1)", self.hotkey_name)
        logger.info(" Read Aloud Hotkeys: %s and F8 (Stop: Esc / Shift+%s)", self.read_hotkey_name, self.read_hotkey_name)
        logger.info(" TTS Voice: %s | Max Chars: %d", self.voice, self.max_read_chars)
        logger.info(" Audio Feedback: %s | Auto-Paste: %s", self.audio_feedback, self.auto_paste)
        logger.info("==================================================")

        from ctypes import wintypes
        HOTKEY_ID_PTT = 1
        HOTKEY_ID_READ_F10 = 2
        HOTKEY_ID_READ_F8 = 3
        HOTKEY_ID_READ_CTRL_SHIFT_S = 4
        HOTKEY_ID_READ_CTRL_F10 = 5
        HOTKEY_ID_READ_PAUSE = 6
        HOTKEY_ID_STOP = 7

        MOD_NOREPEAT = 0x4000
        MOD_SHIFT = 0x0004
        MOD_CONTROL = 0x0002
        MOD_ALT = 0x0001

        # Register system-wide global hotkeys with the OS
        ok_ptt = user32.RegisterHotKey(None, HOTKEY_ID_PTT, MOD_NOREPEAT, self.vk_code)
        ok_f10 = user32.RegisterHotKey(None, HOTKEY_ID_READ_F10, MOD_NOREPEAT, self.read_vk_code)
        ok_f8 = user32.RegisterHotKey(None, HOTKEY_ID_READ_F8, MOD_NOREPEAT, 0x77)  # F8
        ok_css = user32.RegisterHotKey(None, HOTKEY_ID_READ_CTRL_SHIFT_S, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x53)  # Ctrl+Shift+S
        ok_cf10 = user32.RegisterHotKey(None, HOTKEY_ID_READ_CTRL_F10, MOD_CONTROL | MOD_NOREPEAT, self.read_vk_code)  # Ctrl+F10
        ok_pause = user32.RegisterHotKey(None, HOTKEY_ID_READ_PAUSE, MOD_NOREPEAT, 0x13)  # Pause/Break
        ok_stop = user32.RegisterHotKey(None, HOTKEY_ID_STOP, MOD_SHIFT | MOD_NOREPEAT, self.read_vk_code) # Shift+F10

        logger.info("Registered Hotkeys -> PTT(%s): %s | Read(Ctrl+Shift+S): %s | Read(Ctrl+F10): %s | Read(F8): %s | Read(Pause): %s | Read(F10): %s",
                    self.hotkey_name, ok_ptt, ok_css, ok_cf10, ok_f8, ok_pause, ok_f10)

        msg = wintypes.MSG()
        try:
            # Native OS Message Loop: 0% CPU, zero delay, never misses key presses
            while self.running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == 0x0312:  # WM_HOTKEY
                    hotkey_id = msg.wParam
                    if hotkey_id in (HOTKEY_ID_READ_F10, HOTKEY_ID_READ_F8, HOTKEY_ID_READ_CTRL_SHIFT_S, HOTKEY_ID_READ_CTRL_F10, HOTKEY_ID_READ_PAUSE):
                        logger.info("[HOTKEY EVENT] Read Aloud key pressed (ID %d)!", hotkey_id)
                        if self.is_speaking:
                            self.stop_speaking()
                        else:
                            threading.Thread(target=self.trigger_read_aloud, daemon=True).start()

                    elif hotkey_id == HOTKEY_ID_STOP:
                        logger.info("[HOTKEY EVENT] Stop / Mute pressed!")
                        self.stop_speaking()

                    elif hotkey_id == HOTKEY_ID_PTT:
                        logger.info("[HOTKEY EVENT] PTT (Mic) pressed!")
                        if self.is_speaking:
                            self.stop_speaking()
                        self.handle_ptt_toggle()

                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        except KeyboardInterrupt:
            logger.info("Voice Companion shutting down...")
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID_PTT)
            user32.UnregisterHotKey(None, HOTKEY_ID_READ_F10)
            user32.UnregisterHotKey(None, HOTKEY_ID_READ_F8)
            user32.UnregisterHotKey(None, HOTKEY_ID_READ_CTRL_SHIFT_S)
            user32.UnregisterHotKey(None, HOTKEY_ID_READ_CTRL_F10)
            user32.UnregisterHotKey(None, HOTKEY_ID_READ_PAUSE)
            user32.UnregisterHotKey(None, HOTKEY_ID_STOP)
            if self.state_recording:
                self.recorder.stop()
            if self.is_speaking:
                self.stop_speaking()
            self.running = False


def check_bridge_health(url: str) -> bool:
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Antigravity Voice Companion")
    parser.add_argument("--test-stt", action="store_true", help="Send a test wav to STT endpoint and print output")
    parser.add_argument("--test-tts", type=str, help="Synthesize and play Russian text via TTS")
    parser.add_argument("--test-read-last", action="store_true", help="Read aloud latest assistant response")
    parser.add_argument("--mode", choices=["hold", "toggle"], help="Set PTT mode")
    parser.add_argument("--hotkey", type=str, help="Set PTT hotkey (F9, F8, SCROLL_LOCK, etc.)")
    parser.add_argument("--read-hotkey", type=str, help="Set Read Aloud hotkey (F10, F11, etc.)")
    parser.add_argument("--voice", choices=["M1", "F1"], help="Set TTS voice")
    args = parser.parse_args()

    cfg = load_config()
    if args.mode:
        cfg["mode"] = args.mode
    if args.hotkey:
        cfg["hotkey"] = args.hotkey
    if args.read_hotkey:
        cfg["read_hotkey"] = args.read_hotkey
    if args.voice:
        cfg["voice"] = args.voice
    save_config(cfg)

    bridge_url = cfg.get("voice_bridge_url", "http://127.0.0.1:18002")
    if not check_bridge_health(bridge_url):
        logger.error("Voice Bridge at %s is unreachable! Please start local-voice first.", bridge_url)
        sys.exit(1)

    companion = VoiceCompanion(cfg)

    if args.test_stt:
        test_wav = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "local-voice", "test-audio", "test1.wav"))
        if os.path.isfile(test_wav):
            with open(test_wav, "rb") as f:
                res = companion.send_stt_request(f.read())
            print(f"Test STT Result: {res}")
        else:
            print("test1.wav not found")
        return

    if args.test_tts:
        companion.speak(args.test_tts, voice=cfg.get("voice", "M1"))
        return

    if args.test_read_last:
        raw = get_latest_assistant_response()
        clean = sanitize_markdown_for_speech(raw, max_chars=cfg.get("max_read_chars", 1800))
        print(f"Reading last response ({len(clean)} chars): {clean[:120]}...")
        companion.speak(clean, voice=cfg.get("voice", "M1"))
        return

    companion.run()


if __name__ == "__main__":
    main()
