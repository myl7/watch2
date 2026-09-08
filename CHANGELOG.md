# Changelog

Version numbering restarts with this fork. Upstream's own history, up to and
including its 0.2.0, is at
[bradautomates/claude-video](https://github.com/bradautomates/claude-video/blob/main/CHANGELOG.md);
those entries used the same low numbers this fork now reuses, so they are not
reproduced here.

## [0.1.0] — 2026-09-08

First release of the fork.

### Added
- **Provider registry** (`skills/watch2/scripts/asr.py`). Every backend speaks the same OpenAI `/audio/transcriptions` shape, so adding one is a row in `PROVIDERS` instead of a new module and a new branch in `watch.py`.
- **DeepInfra backends** — `deepinfra` (`Qwen/Qwen3-ASR-1.7B`, $0.027/hr, the default), `deepinfra-cheap` (`Qwen/Qwen3-ASR-0.6B`, $0.012/hr), `deepinfra-whisper` (`openai/whisper-large-v3-turbo`, $0.012/hr). `auto` walks deepinfra → groq → openai for the first key that is set.
- **Reports are written to disk** at `$XDG_DATA_HOME/watch2/<date>-<title>.md` (`~/.local/share/watch2` by default; override with `WATCH_NOTES_DIR` or `--notes`). The script prints the path and a one-line summary; the agent reads the file and writes its notes into the `## Notes` placeholder, keeping the summary and its source transcript together. `--stdout` prints the report instead, for debugging.
- **User agent rotation past Bilibili's HTTP 412.** That 412 is a rate limit bucketed per (IP, User-Agent) which recovers in roughly ten minutes, so no fixed user agent escapes it: on one video page a bare request and a browser UA swapped which of them failed within ten minutes, while a third, unused UA went straight through. `_run_ytdlp` retries a Bilibili request through a short rotation on a 412, judging success by whether the caller got its file rather than by yt-dlp's exit code. Setting `WATCH_YTDLP_USER_AGENT` pins one identity and opts out.
- **`ytdlp_age_days` and `ytdlp_stale`** in `setup.py --json`, which a failed download now leads with. yt-dlp versions are release dates, so this needs no network. Every download failure seen while building this traced back to a two-month-old yt-dlp, not to cookies or anti-bot measures.

### Changed
- **The skill is named `watch2`, invoked as `/watch2`**, and lives in `skills/watch2/`.
- **Qwen3-ASR is the default transcriber rather than Whisper.** On a mixed zh/en podcast Whisper returned the entire transcript with no punctuation and turned "ChatGPT" into 差子就列, "运行脚本" into 允许脚本, and "语言方面" into 预言方面; Qwen3-ASR got all three right. It is also cheaper than Groq. Whisper keeps finer timestamps (~2-6s spans against Qwen3-ASR's fixed ~27s slices), which is the reason to override.
- **Default detail is `transcript`, not `balanced`.** Frames are the expensive part of a run and most questions are about what was said. Pass `--detail balanced` for frames.
- `--whisper` → `--asr`, `--no-whisper` → `--no-asr`. The old spellings still work as aliases.

### Fixed
- **Frame extraction was broken on ffmpeg 8 and later**, which removed `-vsync`; every scene and keyframe run aborted with "Unrecognized option 'vsync'". Now uses `-fps_mode vfr` (available since ffmpeg 5.0). This accounted for 21 of the test suite's failures.
- A cookie source no longer forces a hardcoded browser user agent. Cookies are for member-only or age-gated content; conflating them with the UA meant configuring cookies changed request fingerprinting for unrelated reasons.

### Removed
- **Doubao / Volcano Engine backend** and its hand-rolled WebSocket and binary sub-protocol implementation (616 lines). Qwen3-ASR covers the Chinese case it existed for, over plain HTTP.

### Note
- The config directory is `~/.config/watch/` and environment variables keep the `WATCH_` prefix. Only the skill was renamed.
