"""Téléchargement de la vidéo + sous-titres (json3, avec horodatage au mot) via yt-dlp."""
from __future__ import annotations

from pathlib import Path

import yt_dlp

from .models import VideoInfo


def download(url: str, out_dir: Path, langs: list[str] | None = None,
             max_height: int = 1080) -> tuple[Path, Path | None, VideoInfo]:
    """Télécharge via yt-dlp.

    Si YouTube répond « Sign in to confirm you're not a bot » (fréquent depuis un serveur / VPN),
    passe des cookies : SHORT_TAKER_COOKIES_FROM_BROWSER=chrome (ou firefox, edge…)
    ou SHORT_TAKER_COOKIES=/chemin/cookies.txt dans .env.
    """
    import os
    out_dir.mkdir(parents=True, exist_ok=True)
    langs = langs or ["fr", "en"]
    opts = {
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "format": f"bv*[height<={max_height}][ext=mp4]+ba[ext=m4a]/b[height<={max_height}]/b",
        "merge_output_format": "mp4",
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [f"{l}.*" for l in langs] + langs,
        "subtitlesformat": "json3/vtt/srt/best",
        "quiet": True,
        "noprogress": True,
        "ignoreerrors": False,
    }
    if os.environ.get("SHORT_TAKER_COOKIES_FROM_BROWSER"):
        opts["cookiesfrombrowser"] = (os.environ["SHORT_TAKER_COOKIES_FROM_BROWSER"],)
    if os.environ.get("SHORT_TAKER_COOKIES"):
        opts["cookiefile"] = os.environ["SHORT_TAKER_COOKIES"]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    vid = info["id"]
    video_path = out_dir / f"{vid}.mp4"
    if not video_path.exists():  # extension différente selon le format
        video_path = next(p for p in out_dir.glob(f"{vid}.*") if p.suffix in {".mp4", ".mkv", ".webm"})

    subs = None
    exts = ("json3", "vtt", "srt")  # json3 (YouTube, timing au mot) d'abord, puis vtt/srt (autres sites)
    for lang in langs + ["*"]:
        for ext in exts:
            cands = sorted(out_dir.glob(f"{vid}.{lang}*.{ext}"))
            if cands:
                subs = cands[0]
                break
        if subs:
            break

    meta = VideoInfo(
        id=vid, title=info.get("title", ""), channel=info.get("channel") or info.get("uploader", ""),
        url=info.get("webpage_url", url), duration=float(info.get("duration") or 0),
        views=int(info.get("view_count") or 0), license=info.get("license") or "",
        description=(info.get("description") or "")[:2000],
    )
    return video_path, subs, meta
