"""Découpe à partir d'un moments.json écrit à la main (ou par Claude Code).

  python -m short_taker.cut_from_json output/<id> [--mode blur|crop] [--no-subs]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import cut, transcribe
from .models import Moment


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("video_dir", help="Dossier output/<id> contenant transcript.json et moments.json")
    p.add_argument("--mode", choices=["smart", "blur", "crop"], default="smart")
    p.add_argument("--no-subs", action="store_true")
    a = p.parse_args()

    vdir = Path(a.video_dir)
    vid = vdir.name
    sources = vdir.parent / "sources"
    video = next(p for p in sources.glob(f"{vid}.*") if p.suffix in {".mp4", ".mkv", ".webm"})
    segments = transcribe.load(vdir / "transcript.json")
    data = json.loads((vdir / "moments.json").read_text(encoding="utf-8"))
    for i, m in enumerate(data["moments"], 1):
        mo = Moment(m["start"], m["end"], m["title"], m.get("hook", ""), m.get("reason", ""),
                    int(m.get("score", 5)), m.get("hashtags", []), m.get("face_x"))
        out = vdir / f"{i:02d}_{cut.slugify(mo.title)}.mp4"
        cut.cut(video, mo, segments, out, mode=m.get("mode", a.mode), subtitles=not a.no_subs)
        print(f"✅ {out}")


if __name__ == "__main__":
    main()
