import io
import os
import re
import shutil
import subprocess
import tempfile
import threading
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Optional

import anyio.from_thread
import soundfile as sf
import torch
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from pronunciation import for_silero, spoken_numbers

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
FFMPEG_BIN = "/usr/bin/ffmpeg"
FFMPEG_TIMEOUT = 30
# Handlers are plain functions, so FastAPI runs them in its thread pool and a slow
# request never stalls the event loop; the models themselves take one request at a time.


class Gate:
    """One request at a time on a model; a few more may wait, the rest are refused at once
    instead of piling up behind it."""

    def __init__(self, waiting: int):
        self.lock = threading.Lock()
        self.places = threading.BoundedSemaphore(waiting + 1)

    @contextmanager
    def __call__(self):
        if not self.places.acquire(blocking=False):
            raise HTTPException(status_code=503, detail="Голосовая служба занята, попробуйте ещё раз")
        try:
            with self.lock:
                yield
        finally:
            self.places.release()


# A tab asks for the part it plays and the next one; two tabs may speak at once.
tts_gate = Gate(waiting=4)
stt_gate = Gate(waiting=1)


def gone(request: Optional[Request]) -> bool:
    """The client gave up (■, a new answer, its timeout): the rest of the work would reach no one.
    Checked between parts, since a part already started cannot be interrupted."""
    if request is None:
        return False
    return anyio.from_thread.run(request.is_disconnected)


def stop_if_gone(request: Optional[Request], what: str) -> None:
    if gone(request):
        print(f"{what}: the client left, the rest is not computed", flush=True)
        raise HTTPException(status_code=499, detail="Client closed request")

# Глобальные переменные моделей
# End-to-end GigaAM: punctuation, capitals, ё and digits in the text, not a lowercase word stream.
STT_MODEL = "v3_e2e_rnnt"
stt_model = None
tts_model = None
tts_sample_rate = 48000


def get_stt_model():
    global stt_model
    if stt_model is None:
        import gigaam
        print(f"Загрузка GigaAM {STT_MODEL} на CPU...")
        stt_model = gigaam.load_model(STT_MODEL, download_root=str(MODELS_DIR), device="cpu")
        print(f"GigaAM {STT_MODEL} успешно инициализирована.")
    return stt_model


def get_tts_model():
    global tts_model
    if tts_model is None:
        model_path = MODELS_DIR / "v5_6_ru.pt"
        if not model_path.exists():
            raise RuntimeError(f"Модель Silero TTS не найдена: {model_path}")
        print(f"Загрузка Silero TTS v5.6 ({model_path.name}) на CPU...")
        importer = torch.package.PackageImporter(str(model_path))
        tts_model = importer.load_pickle("tts_models", "model")
        tts_model.to(torch.device("cpu"))
        print("Silero TTS v5.6 успешно инициализирована.")
    return tts_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Предзагрузка моделей при старте службы
    print("Инициализация голосовых моделей...")
    get_tts_model()
    get_stt_model()
    print("Все модели загружены. Голосовая служба готова к приёму запросов.")
    yield


app = FastAPI(title="OpenHands-Nexus voice service", lifespan=lifespan)

# CORS: разрешены только локальные интерфейсы, CORS "*" строго запрещен
ALLOWED_ORIGINS = [
    "http://127.0.0.1:18020",
    "http://localhost:18020",
]

# The size of OpenAI's own limit for an uploaded recording; a dictation is far smaller.
UPLOAD_MAX_BYTES = 25 * 1024 * 1024
TOO_LARGE = "Запись больше 25 МБ: так много служба не принимает"
BODY_MAX_BYTES = UPLOAD_MAX_BYTES + 64 * 1024  # the recording and its multipart framing


