"""Turn recorded scenes into the final video: frames -> 30 fps H.264, voices mixed at their logged
times, captions (burned in, plus a sidecar .srt) and chapter titles.

    uv run --project ../backend --with numpy python assemble.py
"""

from __future__ import annotations

import json
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

import script

HERE = Path(__file__).resolve().parent
SCENES = HERE / ".cache" / "scenes"
OUT = HERE / "out"
RATE = 24000
FPS = 30
# Soft white fades into and out of the title cards; every other scene cut is seamless.
FADE_IN = {"intro", "landing", "outro"}
FADE_OUT = {"intro", "how", "outro"}


def sh(*args: str) -> None:
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def read_wav(path: str) -> np.ndarray:
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def click_sound() -> np.ndarray:
    """A soft, short tick for mouse clicks."""
    n = int(RATE * 0.018)
    t = np.arange(n) / RATE
    rng = np.random.default_rng(7)
    tone = 0.5 * np.sin(2 * np.pi * 2200 * t) + 0.5 * rng.uniform(-1, 1, n)
    return (tone * np.exp(-t * 320) * 0.10).astype(np.float32)


# ------------------------------------------------------------------ video
def scene_video(name: str) -> tuple[Path, float]:
    d = SCENES / name
    tl = json.loads((d / "timeline.json").read_text())
    t0, t_end, frames = tl["t0"], tl["t_end"], tl["frames"]
    lines = ["ffconcat version 1.0"]
    for i, (n, ts) in enumerate(frames):
        start = max(0.0, ts - t0)
        nxt = (frames[i + 1][1] - t0) if i + 1 < len(frames) else (t_end - t0)
        dur = max(0.001, nxt - start)
        if i == 0 and start > 0:
            dur += start  # stretch the first frame back to the scene start
        lines += [f"file 'frames/{n:06d}.jpg'", f"duration {dur:.4f}"]
    lines.append(f"file 'frames/{frames[-1][0]:06d}.jpg'")
    (d / "frames.ffconcat").write_text("\n".join(lines) + "\n")
    out = d / "video.mp4"
    length = t_end - t0
    fades = "".join([
        f",fade=t=in:st=0:d=0.5:color=white" if name in FADE_IN else "",
        f",fade=t=out:st={length - 0.6:.3f}:d=0.6:color=white" if name in FADE_OUT else "",
    ])
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(d / "frames.ffconcat"),
       "-vf", f"fps={FPS},scale=1920:1080:flags=lanczos:force_original_aspect_ratio=decrease,"
              f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=white{fades},format=yuv420p",
       "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-r", str(FPS), "-t", f"{t_end - t0:.3f}", str(out))
    return out, t_end - t0


# ------------------------------------------------------------------ audio
def scene_audio(name: str, length: float) -> tuple[np.ndarray, list[dict]]:
    tl = json.loads((SCENES / name / "timeline.json").read_text())
    mix = np.zeros(int((length + 1) * RATE), dtype=np.float32)
    tick = click_sound()
    for ev in tl["events"]:
        start = int(ev["t"] * RATE)
        if ev["kind"] in ("narration", "voice"):
            clip = read_wav(ev["path"]) * (1.0 if ev["kind"] == "narration" else 0.92)
        elif ev["kind"] == "click":
            clip = tick
        else:
            continue
        end = min(len(mix), start + len(clip))
        mix[start:end] += clip[: end - start]
    return mix[: int(length * RATE)], tl["events"]


# ------------------------------------------------------------------ captions
def _wrap(text: str, width: int = 52) -> list[str]:
    words, rows, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            rows.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        rows.append(cur)
    return rows


def _chunks(text: str, max_chars: int = 100) -> list[str]:
    """Split a long caption at sentence or clause boundaries so each cue fits two lines."""
    if len(text) <= max_chars:
        return [text]
    parts = re.split(r"(?<=[.?!])\s+|(?<=,)\s+(?=\S{3,})", text)
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + 1 + len(p) > max_chars:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        out.append(cur)
    return out


def cues(events: list[dict], offset: float) -> list[dict]:
    out = []
    for ev in events:
        if ev["kind"] not in ("narration", "voice"):
            continue
        speaker = ev.get("speaker") if ev["kind"] == "voice" else None
        pieces = _chunks(ev["text"])
        total = sum(len(p) for p in pieces)
        t = offset + ev["t"]
        for p in pieces:
            d = ev["duration"] * len(p) / total
            out.append({"start": t, "end": t + d, "text": p, "speaker": speaker})
            t += d
    return out


