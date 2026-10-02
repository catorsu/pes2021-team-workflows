"""Audited attribute requests and workflow event recording."""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from pathlib import Path

from pes_workflows.checkpoint_io import save
from pes_workflows.claude_cli import ClaudeCodeSubprocessAdapter, CodexSubprocessAdapter
from pes_workflows.config import CHOICES, Config
from pes_workflows.events import BuildEvent
from pes_workflows.llm.base import BaseLLMAdapter, Message, ModelResponse
from pes_workflows.storage.atomic import write_text_atomic


class _VerbatimResponse:
    @staticmethod
    def _extract_clean_json(text: str) -> str:
        # Let the contract parser inspect the entire final response.
        return text.strip()


class _AttributeClaudeAdapter(_VerbatimResponse, ClaudeCodeSubprocessAdapter):
    pass


class _AttributeCodexAdapter(_VerbatimResponse, CodexSubprocessAdapter):
    pass


class AuditedAdapter(BaseLLMAdapter):
    """Audit each transport attempt under the shared retry and artifact contracts.

    Stages and repairs use the same engine and tool scope. The outer retry loop
    invokes exactly one transport attempt at a time so no retry bypasses auditing.
    Claude enforces max_turns; Codex currently has no equivalent CLI ceiling.
    """

    def __init__(
        self,
        audit_dir: Path,
        *,
        engine: str = "claude-code",
        model: str | None = None,
        effort: str = Config.DEFAULT_EFFORT,
        delay: float = 5.0,
        fast_mode: bool = False,
        max_turns: int = Config.DEFAULT_PLAYER_ATTRIBUTE_MAX_TURNS,
        allowed_tools: tuple[str, ...] = ("WebSearch", "WebFetch"),
    ) -> None:
        if engine not in CHOICES["engine"]:
            raise ValueError(f"engine must be one of {CHOICES['engine']}")
        if type(max_turns) is not int or max_turns < 1:
            raise ValueError("max_turns must be a positive integer")
        self.engine: str = engine
        self._transport: BaseLLMAdapter
        if engine == "codex":
            if allowed_tools not in ((), ("WebSearch", "WebFetch")):
                raise ValueError("Codex hosted web research combines search and fetch")
            self._transport = _AttributeCodexAdapter(
                model=model
                if model is not None
                else CodexSubprocessAdapter.DEFAULT_MODEL,
                effort=effort,
                delay=delay,
                fast_mode=fast_mode,
                web_search=bool(allowed_tools),
            )
        else:
            self._transport = _AttributeClaudeAdapter(
                model=model if model is not None else Config.DEFAULT_MODEL,
                effort=effort,
                delay=delay,
                fast_mode=fast_mode,
                max_turns=max_turns,
                allowed_tools=allowed_tools,
            )
        super().__init__(model=self._transport.model, logger=self._transport.logger)
        self.provider_name = self._transport.provider_name
        self.audit_dir: Path = audit_dir
        self.sequence: int = 0
        self.transport_metadata = {
            "engine": engine,
            "provider": self.provider_name,
            "model": self.model,
            "effort": effort,
            "fast_mode": fast_mode,
            "tools": (["web_search"] if allowed_tools else [])
            if engine == "codex"
            else list(allowed_tools),
            "max_turns": max_turns,
            "max_turns_enforced": engine == "claude-code",
        }
        if engine == "codex":
            self.logger.warning(
                "Codex has no native turn ceiling; max_turns=%s applies only to "
                "Claude Code. Codex manages its tool loop and context compaction.",
                max_turns,
            )

    def is_retryable_error(self, error: BaseException) -> bool:
        return self._transport.is_retryable_error(error)

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
        save(
            stem.with_suffix(".request.json"),
            {**kwargs, "transport": self.transport_metadata},
        )
        try:
            answer = self._transport._generate_once(
                messages=messages, turn=turn, team_name=team_name, user_id=user_id
            )
            write_text_atomic(stem.with_suffix(".response.txt"), answer[0])
            return answer
        except BaseException as error:
            save(
                stem.with_suffix(".error.json"),
                {"error": str(error), "error_type": type(error).__name__},
            )
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
