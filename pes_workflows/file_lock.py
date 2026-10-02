"""POSIX workflow and commit locks owned by an ExitStack."""

from __future__ import annotations

import fcntl
from contextlib import ExitStack
from pathlib import Path
from typing import TextIO


def acquire_lock(resources: ExitStack, path: Path, *, blocking: bool = False) -> TextIO:
    """Hold an exclusive lock until stack exit, failing fast unless blocking is set."""
    lock = resources.enter_context(path.open("a"))
    flags = fcntl.LOCK_EX
    if not blocking:
        flags |= fcntl.LOCK_NB
    fcntl.flock(lock, flags)
    return lock
