"Provider-neutral LLM adapter contract and retry orchestration."

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence

from pes_workflows.config import Config

Message = Mapping[str, str]
ModelResponse = tuple[str, str]


class LLMResponseError(RuntimeError):
    "Raised when a provider returns no usable final response content."


class BaseLLMAdapter(ABC):
    "Normalize provider transports to one stateless generation interface."

    provider_name: str = "unknown"

    def __init__(
        self,
        model: str,
        *,
        logger: logging.Logger | None = None,
        max_retries: int = Config.MAX_RETRIES,
        initial_backoff: float = Config.RETRY_INITIAL_BACKOFF,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not model:
            raise ValueError("model must not be empty")
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        if initial_backoff < 0:
            raise ValueError("initial_backoff must not be negative")
        self.model: str = model
        self.logger: logging.Logger = logger or logging.getLogger(__name__)
        self.max_retries: int = max_retries
        self.initial_backoff: float = initial_backoff
        self._sleep: Callable[[float], None] = sleep

    def generate(
        self,
        messages: Sequence[Message],
        turn: int,
        team_name: str,
        user_id: str | None = None,
    ) -> ModelResponse:
        "Generate one response with uniform bounded exponential retries."

        backoff = self.initial_backoff
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._generate_once(
                    messages=messages,
                    turn=turn,
                    team_name=team_name,
                    user_id=user_id,
                )
            except Exception as error:
                if not self.is_retryable_error(error):
                    self.logger.error(
                        "[%s] %s request failed permanently on turn %s: %s",
                        team_name,
                        self.provider_name,
                        turn,
                        error,
                    )
                    raise
                self.logger.warning(
                    "[%s] %s request failed on turn %s (attempt %s/%s): %s",
                    team_name,
                    self.provider_name,
                    turn,
                    attempt,
                    self.max_retries,
                    error,
                )
                if attempt == self.max_retries:
                    raise
                self._sleep(backoff)
                backoff *= 2

        raise RuntimeError(f"{self.provider_name} retry loop ended unexpectedly")

    @abstractmethod
    def _generate_once(
        self,
        *,
        messages: Sequence[Message],
        turn: int,
        team_name: str,
        user_id: str | None,
    ) -> ModelResponse:
        "Execute exactly one provider request."

    @abstractmethod
    def is_retryable_error(self, error: BaseException) -> bool:
        "Return whether a provider or transport error is transient."


__all__ = ["BaseLLMAdapter", "LLMResponseError", "Message", "ModelResponse"]
