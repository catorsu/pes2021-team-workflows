"""Expand shared prompt fragments without changing their original bytes."""

from __future__ import annotations

import re
from pathlib import Path

_INCLUDE = re.compile(rb"^<!-- INCLUDE ([^\r\n]+) -->\r?\n", re.MULTILINE)


def read_prompt_bytes(path: Path, *, _ancestors: tuple[Path, ...] = ()) -> bytes:
    resolved = path.resolve()
    if resolved in _ancestors:
        raise ValueError(f"Circular prompt include: {path}")
    return _INCLUDE.sub(
        lambda match: read_prompt_bytes(
            path.parent / match[1].decode("utf-8"),
            _ancestors=(*_ancestors, resolved),
        ),
        path.read_bytes(),
    )


def read_prompt_text(path: Path) -> str:
    # Match Path.read_text's universal-newline behavior after byte expansion.
    return (
        read_prompt_bytes(path)
        .decode("utf-8")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
