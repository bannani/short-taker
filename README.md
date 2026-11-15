# 🎬 Short Taker

**Give it a theme, get shorts.** Short Taker searches YouTube for long videos, lets Claude pick the best ones, *watches* them (transcript + audio energy + key frames), and cuts the best moments into 1080x1920 shorts that follow the speaker's face, with a hook title and word-by-word captions.

```bash
python -m short_taker run "startup founders" --videos 2 -c 3
```

```
theme ─▶ YouTube search, most viewed & liked first ─▶ Claude picks videos ─▶ download + transcript ─▶ audio energy 🔊
                                                                           │
report.md ◀─ 9:16 shorts ◀─ face-tracking crop ◀─ Claude watches frames ◀─ Claude picks moments
```

Three ways to use it:

| | Where | Needs | YouTube search & download |
|---|---|---|---|
| **1. Claude.ai skill** | Claude chat (web, desktop, mobile) | Nothing, Claude is the editor | ❌ upload the video + transcript |
| **2. Claude Code plugin** | Your terminal | Claude Code, ffmpeg, Python | ✅ |
| **3. Standalone CLI** | Your terminal | ffmpeg, Python, Anthropic API key | ✅ fully autonomous |

---

## 1. Claude.ai skill (no install, no API key)

1. Download **`short-taker-skill.zip`** from the [latest release](https://github.com/bannani/short-taker/releases/latest).
2. In Claude: **Settings → Capabilities → Skills → Upload skill** and pick the zip. Code execution must be enabled.
3. In a new chat, upload your video (.mp4) and its transcript, then ask: *"Make 3 shorts from this video"*.

**Getting the transcript:** a .srt / .vtt file, or on YouTube click **"…" → "Show transcript"**, select everything and paste it into the chat.

> The Claude.ai sandbox can't reach YouTube or download Whisper models, so the video and transcript have to be uploaded. Uploads are size-limited: prefer 720p or shorter videos. If a video is too large, Claude still picks the moments and gives you ffmpeg commands to run locally.

## 2. Claude Code plugin

```bash
/plugin marketplace add bannani/short-taker
/plugin install short-taker@short-taker
```

Then in Claude Code: `/short-taker:run startup founders` (autonomous, works **without** an API key: Claude Code is the agent and looks at the frames itself), or *"Make 3 shorts from https://www.youtube.com/watch?v=…"*. Clone the repo too if you want Claude to use the CLI below for searching and downloading (see [`CLAUDE.md`](CLAUDE.md)).

## 3. Standalone CLI

```bash
git clone https://github.com/bannani/short-taker && cd short-taker
# ffmpeg is required: apt install ffmpeg / brew install ffmpeg / winget install ffmpeg
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set ANTHROPIC_API_KEY (and YOUTUBE_API_KEY, recommended)
```

```bash
# 🤖 Autonomous: theme → search → Claude picks 2 videos → watches them → 3 shorts each → report
python -m short_taker run "startup founders" --videos 2 -c 3

# Search only (Creative Commons only by default, needs YOUTUBE_API_KEY)
python -m short_taker search "startup founder interview" -n 10

# Shorts from a URL
python -m short_taker make "https://www.youtube.com/watch?v=XXXX" -c 3

# See what Claude would pick, without cutting
python -m short_taker make URL --dry-run

# Steer the selection
python -m short_taker make URL --instructions "favor the funny moments"
```

| Option | Default | |
|---|---|---|
| `-c, --count` | 3 | shorts per video |
| `--min / --max` | 20 / 59 | short duration (s) |
| `--mode` | `smart` | `smart` = follows the face, `blur` = full frame over blurred background, `crop` = centered crop |
| `--no-vision` | | skip frames + audio analysis (cheaper, transcript only) |
| `--sort` (run, search) | `popular` | `popular` = views + likes, `views`, `likes`, `relevance` |
| `--min-views` (run, search) | 0 | skip videos below this view count |
| `--videos` (run) | 2 | long videos to process |
| `--min-video / --max-video` (run) | 8 / 90 | source video duration (min) |
| `--prepare-only` (run) | | search, download, transcribe only: let Claude Code pick the moments |
| `--langs` | `fr,en` | caption languages, by priority |
| `--no-subs` | | no burned-in captions |
| `--license` | `creativeCommon` | `creativeCommon`, `youtube`, `any` |

Output:

```
output/
  sources/<id>.mp4          source video + captions
  <id>/transcript.json      transcript (cached)
  <id>/moments.json         Claude's picks: title, hook, reason, score, hashtags
  <id>/01_my-title.mp4      the shorts
  runs/<date>_<theme>.md    run report: sources, scores, titles, hashtags, credit lines
  history.json              videos already processed (never processed twice)
```

### How Claude "watches" a video

1. **Picks the videos**: up to 50 on-theme results are ranked by popularity (views + likes + like rate, log scale), then Claude keeps, among the most popular, the ones most likely to give good shorts (lots of talking, strong opinions, anecdotes, on-theme).
2. **Reads**: the full timestamped transcript, with 🔊 tags on loud moments (laughs, raised voices, applause) from the audio track.
3. **Proposes** twice as many candidate moments as needed.
4. **Watches**: 4 key frames per candidate are sent to Claude (vision). It drops visually weak clips, re-scores the rest and says where the subject is.
5. **Crops**: OpenCV finds the face to center the 9:16 crop (falls back on Claude's estimate, then on a blurred background).

### Run it every day

```bash
# Linux / macOS (crontab -e): every day at 7:00
0 7 * * * cd /path/to/short-taker && .venv/bin/python -m short_taker run "startup founders" --videos 2 -c 3 >> output/cron.log 2>&1
```

On Windows, create a daily task in Task Scheduler running the same command. Thanks to `history.json`, each run picks new videos.

Transcript sources, in order: YouTube captions (json3, word-level timing) → local Whisper (`faster-whisper`).

## Repo layout

```
short_taker/            standalone CLI (search, download, transcribe, analyze, cut)
skills/short-taker/     the skill (SKILL.md + scripts/shorts.py), used by Claude.ai and Claude Code
.claude-plugin/         Claude Code plugin + marketplace manifests
CLAUDE.md               instructions when the repo is opened in Claude Code
```

## ⚖️ Copyright

Reposting clips of other creators' videos without permission can infringe copyright and YouTube's terms (strikes, demonetization). Use your own videos, **Creative Commons** videos (the default search filter, credit the author), or videos you have permission to use.

## 🇫🇷 En bref

Short Taker transforme une vidéo longue en shorts 9:16 : Claude lit la transcription, choisit les meilleurs moments et ffmpeg les découpe avec accroche et sous-titres. Sur Claude.ai, installe le skill depuis la release et envoie la vidéo + la transcription dans le chat. En local, utilise la CLI ou le plugin Claude Code.

## License

MIT © Mohamed Fares Bannani
