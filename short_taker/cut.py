"""Découpe ffmpeg : extrait le moment, recadre en 9:16 (1080x1920), incruste l'accroche et les sous-titres."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .models import Moment, Segment, Word

W, H = 1080, 1920


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def _words_in(segments: list[Segment], start: float, end: float) -> list[Word]:
    words: list[Word] = []
    for s in segments:
        if s.end < start or s.start > end:
            continue
        if s.words:
            words += [w for w in s.words if w.end > start and w.start < end]
        else:  # pas d'horodatage au mot : on répartit uniformément
            toks = s.text.split()
            step = (s.end - s.start) / max(len(toks), 1)
            words += [Word(s.start + i * step, s.start + (i + 1) * step, t) for i, t in enumerate(toks)
                      if s.start + (i + 1) * step > start and s.start + i * step < end]
    return words


def build_ass(moment: Moment, segments: list[Segment], path: Path, words_per_line: int = 3) -> None:
    """Sous-titres façon shorts : 2-4 mots à la fois, gros, centrés bas, + accroche en haut."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Arial,86,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,520,1
Style: Hook,Arial,72,&H0000F0FF,&H0000FFFF,&H00000000,&HAA000000,-1,0,0,0,100,100,0,0,3,4,0,8,60,60,180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    dur = moment.end - moment.start
    if moment.hook:
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(min(4.0, dur))},Hook,,0,0,0,,{_esc(moment.hook.upper())}\n")

    words = _words_in(segments, moment.start, moment.end)
    for i in range(0, len(words), words_per_line):
        chunk = words[i:i + words_per_line]
        s = chunk[0].start - moment.start
        e = (words[i + words_per_line].start if i + words_per_line < len(words) else chunk[-1].end) - moment.start
        text = " ".join(_esc(w.text) for w in chunk).upper()
        lines.append(f"Dialogue: 0,{_ass_time(s)},{_ass_time(min(e, dur))},Sub,,0,0,0,,{text}\n")
    path.write_text("".join(lines), encoding="utf-8")


def _filter(mode: str, ass: Path | None, face_x: float | None = None) -> str:
    if mode == "smart" and face_x is not None:  # recadrage centré sur le sujet (visage)
        fx = min(max(face_x, 0.0), 1.0)
        vf = (f"[0:v]crop=ih*9/16:ih:x='clip({fx:.3f}*iw-ih*9/32\\,0\\,iw-ih*9/16)':y=0,"
              f"scale={W}:{H},setsar=1[v]")
    elif mode == "crop":  # recadrage centré : idéal quand la personne est au centre
        vf = f"[0:v]crop=ih*9/16:ih,scale={W}:{H},setsar=1[v]"
    else:  # "blur" : vidéo entière au centre + fond flouté (marche avec tout)
        vf = (f"[0:v]split[a][b];"
              f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:5[bg];"
              f"[b]scale={W}:-2[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]")
    if ass:
        p = str(ass).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        vf = vf[:-3] + f"[pre];[pre]subtitles='{p}'[v]"
    return vf


def slugify(s: str, n: int = 50) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s_-]+", "-", s)[:n] or "short"


def cut(video: Path, moment: Moment, segments: list[Segment], out: Path,
        mode: str = "blur", subtitles: bool = True) -> Path:
    """mode : "blur" (fond flouté), "crop" (centre), "smart" (suit le sujet, repli sur blur)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    face_x = None
    if mode in ("smart", "crop"):
        from . import signals
        w, h, _ = signals.probe(video)
        if w / h < 0.6:  # source déjà verticale : pas de recadrage horizontal possible
            mode = "blur"
        elif mode == "smart":
            face_x = signals.face_center(video, moment.start, moment.end)
            if face_x is None:
                face_x = moment.face_x  # avis de Claude après avoir vu les images
            if face_x is None:
                mode = "blur"
            else:
                moment.face_x = face_x
    ass = None
    if subtitles:
        ass = out.with_suffix(".ass")
        build_ass(moment, segments, ass)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{moment.start:.3f}", "-to", f"{moment.end:.3f}", "-i", str(video),
        "-filter_complex", _filter(mode, ass, face_x), "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out),
    ]
    subprocess.run(cmd, check=True)
    return out
