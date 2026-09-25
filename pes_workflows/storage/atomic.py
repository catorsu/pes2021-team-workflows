"""Atomic file publication and stable JSON hashing."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

_MAX_TEMP_PREFIX_BYTES = 64


def _bounded_temp_prefix(path: Path) -> str:
    """Build a collision-resistant temp prefix within filesystem limits."""

    direct = f".{path.name}."
    if len(direct.encode("utf-8")) <= _MAX_TEMP_PREFIX_BYTES:
        return direct

    digest = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:12]
    trailer = f".{digest}."
    retained = []
    retained_bytes = 0
    budget = _MAX_TEMP_PREFIX_BYTES - len(f".{trailer}".encode())
    for character in path.name:
        encoded_size = len(character.encode("utf-8"))
        if retained_bytes + encoded_size > budget:
            break
        retained.append(character)
        retained_bytes += encoded_size
    stem = "".join(retained) or "artifact"
    return f".{stem}{trailer}"


def stable_json_sha256(value: Any) -> str:
    """Hash JSON semantics independently of key insertion order or formatting."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_text_atomic(
    path: Path,
    content: str,
    *,
    replace: Callable[[Path, Path], None] = os.replace,
) -> None:
    """Publish complete UTF-8 text without translating its line endings."""
    write_bytes_atomic(path, content.encode("utf-8"), replace=replace)


def write_bytes_atomic(
    path: Path,
    content: bytes,
    *,
    replace: Callable[[Path, Path], None] = os.replace,
) -> None:
    """Publish complete binary content without exposing a truncated target."""

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=_bounded_temp_prefix(path),
            suffix=".tmp",
            delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        replace(temp_path, path)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logging.getLogger(__name__).exception(
                    "Failed to remove temporary file %s", temp_path
                )


__all__ = ["stable_json_sha256", "write_bytes_atomic", "write_text_atomic"]
