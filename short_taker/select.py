"""Claude choisit, parmi les résultats de recherche, les vidéos qui donneront les meilleurs shorts."""
from __future__ import annotations

import os

import anthropic

from .models import VideoInfo

TOOL = {
    "name": "pick_videos",
    "description": "Choisit les vidéos les plus prometteuses pour en tirer des shorts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "picks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "reason"],
                },
            }
        },
        "required": ["picks"],
    },
}


def pick_videos(theme: str, videos: list[VideoInfo], n: int, language: str = "français") -> list[tuple[VideoInfo, str]]:
    if len(videos) <= n:
        return [(v, "seul candidat") for v in videos]
    if not os.environ.get("ANTHROPIC_API_KEY"):
        ranked = sorted(videos, key=lambda v: v.popularity, reverse=True)
        return [(v, f"parmi les plus populaires : {v.views:,} vues, {v.likes:,} likes "
                    "(pas de clé API pour le choix par Claude)") for v in ranked[:n]]

    lines = []
    for v in videos:
        m, s = divmod(int(v.duration), 60)
        lines.append(f"- id={v.id} | {v.title} | {v.channel} | {m}:{s:02d} | {v.views:,} vues | {v.likes:,} likes | "
                     f"{v.description[:200].replace(chr(10), ' ')}")
    prompt = f"""Thème demandé : « {theme} »

Voici des vidéos YouTube candidates. Choisis les {n} qui donneront les meilleurs shorts sur ce thème.
Les vidéos sont déjà classées de la plus populaire (vues + likes) à la moins populaire : la popularité
est un critère important, une vidéo très vue et très likée prouve que son contenu plaît. Privilégie aussi : beaucoup de parole (interviews, podcasts, conférences, débats, témoignages), des intervenants
charismatiques, des sujets à opinions fortes ou à anecdotes, une bonne pertinence avec le thème.
Évite : musique seule, compilations déjà découpées, vidéos sans parole, lives de plusieurs heures peu pertinents.
Réponds en {language}.

{chr(10).join(lines)}"""
    resp = anthropic.Anthropic().messages.create(
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"),
        max_tokens=1500,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "pick_videos"},
        messages=[{"role": "user", "content": prompt}],
    )
    picks = next(b for b in resp.content if b.type == "tool_use").input.get("picks", [])
    by_id = {v.id: v for v in videos}
    out = [(by_id[p["id"]], p["reason"]) for p in picks if p["id"] in by_id]
    return out[:n] or [(v, "repli") for v in videos[:n]]
