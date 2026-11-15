"""L'agent : Claude lit la transcription horodatée et choisit les meilleurs moments pour des shorts."""
from __future__ import annotations

import os

import anthropic

from .models import Moment, Segment, VideoInfo

SYSTEM = """Tu es un monteur expert en contenus courts (YouTube Shorts, TikTok, Reels).
On te donne la transcription horodatée d'une vidéo. Ta mission : repérer les passages qui
feront les meilleurs shorts autonomes.

Un bon moment :
- accroche dans les 2-3 premières secondes (question, affirmation forte, surprise, chiffre, émotion) ;
- se comprend SANS le reste de la vidéo (pas de « comme je disais », pas de référence à ce qui précède) ;
- a un arc complet : accroche → développement → chute / punchline / conclusion ;
- commence et finit sur une phrase complète (jamais au milieu d'un mot ou d'une idée) ;
- apporte de la valeur : info utile, rire, émotion, opinion tranchée, histoire.

Évite : intros, remerciements, sponsors, « abonnez-vous », passages techniques sans contexte.
Les moments ne doivent pas se chevaucher. Utilise les horodatages fournis pour start/end.
Note honnêtement : un 9-10 doit vraiment pouvoir devenir viral."""

TOOL = {
    "name": "submit_moments",
    "description": "Soumet la liste des meilleurs moments à découper en shorts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "moments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "number", "description": "Début en secondes"},
                        "end": {"type": "number", "description": "Fin en secondes"},
                        "title": {"type": "string", "description": "Titre accrocheur du short (< 70 caractères)"},
                        "hook": {"type": "string", "description": "Texte d'accroche à afficher en haut de l'écran (< 8 mots)"},
                        "reason": {"type": "string", "description": "Pourquoi ce passage marche en short"},
                        "score": {"type": "integer", "minimum": 1, "maximum": 10},
                        "hashtags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["start", "end", "title", "hook", "reason", "score"],
                },
            }
        },
        "required": ["moments"],
    },
}


def _fmt(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:05.2f}"


def _transcript_text(segments: list[Segment], energy: list[str] | None = None) -> str:
    energy = energy or [""] * len(segments)
    return "\n".join(f"[{s.start:.2f}-{s.end:.2f}] ({_fmt(s.start)}){' ' + e if e else ''} {s.text}"
                     for s, e in zip(segments, energy))


def _snap(moment: Moment, segments: list[Segment], min_d: float, max_d: float) -> Moment | None:
    """Recale start/end sur les bornes de phrases et force la durée dans [min_d, max_d]."""
    starts = [s.start for s in segments]
    ends = [s.end for s in segments]
    start = min(starts, key=lambda x: abs(x - moment.start))
    end = min(ends, key=lambda x: abs(x - moment.end))
    if end - start > max_d:
        ok = [e for e in ends if start + min_d <= e <= start + max_d]
        end = max(ok) if ok else start + max_d
    if end - start < min_d:
        ok = [e for e in ends if e >= start + min_d]
        end = min(ok) if ok else start + min_d
    if end <= start:
        return None
    moment.start = max(0.0, start - 0.15)  # petite marge pour ne pas couper la 1re syllabe
    moment.end = end + 0.3
    return moment


