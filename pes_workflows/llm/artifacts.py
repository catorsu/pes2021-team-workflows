"""Shared contract-repair loop for independently generated artifacts."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from pes_workflows.contracts.errors import ArtifactContractError
from pes_workflows.contracts.json_codec import parse_single_json_artifact
from pes_workflows.events import (
    ARTIFACT_FAILED,
    ARTIFACT_REPAIR,
    BuildObserver,
    emit_event,
    stage_for_artifact,
)

ArtifactT = TypeVar("ArtifactT")


def request_validated_artifact(
    *,
    call_model: Callable[..., tuple[str, str]],
    system_prompt: str,
    user_prompt: str,
    turn: int,
    artifact_name: str,
    team_name: str,
    event_team: str,
    user_id: str | None,
    validator: Callable[[dict[str, Any]], ArtifactT],
    repair_prompt: Callable[[ArtifactContractError], str],
    exhausted_error: Callable[[ArtifactContractError, int], ArtifactContractError],
    max_repairs: int,
    logger: logging.Logger,
    workflow: str,
    preset: str | None,
    observer: BuildObserver,
) -> tuple[ArtifactT, dict[str, Any]]:
    if max_repairs < 0:
        raise ValueError("max_repairs must not be negative")
    base_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    messages = list(base_messages)
    repairs: list[dict[str, str]] = []
    stage = stage_for_artifact(artifact_name)
    event_fields: dict[str, Any] = dict(
        team=event_team,
        turn=turn,
        artifact_name=artifact_name,
        stage=stage,
        preset=preset,
        workflow=workflow,
    )
    for repair_index in range(max_repairs + 1):
        logger.info(
            "[%s] Call %d: requesting %s (attempt %d)",
            team_name,
            turn,
            artifact_name,
            repair_index + 1,
        )
        response, reasoning = call_model(messages, turn, team_name, user_id=user_id)
        try:
            raw = parse_single_json_artifact(response, artifact_name)
            accepted = validator(raw)
        except ArtifactContractError as error:
            details: dict[str, Any] = dict(
                error_kind=error.kind, json_path=error.path, detail=error.detail
            )
            if repair_index == max_repairs:
                emit_event(
                    observer,
                    ARTIFACT_FAILED,
                    **event_fields,
                    **details,
                    repairs=len(repairs),
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                raise exhausted_error(error, max_repairs) from error
            correction = repair_prompt(error)
            repairs.append(
                {
                    "error_kind": error.kind,
                    "json_path": error.path,
                    "validator_error": error.detail,
                    "repair_prompt": correction,
                }
            )
            logger.warning(
                "[%s] %s rejected at %s; requesting scoped correction: %s",
                team_name,
                artifact_name,
                error.path,
                error.detail,
            )
            emit_event(
                observer,
                ARTIFACT_REPAIR,
                **event_fields,
                **details,
                repair_index=repair_index + 1,
                max_repairs=max_repairs,
            )
            messages = base_messages + [
                {"role": "assistant", "content": response},
                {"role": "user", "content": correction},
            ]
            continue
        logger.info("[%s] Call %d: %s accepted", team_name, turn, artifact_name)
        return accepted, {
            "raw": raw,
            "response_content": response,
            "reasoning_content": reasoning,
            "repairs": repairs,
            "reasoning_available": bool(reasoning),
            "policy_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        }
    raise RuntimeError(f"{artifact_name} correction loop ended unexpectedly")
