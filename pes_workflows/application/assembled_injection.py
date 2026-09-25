"""Precompile and inject an assembled semantic game plan."""

from __future__ import annotations

import itertools
import json
import logging
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pes_workflows.compiler.compile import compile_semantic_game_plan
from pes_workflows.compiler.errors import SemanticGridError
from pes_workflows.compiler.injection import _inject_compiled_formation
from pes_workflows.config import Config, resolve_global_auto_options
from pes_workflows.csv_validation import validate_csv_file, validate_csv_target
from pes_workflows.events import (
    COMPILE_COMPLETED,
    COMPILE_FAILED,
    COMPILE_STARTED,
    INJECTION_COMPLETED,
    INJECTION_FAILED,
    INJECTION_LINE,
    INJECTION_STARTED,
    INJECTION_WAITING_LOCK,
    NULL_OBSERVER,
    STAGE_COMPILE,
    STAGE_INJECT,
    STAGE_PREFLIGHT,
    BuildObserver,
    emit_event,
)
from pes_workflows.storage.atomic import write_text_atomic


def annotate_failure(
    error: BaseException, *, stage: str, csv_modified: bool
) -> BaseException:
    """Tag an exception with the stage it escaped from and what it wrote."""

    setattr(error, "pes_stage", stage)
    setattr(error, "pes_csv_modified", csv_modified)
    return error


def semantic_plan_filename(team_name: str) -> str:
    """The canonical saved-plan filename; also what a run manifest records."""

    return f"semantic_game_plan_{team_name}.json"