class LimitBody:
    """Refuses an oversized request body before it is parsed and spooled to disk: by its length
    header at once, and a body without one (chunked) by counting its bytes as they arrive. Plain
    ASGI: an @app.middleware wrapper would change what request.is_disconnected() sees."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope.get("headers") or []).get(b"content-length", b"")
        if length.isdigit() and int(length) > BODY_MAX_BYTES:
            await JSONResponse({"detail": TOO_LARGE}, status_code=413)(scope, receive, send)
            return
        seen = 0

        async def counted():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > BODY_MAX_BYTES:
                    # FastAPI passes an HTTPException from reading the body on as the answer.
                    raise HTTPException(status_code=413, detail=TOO_LARGE)
            return message

        await self.app(scope, counted, send)


app.add_middleware(LimitBody)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# The interface stops a recording at 5 minutes; 6 minutes take about a minute to recognize.
STT_MAX_AUDIO_SECONDS = 360
TOO_LONG = "Запись длиннее 6 минут: столько за один раз служба не распознаёт"


def convert_to_wav(input_path: str, output_path: str) -> None:
    """Конвертация любого браузерного формата (webm/opus, ogg, mp4/aac, wav) в 16kHz mono 16-bit PCM WAV"""
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i", input_path,
        # Decoding stops just past the limit: an hour-long recording costs no more than that.
        "-t", str(STT_MAX_AUDIO_SECONDS + 1),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        output_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=FFMPEG_TIMEOUT)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {res.stderr.decode('utf-8', errors='replace')}")



# GigaAM transcribe() takes at most 25 s; its own longform mode needs pyannote and a gated HF model.
# Long dictation is cut at the quietest 100 ms between 14 and 22 s of each remaining piece.
STT_MAX_SECONDS = 22
STT_MIN_SECONDS = 14


def split_long_wav(wav_path: str, tmpdir: str) -> list[str]:
    audio, rate = sf.read(wav_path, dtype="float32")
    if len(audio) <= STT_MAX_SECONDS * rate:
        return [wav_path]
    window = rate // 10
    paths, start = [], 0
    while len(audio) - start > STT_MAX_SECONDS * rate:
        lo, hi = start + STT_MIN_SECONDS * rate, start + STT_MAX_SECONDS * rate
        frames = audio[lo:hi][: (hi - lo) // window * window].reshape(-1, window)
        cut = lo + int((frames ** 2).mean(axis=1).argmin()) * window + window // 2
        paths.append(audio[start:cut])
        start = cut
    paths.append(audio[start:])
    out = []
    for i, piece in enumerate(paths):
        path = os.path.join(tmpdir, f"part{i}.wav")
        sf.write(path, piece, rate, subtype="PCM_16")
        out.append(path)
    return out

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "ready": (stt_model is not None and tts_model is not None),
        "service": "nexus-voice",
        "stt": f"GigaAM {STT_MODEL} (MIT)",
        "tts": "Silero TTS v5.6 ru (CC BY-NC 4.0)",
        "device": "cpu",
        "port": 18020
    }


class SpeechRequest(BaseModel):
    input: str
    model: Optional[str] = "tts-1"
    voice: Optional[str] = "xenia"
    response_format: Optional[str] = "wav"
    speed: Optional[float] = 1.0
    # Nexus extension: «Полностью» reads links, paths and hashes out instead of naming them.
    full: bool = False


# The size of OpenAI's own limit; the interface sends parts of at most 400 characters.
TTS_MAX_CHARS = 4096


# Silero reads **word** as emphasis markup and fails on any other asterisks;
# one call also fails beyond roughly 900 characters, so long text goes in parts.
TTS_CHUNK_CHARS = 700
TTS_PAUSE_SECONDS = 0.25
# Said in place of a part the model rejects: the listener learns that something went unread,
# and the rest of the answer still plays.
TTS_SKIPPED = "Этот фрагмент не озвучен, он есть на экране."


def tts_chunks(text: str, full: bool = False) -> list[str]:
    text = spoken_numbers(for_silero(text, full))
    text = text.replace("*", "")
    # A line without its own punctuation (list item, heading) still ends a phrase.
    text = re.sub(r"(?<![.!?…:;,])[ \t]*\n\s*", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    chunks: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?…;:])\s+", text):
        while len(sentence) > TTS_CHUNK_CHARS:
            cut = sentence.rfind(" ", 0, TTS_CHUNK_CHARS)
            cut = cut if cut > 0 else TTS_CHUNK_CHARS
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:cut])
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > TTS_CHUNK_CHARS:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    # Parts without letters or digits make the model fail and carry nothing to say.
    return [chunk for chunk in chunks if re.search(r"\w", chunk)]


def say(model, text: str, speaker: str):
    return model.apply_tts(text=text, speaker=speaker, sample_rate=tts_sample_rate)


def synthesize(model, chunk: str, speaker: str) -> list:
    """A part the model rejects is tried once more in two halves, in order. What still fails is
    replaced by the notice: a silently dropped part would pass for a complete answer to a
    listener who cannot compare it with the text on screen."""
    try:
        return [say(model, chunk, speaker)]
    except Exception as error:
        print(f"TTS failed on a part of {len(chunk)} characters ({type(error).__name__}), "
              "retrying in halves", flush=True)
        failure = error
    spaces = [i for i, c in enumerate(chunk) if c == " "]
    cut = min(spaces, key=lambda i: abs(i - len(chunk) // 2), default=0)
    halves = [half for half in (chunk[:cut], chunk[cut + 1:]) if cut and re.search(r"\w", half)]
    audio, skipped = [], False
    for half in halves:
        try:
            audio.append(say(model, half, speaker))
            skipped = False
            continue
        except Exception as error:
            print(f"TTS failed on a half of {len(half)} characters ({type(error).__name__})", flush=True)
            failure = error
        if not skipped:
            audio.append(None)
            skipped = True
    if not halves:
        audio = [None]
    if None in audio:
        try:
            notice = say(model, TTS_SKIPPED, speaker)
        except Exception:
            raise HTTPException(status_code=422, detail="Не удалось озвучить ответ полностью") from failure
        audio = [notice if part is None else part for part in audio]
    return audio


@app.post("/v1/audio/speech")
@app.post("/audio/speech")
def speech(req: SpeechRequest, request: Request = None):
    text = req.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty input text")
    if len(text) > TTS_MAX_CHARS:
        raise HTTPException(status_code=413, detail=f"Текст длиннее {TTS_MAX_CHARS} знаков: озвучивайте частями")

    # Допустимые голоса Silero ru: xenia, baya, aidar, kseniya, eugene
    speaker = req.voice.lower() if req.voice else "xenia"
    valid_speakers = {"xenia", "baya", "aidar", "kseniya", "eugene"}
    if speaker not in valid_speakers:
        speaker = "xenia"

    chunks = tts_chunks(text, req.full)
    if not chunks:
        raise HTTPException(status_code=400, detail="Nothing to speak in input text")

    model = get_tts_model()
    pause = torch.zeros(int(tts_sample_rate * TTS_PAUSE_SECONDS))
    parts = []
    with tts_gate(), torch.no_grad():
        for chunk in chunks:
            stop_if_gone(request, "TTS")
            if parts:
                parts.append(pause)
            parts.extend(synthesize(model, chunk, speaker))
    if not parts:
        raise HTTPException(status_code=422, detail="The voice model cannot read this text")

    audio_np = torch.cat(parts).numpy()
    response_format = (req.response_format or "wav").lower()
    speed = max(0.5, min(2.0, req.speed or 1.0))

    # Plain WAV at normal speed needs no conversion.
    if response_format != "mp3" and abs(speed - 1.0) <= 0.01:
        buffer = io.BytesIO()
        sf.write(buffer, audio_np, tts_sample_rate, subtype="PCM_16", format="WAV")
        return Response(content=buffer.getvalue(), media_type="audio/wav")

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_wav = os.path.join(tmpdir, "raw.wav")
        sf.write(raw_wav, audio_np, tts_sample_rate, subtype="PCM_16")

        target_ext = "mp3" if response_format == "mp3" else "wav"
        out_file = os.path.join(tmpdir, f"output.{target_ext}")

        ffmpeg_cmd = [FFMPEG_BIN, "-y", "-i", raw_wav]
        if abs(speed - 1.0) > 0.01:
            ffmpeg_cmd.extend(["-filter:a", f"atempo={speed:.2f}"])

        if target_ext == "mp3":
            ffmpeg_cmd.extend(["-c:a", "libmp3lame", "-q:a", "2", out_file])
            media_type = "audio/mpeg"
        else:
            ffmpeg_cmd.extend(["-c:a", "pcm_s16le", out_file])
            media_type = "audio/wav"

        res = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=FFMPEG_TIMEOUT)
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg processing failed: {res.stderr.decode('utf-8', errors='replace')}")

        with open(out_file, "rb") as f:
            audio_bytes = f.read()

    return Response(content=audio_bytes, media_type=media_type)


@app.post("/v1/audio/transcriptions")
@app.post("/audio/transcriptions")
def transcriptions(
    request: Request,
    file: UploadFile = File(...),
):
    # Поля model и Authorization из запроса Canvas не нужны: модель одна, ключа нет.
    stt = get_stt_model()

    with tempfile.TemporaryDirectory() as tmpdir:
        filename = file.filename or "upload.audio"
        suffix = Path(filename).suffix or ".bin"
        input_path = os.path.join(tmpdir, f"input{suffix}")
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        # The middleware's bound includes the multipart framing; this one is the recording's own.
        if os.path.getsize(input_path) > UPLOAD_MAX_BYTES:
            raise HTTPException(status_code=413, detail=TOO_LARGE)

        # Decoding is part of the work the gate bounds: a refused request costs no ffmpeg run.
        with stt_gate():
            wav_path = os.path.join(tmpdir, "converted.wav")
            try:
                convert_to_wav(input_path, wav_path)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Audio decoding error: {e}")

            if sf.info(wav_path).duration > STT_MAX_AUDIO_SECONDS:
                raise HTTPException(status_code=413, detail=TOO_LONG)

            texts = []
            for part_path in split_long_wav(wav_path, tmpdir):
                stop_if_gone(request, "STT")
                try:
                    transcription = stt.transcribe(part_path)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"ASR transcription error: {e}")
                texts.append(transcription.get("text", "") if isinstance(transcription, dict) else str(transcription))
        text_result = " ".join(t.strip() for t in texts if t.strip())

    return {"text": text_result}