def find_moments(segments: list[Segment], video: VideoInfo, count: int = 3,
                 min_duration: float = 20, max_duration: float = 59,
                 language: str = "français", extra_instructions: str = "",
                 energy: list[str] | None = None) -> list[Moment]:
    client = anthropic.Anthropic()
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

    user = f"""Vidéo : « {video.title} » — chaîne : {video.channel} — durée : {_fmt(video.duration)}

Description (extrait) :
{video.description[:800]}

Trouve les {count} meilleurs moments pour des shorts de {int(min_duration)} à {int(max_duration)} secondes.
Écris title, hook et reason en {language}.
{extra_instructions}
{"Les segments marqués 🔊 ont une énergie audio forte (rires, voix qui monte, applaudissements), 🔈 sont calmes : c'est un indice, pas une règle." if energy else ""}

Transcription horodatée ([début-fin] en secondes) :
{_transcript_text(segments, energy)}"""

    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "submit_moments"},
        messages=[{"role": "user", "content": user}],
    )
    block = next(b for b in resp.content if b.type == "tool_use")
    raw = block.input.get("moments", [])

    moments: list[Moment] = []
    for m in raw:
        mo = Moment(float(m["start"]), float(m["end"]), m["title"], m["hook"],
                    m["reason"], int(m["score"]), m.get("hashtags", []))
        mo = _snap(mo, segments, min_duration, max_duration)
        if mo and not any(mo.start < o.end and o.start < mo.end for o in moments):
            moments.append(mo)
    moments.sort(key=lambda m: m.score, reverse=True)
    return moments[:count]


REVIEW_TOOL = {
    "name": "review_moments",
    "description": "Verdict final sur chaque moment candidat après avoir regardé les images.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reviews": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "Numéro du candidat"},
                        "keep": {"type": "boolean"},
                        "score": {"type": "integer", "minimum": 1, "maximum": 10,
                                  "description": "Note finale (texte + visuel)"},
                        "subject_x": {"type": "number", "minimum": 0, "maximum": 1,
                                      "description": "Position horizontale du sujet principal (0 = gauche, 1 = droite)"},
                        "visual_note": {"type": "string"},
                    },
                    "required": ["index", "keep", "score", "subject_x", "visual_note"],
                },
            }
        },
        "required": ["reviews"],
    },
}


def review_with_vision(video_path, candidates: list[Moment], segments: list[Segment], work_dir,
                       frames_per_moment: int = 4, language: str = "français") -> list[Moment]:
    """2e passe : Claude « regarde » des images clés de chaque candidat et tranche."""
    import base64
    from pathlib import Path

    from . import signals

    content: list[dict] = [{"type": "text", "text": (
        "Tu es monteur de shorts. Pour chaque moment candidat, tu as l'extrait de transcription "
        "et quelques images clés. Juge l'intérêt VISUEL pour un short vertical : visage visible et expressif, "
        "action, image lisible une fois recadrée en 9:16. Rejette (keep=false) les passages visuellement "
        "inexploitables (écran noir, slides illisibles, plan trop large sans sujet) sauf si le texte est exceptionnel. "
        f"Donne la position horizontale du sujet principal pour le recadrage. Réponds en {language}.")}]
    for i, m in enumerate(candidates):
        excerpt = " ".join(s.text for s in segments if s.end > m.start and s.start < m.end)[:1200]
        content.append({"type": "text", "text": f"\n--- Candidat {i} : « {m.title} » ({m.start:.1f}s → {m.end:.1f}s, "
                                                f"note texte {m.score}/10)\nTranscription : {excerpt}"})
        times = [m.start + (m.end - m.start) * (k + 0.5) / frames_per_moment for k in range(frames_per_moment)]
        for f in signals.extract_frames(Path(video_path), times, Path(work_dir) / "frames" / f"c{i}"):
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": base64.b64encode(f.read_bytes()).decode()}})

    resp = anthropic.Anthropic().messages.create(
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"),
        max_tokens=3000,
        tools=[REVIEW_TOOL],
        tool_choice={"type": "tool", "name": "review_moments"},
        messages=[{"role": "user", "content": content}],
    )
    reviews = next(b for b in resp.content if b.type == "tool_use").input.get("reviews", [])
    kept = []
    for r in reviews:
        i = r.get("index")
        if not isinstance(i, int) or not 0 <= i < len(candidates) or not r.get("keep"):
            continue
        m = candidates[i]
        m.score = int(r.get("score", m.score))
        m.face_x = float(r.get("subject_x", 0.5))
        m.visual_note = r.get("visual_note", "")
        kept.append(m)
    kept.sort(key=lambda m: m.score, reverse=True)
    return kept
