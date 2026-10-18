"""Gemini text-to-speech with a disk cache. One clip per caption line, so captions line up exactly.

    uv run --project ../backend python tts.py            # generate every clip in script.py

Clips are 24 kHz mono WAV under demo/.cache/tts/, keyed by (model, voice, text). The trailing silence
the model adds is trimmed, so the recorder can pace each line by its real length.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import time
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache" / "tts"
MODEL = "gemini-3.8-flash-tts"
RATE = 24000


def _client():
    sys.path.insert(0, str(HERE.parent / "backend" / "src"))
    from google import genai

    from relay.config import settings
    return genai.Client(api_key=settings().gemini_api_key)


def _key(voice: str, text: str) -> str:
    return hashlib.sha256(f"{MODEL}|{voice}|{text}".encode()).hexdigest()[:20]


def _pcm(data: bytes) -> bytes:
    """Raw 16-bit PCM from a WAV (or raw PCM) response."""
    if data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data)) as w:
            assert w.getframerate() == RATE and w.getnchannels() == 1 and w.getsampwidth() == 2
            return w.readframes(w.getnframes())
    return data


def _trim(pcm: bytes, threshold: int = 300, keep_ms: int = 60) -> bytes:
    """Drop leading and trailing near-silence, keeping a few milliseconds of room."""
    import array
    a = array.array("h", pcm)
    n = len(a)
    start = next((i for i in range(n) if abs(a[i]) > threshold), 0)
    end = next((i for i in range(n - 1, -1, -1) if abs(a[i]) > threshold), n - 1)
    pad = RATE * keep_ms // 1000
    return a[max(0, start - pad): min(n, end + pad)].tobytes()


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)


def clip(text: str, voice: str, client=None) -> tuple[Path, float]:
    """Path and duration (seconds) of the spoken clip, generating it if needed."""
    path = CACHE / f"{_key(voice, text)}.wav"
    if not path.exists():
        from google.genai import types
        client = client or _client()
        last = None
        for attempt in range(5):
            try:
                r = client.models.generate_content(
                    model=MODEL, contents=text,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))))
                part = r.candidates[0].content.parts[0]
                write_wav(path, _trim(_pcm(part.inline_data.data)))
                break
            except Exception as e:  # noqa: BLE001 - rate limits and empty candidates are retried
                last = e
                time.sleep(4 * (attempt + 1))
        else:
            raise RuntimeError(f"TTS failed for {text[:60]!r}: {last}")
    with wave.open(str(path)) as w:
        return path, w.getnframes() / RATE


def faster(path: Path, factor: float) -> tuple[Path, float]:
    """A tempo-adjusted copy of a clip (same pitch), cached next to it."""
    out = path.with_name(f"{path.stem}.x{int(factor * 100)}.wav")
    if not out.exists():
        import subprocess
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-filter:a", f"atempo={factor}",
                        "-ar", str(RATE), "-ac", "1", str(out)], check=True)
    with wave.open(str(out)) as w:
        return out, w.getnframes() / RATE


def build_all() -> dict:
    """Generate every narration and call clip in script.py and write a manifest of durations."""
    import script
    client = _client()
    manifest: dict[str, list[dict]] = {}
    lines = [(b["id"], i, text, script.NARRATOR) for b in script.BEATS for i, text in enumerate(b["lines"])]
    lines += [(f"call:{i}", 0, seg["text"], script.CALL_VOICES[seg["speaker_email"]])
              for i, seg in enumerate(script.call_segments())]
    for n, (bid, i, line, voice) in enumerate(lines, 1):
        text, spoken = (line["text"], line["say"]) if isinstance(line, dict) else (line, line)
        path, dur = clip(spoken, voice, client)
        if voice == script.NARRATOR and script.NARRATOR_TEMPO != 1.0:
            path, dur = faster(path, script.NARRATOR_TEMPO)
        manifest.setdefault(bid, []).append({"text": text, "voice": voice, "path": str(path), "duration": round(dur, 3)})
        print(f"[{n}/{len(lines)}] {dur:5.2f}s  {voice:9s} {text[:70]}", flush=True)
    out = HERE / ".cache" / "manifest.json"
    out.write_text(json.dumps(manifest, indent=1))
    return manifest


if __name__ == "__main__":
    build_all()
