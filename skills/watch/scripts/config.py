#!/usr/bin/env python3
"""Shared /watch configuration helpers."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from asr import PREFERENCE, PROVIDERS  # noqa: E402


CONFIG_DIR = Path.home() / ".config" / "watch"
CONFIG_FILE = CONFIG_DIR / ".env"

DEFAULT_DETAIL = "transcript"

# Where reports land. The transcript of an hour-long video is tens of thousands
# of tokens; it goes to a file so the agent reads what it needs instead of
# taking the whole thing through stdout.
DEFAULT_NOTES_DIR = Path.home() / "watch-notes"

DETAILS = {"transcript", "efficient", "balanced", "token-burner"}

DEFAULT_TRANSCRIBER = "auto"

# auto walks PREFERENCE until a key turns up; any provider name forces that one.
TRANSCRIBERS = {"auto", *PROVIDERS}


def read_env_file(path: Path | None = None) -> dict[str, str]:
    if path is None:
        path = CONFIG_FILE
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, _, value = raw.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
            value = value[1:-1]
        else:
            # Strip an inline comment (a '#' preceded by whitespace) from an
            # unquoted value. Without this, `WATCH_DETAIL=balanced  # note`
            # parses as "balanced  # note", fails validation, and silently
            # falls back to the default. Keeps '#' inside quotes / API keys.
            for i, ch in enumerate(value):
                if ch == "#" and i > 0 and value[i - 1] in " \t":
                    value = value[:i].rstrip()
                    break
        values[key.strip()] = value
    return values


def get_config() -> dict[str, object]:
    file_values = read_env_file()

    detail = (
        os.environ.get("WATCH_DETAIL")
        or file_values.get("WATCH_DETAIL")
        or DEFAULT_DETAIL
    )
    if detail not in DETAILS:
        detail = DEFAULT_DETAIL

    transcriber = (
        os.environ.get("WATCH_TRANSCRIBER")
        or file_values.get("WATCH_TRANSCRIBER")
        or DEFAULT_TRANSCRIBER
    )
    if transcriber not in TRANSCRIBERS:
        transcriber = DEFAULT_TRANSCRIBER

    notes_dir = (
        os.environ.get("WATCH_NOTES_DIR")
        or file_values.get("WATCH_NOTES_DIR")
        or ""
    ).strip()

    return {
        "detail": detail,
        "transcriber": transcriber,
        "notes_dir": Path(notes_dir).expanduser() if notes_dir else DEFAULT_NOTES_DIR,
        "config_file": str(CONFIG_FILE),
    }


def frame_cap(detail: str) -> int | None:
    if detail == "efficient":
        return 50
    if detail == "balanced":
        return 100
    if detail == "token-burner":
        return None
    if detail == "transcript":
        return None
    return 100
