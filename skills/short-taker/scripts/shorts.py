#!/usr/bin/env python3
"""Short Taker (Claude chat) — parse transcript + cut 9:16 shorts with ffmpeg.

  python3 shorts.py parse <transcript.(srt|vtt|json3|txt)> -o transcript.json
  python3 shorts.py cut <video> transcript.json moments.json -o out/ [--mode blur|crop] [--no-subs]
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

W, H = 1080, 1920
TS = r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?"


def ts(m):
    h, mi, s, ms = m
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + (int((ms or "0").ljust(3, "0")) / 1000)


def parse_cues(text):  # SRT / VTT
    segs = []
    for block in re.split(r"\n\s*\n", text.replace("\r", "")):
        m = re.search(TS + r"\s*-->\s*" + TS, block)
        if not m:
            continue
        g = m.groups()
        body = block[m.end():].strip()
        body = re.sub(r"<[^>]+>", "", body)
        body = " ".join(l.strip() for l in body.split("\n") if l.strip())
        if body:
            segs.append({"start": ts(g[:4]), "end": ts(g[4:]), "text": body})
    out = []  # dédoublonne les sous-titres auto YouTube "roulants"
    for s in segs:
        if out and s["text"].startswith(out[-1]["text"]):
            out[-1]["text"], out[-1]["end"] = s["text"], s["end"]
        elif out and out[-1]["text"].endswith(s["text"]):
            out[-1]["end"] = s["end"]
        else:
            out.append(s)
    return out


def parse_json3(text):
    segs = []
    for ev in json.loads(text).get("events", []):
        if not ev.get("segs"):
            continue
        t0, d = ev.get("tStartMs", 0) / 1000, ev.get("dDurationMs", 0) / 1000
        txt = "".join(s.get("utf8", "") for s in ev["segs"]).replace("\n", " ").strip()
        if txt:
            segs.append({"start": t0, "end": t0 + d, "text": txt})
    return segs


def parse_plain(text):  # copier-coller "Afficher la transcription" : "0:12 texte" ou "0:12\ntexte"
    lines = [l.strip() for l in text.replace("\r", "").split("\n") if l.strip()]
    items, cur = [], None
    for l in lines:
        m = re.match(r"^\[?" + TS + r"\]?\s*(.*)$", l)
        if m and m.group(2) is not None:
            if cur:
                items.append(cur)
            cur = {"start": ts(m.groups()[:4]), "text": m.groups()[4].strip()}
        elif cur:
            cur["text"] = (cur["text"] + " " + l).strip()
    if cur:
        items.append(cur)
    for i, it in enumerate(items):
        it["end"] = items[i + 1]["start"] if i + 1 < len(items) else it["start"] + 4
    return [i for i in items if i["text"]]


def merge(segs, min_len=3.0):
    out = []
    for s in segs:
        if out and out[-1]["end"] - out[-1]["start"] < min_len and s["start"] - out[-1]["end"] < 1:
            out[-1] = {"start": out[-1]["start"], "end": s["end"], "text": out[-1]["text"] + " " + s["text"]}
        else:
            out.append(dict(s))
    return out


def cmd_parse(a):
    raw = Path(a.file).read_text(encoding="utf-8", errors="ignore")
    if raw.lstrip().startswith("{"):
        segs = parse_json3(raw)
    elif "-->" in raw:
        segs = parse_cues(raw)
    else:
        segs = parse_plain(raw)
    segs = merge(segs)
    for s in segs:
        s["start"], s["end"] = round(s["start"], 2), round(s["end"], 2)
    Path(a.o).write_text(json.dumps(segs, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(segs)} segments -> {a.o}")
    for s in segs:
        print(f"[{s['start']:.2f}-{s['end']:.2f}] {s['text']}")


# ---------- cut ----------
def at(t):
    h, r = divmod(max(0.0, t), 3600); m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def esc(t):
    return t.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(m, segs, path, n=3):
    st, en = m["start"], m["end"]; dur = en - st
    L = [f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,DejaVu Sans,82,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,520,1
Style: Hook,DejaVu Sans,70,&H0000F0FF,&H0000FFFF,&H00000000,&HAA000000,-1,0,0,0,100,100,0,0,3,4,0,8,60,60,180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""]
    if m.get("hook"):
        L.append(f"Dialogue: 1,{at(0)},{at(min(4, dur))},Hook,,0,0,0,,{esc(m['hook'].upper())}\n")
    words = []  # mots répartis uniformément dans chaque segment
    for s in segs:
        if s["end"] < st or s["start"] > en:
            continue
        toks = s["text"].split(); step = (s["end"] - s["start"]) / max(len(toks), 1)
        for i, t in enumerate(toks):
            a, b = s["start"] + i * step, s["start"] + (i + 1) * step
            if b > st and a < en:
                words.append((a, b, t))
    for i in range(0, len(words), n):
        c = words[i:i + n]
        s = c[0][0] - st
        e = (words[i + n][0] if i + n < len(words) else c[-1][1]) - st
        L.append(f"Dialogue: 0,{at(s)},{at(min(e, dur))},Sub,,0,0,0,,{esc(' '.join(w[2] for w in c).upper())}\n")
    path.write_text("".join(L), encoding="utf-8")


def vfilter(mode, ass):
    if mode == "crop":
        vf = f"[0:v]crop=ih*9/16:ih,scale={W}:{H},setsar=1"
    else:
        vf = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:5[bg];"
              f"[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    if ass:
        p = str(ass).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        vf += f",subtitles='{p}'"
    return vf + "[v]"


def slug(s):
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[\s_-]+", "-", s)[:50] or "short"


def snap(m, segs, mn, mx):
    starts, ends = [s["start"] for s in segs], [s["end"] for s in segs]
    st = min(starts, key=lambda x: abs(x - m["start"]))
    en = min(ends, key=lambda x: abs(x - m["end"]))
    if en - st > mx:
        ok = [e for e in ends if st + mn <= e <= st + mx]; en = max(ok) if ok else st + mx
    if en - st < mn:
        ok = [e for e in ends if e >= st + mn]; en = min(ok) if ok else st + mn
    m["start"], m["end"] = max(0, st - 0.15), en + 0.3
    return m


def cmd_cut(a):
    segs = json.loads(Path(a.transcript).read_text(encoding="utf-8"))
    data = json.loads(Path(a.moments).read_text(encoding="utf-8"))
    moments = data["moments"] if isinstance(data, dict) else data
    out = Path(a.o); out.mkdir(parents=True, exist_ok=True)
    for i, m in enumerate(moments, 1):
        m = snap(m, segs, a.min, a.max)
        f = out / f"{i:02d}_{slug(m['title'])}.mp4"
        ass = None
        if not a.no_subs:
            ass = f.with_suffix(".ass"); build_ass(m, segs, ass)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{m['start']:.3f}", "-to", f"{m['end']:.3f}",
                        "-i", a.video, "-filter_complex", vfilter(a.mode, ass), "-map", "[v]", "-map", "0:a?",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-r", "30",
                        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(f)], check=True)
        if ass:
            ass.unlink()
        print(f"OK {f}  ({m['start']:.1f}s -> {m['end']:.1f}s)")


def main():
    p = argparse.ArgumentParser(); sp = p.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("parse"); a.add_argument("file"); a.add_argument("-o", default="transcript.json")
    c = sp.add_parser("cut"); c.add_argument("video"); c.add_argument("transcript"); c.add_argument("moments")
    c.add_argument("-o", default="shorts"); c.add_argument("--mode", default="blur", choices=["blur", "crop"])
    c.add_argument("--no-subs", action="store_true"); c.add_argument("--min", type=float, default=15)
    c.add_argument("--max", type=float, default=60)
    args = p.parse_args(); {"parse": cmd_parse, "cut": cmd_cut}[args.cmd](args)


if __name__ == "__main__":
    main()
