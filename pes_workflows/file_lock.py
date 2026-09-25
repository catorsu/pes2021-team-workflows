"""Nonblocking POSIX workflow locks owned by an ExitStack."""

from __future__ import annotations

import fcntl
from contextlib import ExitStack
from pathlib import Path
from typing import TextIO


def acquire_lock(resources: ExitStack, path: Path) -> TextIO:
    lock = resources.enter_context(path.open("a"))
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return lock
