# Changelog

All notable changes to `/watch` are documented here.

## [0.3.0] — 2026-09-07

Fork rename: `cheap-claude-video` → `watch-notes`.

### Added
- **Provider registry** (`scripts/asr.py`, was `scripts/whisper.py`). Every backend speaks the same OpenAI `/audio/transcriptions` shape, so adding one is a row in `PROVIDERS` instead of a new module and a new branch in `watch.py`.
- **DeepInfra backends** — `deepinfra` (`Qwen/Qwen3-ASR-1.7B`, $0.027/hr, the new default), `deepinfra-cheap` (`Qwen/Qwen3-ASR-0.6B`, $0.012/hr), `deepinfra-whisper` (`openai/whisper-large-v3-turbo`, $0.012/hr). `auto` now walks deepinfra → groq → openai.
- **Reports are written to disk** at `~/watch-notes/<date>-<title>.md` (override with `WATCH_NOTES_DIR` or `--notes`). The script prints the path and a one-line summary; the agent reads the file and writes its notes into the `## Notes` placeholder, keeping the summary and its source transcript together. `--stdout` restores the old behavior for debugging.

### Changed
- **Default transcriber is Qwen3-ASR rather than Whisper.** On a mixed zh/en podcast Whisper returned the entire transcript with no punctuation and turned "ChatGPT" into 差子就列, "运行脚本" into 允许脚本, and "语言方面" into 预言方面; Qwen3-ASR got all three right. It is also cheaper than Groq. Whisper keeps finer timestamps (~2-6s spans against Qwen3-ASR's fixed ~27s slices), which is the reason to override.
- **Default detail is `transcript`, not `balanced`.** Frames are the expensive part of a run and most questions are about what was said. Pass `--detail balanced` for frames.
- `--whisper` → `--asr`, `--no-whisper` → `--no-asr`. The old spellings still work as aliases.

### Fixed
- **Frame extraction was broken on ffmpeg 8 and later**, which removed `-vsync`; every scene and keyframe run aborted with "Unrecognized option 'vsync'". Now uses `-fps_mode vfr` (available since ffmpeg 5.0). This was 21 of the test suite's failures.

### Removed
- **Doubao / Volcano Engine backend** and its hand-rolled WebSocket and binary sub-protocol implementation (616 lines). Qwen3-ASR covers the Chinese case it existed for, over plain HTTP.

## [0.2.0] — 2026-06-29

### Added
- **`--detail` dial** with four modes — `transcript` (captions only, no frames), `efficient` (fast keyframe pass, cap 50), `balanced` (scene-aware, cap 100, default), and `token-burner` (scene-aware, uncapped). Set the default with `WATCH_DETAIL` in `~/.config/watch/.env`.
- **Frame deduplication** (default on; `--no-dedup` to disable). Before the budget cap, a pass downscales each frame to a 16×16 grayscale thumbnail and drops frames whose mean per-pixel difference from the last *kept* frame is within threshold — so the budget goes to distinct content instead of held slides and static recordings. The **Frames** report line shows how many near-duplicates were dropped.
- **Whisper auto-chunking.** Audio over the 25 MB upload cap is split into evenly sized chunks, transcribed per chunk, with segment timestamps shifted back into source time. Partial failures are tolerated — transcription only fails if *every* chunk fails, so length alone no longer breaks it.
- **`--timestamps T1,T2,…`** — grab a frame at each absolute timestamp; reserved against the cap, and the only frames produced under `--detail transcript`.
- **`--no-whisper`** — disable transcription entirely (frames only).
- pytest suite covering config, dedup, download, fixtures, frames, setup, timestamps, watch, and whisper (no network; ffmpeg-synthesized clips).

### Changed
- **Restructured into a self-contained `skills/watch/` package** so `SKILL.md` and its `scripts/` runtime are siblings in one folder. This fixes installs on Codex, Cursor, Copilot, and other Agent Skills hosts: `npx skills add` now copies the skill as a working unit instead of grabbing the root `SKILL.md` without its scripts.
- **Harness-agnostic path resolution** — `SKILL.md` resolves `$SKILL_DIR` from where it was Read instead of the Claude-Code-only `${CLAUDE_SKILL_DIR}`, so script calls work on every host.
- `/watch` is now derived from `SKILL.md` frontmatter; the separate `commands/watch.md` wrapper was dropped to avoid a duplicate slash command.
- `balanced` now full-decodes to detect every scene cut across the whole video. The previous early-exit was faster but kept only the first cuts and dropped the tail of long videos.
- `token-burner` is exempt from the long-video "sparse scan" warning, since it keeps every scene-change frame.
- `--max-frames` is now an override on top of each mode's default cap, rather than a fixed default of 80.

### Fixed
- Non-Claude installs (`npx skills add`) were dead on arrival — the installer copied `SKILL.md` without the `scripts/` it shells out to. The self-contained package layout resolves this.

### Removed
- `V2_PLAN.md` and `V2_CONCERNS.md` planning docs.

## [0.1.3] — 2026-05-09

### Fixed
- Windows: `video.info.json` is read as UTF-8 (#4). Previously `Path.read_text()` defaulted to cp1252 on Windows and crashed on yt-dlp's UTF-8 output, silently dropping Title/Uploader from the report. Same fix applied to `.env` reads/writes in `whisper.py` and `setup.py`.
- `download.py` now logs info.json parse failures to stderr instead of swallowing them.

### Security
- Hardened subprocess argv against option injection (#2): inserted `--` before the URL in the yt-dlp argv, and tightened `is_url` to reject `-`-prefixed sources and require a non-empty netloc. Resolved video/audio paths to absolute via `Path.resolve()` before passing to `ffmpeg`/`ffprobe`, so a relative path starting with `-` can't be misinterpreted as a flag.

## [0.1.2] — 2026-04-24

### Fixed
- Windows console crash: removed the emoji from the long-video warning in `watch.py`; cp1252 consoles couldn't encode it.
- `setup.py` now prints `winget` / `pip` install commands on Windows instead of "unsupported platform" — matches what the README already promised.

### Changed
- `SKILL.md` notes that on Windows the scripts must be invoked with `python`, not `python3` (the latter is the Microsoft Store stub on Windows).

## [0.1.1] — 2026-04-24

### Fixed
- Added `commands/watch.md` shim so `/watch` is callable when installed as a Claude Code plugin. Without it, the plugin loaded but the skill wasn't exposed as a slash command.
- `scripts/build-skill.sh` now strips `commands/` from the claude.ai `.skill` bundle alongside `hooks/` and `.claude-plugin/`.

## [0.1.0] — 2026-04-24

Initial marketplace release.

### Added
- `/watch <url-or-path> [question]` slash command.
- yt-dlp download with native caption extraction (manual + auto-subs).
- ffmpeg frame extraction with auto-scaled fps (≤2 fps, ≤100 frames, duration-aware budget).
- `--start` / `--end` focused mode with denser frame budget and transcript range filtering.
- Whisper fallback (Groq preferred, OpenAI secondary) for videos without captions.
- `setup.py` preflight: silent `--check`, structured `--json`, and installer that auto-runs `brew install` on macOS.
- Session-start hook that prints a one-line status on first run / partial config.
- `.skill` bundle packaging for claude.ai upload via `scripts/build-skill.sh`.
