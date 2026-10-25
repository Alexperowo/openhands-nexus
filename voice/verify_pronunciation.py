import argparse
import hashlib
import io
import json
import sys
from pathlib import Path


def offline(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.bind"}:
        raise RuntimeError(f"Network access forbidden during verification: {event}")


def main():
    parser = argparse.ArgumentParser(description="Offline Silero pronunciation proof; no running services")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--stt", action="store_true", help="Also transcribe with cached GigaAM v3_ctc")
    args = parser.parse_args()
    sys.addaudithook(offline)

    import soundfile as sf
    import torch
    from pronunciation import for_silero
    from service import MODELS_DIR, SpeechRequest, get_tts_model, speech

    torch.set_num_threads(2)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model = get_tts_model()
    records = {}
    for name, text in (
        ("without_word", "Я проверил работу."),
        ("raw_latin", "Я проверил OpenHands работу."),
        ("normalized", "Я проверил OpenHands работу."),
        ("terms", "OpenHands и GitHub. API и GPU. Пишем код на Python."),
    ):
        torch.manual_seed(0)
        if name in {"normalized", "terms"}:
            response = speech(SpeechRequest(input=text, voice="xenia"))
            assert response.status_code == 200
            wav_bytes = response.body
        else:
            with torch.inference_mode():
                audio = model.apply_tts(text=text, speaker="xenia", sample_rate=48000)
            buffer = io.BytesIO()
            sf.write(buffer, audio.numpy(), 48000, format="WAV", subtype="PCM_16")
            wav_bytes = buffer.getvalue()
        path = args.output_dir / f"{name}.wav"
        path.write_bytes(wav_bytes)
        audio, rate = sf.read(path)
        rms = float((audio ** 2).mean() ** 0.5)
        assert rate == 48000 and rms > 0.001, f"Invalid or silent audio: {name}"
        records[name] = {
            "input": text, "duration_seconds": len(audio) / rate,
            "synthesis_text": for_silero(text) if name in {"normalized", "terms"} else text,
            "sample_rate": rate, "rms": rms,
            "sha256": hashlib.sha256(wav_bytes).hexdigest(),
        }
        print(f"{name}: {len(audio) / rate:.3f} s, RMS {rms:.5f}", flush=True)

    duration = lambda name: records[name]["duration_seconds"]
    delta = duration("normalized") - duration("without_word")
    ratio = duration("normalized") / duration("without_word")
    assert delta > 0.5 and ratio > 1.2, f"Insufficient duration increase: {delta=}, {ratio=}"
    print(f"OpenHands adds {delta:.3f} s; duration ratio {ratio:.3f}", flush=True)

    if args.stt:
        import gigaam
        import torchaudio
        from unittest.mock import patch

        # Fail on a cache miss instead of letting the library try a download.
        def cached_file(url, path, *args, **kwargs):
            if not Path(path).is_file():
                raise RuntimeError(f"Required local GigaAM file missing: {path}")
            return path

        with patch("gigaam._download_file", side_effect=cached_file):
            stt = gigaam.load_model("v3_ctc", download_root=str(MODELS_DIR), device="cpu")
        for name in records:
            audio, rate = sf.read(args.output_dir / f"{name}.wav", dtype="float32")
            audio = torchaudio.functional.resample(torch.from_numpy(audio), rate, 16000)
            path = args.output_dir / "stt_input.wav"
            try:
                sf.write(path, audio.numpy(), 16000, subtype="PCM_16")
                text = stt.transcribe(str(path)).text
            finally:
                path.unlink(missing_ok=True)
            records[name]["gigaam"] = text
            print(f"GigaAM {name}: {text}", flush=True)

    result = {"network": "forbidden by Python audit hook", "voice": "xenia",
              "duration_delta_seconds": delta, "duration_ratio": ratio, "audio": records}
    (args.output_dir / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
