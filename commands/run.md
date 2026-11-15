---
description: Autonomous shorts from a theme — search YouTube, pick long videos, watch them, cut the best moments into 9:16 shorts
argument-hint: <theme> [number of videos] [shorts per video]
---

Theme and options: $ARGUMENTS

Run Short Taker's autonomous mode on this theme (defaults: 2 videos, 3 shorts per video).

1. Make sure you are in a clone of https://github.com/bannani/short-taker with dependencies installed
   (`pip install -r requirements.txt`, ffmpeg available). If not, clone it into `./short-taker`, install, and continue there.
2. Follow the "Autonomous mode" section of the repo's `CLAUDE.md`:
   - with `ANTHROPIC_API_KEY` set: `python -m short_taker run "<theme>" --videos N -c M`, then summarize the report;
   - otherwise: `--prepare-only`, then read the transcripts, look at the frames, write `moments.json`,
     cut with `python -m short_taker.cut_from_json`, check one frame per short.
3. Finish with a short table: file, score, title, source (with timestamp), plus the hashtags and credit line for each short.
