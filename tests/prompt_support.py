"""Read the task instructions out of a rendered user message.

Every user message opens with its call-scoped data blocks and closes with the
task, so a test double dispatches on the task header rather than on the
message's first line.
"""

from __future__ import annotations

import re

_TASK_HEADER = re.compile(r"^(?:STEP|STAGE) \d+[A-C]? OF \d+\b.*", re.MULTILINE)


def task_text(user_prompt: str) -> str:
    """The task instructions that follow a user message's data blocks."""

    match = _TASK_HEADER.search(user_prompt)
    if match is None:
        raise AssertionError(
            f"user message carries no task header: {user_prompt[:80]!r}"
        )
    return user_prompt[match.start() :]


__all__ = ["task_text"]
