"""Audited attribute requests and workflow event recording."""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from pathlib import Path

from pes_workflows.checkpoint_io import save
from pes_workflows.claude_cli import ClaudeCodeSubprocessAdapter
from pes_workflows.config import Config
from pes_workflows.events import BuildEvent
from pes_workflows.llm.base import Message, ModelResponse
from pes_workflows.storage.atomic import write_text_atomic


class AuditedAdapter(ClaudeCodeSubprocessAdapter):
    """Shared web-enabled transport for player attributes.

    Each stage, contract repair and transport retry uses the same tool scope
    and CLI turn ceiling, with a separate request and response/error audit.
    """

    def __init__(
        self,
        audit_dir: Path,
        *,
        model: str = Config.DEFAULT_MODEL,
        effort: str = Config.DEFAULT_EFFORT,
        delay: float = 5.0,
        fast_mode: bool = False,
        max_turns: int = Config.DEFAULT_PLAYER_ATTRIBUTE_MAX_TURNS,
        allowed_tools: tuple[str, ...] = ("WebSearch", "WebFetch"),
    ) -> None:
        # ~30 players x (search + fetch), plus follow-ups and final JSON.
        # Per CLI request, including repairs; a ceiling, not a target.
        super().__init__(
            model=model,
            effort=effort,
            delay=delay,
            fast_mode=fast_mode,
            max_turns=max_turns,
            allowed_tools=allowed_tools,
        )
        self.audit_dir: Path = audit_dir
        self.sequence: int = 0

    @staticmethod
    def _extract_clean_json(text: str) -> str:
        # Let the contract parser inspect the entire response.
        return text.strip()

    def _generate_once(
        self,
        *,
        messages: Sequence[Message],
        turn: int,
        team_name: str,
        user_id: str | None,
    ) -> ModelResponse:
        kwargs = dict(
            messages=messages, turn=turn, team_name=team_name, user_id=user_id
        )
        self.sequence += 1
        stem = self.audit_dir / f"call_{time.time_ns()}_{self.sequence}"
        save(stem.with_suffix(".request.json"), kwargs)
        try:
            answer = super()._generate_once(
                messages=messages, turn=turn, team_name=team_name, user_id=user_id
            )
            write_text_atomic(stem.with_suffix(".response.txt"), answer[0])
            return answer
        except Exception as error:
            save(stem.with_suffix(".error.json"), {"error": str(error)})
            raise


class Observer:
    def __init__(self, path: Path) -> None:
        self.path: Path = path

    def on_event(self, event: BuildEvent) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "time": time.time(),
                        "kind": event.kind,
                        "team": event.team,
                        "turn": event.turn,
                        "payload": dict(event.payload),
                    },
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