def execute_assembled_injection(
    *,
    output_name: str,
    team_name: str,
    semantic_plan: dict[str, Any],
    team_output_dir: Path,
    step_idx: int,
    source_identity: dict[str, Any],
    roster_path: Path,
    formations_path: Path,
    players_path: Path | None,
    dry_run: bool,
    csv_lock: Any,
    logger: logging.Logger,
    preset_mode: str = "multi",
    auto_substitutions: int = Config.DEFAULT_AUTO_SUBSTITUTIONS,
    auto_change_att_def: int = Config.DEFAULT_AUTO_CHANGE_ATT_DEF,
    auto_switch_preset_tactics: int | None = None,
    report: Callable[[str], None] | None = None,
    observer: BuildObserver = NULL_OBSERVER,
) -> None:
    """Precompile and inject a deterministic, already assembled semantic plan.

    ``output_name`` is the event join key and the saved-plan file stem;
    ``team_name`` is the verbatim CSV spelling that reaches a human.

    ``players_path`` is required even though ``source_identity`` normally
    carries parsed ``player_stats``: the routine roles are then protected by
    construction rather than by whichever caller happened to populate them.
    """

    global_auto_options = resolve_global_auto_options(
        preset_mode=preset_mode,
        auto_substitutions=auto_substitutions,
        auto_change_att_def=auto_change_att_def,
        auto_switch_preset_tactics=auto_switch_preset_tactics,
    )
    team_id = str(semantic_plan.get("Team ID"))
    config_dump_path = team_output_dir / semantic_plan_filename(output_name)
    write_text_atomic(
        config_dump_path, json.dumps(semantic_plan, ensure_ascii=False, indent=2) + "\n"
    )

    for label, path in (
        ("roster", roster_path),
        ("formations", formations_path),
        ("players", players_path),
    ):
        if path is None:
            continue
        try:
            if label == "formations":
                validate_csv_target(path)
            else:
                validate_csv_file(path, writable=True)
        except OSError as error:
            emit_event(
                observer,
                INJECTION_FAILED,
                team=output_name,
                stage=STAGE_PREFLIGHT,
                reason=f"{label}_file_missing"
                if isinstance(error, FileNotFoundError)
                else f"{label}_file_inaccessible",
                dry_run=dry_run,
                csv_modified=False,
                roster_path=str(roster_path),
                formations_path=str(formations_path),
                error_type=type(error).__name__,
                error_message=str(error),
            )
            raise annotate_failure(error, stage=STAGE_PREFLIGHT, csv_modified=False)

    emit_event(
        observer,
        COMPILE_STARTED,
        team=output_name,
        stage=STAGE_COMPILE,
        preset_mode=preset_mode,
        team_id=team_id,
        dry_run=dry_run,
        step_idx=step_idx,
    )
    compile_started_at = time.monotonic()
    try:
        compiled = compile_semantic_game_plan(
            semantic_plan,
            strict=True,
            preset_mode=preset_mode,
            **global_auto_options,
        )
    except SemanticGridError as err:
        emit_event(
            observer,
            COMPILE_FAILED,
            team=output_name,
            stage=STAGE_COMPILE,
            reason="semantic_precompile_rejected",
            preset_mode=preset_mode,
            team_id=team_id,
            dry_run=dry_run,
            csv_modified=False,
            error_type=type(err).__name__,
            # SemanticGridError text is English by contract. Carried under
            # both keys: ``detail`` mirrors artifact_failed's constraint field
            # ``error_message`` is the key every failure renderer reads
            detail=str(err),
            error_message=str(err),
        )
        raise annotate_failure(
            ValueError(f"Downstream semantic precompile failed: {err}"),
            stage=STAGE_COMPILE,
            csv_modified=False,
        ) from err
    except BaseException as err:
        # Anything the compiler did not anticipate still has to close the
        # bracket, or the stage chip spins forever
        emit_event(
            observer,
            COMPILE_FAILED,
            team=output_name,
            stage=STAGE_COMPILE,
            reason="exception",
            preset_mode=preset_mode,
            team_id=team_id,
            dry_run=dry_run,
            csv_modified=False,
            error_type=type(err).__name__,
            detail=str(err),
            error_message=str(err),
            traceback="".join(
                traceback.format_exception(type(err), err, err.__traceback__)
            ),
        )
        raise annotate_failure(err, stage=STAGE_COMPILE, csv_modified=False)
    emit_event(
        observer,
        COMPILE_COMPLETED,
        team=output_name,
        stage=STAGE_COMPILE,
        preset_mode=preset_mode,
        team_id=team_id,
        elapsed_s=time.monotonic() - compile_started_at,
    )

    sink = report
    if sink is None and observer is not NULL_OBSERVER:
        line_counter = itertools.count(1)

        def sink(line: str) -> None:
            emit_event(
                observer,
                INJECTION_LINE,
                team=output_name,
                line=line,
                source="formations_injection",
                sequence=next(line_counter),
            )

    logger.info(f"[{team_name}] Requesting the CSV write lock...")
    emit_event(
        observer,
        INJECTION_WAITING_LOCK,
        team=output_name,
        stage=STAGE_INJECT,
        formations_path=str(formations_path),
        dry_run=dry_run,
    )
    with csv_lock:
        logger.info(
            f"[{team_name}] Write lock acquired; injecting {formations_path}..."
        )
        emit_event(
            observer,
            INJECTION_STARTED,
            team=output_name,
            stage=STAGE_INJECT,
            roster_path=str(roster_path),
            formations_path=str(formations_path),
            players_path=str(players_path) if players_path is not None else None,
            dry_run=dry_run,
            team_id=team_id,
            preset_mode=preset_mode,
        )
        extra = {"report": sink} if sink is not None else {}
        try:
            success = _inject_compiled_formation(
                rosters_csv=roster_path,
                formations_csv=formations_path,
                compiled=compiled,
                dry_run=dry_run,
                player_stats=source_identity.get("player_stats"),
                players_csv=players_path,
                preset_mode=preset_mode,
                **extra,
            )
        except BaseException as err:
            emit_event(
                observer,
                INJECTION_FAILED,
                team=output_name,
                stage=STAGE_INJECT,
                reason="exception",
                dry_run=dry_run,
                csv_modified=False,
                roster_path=str(roster_path),
                formations_path=str(formations_path),
                error_type=type(err).__name__,
                error_message=str(err),
                traceback="".join(
                    traceback.format_exception(type(err), err, err.__traceback__)
                ),
            )
            raise annotate_failure(err, stage=STAGE_INJECT, csv_modified=False)
    if not success:
        error_message = (
            f"[{team_name}] {formations_path} write failed; "
            "check the engine validation errors above!"
        )
        emit_event(
            observer,
            INJECTION_FAILED,
            team=output_name,
            stage=STAGE_INJECT,
            reason="engine_rejected",
            dry_run=dry_run,
            csv_modified=False,
            roster_path=str(roster_path),
            formations_path=str(formations_path),
            error_type="RuntimeError",
            error_message=error_message,
        )
        raise annotate_failure(
            RuntimeError(error_message), stage=STAGE_INJECT, csv_modified=False
        )

    if dry_run:
        logger.info(
            f"[{team_name}] 🧪 Dry-run validation succeeded; "
            f"{formations_path} was not modified."
        )
    else:
        logger.info(f"[{team_name}] 🎉 {formations_path} updated successfully!")
    emit_event(
        observer,
        INJECTION_COMPLETED,
        team=output_name,
        stage=STAGE_INJECT,
        outcome="validated_dry_run" if dry_run else "injected",
        dry_run=dry_run,
        csv_modified=not dry_run,
        formations_path=str(formations_path),
        semantic_plan_path=str(config_dump_path),
        team_id=team_id,
    )


__all__ = [
    "annotate_failure",
    "execute_assembled_injection",
    "semantic_plan_filename",
]
