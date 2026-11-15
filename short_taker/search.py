"""Recherche de vidéos YouTube.

- Avec YOUTUBE_API_KEY : YouTube Data API v3, filtrable par licence (Creative Commons par défaut).
- Sans clé : recherche via yt-dlp (pas de filtre de licence, à réserver à tes propres vidéos).
"""
from __future__ import annotations

import os
import re

import requests

from .models import VideoInfo

API = "https://www.googleapis.com/youtube/v3"


def _iso_duration_to_seconds(iso: str) -> float:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0.0
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return float(d * 86400 + h * 3600 + mi * 60 + s)


def search_api(query: str, max_results: int = 10, license: str = "creativeCommon",
               duration: str = "any", lang: str | None = None, order: str = "relevance") -> list[VideoInfo]:
    key = os.environ["YOUTUBE_API_KEY"]
    params = {
        "key": key, "part": "snippet", "q": query, "type": "video",
        "maxResults": min(max_results, 50), "order": order,
    }
    if duration != "any":  # short (<4 min), medium (4-20), long (>20)
        params["videoDuration"] = duration
    if license and license != "any":
        params["videoLicense"] = license
    if lang:
        params["relevanceLanguage"] = lang
    r = requests.get(f"{API}/search", params=params, timeout=30)
    r.raise_for_status()
    ids = [it["id"]["videoId"] for it in r.json().get("items", [])]
    if not ids:
        return []

    r = requests.get(f"{API}/videos", params={
        "key": key, "part": "snippet,contentDetails,statistics,status", "id": ",".join(ids),
    }, timeout=30)
    r.raise_for_status()
    out = []
    for it in r.json().get("items", []):
        sn = it["snippet"]
        out.append(VideoInfo(
            id=it["id"], title=sn["title"], channel=sn.get("channelTitle", ""),
            url=f"https://www.youtube.com/watch?v={it['id']}",
            duration=_iso_duration_to_seconds(it["contentDetails"]["duration"]),
            views=int(it.get("statistics", {}).get("viewCount", 0)),
            likes=int(it.get("statistics", {}).get("likeCount", 0)),
            published=sn.get("publishedAt", ""),
            license=it.get("status", {}).get("license", ""),
            description=sn.get("description", "")[:2000],
        ))
    return out


def search_ytdlp(query: str, max_results: int = 10) -> list[VideoInfo]:
    import yt_dlp

    opts = {"quiet": True, "skip_download": True, "extract_flat": "in_playlist"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        res = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
    out = []
    for e in res.get("entries", []) or []:
        out.append(VideoInfo(
            id=e["id"], title=e.get("title", ""), channel=e.get("channel") or e.get("uploader", ""),
            url=e.get("url") or f"https://www.youtube.com/watch?v={e['id']}",
            duration=float(e.get("duration") or 0), views=int(e.get("view_count") or 0),
            likes=int(e.get("like_count") or 0),
        ))
    return out


def search(query: str, max_results: int = 10, license: str = "creativeCommon",
           min_duration: float = 120, max_duration: float = 3600, sort: str = "popular",
           min_views: int = 0) -> list[VideoInfo]:
    """sort = "popular" (vues + likes), "views", "likes" ou "relevance".

    En mode popularité, on récupère un large lot de résultats pertinents (jusqu'à 50) puis on les classe :
    les vidéos les plus vues et les plus likées remontent, sans perdre le lien avec le thème.
    """
    pool = max_results if sort == "relevance" else 50
    if os.environ.get("YOUTUBE_API_KEY"):
        videos = search_api(query, pool, license=license)
    else:
        print("⚠️  Pas de YOUTUBE_API_KEY : recherche via yt-dlp, sans filtre de licence ni likes.")
        videos = search_ytdlp(query, min(pool, 30))
    videos = [v for v in videos if (not v.duration or min_duration <= v.duration <= max_duration)
              and v.views >= min_views]
    key = {"popular": lambda v: v.popularity, "views": lambda v: v.views,
           "likes": lambda v: v.likes}.get(sort)
    if key:
        videos.sort(key=key, reverse=True)
    return videos[:max_results]
