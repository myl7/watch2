#!/usr/bin/env python3
"""Download a video via yt-dlp, or resolve a local file path.

Also fetches subtitles (manual first, then auto-generated) in VTT format so
transcribe.py can parse them without needing Whisper.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from config import read_env_file


VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".flv", ".wmv"}

def _ytdlp_auth_args() -> list[str]:
    """Cookie / UA args for yt-dlp, from env or ~/.config/watch/.env.

    - WATCH_YTDLP_COOKIES_FROM_BROWSER: e.g. `chrome`, `firefox`, `chrome:Default`
    - WATCH_YTDLP_COOKIES_FILE: path to a Netscape cookies.txt
    - WATCH_YTDLP_USER_AGENT: send this UA instead of yt-dlp's own

    The UA is sent only when explicitly configured. An earlier version forced a
    hardcoded browser UA whenever a cookie source was set, which coupled two
    unrelated things: cookies are for gated content, while Bilibili's HTTP 412
    is a per-(IP, UA) rate limit that no fixed UA escapes. _run_ytdlp handles
    the 412 by rotating identities; pinning a UA here opts out of that.
    """
    file_values = read_env_file()

    def get(name: str) -> str | None:
        return os.environ.get(name) or file_values.get(name)

    args: list[str] = []
    from_browser = get("WATCH_YTDLP_COOKIES_FROM_BROWSER")
    if from_browser:
        args += ["--cookies-from-browser", from_browser]
    cookies_file = get("WATCH_YTDLP_COOKIES_FILE")
    if cookies_file:
        args += ["--cookies", cookies_file]

    user_agent = get("WATCH_YTDLP_USER_AGENT")
    if user_agent:
        args += ["--user-agent", user_agent]
    return args


# Languages to fetch captions for, in no particular order (the pick below ranks
# them). Chinese variants + English cover the common cases; native captions are
# free, so grabbing them avoids paying an ASR backend. Configurable so a user
# whose videos are in another language can add it.
_DEFAULT_SUB_LANGS = "zh-Hans,zh-Hant,zh,zh-CN,zh-TW,zh-HK,yue,en-orig,en,en-US,en-GB"


def _sub_langs() -> str:
    file_values = read_env_file()
    return os.environ.get("WATCH_SUB_LANGS") or file_values.get("WATCH_SUB_LANGS") or _DEFAULT_SUB_LANGS


def _is_bilibili(url: str) -> bool:
    return "bilibili.com" in url or "b23.tv" in url


def _is_youtube(url: str) -> bool:
    host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def _ytdlp_site_args(url: str) -> list[str]:
    """Site-specific yt-dlp args. YouTube's newer anti-bot sometimes needs a
    remote JS challenge solver, available via yt-dlp's `--remote-components`
    — but that fetches and runs a solver component from yt-dlp's GitHub, so
    it's opt-in rather than on by default. Off for every other site.

    Set WATCH_YTDLP_REMOTE_COMPONENTS to a value like `ejs:github` to enable
    it; unset (the default) or `off`/`0`/`false`/empty leaves it disabled.
    """
    if not _is_youtube(url):
        return []
    file_values = read_env_file()
    value = os.environ.get("WATCH_YTDLP_REMOTE_COMPONENTS")
    if value is None:
        value = file_values.get("WATCH_YTDLP_REMOTE_COMPONENTS")
    if value is None:
        return []  # disabled by default — see the hint in download_url's error message
    value = value.strip()
    if not value or value.lower() in ("off", "0", "false", "none"):
        return []
    return ["--remote-components", value]


def is_url(source: str) -> bool:
    if source.startswith("-"):
        return False
    parsed = urlparse(source)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def resolve_local(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise SystemExit(f"File not found: {p}")
    if p.suffix.lower() not in VIDEO_EXTS:
        print(
            f"[watch2] warning: {p.suffix} is not a known video extension, proceeding anyway",
            file=sys.stderr,
        )
    return {
        "video_path": str(p),
        "subtitle_path": None,
        "info": {"title": p.name, "url": str(p)},
        "downloaded": False,
    }


def _subtitle_lang(name: str) -> str:
    """`video.zh-Hans.vtt` → `zh-Hans`, `video.en-orig.vtt` → `en-orig`."""
    parts = name.split(".")
    return parts[-2] if len(parts) >= 3 else ""


def _pick_subtitle(out_dir: Path, prefer_lang: str | None = None) -> Path | None:
    """Pick the best caption file.

    Rank: (1) the video's own language (`prefer_lang` from info.json) — this
    beats a machine-translated caption in another language; (2) Chinese; (3)
    English; (4) anything. Native captions are free, so preferring the original
    language keeps quality high and avoids paying an ASR backend.
    """
    candidates = sorted(out_dir.glob("video*.vtt"))
    if not candidates:
        return None

    prefer_base = (prefer_lang or "").lower().split("-")[0]

    def rank(path: Path) -> tuple[int, int, str]:
        lang = _subtitle_lang(path.name).lower()
        base = lang.split("-")[0]
        if prefer_base and base == prefer_base:
            tier = 0
        elif base in ("zh", "yue"):
            tier = 1
        elif base == "en":
            tier = 2
        else:
            tier = 3
        orig_bonus = 0 if lang.endswith("-orig") else 1  # prefer original auto-subs
        return (tier, orig_bonus, path.name)

    return sorted(candidates, key=rank)[0]


def _pick_video(out_dir: Path) -> Path | None:
    for ext in (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".opus"):
        for candidate in out_dir.glob(f"video*{ext}"):
            return candidate
    for candidate in out_dir.glob("video.*"):
        if candidate.suffix.lower() in VIDEO_EXTS:
            return candidate
    return None


# Bilibili rate-limits per (IP, User-Agent) and answers a tripped bucket with
# HTTP 412. Each distinct UA gets its own bucket and they recover in roughly ten
# minutes, so the way through is to try another identity rather than to pick the
# "correct" one — there isn't one. Measured 2026-09-07 against one video page:
# a bare request and the UA used minutes earlier both returned 412 while an
# unused UA went through on the first attempt, and the same pairing had been
# reversed ten minutes before that.
_UA_ROTATION: tuple[str | None, ...] = (
    None,  # yt-dlp's own UA
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:131.0) "
    "Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
)


def _run_ytdlp(cmd: list[str], url: str, succeeded) -> subprocess.CompletedProcess:
    """Run yt-dlp, rotating the UA past Bilibili's per-UA 412 rate limit.

    `succeeded` reports whether the attempt produced what the caller wanted;
    yt-dlp's exit code alone is not enough, since it exits non-zero when a
    subtitle variant fails even though the video downloaded.

    Only Bilibili rotates, and only when the user has not pinned a UA of their
    own — an explicit WATCH_YTDLP_USER_AGENT is a decision to respect, not a
    starting point. Every other site keeps the single-attempt behavior.
    """
    file_values = read_env_file()
    pinned = os.environ.get("WATCH_YTDLP_USER_AGENT") or file_values.get(
        "WATCH_YTDLP_USER_AGENT"
    )
    rotate = _is_bilibili(url) and not pinned
    attempts: tuple[str | None, ...] = _UA_ROTATION if rotate else (pinned,)

    result = None
    for i, ua in enumerate(attempts):
        attempt_cmd = list(cmd)
        if ua:
            attempt_cmd = [attempt_cmd[0], "--user-agent", ua, *attempt_cmd[1:]]
        # stdout carries the progress bar and stays live; stderr is captured so
        # a 412 can be recognized, then echoed so nothing is swallowed.
        result = subprocess.run(
            attempt_cmd, stdout=sys.stderr, stderr=subprocess.PIPE, text=True
        )
        if result.stderr:
            sys.stderr.write(result.stderr)
        if succeeded():
            return result
        if not rotate or "412" not in (result.stderr or ""):
            return result
        if i + 1 < len(attempts):
            print(
                f"[watch2] Bilibili returned 412 (per-UA rate limit); "
                f"retrying as a different client ({i + 2}/{len(attempts)})…",
                file=sys.stderr,
            )
    return result


def fetch_captions(url: str, out_dir: Path) -> dict:
    """Fetch metadata and best available VTT captions without downloading video."""
    if shutil.which("yt-dlp") is None:
        raise SystemExit("yt-dlp is not installed. Install with: brew install yt-dlp")

    out_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(out_dir / "video.%(ext)s")
    cmd = [
        "yt-dlp",
        *_ytdlp_auth_args(),
        *_ytdlp_site_args(url),
        "--skip-download",
        "--write-info-json",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", _sub_langs(),
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "--no-playlist",
        "--ignore-errors",
        "-o", output_template,
        "--",
        url,
    ]
    info_path = out_dir / "video.info.json"
    _run_ytdlp(cmd, url, succeeded=info_path.exists)
    info = _read_info(info_path, url)
    subtitle = _pick_subtitle(out_dir, prefer_lang=info.get("language"))
    return {
        "video_path": None,
        "subtitle_path": str(subtitle) if subtitle else None,
        "info": info or {"url": url},
        "downloaded": False,
    }


def _read_info(info_path: Path, url: str) -> dict:
    info: dict = {}
    if info_path.exists():
        try:
            raw = json.loads(info_path.read_text(encoding="utf-8"))
            info = {
                "title": raw.get("title"),
                "uploader": raw.get("uploader") or raw.get("channel"),
                "duration": raw.get("duration"),
                "language": raw.get("language"),
                "url": raw.get("webpage_url") or url,
            }
        except Exception as exc:
            print(f"[watch2] info.json parse failed: {exc}", file=sys.stderr)
            info = {"url": url}
    return info


def _download_failure_hint(url: str) -> str:
    """What to try when yt-dlp came back empty, most likely cause first.

    A stale yt-dlp leads because that is what an extractor break actually is:
    the site changed and the fix shipped in a release you do not have.
    """
    hints: list[str] = []

    from setup import YTDLP_STALE_DAYS, _ytdlp_age_days  # local: avoids a cycle

    age = _ytdlp_age_days()
    if age is not None and age > YTDLP_STALE_DAYS:
        hints.append(
            f"The installed yt-dlp is {age} days old. Site extractors break "
            "constantly and are fixed in releases, so update it first: "
            "`pipx upgrade yt-dlp` (or `brew upgrade yt-dlp`, `pip install -U yt-dlp`)."
        )
    if _is_youtube(url):
        hints.append(
            "If this is a YouTube anti-bot/JS-challenge failure, set "
            "WATCH_YTDLP_REMOTE_COMPONENTS=ejs:github in ~/.config/watch/.env to let "
            "yt-dlp fetch+run its remote JS solver (disabled by default)."
        )
    if _is_bilibili(url):
        hints.append(
            "Every UA in the rotation hit Bilibili's per-(IP, UA) rate limit. "
            "Buckets recover in about ten minutes — wait and retry. Cookies "
            "(WATCH_YTDLP_COOKIES_FROM_BROWSER) do not help here; they are for "
            "member-only or high-bitrate formats."
        )
    return (" " + " ".join(hints)) if hints else ""


def download_url(
    url: str,
    out_dir: Path,
    audio_only: bool = False,
) -> dict:
    if shutil.which("yt-dlp") is None:
        raise SystemExit("yt-dlp is not installed. Install with: brew install yt-dlp")

    out_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(out_dir / "video.%(ext)s")

    fmt = "ba/bestaudio" if audio_only else "bv*[height<=720]+ba/b[height<=720]/bv+ba/b"
    cmd = [
        "yt-dlp",
        *_ytdlp_auth_args(),
        *_ytdlp_site_args(url),
        "-N", "8",
        "-f", fmt,
        "--merge-output-format", "mp4",
        "--write-info-json",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", _sub_langs(),
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "--no-playlist",
        "--ignore-errors",
        "-o", output_template,
        "--",
        url,
    ]

    # yt-dlp may exit non-zero if a subtitle variant fails (e.g. 429) even when
    # the video itself downloaded fine. Treat "video file present" as success.
    result = _run_ytdlp(cmd, url, succeeded=lambda: _pick_video(out_dir) is not None)
    video = _pick_video(out_dir)
    if video is None:
        raise SystemExit(
            f"yt-dlp did not produce a video file in {out_dir} "
            f"(exit {result.returncode}).{_download_failure_hint(url)}"
        )

    info = _read_info(out_dir / "video.info.json", url)
    subtitle = _pick_subtitle(out_dir, prefer_lang=info.get("language"))

    return {
        "video_path": str(video),
        "subtitle_path": str(subtitle) if subtitle else None,
        "info": info or {"url": url},
        "downloaded": True,
    }


def download(
    source: str,
    out_dir: Path,
    audio_only: bool = False,
) -> dict:
    if is_url(source):
        return download_url(source, out_dir, audio_only=audio_only)
    return resolve_local(source)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: download.py <url-or-path> <out-dir>", file=sys.stderr)
        raise SystemExit(2)
    result = download(sys.argv[1], Path(sys.argv[2]))
    print(json.dumps(result, indent=2))
