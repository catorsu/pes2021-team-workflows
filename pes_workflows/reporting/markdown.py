"""Escaping for dynamic text in Markdown headings, paragraphs, and tables."""

from __future__ import annotations

_ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\\": "\\\\",
    "|": "&#124;",
    "`": "\\`",
    "*": "\\*",
    "_": "\\_",
    "[": "\\[",
    "]": "\\]",
    "#": "\\#",
}


def escape_markdown(value: object) -> str:
    """Flatten text to one line and escape characters without re-escaping output."""
    text = " ".join(str(value).splitlines()).strip()
    return "".join(_ESCAPES.get(character, character) for character in text)
