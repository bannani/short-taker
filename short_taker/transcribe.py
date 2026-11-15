"""Transcription : sous-titres YouTube json3 en priorité, sinon Whisper local (faster-whisper)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .models import Segment, Word


def from_json3(path: Path) -> list[Segment]:
    data = json.loads(path.read_text(encoding="utf-8"))
    segments: list[Segment] = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        t0 = ev.get("tStartMs", 0) / 1000
        dur = ev.get("dDurationMs", 0) / 1000
        words: list[Word] = []
        for i, s in enumerate(segs):
            txt = s.get("utf8", "").replace("\n", " ")
            if not txt.strip():
                continue
            ws = t0 + s.get("tOffsetMs", 0) / 1000
            nxt = segs[i + 1].get("tOffsetMs") if i + 1 < len(segs) else None
            we = t0 + nxt / 1000 if nxt is not None else t0 + dur
            words.append(Word(ws, max(we, ws + 0.05), txt.strip()))
        if not words:
            continue
        text = " ".join(w.text for w in words)
        segments.append(Segment(words[0].start, max(words[-1].end, words[0].start), text, words))
    return _merge_short(segments)


_TS = r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?"


def _ts(g) -> float:
    h, mi, se, ms = g
    return int(h or 0) * 3600 + int(mi) * 60 + int(se) + int((ms or "0").ljust(3, "0")) / 1000


def from_cues(path: Path) -> list[Segment]:
    """Sous-titres .vtt / .srt (Wikimedia, Vimeo, fichiers fournis…)."""
    import re

    text = path.read_text(encoding="utf-8", errors="ignore").replace("\r", "")
    raw = []
    for block in re.split(r"\n\s*\n", text):
        m = re.search(_TS + r"\s*-->\s*" + _TS, block)
        if not m:
            continue
        body = re.sub(r"<[^>]+>", "", block[m.end():]).strip()
        body = " ".join(l.strip() for l in body.split("\n") if l.strip())
        if body:
            raw.append(Segment(_ts(m.groups()[:4]), _ts(m.groups()[4:]), body))
    out: list[Segment] = []  # dédoublonne les sous-titres « roulants » (YouTube auto en vtt)
    for sg in raw:
        if out and sg.text.startswith(out[-1].text):
            out[-1] = Segment(out[-1].start, sg.end, sg.text)
        elif out and out[-1].text.endswith(sg.text):
            out[-1].end = sg.end
        else:
            out.append(sg)
    return _merge_short(out)


def _merge_short(segments: list[Segment], min_len: float = 3.0) -> list[Segment]:
    """Les sous-titres auto sont très fragmentés : on regroupe en phrases d'au moins ~3 s."""
    out: list[Segment] = []
    for s in segments:
        if out and (out[-1].end - out[-1].start) < min_len and s.start - out[-1].end < 1.0:
            prev = out[-1]
            out[-1] = Segment(prev.start, s.end, f"{prev.text} {s.text}", prev.words + s.words)
        else:
            out.append(s)
    return out


def from_whisper(video: Path, language: str | None = None) -> list[Segment]:
    from faster_whisper import WhisperModel

    import subprocess

    import numpy as np

    # Décodage audio par ffmpeg (évite les incompatibilités de faster-whisper avec certaines versions de PyAV)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    model = WhisperModel(os.environ.get("WHISPER_MODEL", "small"), device="auto", compute_type="auto")
    segs, _ = model.transcribe(audio, language=language, word_timestamps=True, vad_filter=True)
    out = []
    for s in segs:
        words = [Word(w.start, w.end, w.word.strip()) for w in (s.words or [])]
        out.append(Segment(s.start, s.end, s.text.strip(), words))
    return out


def transcribe(video: Path, subs: Path | None, language: str | None = None) -> list[Segment]:
    if subs and subs.exists():
        segs = from_json3(subs) if subs.suffix == ".json3" else from_cues(subs)
        if segs:
            return segs
    print("ℹ️  Pas de sous-titres exploitables, transcription Whisper locale…")
    return from_whisper(video, language)


def save(segments: list[Segment], path: Path) -> None:
    path.write_text(json.dumps(
        [{"start": s.start, "end": s.end, "text": s.text,
          "words": [w.__dict__ for w in s.words]} for s in segments],
        ensure_ascii=False, indent=1), encoding="utf-8")


def load(path: Path) -> list[Segment]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Segment(s["start"], s["end"], s["text"], [Word(**w) for w in s.get("words", [])]) for s in raw]
