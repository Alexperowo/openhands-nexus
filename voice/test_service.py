"""Voice service behaviour through its real ASGI app; the models are replaced, ffmpeg is real."""
import io
import json
import threading
import unittest
from unittest.mock import patch

import anyio
import numpy as np
import soundfile as sf
import torch
from fastapi import HTTPException

import service
from service import TTS_SKIPPED, SpeechRequest, speech


def call(path, body, content_type, headers=(), leave_after=None):
    """One HTTP request into the app. The client leaves (http.disconnect) once leave_after() is true."""
    messages = [{"type": "http.request", "body": body, "more_body": False}]
    sent = []

    async def receive():
        if messages:
            return messages.pop(0)
        while not (leave_after and leave_after()):
            await anyio.sleep(0.01)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
             "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
             "headers": [(b"content-type", content_type.encode()),
                         (b"content-length", str(len(body)).encode()), *headers],
             "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 18020)}
    anyio.run(service.app, scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


def say(text, **fields):
    return call("/v1/audio/speech", json.dumps({"input": text, **fields}).encode(), "application/json")


def upload(audio, rate=16000, leave_after=None):
    buffer = io.BytesIO()
    sf.write(buffer, audio, rate, subtype="PCM_16", format="WAV")
    boundary = "nexus-test-boundary"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"dictation.wav\"\r\n"
            "Content-Type: audio/wav\r\n\r\n").encode() + buffer.getvalue() + f"\r\n--{boundary}--\r\n".encode()
    return call("/v1/audio/transcriptions", body, f"multipart/form-data; boundary={boundary}", leave_after=leave_after)


def speech_audio(seconds, rate=16000):
    # Noise with a quiet gap every 10 s, so long recordings are cut where they would be in speech.
    audio = np.random.default_rng(1).uniform(-0.3, 0.3, int(seconds * rate)).astype("float32")
    for start in range(10 * rate, len(audio), 10 * rate):
        audio[start:start + rate // 5] = 0
    return audio


class SpeechTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("service.get_tts_model")
        self.model = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.model.apply_tts.side_effect = lambda **_: torch.zeros(480)

    def spoken(self):
        return [call.kwargs["text"] for call in self.model.apply_tts.call_args_list]

    def test_normalized_text_and_full_reading_reach_the_model(self):
        self.assertEqual(say("OpenHands и GitHub через API.")[0], 200)
        self.assertEqual(self.spoken(), ["Оупен Хэндс и Гитхаб через эй-пи-ай."])
        self.model.apply_tts.reset_mock()
        self.assertEqual(say("Файл /tmp/a.py", full=True)[0], 200)
        self.assertEqual(self.spoken(), ["Файл слэш тмп слэш эй точка пай"])

    def test_failed_part_is_retried_in_halves_and_only_the_unread_half_is_named(self):
        failing = {"Важное предупреждение, его надо услышать.", "его надо услышать."}

        def apply(text, **_):
            if text in failing:
                raise RuntimeError("failed")
            return torch.zeros(480)
        self.model.apply_tts.side_effect = apply
        with patch("service.tts_chunks", return_value=["Первое.", "Важное предупреждение, его надо услышать.", "Конец."]):
            self.assertEqual(say("Проверка полного ответа.")[0], 200)
        self.assertEqual(self.spoken(), ["Первое.", "Важное предупреждение, его надо услышать.",
                                         "Важное предупреждение,", "его надо услышать.", TTS_SKIPPED, "Конец."])
        # A part that reads fine in halves needs no notice.
        failing = {"Важное предупреждение, его надо услышать."}
        self.model.apply_tts.reset_mock()
        with patch("service.tts_chunks", return_value=["Важное предупреждение, его надо услышать."]):
            self.assertEqual(say("Проверка.")[0], 200)
        self.assertNotIn(TTS_SKIPPED, self.spoken())

    def test_unreadable_part_without_notice_is_an_error_not_a_shorter_answer(self):
        self.model.apply_tts.side_effect = RuntimeError("failed")
        with patch("service.tts_chunks", return_value=["Первое."]), self.assertRaises(HTTPException) as caught:
            speech(SpeechRequest(input="Проверка."))
        self.assertEqual(caught.exception.status_code, 422)

    def test_limits(self):
        self.assertEqual(say("а" * (service.TTS_MAX_CHARS + 1))[0], 413)
        status, body = call("/v1/audio/transcriptions", b"x", "multipart/form-data; boundary=x",
                            headers=[(b"content-length", str(30 * 1024 * 1024).encode())])
        self.assertEqual(status, 413)
        self.assertIn("25 МБ", json.loads(body)["detail"])
        self.model.apply_tts.assert_not_called()

    def test_client_that_left_stops_the_remaining_parts(self):
        chunks = ["Первая часть.", "Вторая часть.", "Третья часть."]
        with patch("service.tts_chunks", return_value=chunks):
            status, _ = call("/v1/audio/speech", json.dumps({"input": "Длинный ответ."}).encode(), "application/json",
                             leave_after=lambda: self.model.apply_tts.call_count >= 1)
        self.assertEqual(status, 499)
        self.assertEqual(self.spoken(), ["Первая часть."])

    def test_busy_model_takes_a_few_waiting_requests_and_refuses_the_rest(self):
        gate = service.Gate(waiting=1)
        release, inside = threading.Event(), threading.Event()

        def hold():
            with gate():
                inside.set()
                release.wait(5)
        first = threading.Thread(target=hold)
        first.start()
        inside.wait(5)
        second = threading.Thread(target=hold)
        second.start()
        for _ in range(100):
            if gate.places._value == 0:
                break
            threading.Event().wait(0.01)
        with self.assertRaises(HTTPException) as caught, gate():
            pass
        self.assertEqual(caught.exception.status_code, 503)
        release.set()
        first.join(5)
        second.join(5)
        with gate():
            pass


class TranscriptionTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("service.get_stt_model")
        self.model = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.parts = []
        self.model.transcribe.side_effect = lambda path: self.parts.append(sf.info(path).duration) or f"часть {len(self.parts)}"

    def test_long_dictation_is_read_in_parts_in_order(self):
        status, body = upload(speech_audio(50))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["text"], "часть 1 часть 2 часть 3")
        self.assertAlmostEqual(sum(self.parts), 50, delta=0.1)
        self.assertTrue(all(part <= service.STT_MAX_SECONDS for part in self.parts))

    def test_recording_over_the_limit_is_refused_before_recognition(self):
        status, body = upload(np.zeros((service.STT_MAX_AUDIO_SECONDS + 5) * 16000, dtype="float32"))
        self.assertEqual(status, 413)
        self.assertIn("6 минут", json.loads(body)["detail"])
        self.model.transcribe.assert_not_called()

    def test_client_that_left_stops_recognition_between_parts(self):
        status, _ = upload(speech_audio(70), leave_after=lambda: len(self.parts) >= 1)
        self.assertEqual(status, 499)
        self.assertEqual(len(self.parts), 1)


if __name__ == "__main__":
    unittest.main()
