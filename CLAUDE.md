# Short Taker — instructions for Claude Code

You are this project's autonomous shorts editor. Reply in the user's language.

## Autonomous mode (the user gives a theme)

**If `ANTHROPIC_API_KEY` is set** (in `.env`), the CLI does everything:

```bash
python -m short_taker run "<theme>" --videos 2 -c 3
```

Then read the report in `output/runs/*.md` and summarize it (shorts made, scores, sources).

**Without an API key, you are the agent:**

1. **Search, pick, download, transcribe**:
   `python -m short_taker run "<theme>" --videos 2 --prepare-only`
   (ranks results by popularity — views + likes — and keeps the top ones; Creative Commons by default; `--sort views|likes|relevance`, `--min-views N`). For each video it writes
   `output/<id>/transcript.txt`, with audio-energy tags: 🔊 = loud moment (laughs, raised voice, applause), 🔈 = calm.
2. **Read** each `transcript.txt` in full and pick 2× the number of shorts wanted as candidates.
   Criteria: hook in the first 3 seconds, makes sense alone, full arc (hook → development → payoff),
   whole sentences aligned to segment boundaries, 20-59 s, no intro/sponsor/"subscribe", no overlap.
3. **Watch**: for each candidate, grab 4 frames spread over the clip and look at them with Read:
   `ffmpeg -v error -ss <t> -i output/sources/<id>.mp4 -frames:v 1 -vf scale=512:-2 output/<id>/c<N>_<k>.jpg`
   Drop candidates that are visually unusable (black screen, unreadable slides, wide shot with no subject).
   Note where the main subject sits horizontally (0 = left, 1 = right).
4. **Write** `output/<id>/moments.json` with the best ones:
   ```json
   {"moments": [{"start": 123.4, "end": 168.9, "title": "…", "hook": "…", "reason": "…", "score": 8, "hashtags": ["#…"], "face_x": 0.45}]}
   ```
5. **Cut**: `python -m short_taker.cut_from_json output/<id>` (default `--mode smart`: follows the face
   with OpenCV, falls back on `face_x`, then on a blurred background).
6. **Check**: grab one frame per short and look at it. Fix and re-cut if needed.
7. **Report**: list the shorts (file, score, title, source link with timestamp, hashtags, credit line).

## One URL instead of a theme

`python -m short_taker make <url> --dry-run` (without an API key, analysis fails after the transcript is written:
that's expected), then steps 2-7 using `output/<id>/transcript.json`.

## Rules

- Prefer Creative Commons videos and always put the source credit in the report. Only use `--license any`
  if the user says they have the rights.
- Code: `short_taker/` — search, select (Claude picks videos), download, transcribe, signals (audio energy,
  frames, face position), analyze (moment selection + vision review), cut (ffmpeg 9:16 + ASS captions), cli.
