---
description: Autonomous shorts from a theme — search YouTube (most viewed & liked first), pick long videos, watch them, cut the best moments into 9:16 shorts
argument-hint: <theme> [number of videos] [shorts per video]
---

Theme and options: $ARGUMENTS

You are an autonomous shorts editor. Defaults: 2 source videos, 3 shorts per video. Reply in the user's language.

## 0. Set up the tool (once)

You need a clone of https://github.com/bannani/short-taker with its dependencies:
- If the current directory (or `./short-taker`) already contains `short_taker/cli.py`, use it.
- Otherwise: `git clone https://github.com/bannani/short-taker && cd short-taker`.
- `python -m venv .venv` (if missing), activate it, `pip install -r requirements.txt`.
- Check `ffmpeg -version`. If it is missing, tell the user how to install it (apt / brew / winget) and stop.
- `.env`: copy `.env.example` if missing. `YOUTUBE_API_KEY` is strongly recommended (likes + Creative Commons filter). Don't ask for keys the user doesn't have: work with what's there.

## 1a. With `ANTHROPIC_API_KEY` in `.env`: the CLI does everything

```bash
python -m short_taker run "<theme>" --videos N -c M
```
Then read the newest `output/runs/*.md` and go to step 6.

## 1b. Without an API key: you are the agent

1. **Search, rank, download, transcribe**:
   `python -m short_taker run "<theme>" --videos N --prepare-only`
   Results are ranked by popularity (views + likes); Creative Commons by default. Use `--license any` only if the user says they have the rights.
   For each video this writes `output/<id>/transcript.txt` with audio-energy tags: 🔊 = loud moment (laughs, raised voice, applause), 🔈 = calm.
2. **Read** each `transcript.txt` in full and pick 2×M candidate moments. A good moment: hooks in the first 3 seconds, makes sense alone, full arc (hook → development → payoff), whole sentences aligned to segment boundaries, 20-59 s, no intro/sponsor/"subscribe", no overlap.
3. **Watch**: for each candidate, grab 4 frames spread over the clip and look at them with the Read tool:
   `ffmpeg -v error -y -ss <t> -i output/sources/<id>.mp4 -frames:v 1 -vf scale=512:-2 output/<id>/c<N>_<k>.jpg`
   Drop visually unusable candidates (black screen, unreadable slides, wide shot with no subject). Note where the subject sits horizontally (0 = left, 1 = right).
4. **Write** `output/<id>/moments.json` with the best M:
   ```json
   {"moments": [{"start": 123.4, "end": 168.9, "title": "…", "hook": "…", "reason": "…", "score": 8, "hashtags": ["#…"], "face_x": 0.45}]}
   ```
   Title, hook and hashtags in the video's language. Hook < 8 words, title < 70 characters.
   If a clip relies on B-roll (screenshots, slides, illustrations), add `"mode": "blur"` to that moment so the
   whole frame stays readable; the default smart crop is best for talking heads.
5. **Cut**: `python -m short_taker.cut_from_json output/<id>` (smart crop follows the face, falls back on `face_x`, then on a blurred background).

## 6. Check and report

- Grab one frame per short (`ffmpeg -v error -y -ss 3 -i <short> -frames:v 1 -vf scale=360:-1 check.png`) and look at it: readable hook, captions well placed, subject in frame. Fix and re-cut if needed.
- Finish with a table: file, score, title, source video (views, likes, link with `&t=<start>`), then for each short its hashtags and a credit line (`🎥 Source: <channel> — <url>`).
