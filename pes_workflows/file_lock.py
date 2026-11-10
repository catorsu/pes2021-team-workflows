"""Cross-platform (Windows and POSIX) workflow and commit locks owned by an ExitStack."""

from __future__ import annotations

import os
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from typing import TextIO

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


def acquire_lock(resources: ExitStack, path: Path, *, blocking: bool = False) -> TextIO:
    """Hold an exclusive lock until stack exit, failing fast unless blocking is set."""
    lock = resources.enter_context(path.open("a"))
    if sys.platform == "win32":
        fd = lock.fileno()
        while True:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                break
            except OSError as exc:
                if not blocking:
                    raise BlockingIOError(str(exc)) from exc
                time.sleep(0.05)

        def _unlock() -> None:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass

        resources.callback(_unlock)
        return lock
    else:
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        fcntl.flock(lock, flags)
        return lock
