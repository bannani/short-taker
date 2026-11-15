"""CLI Short Taker.

Exemples :
  python -m short_taker run "entrepreneuriat" --videos 3 -c 3      # 100 % autonome
  python -m short_taker search "interview entrepreneur" -n 5
  python -m short_taker make https://www.youtube.com/watch?v=XXXX -c 3
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from . import analyze, cut, download, search, transcribe


# ---------- historique : ne jamais retraiter la même vidéo ----------
def _history_path(out: str) -> Path:
    return Path(out) / "history.json"


def load_history(out: str) -> dict:
    p = _history_path(out)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_history(out: str, h: dict) -> None:
    p = _history_path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- commandes ----------
def cmd_search(a) -> list:
    vids = search.search(a.query, a.n, license=a.license, sort=a.sort, min_views=a.min_views)
    for i, v in enumerate(vids, 1):
        m, s = divmod(int(v.duration), 60)
        print(f"{i:>2}. [{m}:{s:02d}] {v.title} — {v.channel}\n    👁 {v.views:,} vues · 👍 {v.likes:,} likes · "
              f"licence: {v.license or '?'}\n    {v.url}")
    return vids


def process(url: str, a) -> list[dict]:
    """Télécharge, « regarde » et découpe une vidéo. Renvoie la liste des shorts produits."""
    work = Path(a.out)
    print(f"\n⬇️  Téléchargement : {url}")
    video_path, subs, meta = download.download(url, work / "sources", langs=a.langs.split(","),
                                                 max_height=getattr(a, "max_height", 1080))
    vdir = work / meta.id
    vdir.mkdir(parents=True, exist_ok=True)

    tr_path = vdir / "transcript.json"
    if tr_path.exists():
        segments = transcribe.load(tr_path)
    else:
        print("📝 Transcription…")
        segments = transcribe.transcribe(video_path, subs, language=a.langs.split(",")[0])
        transcribe.save(segments, tr_path)
    if not segments:
        print("❌ Aucune parole détectée, vidéo ignorée.")
        return []

    energy = None
    if not getattr(a, "no_vision", False) or getattr(a, "prepare_only", False):
        from . import signals
        print("👂 Analyse de l'énergie audio…")
        try:
            energy = signals.tag_energy(segments, signals.audio_rms(video_path))
        except Exception as e:  # l'audio n'est qu'un indice : on continue sans
            print(f"   (énergie audio indisponible : {e})")

    if getattr(a, "prepare_only", False):  # Claude Code prend le relais (pas besoin de clé API)
        txt = analyze._transcript_text(segments, energy)
        (vdir / "transcript.txt").write_text(f"# {meta.title} — {meta.channel} — {meta.url}\n{txt}\n", encoding="utf-8")
        (vdir / "video.json").write_text(json.dumps(meta.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"📂 Prêt pour l'agent : {vdir}/transcript.txt")
        return []

    vision = not getattr(a, "no_vision", False)
    n_candidates = a.count * 2 if vision else a.count
    print(f"🧠 Claude lit {len(segments)} segments et propose {n_candidates} candidats…")
    moments = analyze.find_moments(segments, meta, count=n_candidates, min_duration=a.min,
                                   max_duration=a.max, extra_instructions=a.instructions or "",
                                   energy=energy)
    if vision and moments:
        print(f"👀 Claude regarde les images de {len(moments)} candidats…")
        try:
            moments = analyze.review_with_vision(video_path, moments, segments, vdir)
        except Exception as e:
            print(f"   (revue visuelle impossible, on garde le choix sur le texte : {e})")
    moments = moments[: a.count]

    (vdir / "moments.json").write_text(json.dumps(
        {"video": meta.to_dict(), "moments": [m.to_dict() for m in moments]},
        ensure_ascii=False, indent=2), encoding="utf-8")

    results = []
    for i, m in enumerate(moments, 1):
        out = vdir / f"{i:02d}_{cut.slugify(m.title)}.mp4"
        print(f"✂️  [{m.score}/10] {m.title} ({m.start:.1f}s → {m.end:.1f}s, {m.duration:.0f}s)")
        print(f"    {m.reason}" + (f"\n    👀 {m.visual_note}" if m.visual_note else ""))
        if not a.dry_run:
            cut.cut(video_path, m, segments, out, mode=a.mode, subtitles=not a.no_subs)
            results.append({"file": str(out), "video": meta.to_dict(), **m.to_dict()})
    print(f"✅ {len(results)} short(s) dans {vdir}")
    return results


def cmd_run(a) -> None:
    """Mode autonome : thème → recherche → choix des vidéos → shorts → rapport."""
    from . import select

    history = load_history(a.out)
    print(f"🔎 Recherche de vidéos sur « {a.query} »…")
    candidates = search.search(a.query, max_results=max(a.videos * 5, 10), license=a.license,
                               min_duration=a.min_video * 60, max_duration=a.max_video * 60,
                               sort=a.sort, min_views=a.min_views)
    fresh = [v for v in candidates if v.id not in history]
    print(f"   {len(candidates)} trouvées, {len(fresh)} jamais traitées.")
    if not fresh:
        print("Rien de nouveau. Essaie un thème plus large ou --license any (si tu as les droits).")
        return

    picks = select.pick_videos(a.query, fresh, a.videos)
    print("🎯 Vidéos retenues :")
    for v, why in picks:
        print(f"   • {v.title} — {v.channel} (👁 {v.views:,} · 👍 {v.likes:,})\n     {why}")

    all_shorts, errors = [], []
    for v, why in picks:
        try:
            shorts = process(v.url, a)
            all_shorts += shorts
            if a.prepare_only:
                continue
            history[v.id] = {"title": v.title, "url": v.url, "theme": a.query,
                             "date": datetime.now().isoformat(timespec="seconds"), "shorts": len(shorts)}
            save_history(a.out, history)
        except Exception as e:  # une vidéo qui plante ne bloque pas les autres
            print(f"❌ {v.url} : {e}")
            errors.append(f"{v.url} : {e}")

    if a.prepare_only:
        print("\n🏁 Préparation terminée : à l'agent de choisir les moments (voir CLAUDE.md).")
        return
    report = write_report(a, picks, all_shorts, errors)
    print(f"\n🏁 Terminé : {len(all_shorts)} shorts. Rapport : {report}")


def write_report(a, picks, shorts, errors) -> Path:
    runs = Path(a.out) / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    p = runs / f"{stamp}_{cut.slugify(a.query, 30)}.md"
    lines = [f"# Short Taker — « {a.query} »", "", f"_{datetime.now():%d/%m/%Y %H:%M}_", "",
             "## Vidéos analysées", ""]
    for v, why in picks:
        lines.append(f"- [{v.title}]({v.url}) — {v.channel} — 👁 {v.views:,} vues · 👍 {v.likes:,} likes "
                     f"(licence : {v.license or '?'}) : {why}")
    lines += ["", "## Shorts", "", "| # | Fichier | Note | Titre | Source |", "|---|---|---|---|---|"]
    for i, s in enumerate(sorted(shorts, key=lambda s: s["score"], reverse=True), 1):
        src = f"[{s['video']['channel']}]({s['video']['url']}&t={int(s['start'])})"
        lines.append(f"| {i} | `{Path(s['file']).parent.name}/{Path(s['file']).name}` | {s['score']}/10 | {s['title']} | {src} |")
    lines += ["", "## Textes prêts à publier", ""]
    for s in sorted(shorts, key=lambda s: s["score"], reverse=True):
        credit = f"🎥 Source : {s['video']['channel']} — {s['video']['url']}"
        lines += [f"### {s['title']}", "", f"{' '.join(s.get('hashtags') or [])}", "", credit, ""]
    if errors:
        lines += ["## Erreurs", ""] + [f"- {e}" for e in errors]
    p.write_text("\n".join(lines), encoding="utf-8")
    (runs / f"{stamp}.json").write_text(json.dumps(shorts, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(prog="short_taker", description="Crée des shorts à partir de vidéos YouTube avec Claude.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("-c", "--count", type=int, default=3, help="Nombre de shorts par vidéo")
        sp.add_argument("--min", type=float, default=20, help="Durée min d'un short (s)")
        sp.add_argument("--max", type=float, default=59, help="Durée max d'un short (s)")
        sp.add_argument("--mode", choices=["smart", "blur", "crop"], default="smart",
                        help="Recadrage 9:16 : smart = suit le visage (repli sur blur)")
        sp.add_argument("--langs", default="fr,en", help="Langues des sous-titres, par priorité")
        sp.add_argument("--no-subs", action="store_true", help="Ne pas incruster les sous-titres")
        sp.add_argument("--no-vision", action="store_true",
                        help="Ne pas faire regarder les images ni analyser l'audio (moins cher)")
        sp.add_argument("--instructions", help="Consigne en plus pour Claude (ex: 'privilégie l'humour')")
        sp.add_argument("--dry-run", action="store_true", help="Analyse seulement, sans découper")
        sp.add_argument("--max-height", type=int, default=1080, help="Qualité max de la vidéo source (ex: 720)")
        sp.add_argument("-o", "--out", default=os.environ.get("SHORT_TAKER_OUT", "output"))

    def sort_args(sp):
        sp.add_argument("--sort", choices=["popular", "views", "likes", "relevance"], default="popular",
                        help="Classement des vidéos : popular = vues + likes (défaut)")
        sp.add_argument("--min-views", type=int, default=0, help="Ignorer les vidéos sous ce nombre de vues")

    s = sub.add_parser("search", help="Chercher des vidéos")
    s.add_argument("query")
    s.add_argument("-n", type=int, default=10)
    s.add_argument("--license", default="creativeCommon", choices=["creativeCommon", "youtube", "any"])
    sort_args(s)

    m = sub.add_parser("make", help="Créer des shorts depuis une ou plusieurs URLs (YouTube ou autre site)")
    m.add_argument("urls", nargs="+")
    m.add_argument("--prepare-only", action="store_true",
                   help="Télécharger et transcrire seulement (Claude Code choisit ensuite les moments)")
    common(m)

    for name in ("run", "auto"):
        r = sub.add_parser(name, help="Mode autonome : un thème → des shorts" if name == "run" else "Alias de run")
        r.add_argument("query", help="Thème, ex: 'productivité', 'histoire de Rome'")
        r.add_argument("--videos", type=int, default=2, help="Nombre de vidéos longues à traiter")
        r.add_argument("--min-video", type=float, default=8, help="Durée min des vidéos sources (min)")
        r.add_argument("--max-video", type=float, default=90, help="Durée max des vidéos sources (min)")
        r.add_argument("--license", default="creativeCommon", choices=["creativeCommon", "youtube", "any"])
        sort_args(r)
        r.add_argument("--prepare-only", action="store_true",
                       help="Chercher, télécharger et transcrire seulement (Claude Code choisit ensuite les moments)")
        common(r)

    a = p.parse_args()
    if a.cmd == "search":
        cmd_search(a)
    elif a.cmd == "make":
        for u in a.urls:
            process(u, a)
    else:
        cmd_run(a)


if __name__ == "__main__":
    main()
