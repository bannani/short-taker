"""Ce que l'agent « voit » et « entend » en plus de la transcription.

- énergie audio par segment (rires, cris, applaudissements, moments forts) ;
- images clés extraites aux moments candidats (envoyées à Claude en vision) ;
- position du visage (OpenCV) pour recadrer le 9:16 sur la personne qui parle.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from .models import Segment

SR = 8000  # suffisant pour l'énergie, léger en mémoire


def probe(video: Path) -> tuple[int, int, float]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    s = d["streams"][0]
    return int(s["width"]), int(s["height"]), float(d["format"].get("duration", 0))


def audio_rms(video: Path) -> np.ndarray:
    """RMS par seconde (en dB) de toute la piste audio."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
        capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if a.size == 0:
        return np.zeros(0)
    n = a.size // SR
    a = a[: n * SR].reshape(n, SR) if n else a.reshape(1, -1)
    rms = np.sqrt((a ** 2).mean(axis=1)) + 1e-9
    return 20 * np.log10(rms)


def tag_energy(segments: list[Segment], rms: np.ndarray) -> list[str]:
    """Étiquette chaque segment : '🔊' (énergie haute) / '' / '🔈' (calme), relatif à la vidéo."""
    if rms.size == 0:
        return [""] * len(segments)
    vals = []
    for s in segments:
        a, b = int(s.start), max(int(s.end), int(s.start) + 1)
        seg = rms[a:b]
        vals.append(float(seg.max()) if seg.size else -90.0)
    v = np.array(vals)
    hi, lo = np.percentile(v, 85), np.percentile(v, 15)
    return ["🔊" if x >= hi else "🔈" if x <= lo else "" for x in v]


def extract_frames(video: Path, times: list[float], out_dir: Path, width: int = 512) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, t in enumerate(times):
        p = out_dir / f"f{i:02d}_{t:.1f}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", str(p)], check=True)
        if p.exists():
            paths.append(p)
    return paths


def face_center(video: Path, start: float, end: float, samples: int = 8) -> float | None:
    """Position horizontale médiane (0-1) du plus grand visage sur le passage, ou None."""
    try:
        import cv2
    except ImportError:
        return None
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if cascade.empty():
        return None
    cap = cv2.VideoCapture(str(video))
    xs = []
    for k in range(samples):
        t = start + (end - start) * (k + 0.5) / samples
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        aw = min(w, 640)  # assez grand pour les visages d'un plan moyen, assez petit pour être rapide
        small = cv2.resize(frame, (aw, int(h * aw / w)))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(24, 24))
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            xs.append((x + fw / 2) / aw)
    cap.release()
    return float(np.median(xs)) if len(xs) >= max(2, samples // 4) else None
