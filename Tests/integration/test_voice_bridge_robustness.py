"""
Rigorous Integration and Edge-Case Test Suite for Local Voice Bridge (:18002).
Adheres strictly to the workstation's Zero Simulation principle:
tests real GigaAM v3 RNN-T STT, real Supertonic 3 TTS, real audio waveforms,
edge-case handling, and route normalization.
"""

import io
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
import wave
import pytest

# Add local-voice to sys.path
VOICE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "local-voice"))
if VOICE_DIR not in sys.path:
    sys.path.insert(0, VOICE_DIR)

import service


@pytest.fixture(scope="module")
def voice_server():
    """Starts an ephemeral or verifies the live Voice Bridge server on port 18002."""
    port = 18002
    server_started = False
    httpd = None

    # Check if 18002 is already running
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                yield f"http://127.0.0.1:{port}"
                return
    except Exception:
        pass

    # Initialize models and launch server in thread on test port 18002 (or 18003 if occupied)
    service.init_models()
    try:
        httpd = service.ThreadingHTTPServer(("127.0.0.1", port), service.VoiceBridgeHandler)
    except OSError:
        port = 18003
        httpd = service.ThreadingHTTPServer(("127.0.0.1", port), service.VoiceBridgeHandler)

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    if httpd:
        httpd.shutdown()
        httpd.server_close()


class TestVoiceBridgeRobustness:
    """Rigorous tests covering real audio transcription, speech synthesis, and route robustness."""

    def test_health_endpoint_and_routing_variants(self, voice_server):
        # 1. Standard /health
        req = urllib.request.Request(f"{voice_server}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "ok"
            assert "gigaam" in data["stt_engine"].lower()
            assert "supertonic" in data["tts_engine"].lower()
            assert set(data["voices"]) >= {"M1", "F1"}
            assert data["ram_mb"] > 100

        # 2. Query param variation: /health?v=2
        req = urllib.request.Request(f"{voice_server}/health?query=probe")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200

        # 3. Proxied route variant: /voice-api/health
        req = urllib.request.Request(f"{voice_server}/voice-api/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200

    def test_real_stt_transcription(self, voice_server):
        test_dir = os.path.join(VOICE_DIR, "test-audio")
        samples = [
            ("test1.wav", "Открой папку проекта и покажи последние изменённые файлы."),
            ("test2.wav", "Проверь, подключён ли планшет по беспроводному."),
            ("test3.wav", "Создай текстовый файл, текст голосового ввода.")
        ]
        for fn, expected_text in samples:
            path = os.path.join(test_dir, fn)
            assert os.path.isfile(path), f"Sample file not found: {path}"
            with open(path, "rb") as f:
                wav_bytes = f.read()

            req = urllib.request.Request(
                f"{voice_server}/stt",
                data=wav_bytes,
                headers={"Content-Type": "audio/wav"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert "text" in data
                assert data["text"].strip() == expected_text
                assert data["latency_ms"] > 0
                assert data["audio_duration_s"] > 1.0

    def test_stt_edge_cases(self, voice_server):
        # 1. Empty body -> HTTP 400
        req = urllib.request.Request(f"{voice_server}/stt", data=b"", method="POST")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 400

        # 2. Extremely short audio (< 0.2s) -> 200 OK with empty text
        short_pcm = (b"\x00\x00" * 1600)  # 0.1s of 16kHz 16-bit silence
        out_io = io.BytesIO()
        with wave.open(out_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(short_pcm)
        short_wav = out_io.getvalue()

        req = urllib.request.Request(
            f"{voice_server}/stt",
            data=short_wav,
            headers={"Content-Type": "audio/wav"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["text"] == ""

    def test_real_tts_synthesis_m1_and_f1(self, voice_server):
        text = "Интеграция рабочей станции Nexus с Antigravity завершена успешно."
        for voice in ["M1", "F1"]:
            payload = json.dumps({"text": text, "voice": voice, "mode": "full"}).encode("utf-8")
            req = urllib.request.Request(
                f"{voice_server}/tts",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                assert resp.status == 200
                assert resp.headers.get("Content-Type") == "audio/wav"
                dur = float(resp.headers.get("X-Duration-Seconds", 0))
                lat = float(resp.headers.get("X-Latency-Ms", 0))
                wav_bytes = resp.read()
                assert len(wav_bytes) > 50000
                assert dur > 1.5
                assert lat > 0

                # Validate valid WAV structure
                with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                    assert wf.getnchannels() == 1
                    assert wf.getsampwidth() == 2
                    assert wf.getframerate() > 0
                    assert wf.getnframes() > 0

    def test_tts_text_sanitization_and_tech_terms(self):
        # Verify tech dictionary expansions
        raw = "Обновлен Docker и настроен REST API через Python и JSON в Windows."
        cleaned = service.clean_text_for_speech(raw, mode="full")
        assert "Докер" in cleaned
        assert "Апи" in cleaned
        assert "Пайтон" in cleaned
        assert "Джейсон" in cleaned
        assert "Виндовс" in cleaned

        # Verify Markdown link & code block stripping
        md_text = "# Заголовок\n```python\nprint('hello')\n```\nСсылка: [Nexus Docs](file:///docs)"
        cleaned_md = service.clean_text_for_speech(md_text, mode="full")
        assert "Код опущен" in cleaned_md
        assert "Нексус Docs" in cleaned_md
        assert "#" not in cleaned_md

    def test_tts_runaway_length_protection(self, voice_server):
        # 10,000 character payload should be safely truncated without OOM or crash
        huge_text = "Тестовая строка для проверки ограничения длины. " * 300
        payload = json.dumps({"text": huge_text, "voice": "M1", "mode": "summary"}).encode("utf-8")
        req = urllib.request.Request(
            f"{voice_server}/tts",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            assert resp.status == 200
            assert resp.headers.get("Content-Type") == "audio/wav"
            wav_bytes = resp.read()
            assert len(wav_bytes) > 1000

    def test_stop_barge_in_endpoint(self, voice_server):
        req = urllib.request.Request(f"{voice_server}/stop", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "stopped"
