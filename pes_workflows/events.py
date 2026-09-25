"""Structured progress events and the null observer."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

_logger = logging.getLogger(__name__)

_EMPTY_PAYLOAD: Mapping[str, Any] = MappingProxyType({})


WORKFLOW_MATCH_PLAN = "match_plan"
WORKFLOW_PLAYER_ATTRIBUTES = "player_attributes"

STAGE_XI_LOCK = "xi_lock"
STAGE_PRESET_PLAN = "preset_plan"
STAGE_BENCH = "bench"
STAGE_COMPILE = "compile"
STAGE_INJECT = "inject"
STAGE_CALL_1 = "call_1"
STAGE_CALL_2 = "call_2"
STAGE_PUBLISH = "publish"
STAGE_PREFLIGHT = "preflight"

MATCH_PLAN_STAGES = (
    STAGE_XI_LOCK,
    STAGE_PRESET_PLAN,
    STAGE_BENCH,
    STAGE_COMPILE,
    STAGE_INJECT,
)
ATTRIBUTE_STAGES = (STAGE_CALL_1, STAGE_CALL_2, STAGE_PUBLISH, STAGE_INJECT)

STAGE_BY_ARTIFACT: Mapping[str, str] = MappingProxyType(
    {
        "StartingXILock": STAGE_XI_LOCK,
        "PresetPlan": STAGE_PRESET_PLAN,
        "BenchDecision": STAGE_BENCH,
        "PlayerProfiles": STAGE_CALL_1,
        "PlayerAbilities": STAGE_CALL_2,
    }
)


def stage_for_artifact(artifact_name: str) -> str:
    """Map a contract artifact name onto its stage."""

    return STAGE_BY_ARTIFACT.get(artifact_name, artifact_name)


TEAM_STARTED = "team_started"

# Artifact lifecycle, shared by both workflows. Consumers disambiguate on
# ``payload["workflow"]`` plus ``payload["artifact_name"]`` because both
# pipelines number their turns from 1
ARTIFACT_STARTED = "artifact_started"
ARTIFACT_COMPLETED = "artifact_completed"
ARTIFACT_REPAIR = "artifact_repair"
ARTIFACT_FAILED = "artifact_failed"

COMPILE_STARTED = "compile_started"
COMPILE_COMPLETED = "compile_completed"
COMPILE_FAILED = "compile_failed"
INJECTION_WAITING_LOCK = "injection_waiting_lock"
INJECTION_STARTED = "injection_started"
INJECTION_LINE = "injection_line"
INJECTION_COMPLETED = "injection_completed"
INJECTION_FAILED = "injection_failed"


ATTRIBUTES_RUN_STARTED = "attributes_run_started"
ATTRIBUTES_REPORTS_PUBLISHED = "attributes_reports_published"
ATTRIBUTES_INJECTION_STARTED = "attributes_injection_started"
ATTRIBUTES_INJECTION_COMPLETED = "attributes_injection_completed"
ATTRIBUTES_INJECTION_FAILED = "attributes_injection_failed"
ATTRIBUTES_MANIFEST_FINALIZED = "attributes_manifest_finalized"
ATTRIBUTES_MANIFEST_FINALIZE_FAILED = "attributes_manifest_finalize_failed"
ATTRIBUTES_RUN_COMPLETED = "attributes_run_completed"
ATTRIBUTES_RUN_FAILED = "attributes_run_failed"


@dataclass(frozen=True, slots=True)
class BuildEvent:
    """One immutable progress fact."""

    kind: str
    team: str | None = None
    turn: int | None = None
    payload: Mapping[str, Any] = _EMPTY_PAYLOAD
    timestamp: float = field(default_factory=time.time)


@runtime_checkable
class BuildObserver(Protocol):
    """Single-method sink, so new event kinds never break implementors."""

    def on_event(self, event: BuildEvent) -> None: ...


class _NullObserver:
    """Thread-safe no-op observer; the default everywhere."""

    __slots__ = ()

    def on_event(self, event: BuildEvent) -> None:
        return None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "NULL_OBSERVER"


NULL_OBSERVER: BuildObserver = _NullObserver()


def emit_event(
    observer: BuildObserver | None,
    kind: str,
    *,
    team: str | None = None,
    turn: int | None = None,
    **payload: Any,
) -> None:
    """Deliver one event, isolating the pipeline from observer failures."""

    if observer is None or observer is NULL_OBSERVER:
        return
    event = BuildEvent(
        kind=kind,
        team=team,
        turn=turn,
        payload=MappingProxyType(dict(payload)),
    )
    try:
        observer.on_event(event)
    except Exception:
        _logger.debug("observer raised on %s event", kind, exc_info=True)


__all__ = [
    "ARTIFACT_COMPLETED",
    "ARTIFACT_FAILED",
    "ARTIFACT_REPAIR",
    "ARTIFACT_STARTED",
    "ATTRIBUTES_INJECTION_COMPLETED",
    "ATTRIBUTES_INJECTION_FAILED",
    "ATTRIBUTES_INJECTION_STARTED",
    "ATTRIBUTES_MANIFEST_FINALIZED",
    "ATTRIBUTES_MANIFEST_FINALIZE_FAILED",
    "ATTRIBUTES_REPORTS_PUBLISHED",
    "ATTRIBUTES_RUN_COMPLETED",
    "ATTRIBUTES_RUN_FAILED",
    "ATTRIBUTES_RUN_STARTED",
    "ATTRIBUTE_STAGES",
    "BuildEvent",
    "BuildObserver",
    "COMPILE_COMPLETED",
    "COMPILE_FAILED",
    "COMPILE_STARTED",
    "INJECTION_COMPLETED",
    "INJECTION_FAILED",
    "INJECTION_LINE",
    "INJECTION_STARTED",
    "INJECTION_WAITING_LOCK",
    "MATCH_PLAN_STAGES",
    "NULL_OBSERVER",
    "STAGE_BENCH",
    "STAGE_BY_ARTIFACT",
    "STAGE_CALL_1",
    "STAGE_CALL_2",
    "STAGE_COMPILE",
    "STAGE_INJECT",
    "STAGE_PREFLIGHT",
    "STAGE_PRESET_PLAN",
    "STAGE_PUBLISH",
    "STAGE_XI_LOCK",
    "TEAM_STARTED",
    "WORKFLOW_MATCH_PLAN",
    "WORKFLOW_PLAYER_ATTRIBUTES",
    "emit_event",
    "stage_for_artifact",
]