def _ts(t: float, sep: str = ",") -> str:
    h, rem = divmod(max(0.0, t), 3600)
    m, s = divmod(rem, 60)
    if sep == ".":
        return f"{int(h)}:{int(m):02d}:{s:05.2f}"
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}{sep}{int((s % 1) * 1000):03d}"


def write_srt(all_cues: list[dict], path: Path) -> None:
    blocks = []
    for i, c in enumerate(all_cues, 1):
        text = "\n".join(_wrap((f"{c['speaker']}: " if c["speaker"] else "") + c["text"]))
        blocks.append(f"{i}\n{_ts(c['start'])} --> {_ts(c['end'] - 0.02)}\n{text}\n")
    path.write_text("\n".join(blocks))


def _ass_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def write_ass(all_cues: list[dict], chapters: list[dict], path: Path) -> None:
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Helvetica Neue,44,&H00FFFFFF,&H00FFFFFF,&H64141414,&H64141414,0,0,0,0,100,100,0,0,3,14,0,2,160,160,54,1
Style: Chapter,Helvetica Neue,34,&H00FFFFFF,&H00FFFFFF,&H00E88A00,&H00E88A00,1,0,0,0,100,100,0,0,3,12,0,7,28,28,22,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows = []
    for c in all_cues:
        body = r"\N".join(_ass_escape(r) for r in _wrap(c["text"], 56 if not c["speaker"] else 50))
        if c["speaker"]:
            body = r"{\c&H7FD8FF&}" + _ass_escape(c["speaker"]) + r":{\c&HFFFFFF&} " + body
        rows.append(f"Dialogue: 0,{_ts(c['start'], '.')},{_ts(c['end'] - 0.02, '.')},Caption,,0,0,0,,{body}")
    for ch in chapters:
        rows.append(f"Dialogue: 1,{_ts(ch['start'], '.')},{_ts(ch['start'] + 4.2, '.')},Chapter,,0,0,0,,"
                    rf"{{\fad(250,400)}}{_ass_escape(ch['text'])}")
    path.write_text(head + "\n".join(rows) + "\n")


# ------------------------------------------------------------------ main
def main() -> None:
    OUT.mkdir(exist_ok=True)
    names = [s for s in script.SCENE_ORDER if (SCENES / s / "timeline.json").exists()]
    missing = [s for s in script.SCENE_ORDER if s not in names]
    if missing:
        print("missing scenes (skipped):", missing)
    videos, audio, all_cues, chapters = [], [], [], []
    offset = 0.0
    for name in names:
        v, length = scene_video(name)
        a, events = scene_audio(name, length)
        videos.append(v)
        audio.append(a)
        all_cues += cues(events, offset)
        chapters += [{"start": offset + e["t"], "text": e["text"]} for e in events if e["kind"] == "chapter"]
        print(f"  {name:14s} {length:6.1f}s  at {offset:6.1f}s")
        offset += length
    concat = OUT / "scenes.txt"
    concat.write_text("".join(f"file '{v}'\n" for v in videos))
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy",
       str(OUT / "video_only.mp4"))
    full = np.concatenate(audio)
    peak = float(np.max(np.abs(full))) or 1.0
    full = np.clip(full / max(peak, 1.0), -1, 1)
    with wave.open(str(OUT / "voice.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((full * 32767).astype(np.int16).tobytes())
    write_srt(all_cues, OUT / "relay-demo.srt")
    write_ass(all_cues, chapters, OUT / "captions.ass")
    sh("ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / "video_only.mp4"), "-i", str(OUT / "voice.wav"),
       "-vf", f"ass={OUT / 'captions.ass'}", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000",
       "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart", "-shortest",
       str(OUT / "relay-demo.mp4"))
    sh("ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / "video_only.mp4"), "-i", str(OUT / "voice.wav"),
       "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
       "-ac", "2", "-movflags", "+faststart", "-shortest", str(OUT / "relay-demo-no-captions.mp4"))
    print(f"done: {OUT / 'relay-demo.mp4'} ({offset:.1f}s), captions {OUT / 'relay-demo.srt'}")


if __name__ == "__main__":
    main()
