"""Shared filename helpers that preserve each workflow's naming policy."""

from __future__ import annotations

import re

_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_path_component(text: str) -> str:
    """Keep readable team names, replacing illegal characters and trailing dots."""
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("_", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(" .")
    return cleaned or "team"


def slugify(
    text: str, *, max_length: int = 40, lowercase: bool = False, fallback: str = ""
) -> str:
    """Produce a bounded Unicode slug using the caller's case and fallback policy."""
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s-]+", "_", text).strip("_")
    if lowercase:
        text = text.lower()
    return text[:max_length] or fallback
