from __future__ import annotations

import mimetypes
import re
from datetime import datetime
from pathlib import Path, PurePath

INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str, fallback: str = "file", max_bytes: int = 240) -> str:
    name = PurePath(name or "").name
    name = INVALID.sub("_", name).strip(" .")
    if name in {"", ".", ".."}:
        name = fallback
    stem, suffix = Path(name).stem, Path(name).suffix[:20]
    while len((stem + suffix).encode("utf-8")) > max_bytes and stem:
        stem = stem[:-1]
    return (stem or fallback) + suffix


def fallback_filename(message_id: int, media_type: str, timestamp: datetime, mime_type: str | None = None) -> str:
    extension = mimetypes.guess_extension(mime_type or "") or ""
    return sanitize_filename(f"{message_id}_{media_type}_{timestamp:%Y%m%d_%H%M%S}{extension}")


def format_bytes(value: float) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if abs(value) < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} TB"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {sec}s" if hours else f"{minutes}m {sec}s"

