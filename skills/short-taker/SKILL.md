---
name: short-taker
description: Turn a video uploaded to the chat into vertical 9:16 shorts (YouTube Shorts, TikTok, Reels). Claude reads the timestamped transcript, picks the best moments and cuts them with a hook and burned-in captions.
---

# Short Taker

You are the editor. From a video and its timestamped transcript, you pick the best moments and deliver 1080x1920 shorts ready to publish. Reply in the user's language.

## Theme mode: "I find, you upload" (the user gives a theme, no video)
YouTube can't be downloaded from the Claude.ai sandbox, but the web can be searched. Three light round trips:
1. **Find**: with WebSearch, look for long YouTube videos (8-60 min) on the theme with lots of talking (analysis, podcasts, interviews, debates), as popular as possible, Creative Commons preferred. Propose 3 (title, channel, duration, views if known, link) and recommend one.
2. **Subtitles**: ask the user to run this on their computer and upload the .srt:
   `yt-dlp --skip-download --write-auto-subs --sub-langs en --convert-subs srt -o "%(id)s" <URL>` (adapt the language).
3. **Pick**: parse the .srt (Parse step below) and pick the moments (step 3). Then give ONE command that downloads only those clips in good quality:
   `yt-dlp -f "bv*[height<=1080]+ba/b" --merge-output-format mp4 --download-sections "*START-END" --download-sections "*START-END" --force-keyframes-at-cuts -o "%(id)s_%(section_start)d.%(ext)s" <URL>` (one --download-sections per moment, seconds).
4. **Cut**: each uploaded clip starts at its moment's START. For each, write a moments.json with start=0 and end=END-START and a shifted transcript (subtract START from segment times, keep the segments inside the clip), then run `cut` (step 4), check (step 5) and deliver (step 6).

## Sandbox limits (read first)
- **YouTube is usually unreachable** from the Claude.ai sandbox (yt-dlp and arbitrary network calls are blocked). Do not try to download. If the user only gives a URL, ask them to upload:
  1. the video file (.mp4). Upload size is limited, so suggest 720p or a shorter video;
  2. the timestamped transcript: a .srt / .vtt / .json3 file, or a copy-paste from YouTube ("…" under the video → "Show transcript" → select all → paste).
  In Claude Code (local machine), downloading works: use the repo's CLI (`python -m short_taker make <url> --dry-run`) instead.
- **No Whisper in the sandbox** (models come from HuggingFace, which is blocked). Without a transcript, ask for one. Never claim you "listened to" the video: you work from the transcript.
- If the video is too big to upload, still analyze the transcript alone, list the moments and give one ffmpeg command per moment so the user can cut them locally.

## Steps
1. **Prepare**: copy `scripts/shorts.py` from this skill's folder into the working directory (if the skill folder isn't readable, recreate the file from the repo: https://github.com/bannani/short-taker/blob/main/skills/short-taker/scripts/shorts.py). Check `ffmpeg -version`. If the transcript was pasted in the message, write it to `transcript.txt`.
2. **Parse**: `python3 shorts.py parse <transcript_file> -o transcript.json`. The output prints the full timestamped transcript: read all of it.
3. **Pick the moments** (your job, not the script's). By default 3 moments of 20 to 59 s, unless told otherwise. A good moment:
   - hooks in the first 2-3 seconds (question, bold claim, surprise, number, emotion);
   - stands on its own without the rest of the video (no "as I was saying");
   - has a full arc: hook → development → payoff or conclusion;
   - starts and ends on a complete sentence, aligned to segment boundaries;
   - no intro, thanks, sponsor or "subscribe"; no overlap between moments.
   Score each moment honestly out of 10. Write `moments.json`:
   ```json
   {"moments": [{"start": 83.2, "end": 127.9, "title": "Title < 70 chars", "hook": "Hook < 8 words", "reason": "Why it works", "score": 8, "hashtags": ["#..."]}]}
   ```
   Title, hook and hashtags are in the video's language.
4. **Cut**: `python3 shorts.py cut <video> transcript.json moments.json -o shorts`
   - `--mode blur` (default): full video centered over a blurred background, always works;
   - `--mode crop`: centered crop, best when the speaker is in the middle of the frame;
   - `--no-subs`: no burned-in captions.
5. **Check**: for each short, grab a frame (`ffmpeg -ss 3 -i <short> -frames:v 1 -vf scale=360:-1 check_N.png`) and look at it (readable hook, well-placed captions, correct framing). Fix if needed.
6. **Deliver**: send the .mp4 files with a short table (no., start → end, title, score, reason) and the titles and hashtags ready to copy.

## Copyright
If the video doesn't seem to belong to the user, remind them in one sentence that reposting needs their own videos, a Creative Commons license (credit the author) or the creator's permission. Then continue.
