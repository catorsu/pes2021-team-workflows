"""Generate and validate one independent model artifact."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from pes_workflows.config import Config
from pes_workflows.contracts.constants import SCHEMA_VERSION
from pes_workflows.contracts.errors import (
    ArtifactContractError,
    ArtifactSchemaError,
)
from pes_workflows.events import (
    NULL_OBSERVER,
    WORKFLOW_MATCH_PLAN,
    BuildObserver,
)
from pes_workflows.llm.artifacts import request_validated_artifact


def build_repair_prompt(error: ArtifactContractError) -> str:
    return (
        "CORRECT THE CURRENT JSON ARTIFACT ONLY.\n"
        f"Error kind: {error.kind}\n"
        f"JSON path: {error.path}\n"
        f"Constraint: {error.detail}\n\n"
        "Keep valid tactical decisions unchanged. Return exactly one complete, corrected "
        "JSON object for the current artifact: no Markdown fence, prose, or terminator."
    )


def request_artifact(
    *,
    call_model: Callable[..., Any],
    system_prompt: str,
    user_prompt: str,
    turn: int,
    artifact_name: str,
    output_name: str,
    team_name: str,
    user_id: str | None,
    validator: Callable[[dict[str, Any]], Any],
    logger: logging.Logger,
    preset: str | None = None,
    observer: BuildObserver = NULL_OBSERVER,
) -> Any:
    """Request one JSON artifact and repair only its rejected contract path.

    ``output_name`` is the event join key every consumer indexes teams by;
    ``team_name`` is the verbatim CSV spelling that reaches a human.
    """

    def validate(raw: dict[str, Any]) -> Any:
        if raw.get("Schema Version") != SCHEMA_VERSION:
            raise ArtifactSchemaError(
                artifact_name,
                "$.Schema Version",
                f"live generation requires {SCHEMA_VERSION!r}",
            )
        return validator(raw)

    return request_validated_artifact(
        call_model=call_model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        turn=turn,
        artifact_name=artifact_name,
        team_name=team_name,
        event_team=output_name,
        user_id=user_id,
        validator=validate,
        repair_prompt=build_repair_prompt,
        exhausted_error=lambda error, count: ArtifactContractError(
            artifact_name,
            error.path,
            f"failed after {count} correction(s): {error.detail}",
        ),
        max_repairs=Config.MAX_FORMAT_REPAIRS,
        logger=logger,
        workflow=WORKFLOW_MATCH_PLAN,
        preset=preset,
        observer=observer,
    )
