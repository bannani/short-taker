"""CLI Short Taker.

Exemples :
  python -m short_taker search "interview entrepreneur" -n 5
  python -m short_taker make https://www.youtube.com/watch?v=XXXX -c 3
  python -m short_taker auto "astuces cuisine" --videos 2 -c 3
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from . import analyze, cut, download, search, transcribe


def cmd_search(a) -> list:
    vids = search.search(a.query, a.n, license=a.license)
    for i, v in enumerate(vids, 1):
        m, s = divmod(int(v.duration), 60)
        print(f"{i:>2}. [{m}:{s:02d}] {v.title} — {v.channel} ({v.views:,} vues, licence: {v.license or '?'})\n    {v.url}")
    return vids


def process(url: str, a) -> list[Path]:
    work = Path(a.out)
    print(f"\n⬇️  Téléchargement : {url}")
    video_path, subs, meta = download.download(url, work / "sources", langs=a.langs.split(","))
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

    print(f"🧠 Claude analyse {len(segments)} segments…")
    moments = analyze.find_moments(segments, meta, count=a.count, min_duration=a.min,
                                   max_duration=a.max, extra_instructions=a.instructions or "")
    (vdir / "moments.json").write_text(json.dumps(
        {"video": meta.to_dict(), "moments": [m.to_dict() for m in moments]},
        ensure_ascii=False, indent=2), encoding="utf-8")

    outputs = []
    for i, m in enumerate(moments, 1):
        out = vdir / f"{i:02d}_{cut.slugify(m.title)}.mp4"
        print(f"✂️  [{m.score}/10] {m.title} ({m.start:.1f}s → {m.end:.1f}s, {m.duration:.0f}s)")
        print(f"    {m.reason}")
        if not a.dry_run:
            cut.cut(video_path, m, segments, out, mode=a.mode, subtitles=not a.no_subs)
            outputs.append(out)
    print(f"✅ {len(outputs)} short(s) dans {vdir}")
    return outputs


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(prog="short_taker", description="Crée des shorts à partir de vidéos YouTube avec Claude.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("-c", "--count", type=int, default=3, help="Nombre de shorts par vidéo")
        sp.add_argument("--min", type=float, default=20, help="Durée min d'un short (s)")
        sp.add_argument("--max", type=float, default=59, help="Durée max d'un short (s)")
        sp.add_argument("--mode", choices=["blur", "crop"], default="blur", help="Recadrage 9:16")
        sp.add_argument("--langs", default="fr,en", help="Langues des sous-titres, par priorité")
        sp.add_argument("--no-subs", action="store_true", help="Ne pas incruster les sous-titres")
        sp.add_argument("--instructions", help="Consigne en plus pour Claude (ex: 'privilégie l'humour')")
        sp.add_argument("--dry-run", action="store_true", help="Analyse seulement, sans découper")
        sp.add_argument("-o", "--out", default="output")

    s = sub.add_parser("search", help="Chercher des vidéos")
    s.add_argument("query")
    s.add_argument("-n", type=int, default=10)
    s.add_argument("--license", default="creativeCommon", choices=["creativeCommon", "youtube", "any"])

    m = sub.add_parser("make", help="Créer des shorts depuis une ou plusieurs URLs")
    m.add_argument("urls", nargs="+")
    common(m)

    au = sub.add_parser("auto", help="Chercher puis créer des shorts automatiquement")
    au.add_argument("query")
    au.add_argument("--videos", type=int, default=2, help="Nombre de vidéos à traiter")
    au.add_argument("--license", default="creativeCommon", choices=["creativeCommon", "youtube", "any"])
    common(au)

    a = p.parse_args()
    if a.cmd == "search":
        cmd_search(a)
    elif a.cmd == "make":
        for u in a.urls:
            process(u, a)
    elif a.cmd == "auto":
        a.n = a.videos
        for v in cmd_search(a)[: a.videos]:
            try:
                process(v.url, a)
            except Exception as e:  # une vidéo qui plante ne bloque pas les autres
                print(f"❌ {v.url} : {e}")


if __name__ == "__main__":
    main()
