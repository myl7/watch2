# watch2

An agent skill that turns a video into timestamped markdown notes.

Point it at a URL or a local file. It pulls the platform's own captions when they exist (free), transcribes the audio when they don't, writes a markdown report to `~/.local/share/watch2/`, and hands the path to your agent, which reads it and writes the notes into the same file.

Works in Claude Code, Codex, Cursor, Copilot, and anything else that loads Agent Skills.

## Why not just use Whisper

Whisper is bad at Chinese. On a mixed Chinese/English podcast, `whisper-large-v3-turbo` returned the whole transcript with no punctuation at all, and made these errors that `Qwen3-ASR-1.7B` did not:

| Spoken | Whisper | Qwen3-ASR |
| --- | --- | --- |
| ChatGPT | 差子就列 | ChatGPT |
| 运行脚本 | 允许脚本 | 运行脚本 |
| 语言方面 | 预言方面 | 语言方面 |
| ad hoc | ad hoc | ad hoc |

Qwen3-ASR is also cheaper. On DeepInfra it is $0.027 per hour of audio against Groq's $0.040 and OpenAI's $0.360. So it is the default here.

The one thing Whisper does better is timestamp granularity: Qwen3-ASR reports fixed ~27-second slices, Whisper reports ~2-6 second spans. That matters if you need to quote an exact line, not if you want to jump to a topic.

## Backends

All of them speak the OpenAI `/audio/transcriptions` shape, so adding one is a row in `PROVIDERS` in [`skills/watch2/scripts/asr.py`](skills/watch2/scripts/asr.py).

| `--asr` | Model | USD/hour | Timestamps |
| --- | --- | --- | --- |
| `deepinfra` (default) | `Qwen/Qwen3-ASR-1.7B` | 0.027 | ~27s |
| `deepinfra-cheap` | `Qwen/Qwen3-ASR-0.6B` | 0.012 | ~27s |
| `deepinfra-whisper` | `openai/whisper-large-v3-turbo` | 0.012 | ~6s |
| `groq` | `whisper-large-v3-turbo` | 0.040 | ~2s |
| `openai` | `whisper-1` | 0.360 | ~5s |

Native captions cost nothing and are tried first, so most YouTube videos never reach an API.

## Install

Requires `python3`, `ffmpeg`, and `yt-dlp`. The setup script checks for them and offers to install what is missing.

Claude Code:

```
/plugin marketplace add myl7/watch2
/plugin install watch2@watch2
```

Everything else:

```
npx skills add myl7/watch2 -g
```

Or clone and symlink:

```
git clone https://github.com/myl7/watch2.git
ln -s "$(pwd)/watch2/skills/watch" ~/.claude/skills/watch2   # or ~/.codex/skills/watch
```

Then add a key to `~/.config/watch/.env`:

```
DEEPINFRA_API_KEY=...
```

`GROQ_API_KEY` and `OPENAI_API_KEY` also work. With no key at all the skill still runs, but videos without native captions come back with no transcript.

## Use

```
/watch2 https://www.youtube.com/watch?v=...
/watch2 ~/Downloads/talk.mp4 what does he say about latency?
/watch2 https://www.bilibili.com/video/... --detail balanced
```

Frames are off by default. Add `--detail balanced` when the question is about something shown rather than said.

## Configuration

Everything lives in `~/.config/watch/.env`.

| Key | Default | What it does |
| --- | --- | --- |
| `DEEPINFRA_API_KEY` | — | Preferred ASR key |
| `GROQ_API_KEY` / `OPENAI_API_KEY` | — | Fallback ASR keys |
| `WATCH_TRANSCRIBER` | `auto` | Force a backend. `auto` walks deepinfra → groq → openai for the first key set |
| `WATCH_DETAIL` | `transcript` | `transcript` (no frames) / `efficient` / `balanced` / `token-burner` |
| `WATCH_NOTES_DIR` | `$XDG_DATA_HOME/watch2` (`~/.local/share/watch2`) | Where reports are written |
| `WATCH_YTDLP_COOKIES_FROM_BROWSER` | — | Browser to pull cookies from. Only for member-only or age-gated content |

## When a download fails

Update yt-dlp first. Site extractors break constantly and the fix ships in a release, so a yt-dlp more than a few weeks old is the most likely cause. `setup.py --json` reports `ytdlp_age_days` and `ytdlp_stale` for exactly this reason.

```
pipx upgrade yt-dlp   # or: brew upgrade yt-dlp / pip install -U yt-dlp
```

Bilibili returns HTTP 412 when a rate-limit bucket is tripped. The bucket is per (IP, User-Agent) and recovers in about ten minutes, which is why the same request can succeed bare and fail with a browser UA, then swap a few minutes later. There is no UA that always works, so the skill rotates through several on a 412. Leave `WATCH_YTDLP_USER_AGENT` unset: pinning one turns the rotation off. If every attempt fails, wait ten minutes. Cookies do not help; they are for member-only content.

YouTube occasionally needs `WATCH_YTDLP_REMOTE_COMPONENTS=ejs:github`, which lets yt-dlp fetch and run its remote JS challenge solver. It is off by default because it downloads and executes a component at runtime.

## Development

```
uv run --with pytest python -m pytest tests -q
```

`dev-sync.sh` copies the working tree into your installed plugin cache so you can test edits without reinstalling.

## Credits

Forked from [bradautomates/claude-video](https://github.com/bradautomates/claude-video) by Bradley Bonanno. This fork replaces the Whisper-only transcription path with a provider registry, defaults to Qwen3-ASR for Chinese, turns frames off by default, and writes reports to disk instead of stdout. MIT, same as upstream. See [LICENSE](LICENSE).
