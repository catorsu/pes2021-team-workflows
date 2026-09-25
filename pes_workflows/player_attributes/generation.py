"""Sequential two-call squad generation and publication workflow."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import traceback
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    TypeVar,
)

from pes_workflows.config import Config
from pes_workflows.contracts.errors import ArtifactContractError
from pes_workflows.contracts.json_codec import (
    canonical_json,
)
from pes_workflows.events import (
    ARTIFACT_COMPLETED,
    ARTIFACT_STARTED,
    ATTRIBUTE_STAGES,
    ATTRIBUTES_INJECTION_COMPLETED,
    ATTRIBUTES_INJECTION_FAILED,
    ATTRIBUTES_INJECTION_STARTED,
    ATTRIBUTES_MANIFEST_FINALIZE_FAILED,
    ATTRIBUTES_MANIFEST_FINALIZED,
    ATTRIBUTES_REPORTS_PUBLISHED,
    ATTRIBUTES_RUN_COMPLETED,
    ATTRIBUTES_RUN_FAILED,
    ATTRIBUTES_RUN_STARTED,
    NULL_OBSERVER,
    STAGE_INJECT,
    STAGE_PUBLISH,
    WORKFLOW_PLAYER_ATTRIBUTES,
    BuildObserver,
    emit_event,
    stage_for_artifact,
)
from pes_workflows.llm.artifacts import request_validated_artifact
from pes_workflows.llm.base import BaseLLMAdapter
from pes_workflows.reporting.player_attributes import (
    render_player_attribute_team_markdown,
)
from pes_workflows.storage.atomic import stable_json_sha256, write_text_atomic
from pes_workflows.storage.run_layout import (
    CONVERSATION_HISTORY_NAME,
    SYSTEM_PROMPT_NAME,
    new_run_id,
)

from .constants import PLAYER_ABILITIES_ARTIFACT, PLAYER_PROFILES_ARTIFACT
from .contracts import (
    PlayerAbilities,
    PlayerAttributeTeam,
    PlayerProfiles,
    merge_player_artifacts,
    validate_player_abilities,
    validate_player_profiles,
)
from .injection import (
    PlayerInjectionResult,
    inject_player_attributes,
    preflight_player_injection,
)
from .prompts import PlayerAttributePromptBuilder
from .sources import PlayerDesignTarget, TeamIdentity

logger = logging.getLogger("PES2021_PlayerAttributes")
_ArtifactT = TypeVar("_ArtifactT", PlayerProfiles, PlayerAbilities)


@dataclass(frozen=True, slots=True)
class PlayerAttributeBuildResult:
    """Artifacts and commit summary for one complete squad build."""

    profiles: PlayerProfiles
    abilities: PlayerAbilities
    team: PlayerAttributeTeam
    profiles_path: Path
    abilities_path: Path
    config_path: Path
    report_path: Path
    manifest_path: Path
    injection: PlayerInjectionResult
    manifest_finalized: bool
    manifest_finalization_error: str | None


def build_scoped_repair_prompt(
    error: ArtifactContractError,
    *,
    artifact_name: str,
    immutable_context: Mapping[str, object],
) -> str:
    """Request one full-object correction while identifying one rejected path."""

    context = json.dumps(dict(immutable_context), ensure_ascii=False, sort_keys=True)
    return (
        f"CORRECT THE CURRENT {artifact_name} JSON OBJECT ONLY.\n"
        f"Error kind: {error.kind}\n"
        f"JSON path: {error.path}\n"
        f"Constraint: {error.detail}\n"
        f"Immutable source context: {context}\n\n"
        "Change only what is required to satisfy that path and its direct invariant. "
        "Preserve every valid team identity, player identity, roster position, order, "
        "and already-valid decision. Return exactly one complete corrected bare JSON "
        "object with no Markdown fence, prose, or extra value."
    )


def _request_validated_artifact(
    *,
    call_model: Callable[..., tuple[str, str]],
    system_prompt: str,
    user_prompt: str,
    artifact_name: str,
    validator: Callable[[Mapping[str, Any]], _ArtifactT],
    immutable_context: Mapping[str, object],
    turn: int,
    team_name: str,
    user_id: str,
    event_logger: logging.Logger,
    observer: BuildObserver = NULL_OBSERVER,
) -> tuple[_ArtifactT, dict[str, Any]]:
    """Make one squad call under the shared contract-repair budget."""

    accepted, record = request_validated_artifact(
        call_model=call_model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        turn=turn,
        artifact_name=artifact_name,
        team_name=team_name,
        event_team=team_name,
        user_id=user_id,
        validator=validator,
        repair_prompt=lambda error: build_scoped_repair_prompt(
            error, artifact_name=artifact_name, immutable_context=immutable_context
        ),
        exhausted_error=lambda error, count: type(error)(
            artifact_name,
            error.path,
            f"failed after {count} scoped correction(s): {error.detail}",
        ),
        max_repairs=Config.MAX_FORMAT_REPAIRS,
        logger=event_logger,
        workflow=WORKFLOW_PLAYER_ATTRIBUTES,
        preset=None,
        observer=observer,
    )
    raw = accepted.to_dict()
    record.pop("response_content")
    record.update(
        artifact=artifact_name,
        raw=raw,
        artifact_sha256=stable_json_sha256(raw),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    return accepted, record


def _call_audit(record: Mapping[str, Any]) -> dict[str, Any]:
    """The manifest's projection of one call record.

    The manifest is the index over a run, not a second copy of it: the prompts,
    the reasoning and the correction requests live in the turn artifacts beside
    it, and only the error trail and the digests are repeated here.
    """

    repairs = record.get("repairs") or []
    return {
        "artifact": record["artifact"],
        "artifact_sha256": record["artifact_sha256"],
        "repairs": [
            {
                "error_kind": repair["error_kind"],
                "json_path": repair["json_path"],
                "validator_error": repair["validator_error"],
            }
            for repair in repairs
        ],
        "reasoning_available": bool(record.get("reasoning_available")),
    }


# Both calls are issued under one static policy. Everything that differs between
# them — ``PLAYER_INPUT`` in each, ``FROZEN_PLAYER_PROFILES`` in Call 2 — travels
# in the user message, which the conversation history archives per call
def render_system_prompt_dump(team_name: str, system_prompt: str) -> str:
    """Archive the one fully expanded system prompt the whole run is issued under.

    Written before Call 1, so a run that dies mid pipeline still archives the
    policy every request it made was issued under.
    """

    digest = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
    lines = [
        f"# Complete API System Prompt - {team_name}",
        "",
        f"- Policy SHA-256: `{digest}`",
        "",
        system_prompt.rstrip(),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _history_record(
    record: Mapping[str, Any],
    *,
    turn: int,
    source_sha256: str,
    parent_artifact_sha256: Sequence[str],
) -> dict[str, Any]:
    """One conversation-history entry.

    Carries whether reasoning was returned, never the reasoning itself: the
    thinking process belongs to the turn page a reader opens deliberately, not
    to the machine-readable index every history reader parses.
    """

    return {
        "turn": turn,
        "title": record["artifact"],
        "artifact_type": record["artifact"],
        "format_repairs": record["repairs"],
        "accepted_artifact": record["raw"],
        "reasoning_tokens_returned": bool(record["reasoning_available"]),
        "schema_version": record["raw"]["Schema Version"],
        "source_sha256": source_sha256,
        "policy_sha256": record["policy_sha256"],
        "artifact_sha256": record["artifact_sha256"],
        "parent_artifact_sha256": list(parent_artifact_sha256),
    }


def _bracketed_artifact_request(
    *,
    observer: BuildObserver,
    team_name: str,
    turn: int,
    artifact_name: str,
    request: Callable[[], tuple[Any, dict[str, Any]]],
) -> tuple[Any, dict[str, Any]]:
    """Wrap one squad call in the ``artifact_started``/``_completed`` bracket."""

    stage = stage_for_artifact(artifact_name)
    emit_event(
        observer,
        ARTIFACT_STARTED,
        team=team_name,
        turn=turn,
        artifact_name=artifact_name,
        stage=stage,
        preset=None,
        turn_index=turn,
        turn_total=2,
        parallel=False,
        workflow=WORKFLOW_PLAYER_ATTRIBUTES,
    )
    started_at = time.monotonic()
    accepted, audit = request()
    repairs = audit.get("repairs") or []
    emit_event(
        observer,
        ARTIFACT_COMPLETED,
        team=team_name,
        turn=turn,
        artifact_name=artifact_name,
        stage=stage,
        preset=None,
        turn_index=turn,
        turn_total=2,
        repairs=len(repairs),
        repair_paths=[item.get("json_path") for item in repairs],
        reasoning_available=bool(audit.get("reasoning_available")),
        artifact_sha256=audit.get("artifact_sha256"),
        elapsed_s=time.monotonic() - started_at,
        workflow=WORKFLOW_PLAYER_ATTRIBUTES,
    )
    return accepted, audit


def request_player_profiles(
    *,
    call_model: Callable[..., tuple[str, str]],
    system_prompt: str,
    user_prompt: str,
    team: TeamIdentity,
    targets: Sequence[PlayerDesignTarget],
    user_id: str,
    event_logger: logging.Logger = logger,
    observer: BuildObserver = NULL_OBSERVER,
) -> tuple[PlayerProfiles, dict[str, Any]]:
    """Generate and validate the single squad-wide Call 1 artifact."""

    identities = [target.identity_contract() for target in targets]
    return _bracketed_artifact_request(
        observer=observer,
        team_name=team.name,
        turn=1,
        artifact_name=PLAYER_PROFILES_ARTIFACT,
        request=lambda: _request_validated_artifact(
            call_model=call_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            artifact_name=PLAYER_PROFILES_ARTIFACT,
            validator=lambda raw: validate_player_profiles(
                raw, expected_sources=identities, expected_team=team
            ),
            immutable_context={
                "Team Name": team.name,
                "Team ID": team.team_id,
                "Players": identities,
            },
            turn=1,
            team_name=team.name,
            user_id=user_id,
            event_logger=event_logger,
            observer=observer,
        ),
    )


def request_player_abilities(
    *,
    call_model: Callable[..., tuple[str, str]],
    system_prompt: str,
    user_prompt: str,
    profiles: PlayerProfiles,
    user_id: str,
    event_logger: logging.Logger = logger,
    observer: BuildObserver = NULL_OBSERVER,
) -> tuple[PlayerAbilities, dict[str, Any]]:
    """Generate and validate the single squad-wide Call 2 artifact."""

    identities = [
        {
            "Player ID": player.player_id,
            "Player Name": player.player_name,
            "Age": player.age,
        }
        for player in profiles.players
    ]
    return _bracketed_artifact_request(
        observer=observer,
        team_name=profiles.team_name,
        turn=2,
        artifact_name=PLAYER_ABILITIES_ARTIFACT,
        request=lambda: _request_validated_artifact(
            call_model=call_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            artifact_name=PLAYER_ABILITIES_ARTIFACT,
            validator=lambda raw: validate_player_abilities(raw, profiles=profiles),
            immutable_context={
                "Frozen PlayerProfiles SHA-256": stable_json_sha256(profiles.to_dict()),
                "Team Name": profiles.team_name,
                "Team ID": profiles.team_id,
                "Players": identities,
            },
            turn=2,
            team_name=profiles.team_name,
            user_id=user_id,
            event_logger=event_logger,
            observer=observer,
        ),
    )


_TEAM_SLUG_MAX_CHARS = 32


def _team_slug(team_name: str) -> str:
    """A filesystem-safe, bounded run-directory component for one team."""

    slug = re.sub(r"[^\w\s-]", "", team_name, flags=re.UNICODE)
    slug = re.sub(r"[\s-]+", "_", slug).strip("_").lower()
    return slug[:_TEAM_SLUG_MAX_CHARS] or "team"


def _prepare_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / f".player_attributes_probe_{uuid.uuid4().hex}"
    try:
        write_text_atomic(probe, "")
    finally:
        probe.unlink(missing_ok=True)


def _paths_alias(first: Path, second: Path) -> bool:
    if first.resolve() == second.resolve():
        return True
    try:
        return first.samefile(second)
    except (FileNotFoundError, OSError):
        return False


class PlayerAttributeRunner:
    """Run Call 1 then Call 2 for the complete squad and inject once."""

    def __init__(
        self,
        *,
        output_base_dir: Path,
        model: str = Config.DEFAULT_MODEL,
        prompt_builder: PlayerAttributePromptBuilder | None = None,
        dry_run: bool = False,
        llm_adapter: BaseLLMAdapter,
        observer: BuildObserver = NULL_OBSERVER,
    ) -> None:
        self.output_base_dir: Path = Path(output_base_dir)
        self.model: str = model
        self.llm_adapter: BaseLLMAdapter = llm_adapter
        self.prompt_builder: PlayerAttributePromptBuilder = (
            prompt_builder or PlayerAttributePromptBuilder()
        )
        self.dry_run: bool = dry_run
        self._observer: BuildObserver = observer

    def run(
        self,
        *,
        team: TeamIdentity,
        targets: Sequence[PlayerDesignTarget],
        players_csv: Path,
    ) -> PlayerAttributeBuildResult:
        observer = self._observer
        run_started_at = time.monotonic()
        logger.info(
            "[%s] Player Attributes generation started: %d players, "
            "model=%s, dry_run=%s",
            team.name,
            len(targets),
            self.model,
            self.dry_run,
        )
        try:
            return self._run(
                team=team,
                targets=targets,
                players_csv=players_csv,
                observer=observer,
                run_started_at=run_started_at,
            )
        except Exception as err:
            emit_event(
                observer,
                ATTRIBUTES_RUN_FAILED,
                team=team.name,
                team_id=team.team_id,
                reason="exception",
                dry_run=self.dry_run,
                csv_modified=False,
                error_type=type(err).__name__,
                error_message=str(err),
                traceback="".join(
                    traceback.format_exception(type(err), err, err.__traceback__)
                ),
                elapsed_s=time.monotonic() - run_started_at,
            )
            raise

    def _run(
        self,
        *,
        team: TeamIdentity,
        targets: Sequence[PlayerDesignTarget],
        players_csv: Path,
        observer: BuildObserver,
        run_started_at: float,
    ) -> PlayerAttributeBuildResult:
        targets = tuple(targets)
        if not targets:
            raise ValueError("targets must contain at least one player")
        if len({target.player_id for target in targets}) != len(targets):
            raise ValueError("targets must not contain duplicate Player IDs")

        players_csv = Path(players_csv)
        source_sha256 = preflight_player_injection(
            players_csv=players_csv,
            target_ids=(target.player_id for target in targets),
            require_commit=not self.dry_run,
        )
        bound_digests = {
            target.source_players_sha256
            for target in targets
            if target.source_players_sha256 is not None
        }
        if len(bound_digests) > 1 or (
            bound_digests and source_sha256 not in bound_digests
        ):
            raise RuntimeError(
                f"{players_csv}: source snapshot changed since roster resolution"
            )

        team_dir = self.output_base_dir / (
            f"{_team_slug(team.name)}__{team.kind.lower()}_{team.team_id}"
        )
        run_dir = team_dir / new_run_id()
        _prepare_directory(run_dir)
        profiles_path = run_dir / "player_profiles.json"
        abilities_path = run_dir / "player_abilities.json"
        config_path = run_dir / "player_attributes.json"
        report_path = run_dir / "player_attributes.md"
        manifest_path = run_dir / "generation_manifest.json"
        system_prompt_path = run_dir / SYSTEM_PROMPT_NAME
        history_path = run_dir / CONVERSATION_HISTORY_NAME
        protected_paths = (
            profiles_path,
            abilities_path,
            config_path,
            report_path,
            manifest_path,
            system_prompt_path,
            history_path,
        )
        # A standing write fence rather than a reachable branch: every name
        # above is a distinct literal under this run's own fresh directory, so
        # the only way one of them can address the editor database is a
        # configured players path that reaches inside the output root
        for path in protected_paths:
            if _paths_alias(path, players_csv):
                raise ValueError(f"output path must not point to Players.csv: {path}")

        user_id = self._generate_user_id(team)
        emit_event(
            observer,
            ATTRIBUTES_RUN_STARTED,
            team=team.name,
            team_id=team.team_id,
            team_kind=team.kind,
            model=self.model,
            dry_run=self.dry_run,
            player_count=len(targets),
            player_ids=[target.player_id for target in targets],
            run_dir=str(run_dir),
            players_csv=str(players_csv),
            source_sha256=source_sha256,
            user_id=user_id,
            stages=list(ATTRIBUTE_STAGES),
            workflow=WORKFLOW_PLAYER_ATTRIBUTES,
        )

        system_prompt, profiles_prompt = self.prompt_builder.build_profiles_call(
            team, targets
        )
        write_text_atomic(
            system_prompt_path, render_system_prompt_dump(team.name, system_prompt)
        )
        profiles, profiles_record = request_player_profiles(
            call_model=self._call_model,
            system_prompt=system_prompt,
            user_prompt=profiles_prompt,
            team=team,
            targets=targets,
            user_id=user_id,
            observer=observer,
        )
        # The frozen artifact carried into Call 2's user message is the
        # canonical, accepted Call 1 object; the roster is re-supplied unchanged
        # beside it, under the same system prompt already archived above
        _, abilities_prompt = self.prompt_builder.build_abilities_call(
            team, targets, profiles
        )
        abilities, abilities_record = request_player_abilities(
            call_model=self._call_model,
            system_prompt=system_prompt,
            user_prompt=abilities_prompt,
            profiles=profiles,
            user_id=user_id,
            observer=observer,
        )
        profiles_parents: tuple[str, ...] = ()
        abilities_parents = (profiles_record["artifact_sha256"],)
        write_text_atomic(
            history_path,
            json.dumps(
                [
                    _history_record(
                        profiles_record,
                        turn=1,
                        source_sha256=source_sha256,
                        parent_artifact_sha256=profiles_parents,
                    ),
                    _history_record(
                        abilities_record,
                        turn=2,
                        source_sha256=source_sha256,
                        parent_artifact_sha256=abilities_parents,
                    ),
                ],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        accepted_team = merge_player_artifacts(profiles, abilities, team_kind=team.kind)

        write_text_atomic(profiles_path, canonical_json(profiles.to_dict()) + "\n")
        write_text_atomic(abilities_path, canonical_json(abilities.to_dict()) + "\n")
        write_text_atomic(config_path, canonical_json(accepted_team.to_dict()) + "\n")
        write_text_atomic(
            report_path, render_player_attribute_team_markdown(accepted_team)
        )
        # Built once and mutated in place through the status transitions, so
        # every rewrite below carries the same identity keys
        manifest: dict[str, Any] = {
            "status": "prepared",
            "model": self.model,
            "team": {
                "name": team.name,
                "kind": team.kind,
                "id": team.team_id,
            },
            "players_csv_source_sha256": source_sha256,
            "profile_count": len(targets),
            "calls": [_call_audit(profiles_record), _call_audit(abilities_record)],
            "artifacts": {
                "player_profiles": profiles_path.name,
                "player_abilities": abilities_path.name,
                "merged_player_attributes": config_path.name,
                "report": report_path.name,
                "system_prompt": system_prompt_path.name,
                "conversation_history": history_path.name,
            },
        }
        write_text_atomic(manifest_path, canonical_json(manifest) + "\n")
        logger.info("[%s] Reports published to %s", team.name, run_dir)
        emit_event(
            observer,
            ATTRIBUTES_REPORTS_PUBLISHED,
            team=team.name,
            stage=STAGE_PUBLISH,
            profiles_path=str(profiles_path),
            abilities_path=str(abilities_path),
            config_path=str(config_path),
            report_path=str(report_path),
            manifest_path=str(manifest_path),
            player_count=len(targets),
            manifest_status="prepared",
        )

        emit_event(
            observer,
            ATTRIBUTES_INJECTION_STARTED,
            team=team.name,
            stage=STAGE_INJECT,
            players_csv=str(players_csv),
            dry_run=self.dry_run,
            target_count=len(targets),
            expected_players_sha256=source_sha256,
        )
        logger.info(
            "[%s] %s player attributes for %s",
            team.name,
            "Validating without database writes" if self.dry_run else "Applying",
            players_csv,
        )
        try:
            injection = inject_player_attributes(
                players_csv=players_csv,
                team=accepted_team,
                dry_run=self.dry_run,
                expected_players_sha256=source_sha256,
            )
        except BaseException as injection_error:
            manifest["status"] = "injection_failed"
            emit_event(
                observer,
                ATTRIBUTES_INJECTION_FAILED,
                team=team.name,
                stage=STAGE_INJECT,
                dry_run=self.dry_run,
                csv_modified=False,
                players_csv=str(players_csv),
                manifest_status="injection_failed",
                error_type=type(injection_error).__name__,
                error_message=str(injection_error),
                traceback="".join(
                    traceback.format_exception(
                        type(injection_error),
                        injection_error,
                        injection_error.__traceback__,
                    )
                ),
            )
            try:
                write_text_atomic(manifest_path, canonical_json(manifest) + "\n")
            except OSError as failure_record_error:
                logger.exception(
                    "Could not record injection failure in %s", manifest_path
                )
                emit_event(
                    observer,
                    ATTRIBUTES_MANIFEST_FINALIZE_FAILED,
                    team=team.name,
                    manifest_path=str(manifest_path),
                    phase="injection_failure_record",
                    status_attempted="injection_failed",
                    error_type="OSError",
                    error_message=str(failure_record_error),
                    players_csv_written=False,
                    warning_state=None,
                    severity="warning",
                )
            raise

        manifest["status"] = "validated" if self.dry_run else "injected"
        manifest["players_csv_result_sha256"] = injection.players_sha256_after
        emit_event(
            observer,
            ATTRIBUTES_INJECTION_COMPLETED,
            team=team.name,
            stage=STAGE_INJECT,
            outcome=manifest["status"],
            dry_run=self.dry_run,
            csv_modified=not self.dry_run,
            modified_count=injection.modified_count,
            players_sha256_before=injection.players_sha256_before,
            players_sha256_after=injection.players_sha256_after,
        )
        manifest_finalized = True
        manifest_error: str | None = None
        unfinalized_warning_state = (
            "injected_manifest_unfinalized"
            if not self.dry_run
            else "validated_manifest_unfinalized"
        )
        try:
            write_text_atomic(manifest_path, canonical_json(manifest) + "\n")
        except OSError as error:
            manifest_finalized = False
            manifest_error = str(error)
            logger.critical(
                "Could not finalize audit manifest %s: %s", manifest_path, error
            )
            # A warning state, never a failure — only the audit record is
            # incomplete
            emit_event(
                observer,
                ATTRIBUTES_MANIFEST_FINALIZE_FAILED,
                team=team.name,
                manifest_path=str(manifest_path),
                phase="finalize",
                status_attempted=manifest["status"],
                error_type="OSError",
                error_message=str(error),
                players_csv_written=not self.dry_run,
                warning_state=unfinalized_warning_state,
                severity="warning",
            )
        else:
            emit_event(
                observer,
                ATTRIBUTES_MANIFEST_FINALIZED,
                team=team.name,
                manifest_path=str(manifest_path),
                status=manifest["status"],
                players_csv_result_sha256=injection.players_sha256_after,
            )

        logger.info(
            "[%s] %s; %d players, manifest finalized=%s (%.1fs)",
            team.name,
            "Generated (not applied)" if self.dry_run else "Applied to database",
            len(targets),
            manifest_finalized,
            time.monotonic() - run_started_at,
        )
        emit_event(
            observer,
            ATTRIBUTES_RUN_COMPLETED,
            team=team.name,
            team_id=team.team_id,
            status=(
                manifest["status"] if manifest_finalized else unfinalized_warning_state
            ),
            warning_state=None if manifest_finalized else unfinalized_warning_state,
            manifest_finalized=manifest_finalized,
            dry_run=self.dry_run,
            csv_modified=not self.dry_run,
            run_dir=str(run_dir),
            manifest_path=str(manifest_path),
            config_path=str(config_path),
            report_path=str(report_path),
            modified_count=injection.modified_count,
            elapsed_s=time.monotonic() - run_started_at,
        )
        return PlayerAttributeBuildResult(
            profiles=profiles,
            abilities=abilities,
            team=accepted_team,
            profiles_path=profiles_path,
            abilities_path=abilities_path,
            config_path=config_path,
            report_path=report_path,
            manifest_path=manifest_path,
            injection=injection,
            manifest_finalized=manifest_finalized,
            manifest_finalization_error=manifest_error,
        )

    def _call_model(
        self,
        messages: list[dict[str, str]],
        turn: int,
        team_name: str,
        user_id: str | None = None,
    ) -> tuple[str, str]:
        return self.llm_adapter.generate(messages, turn, team_name, user_id=user_id)

    @staticmethod
    def _generate_user_id(team: TeamIdentity) -> str:
        digest = hashlib.md5(
            f"{team.name}:{team.kind}:{team.team_id}".encode()
        ).hexdigest()[:16]
        return f"pes_attributes_{digest}"


__all__ = [
    "PlayerAttributeBuildResult",
    "PlayerAttributeRunner",
    "build_scoped_repair_prompt",
    "render_system_prompt_dump",
    "request_player_abilities",
    "request_player_profiles",
]
