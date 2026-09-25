"""Build one team's Contract v2.2 match plan."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, TypeVar

from pes_workflows.application.artifact_generation import request_artifact
from pes_workflows.application.assembled_injection import (
    execute_assembled_injection,
    semantic_plan_filename,
)
from pes_workflows.config import Config, resolve_global_auto_options
from pes_workflows.contracts.assembly import assemble_semantic_game_plan
from pes_workflows.contracts.bench import validate_bench_decision
from pes_workflows.contracts.constants import PRESET_NAMES, SCHEMA_VERSION
from pes_workflows.contracts.json_codec import (
    canonical_json as canonical_artifact_json,
)
from pes_workflows.contracts.preset import PresetPlan, validate_preset_plan
from pes_workflows.contracts.strategy import validate_starting_xi_lock
from pes_workflows.events import (
    ARTIFACT_COMPLETED,
    ARTIFACT_STARTED,
    MATCH_PLAN_STAGES,
    NULL_OBSERVER,
    STAGE_BENCH,
    STAGE_INJECT,
    STAGE_PRESET_PLAN,
    STAGE_XI_LOCK,
    TEAM_STARTED,
    WORKFLOW_MATCH_PLAN,
    BuildObserver,
    emit_event,
)
from pes_workflows.llm.base import BaseLLMAdapter
from pes_workflows.players.generator import GeneratedPlayerRecords
from pes_workflows.players.records import (
    parse_player_records_identity,
    scope_player_records,
)
from pes_workflows.prompts.loader import TemplateLoader
from pes_workflows.storage.artifact_store import (
    slugify,
    write_artifact_files,
)
from pes_workflows.storage.atomic import stable_json_sha256
from pes_workflows.storage.run_layout import (
    CONVERSATION_HISTORY_NAME,
    MANIFEST_SCHEMA_VERSION,
    RUN_STATUS_FAILED,
    RUN_STATUS_GENERATED,
    RUN_STATUS_INJECTED,
    RUN_STATUS_INJECTION_FAILED,
    SYSTEM_PROMPT_NAME,
    RunRecorder,
    create_run_dir,
    new_batch_id,
)

T = TypeVar("T")

logger = logging.getLogger("PES2021_Builder")


def _error_detail(err: BaseException, *, stage: str | None = None) -> dict[str, Any]:
    """The manifest's structured failure record."""

    # ``pes_stage``/``pes_csv_modified`` are set by
    # ``assembled_injection.annotate_failure``, which knows whether the failure
    # escaped preflight, compile or the transaction itself — the caller only
    # sees one exception for all three
    return {
        "type": type(err).__name__,
        "message": str(err),
        "stage": getattr(err, "pes_stage", None) or stage,
        "csv_modified": getattr(err, "pes_csv_modified", None),
    }


class MatchPlanRunner:
    _observer: BuildObserver = NULL_OBSERVER
    batch_id: str | None = None

    def __init__(
        self,
        *,
        loader: TemplateLoader,
        output_base_dir: Path,
        roster_path: Path,
        formations_path: Path,
        model: str = Config.DEFAULT_MODEL,
        dry_run: bool = False,
        csv_lock: threading.Lock | None = None,
        preset_mode: str = Config.DEFAULT_PRESET_MODE,
        auto_substitutions: int = Config.DEFAULT_AUTO_SUBSTITUTIONS,
        auto_change_att_def: int = Config.DEFAULT_AUTO_CHANGE_ATT_DEF,
        auto_switch_preset_tactics: int | None = None,
        llm_adapter: BaseLLMAdapter,
        players_path: Path | None,
        teams_players_path: Path | None,
        observer: BuildObserver = NULL_OBSERVER,
        batch_id: str | None = None,
    ) -> None:
        if preset_mode not in Config.SUPPORTED_PRESET_MODES:
            raise ValueError(
                f"preset_mode must be one of {Config.SUPPORTED_PRESET_MODES!r}; "
                f"got {preset_mode!r}"
            )
        loader_mode = getattr(loader, "preset_mode", preset_mode)
        self.global_auto_options = resolve_global_auto_options(
            preset_mode=preset_mode,
            auto_substitutions=auto_substitutions,
            auto_change_att_def=auto_change_att_def,
            auto_switch_preset_tactics=auto_switch_preset_tactics,
        )
        if loader_mode != preset_mode:
            raise ValueError(
                "TemplateLoader and MatchPlanRunner preset modes must match; "
                f"got loader={loader_mode!r}, runner={preset_mode!r}"
            )
        self.loader: TemplateLoader = loader
        self.output_base_dir: Path = output_base_dir
        self.roster_path: Path = roster_path
        self.formations_path: Path = formations_path
        # Keyword-only and required, like the injection call they feed: the four
        # editor CSVs are configured independently, so a runner either names the
        # files it reads or states that it has none
        self.players_path: Path | None = players_path
        self.teams_players_path: Path | None = teams_players_path
        self.model: str = model
        self.llm_adapter: BaseLLMAdapter = llm_adapter
        self.dry_run: bool = dry_run
        self.preset_mode: str = preset_mode
        self.csv_lock: threading.Lock = csv_lock or threading.Lock()
        self._observer = observer
        self.batch_id = batch_id or new_batch_id()

    def run_team(self, records: GeneratedPlayerRecords) -> None:
        """Run Contract v2.2 as a scoped artifact DAG and inject its local assembly."""
        # Per-call, never on ``self``: one shared runner serves N concurrent
        # teams, so a self._run_dir would interleave two teams' manifests
        run_box: list[RunRecorder] = []
        try:
            return self._run_team(records, run_box=run_box)
        except Exception as err:
            # First-wins, so this is a no-op when the injection handler already
            # recorded the more precise ``injection_failed``
            if run_box:
                run_box[0].finish(RUN_STATUS_FAILED, error=_error_detail(err))
            raise

    def _run_team(
        self, records: GeneratedPlayerRecords, *, run_box: list[RunRecorder]
    ) -> None:
        output_name = records.output_name
        team_name = records.team_name
        user_id = self._generate_user_id(output_name)
        total_turns = len(self.loader.user_templates)
        active_preset_names = PRESET_NAMES if self.preset_mode == "multi" else ("Main",)
        preset_turns = tuple(range(2, 2 + len(active_preset_names)))
        expected_turns = 5 if self.preset_mode == "multi" else 3
        bench_turn = expected_turns

        if total_turns != expected_turns:
            raise ValueError(
                f"Contract v2.2 {self.preset_mode!r} mode requires exactly "
                f"{expected_turns} templates."
            )

        logger.info(
            f"[{team_name}] >>> Starting Contract v2.2 run "
            f"(model={self.model}, {total_turns} artifacts, "
            f"preset_mode={self.preset_mode}, user_id={user_id})"
        )

        team_root = self.output_base_dir / output_name
        team_output_dir = create_run_dir(team_root)
        run = RunRecorder(team_output_dir)
        run_box.append(run)
        run.start(self._manifest_seed(records, output_name, run))

        observer = self._observer
        emit_event(
            observer,
            TEAM_STARTED,
            team=output_name,
            display_name=team_name,
            model=self.model,
            preset_mode=self.preset_mode,
            artifact_count=total_turns,
            preset_names=list(active_preset_names),
            stages=list(MATCH_PLAN_STAGES),
            dry_run=self.dry_run,
            user_id=user_id,
            output_dir=str(team_output_dir),
            run_id=run.run_id,
            batch_id=self.batch_id,
            manifest_path=(
                str(run.manifest_path) if run.manifest_path is not None else None
            ),
            team_id=records.team_id,
            workflow=WORKFLOW_MATCH_PLAN,
        )

        player_records = records.content.strip()
        source_identity = self._parse_player_records_identity(
            player_records, records.label
        )
        source_digest = hashlib.sha256(player_records.encode("utf-8")).hexdigest()
        # Only the static rule bases live here; every call-scoped document
        # travels in that call's user message (system_prompt.md pipeline table)
        system_prompt = self.loader.build_system_prompt()
        policy_digest = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
        run.update(
            team={"id": str(source_identity["team_id"])},
            source={"sha256": source_digest, "policy_sha256": policy_digest},
        )

        system_prompt_dump_path = team_output_dir / SYSTEM_PROMPT_NAME
        with open(system_prompt_dump_path, "w", encoding="utf-8") as f:
            f.write(f"# Complete API System Prompt - {team_name}\n\n{system_prompt}")

        # Artifact 1 is the only model call that can choose personnel. Python
        # verifies source identity before the XI becomes immutable input
        step1_prompt, step1_title = self.loader.get_turn_user_prompt(
            1, player_records_content=player_records
        )
        logger.info(f"[{team_name}] >>> Artifact 1/{total_turns}: {step1_title}")
        self._emit_artifact_started(
            team_name=output_name,
            turn=1,
            artifact_name="StartingXILock",
            stage=STAGE_XI_LOCK,
            preset=None,
            turn_total=total_turns,
            parallel=False,
            title=step1_title,
        )
        step1_started_at = time.monotonic()
        xi_lock, step1_record = self._request_v2_artifact(
            system_prompt=system_prompt,
            user_prompt=step1_prompt,
            turn=1,
            artifact_name="StartingXILock",
            output_name=output_name,
            team_name=team_name,
            user_id=f"{user_id}-starting-xi",
            validator=lambda raw: validate_starting_xi_lock(raw, source_identity),
        )
        self._emit_artifact_completed(
            team_name=output_name,
            turn=1,
            artifact_name="StartingXILock",
            stage=STAGE_XI_LOCK,
            preset=None,
            turn_total=total_turns,
            record=step1_record,
            elapsed_s=time.monotonic() - step1_started_at,
        )

        locked_ids = [item.player_id for item in xi_lock.starting_xi]
        locked_records = scope_player_records(
            player_records, locked_ids, "locked Starting XI"
        )
        # Every PresetPlan call freezes exactly the StartingXILock
        preset_frozen_json = canonical_artifact_json([xi_lock.to_model_dict()])

        # Preset artifacts are independent once the shared XI is frozen
        preset_jobs = {}
        preset_records: dict[int, dict[str, Any]] = {}
        preset_started_at: dict[int, float] = {}
        parallel_presets = len(active_preset_names) > 1
        with ThreadPoolExecutor(
            max_workers=len(active_preset_names)
        ) as preset_executor:
            for turn, preset_name in zip(preset_turns, active_preset_names):
                scoped_prompt, title = self.loader.get_turn_user_prompt(
                    turn,
                    player_records_content=locked_records,
                    frozen_artifacts_json=preset_frozen_json,
                )
                logger.info(
                    f"[{team_name}] >>> Artifact {turn}/{total_turns}: {title}"
                    + (" (parallel)" if len(active_preset_names) > 1 else "")
                )
                # Fires at submit time rather than call time; because
                # max_workers equals the preset count, every preset starts
                # immediately, so the two coincide in practice
                self._emit_artifact_started(
                    team_name=output_name,
                    turn=turn,
                    artifact_name="PresetPlan",
                    stage=STAGE_PRESET_PLAN,
                    preset=preset_name,
                    turn_total=total_turns,
                    parallel=parallel_presets,
                    title=title,
                )
                preset_started_at[turn] = time.monotonic()
                future = preset_executor.submit(
                    self._request_v2_artifact,
                    system_prompt=system_prompt,
                    user_prompt=scoped_prompt,
                    turn=turn,
                    artifact_name="PresetPlan",
                    output_name=output_name,
                    team_name=team_name,
                    user_id=f"{user_id}-preset-{preset_name.lower()}",
                    validator=lambda raw, name=preset_name: validate_preset_plan(
                        raw,
                        name,
                        xi_lock,
                        preset_mode=self.preset_mode,
                    ),
                    preset=preset_name,
                )
                preset_jobs[future] = (turn, preset_name, title, scoped_prompt)

            preset_results = {}
            preset_failure: BaseException | None = None
            for future in as_completed(preset_jobs):
                turn, preset_name, title, scoped_prompt = preset_jobs[future]
                try:
                    preset, record = future.result()
                except BaseException as err:
                    if preset_failure is None:
                        preset_failure = err
                    continue
                preset_results[preset_name] = preset
                record.update(
                    {
                        "turn": turn,
                        "title": title,
                        "user_prompt": scoped_prompt,
                        "artifact": preset,
                    }
                )
                preset_records[turn] = record
                logger.info(
                    f"[{team_name}] ✓ Artifact {turn}/{total_turns} frozen: "
                    f"{preset_name}"
                )
                self._emit_artifact_completed(
                    team_name=output_name,
                    turn=turn,
                    artifact_name="PresetPlan",
                    stage=STAGE_PRESET_PLAN,
                    preset=preset_name,
                    turn_total=total_turns,
                    record=record,
                    elapsed_s=time.monotonic() - preset_started_at[turn],
                )
            if preset_failure is not None:
                raise preset_failure

        frozen_presets: dict[str, PresetPlan] = {
            name: preset_results[name] for name in active_preset_names
        }

        # The final artifact receives frozen demand sources, not conversation replay
        bench_frozen = [xi_lock.to_model_dict()] + [
            frozen_presets[name].to_model_dict() for name in active_preset_names
        ]
        # Coverage Gaps compares each substitute against the starter holding the
        # source duty, so the extract carries every dossier: the eleven starters
        # in Slot order, then the non-starters
        starter_ids = {item.player_id for item in xi_lock.starting_xi}
        squad_ids = locked_ids + [
            player_id
            for player_id in source_identity["players"]
            if player_id not in starter_ids
        ]
        bench_records = scope_player_records(
            player_records, squad_ids, "matchday squad"
        )
        scoped_bench_prompt, bench_title = self.loader.get_turn_user_prompt(
            bench_turn,
            player_records_content=bench_records,
            frozen_artifacts_json=canonical_artifact_json(bench_frozen),
        )
        logger.info(
            f"[{team_name}] >>> Artifact {bench_turn}/{total_turns}: {bench_title}"
        )
        self._emit_artifact_started(
            team_name=output_name,
            turn=bench_turn,
            artifact_name="BenchDecision",
            stage=STAGE_BENCH,
            preset=None,
            turn_total=total_turns,
            parallel=False,
            title=bench_title,
        )
        bench_started_at = time.monotonic()
        bench, bench_record = self._request_v2_artifact(
            system_prompt=system_prompt,
            user_prompt=scoped_bench_prompt,
            turn=bench_turn,
            artifact_name="BenchDecision",
            output_name=output_name,
            team_name=team_name,
            user_id=f"{user_id}-bench",
            validator=lambda raw: validate_bench_decision(
                raw,
                xi_lock,
                source_identity,
            ),
        )
        self._emit_artifact_completed(
            team_name=output_name,
            turn=bench_turn,
            artifact_name="BenchDecision",
            stage=STAGE_BENCH,
            preset=None,
            turn_total=total_turns,
            record=bench_record,
            elapsed_s=time.monotonic() - bench_started_at,
        )

        # Build records in stable logical order even though preset calls ran in
        # parallel. Raw reasoning tokens are intentionally never persisted
        step1_record.update(
            {
                "turn": 1,
                "title": step1_title,
                "user_prompt": step1_prompt,
                "artifact": xi_lock,
            }
        )
        ordered_records = [step1_record]
        ordered_records.extend(preset_records[turn] for turn in preset_turns)
        bench_record.update(
            {
                "turn": bench_turn,
                "title": bench_title,
                "user_prompt": scoped_bench_prompt,
                "artifact": bench,
            }
        )
        ordered_records.append(bench_record)

        artifact_hashes: dict[int, str] = {}
        for record in ordered_records:
            artifact_hashes[record["turn"]] = stable_json_sha256(record["raw"])
        for record in ordered_records:
            turn = record["turn"]
            if turn == 1:
                parent_turns = []
            elif turn in preset_turns:
                parent_turns = [1]
            else:
                parent_turns = [1, *preset_turns]
            record["artifact_sha256"] = artifact_hashes[turn]
            record["parent_artifact_sha256"] = [
                artifact_hashes[parent] for parent in parent_turns
            ]

        history_records = []
        for record in ordered_records:
            artifact = record["artifact"]
            write_artifact_files(team_output_dir=team_output_dir, record=record)
            history_records.append(
                {
                    "turn": record["turn"],
                    "title": record["title"],
                    "artifact_type": type(artifact).__name__,
                    "format_repairs": record["repairs"],
                    "accepted_artifact": record["raw"],
                    "reasoning_tokens_returned": bool(record["reasoning_available"]),
                    "schema_version": record["raw"]["Schema Version"],
                    "source_sha256": source_digest,
                    "policy_sha256": record.get("policy_sha256", policy_digest),
                    "artifact_sha256": record["artifact_sha256"],
                    "parent_artifact_sha256": record["parent_artifact_sha256"],
                }
            )

        # The compiler artifact is assembled once from frozen objects. This is
        # also the JSON persisted for future replay and injection
        semantic_plan = assemble_semantic_game_plan(
            source_identity,
            xi_lock,
            frozen_presets,
            bench,
            preset_mode=self.preset_mode,
        )

        history_file_path = team_output_dir / CONVERSATION_HISTORY_NAME
        with open(history_file_path, "w", encoding="utf-8") as f:
            json.dump(history_records, f, ensure_ascii=False, indent=2)

        run.update(
            RUN_STATUS_GENERATED,
            artifact_count=len(ordered_records),
            artifacts=self._manifest_generation_artifacts(
                ordered_records=ordered_records
            ),
        )

        logger.info(
            f"[{team_name}] >>> Running the final injection: assembling and "
            "validating the semantic game plan locally ..."
        )
        try:
            self._execute_assembled_injection(
                output_name=output_name,
                team_name=team_name,
                semantic_plan=semantic_plan,
                team_output_dir=team_output_dir,
                step_idx=total_turns + 1,
                source_identity=source_identity,
            )
        except Exception as err:
            run.finish(
                RUN_STATUS_INJECTION_FAILED,
                error=_error_detail(err, stage=STAGE_INJECT),
            )
            raise
        run.finish(
            RUN_STATUS_GENERATED if self.dry_run else RUN_STATUS_INJECTED,
            artifacts=self._manifest_injection_artifacts(team_name=output_name),
        )

    def _manifest_seed(
        self, records: GeneratedPlayerRecords, team_name: str, run: Any
    ) -> dict[str, Any]:
        """The manifest as it exists before any model call."""

        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "workflow": WORKFLOW_MATCH_PLAN,
            "batch_id": self.batch_id,
            "run_id": run.run_id,
            "status": None,
            "team": {"name": team_name, "id": records.team_id},
            "model": self.model,
            "preset_mode": self.preset_mode,
            "global_auto_options": dict(self.global_auto_options),
            "dry_run": bool(self.dry_run),
            "contract_schema_version": SCHEMA_VERSION,
            "source": {
                "team_id": records.team_id,
                "team_name": records.team_name,
                "players_csv_sha256": records.players_sha256,
                "rosters_csv_sha256": records.roster_sha256,
                "sha256": None,
                "policy_sha256": None,
            },
            "targets": {
                "players_csv": str(self.players_path)
                if self.players_path is not None
                else None,
                "teams_players_csv": str(self.teams_players_path)
                if self.teams_players_path is not None
                else None,
                "rosters_csv": str(self.roster_path),
                "formations_csv": str(self.formations_path),
            },
            "artifact_count": None,
            "artifacts": {},
        }

    def _manifest_generation_artifacts(
        self, *, ordered_records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Everything the DAG itself wrote, all of it already on disk."""

        return {
            "system_prompt": SYSTEM_PROMPT_NAME,
            "turns": [
                f"Turn_{record['turn']:02d}_{slugify(record['title'])}"
                for record in ordered_records
            ],
            "conversation_history": CONVERSATION_HISTORY_NAME,
        }

    def _manifest_injection_artifacts(self, *, team_name: str) -> dict[str, Any]:
        """The injection tail, recorded only once the injection has returned."""

        return {
            "semantic_game_plan": semantic_plan_filename(team_name),
        }

    def _emit_artifact_started(
        self,
        *,
        team_name: str,
        turn: int,
        artifact_name: str,
        stage: str,
        preset: str | None,
        turn_total: int,
        parallel: bool,
        title: str,
    ) -> None:
        emit_event(
            self._observer,
            ARTIFACT_STARTED,
            team=team_name,
            turn=turn,
            artifact_name=artifact_name,
            stage=stage,
            preset=preset,
            turn_index=turn,
            turn_total=turn_total,
            parallel=parallel,
            title=title,
            workflow=WORKFLOW_MATCH_PLAN,
        )

    def _emit_artifact_completed(
        self,
        *,
        team_name: str,
        turn: int,
        artifact_name: str,
        stage: str,
        preset: str | None,
        turn_total: int,
        record: dict[str, Any],
        elapsed_s: float,
    ) -> None:
        repairs = record.get("repairs") or []
        emit_event(
            self._observer,
            ARTIFACT_COMPLETED,
            team=team_name,
            turn=turn,
            artifact_name=artifact_name,
            stage=stage,
            preset=preset,
            turn_index=turn,
            turn_total=turn_total,
            repairs=len(repairs),
            repair_paths=[item.get("json_path") for item in repairs],
            reasoning_available=bool(record.get("reasoning_available")),
            elapsed_s=elapsed_s,
            workflow=WORKFLOW_MATCH_PLAN,
        )

    def _request_v2_artifact(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        turn: int,
        artifact_name: str,
        output_name: str,
        team_name: str,
        user_id: str | None,
        validator: Callable[[dict[str, Any]], T],
        preset: str | None = None,
    ) -> tuple[T, dict[str, Any]]:
        """Request one validated artifact bound to this runner's model call and observer."""

        return request_artifact(
            call_model=self._call_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            turn=turn,
            artifact_name=artifact_name,
            output_name=output_name,
            team_name=team_name,
            user_id=user_id,
            validator=validator,
            logger=logger,
            preset=preset,
            observer=self._observer,
        )

    def _execute_assembled_injection(
        self,
        *,
        output_name: str,
        team_name: str,
        semantic_plan: dict[str, Any],
        team_output_dir: Path,
        step_idx: int,
        source_identity: dict[str, Any],
    ) -> None:
        """Precompile and inject a deterministic, already assembled semantic plan."""
        execute_assembled_injection(
            output_name=output_name,
            team_name=team_name,
            semantic_plan=semantic_plan,
            team_output_dir=team_output_dir,
            step_idx=step_idx,
            source_identity=source_identity,
            roster_path=self.roster_path,
            formations_path=self.formations_path,
            players_path=self.players_path,
            dry_run=self.dry_run,
            csv_lock=self.csv_lock,
            logger=logger,
            preset_mode=self.preset_mode,
            observer=self._observer,
            **self.global_auto_options,
        )

    @classmethod
    def _parse_player_records_identity(
        cls, content: str, source_label: str
    ) -> dict[str, Any]:
        """Parse a PLAYER_RECORDS document into the run's authoritative source identity."""

        return parse_player_records_identity(content, source_label)

    def _call_model(
        self,
        messages: list[dict[str, str]],
        turn: int,
        team_name: str,
        user_id: str | None = None,
    ) -> tuple[str, str]:
        """Call the selected provider through the normalized adapter contract."""

        return self.llm_adapter.generate(messages, turn, team_name, user_id=user_id)

    @staticmethod
    def _generate_user_id(team_name: str) -> str:
        """Generate a transport-safe request correlation identifier."""
        raw_hash = hashlib.md5(team_name.encode("utf-8")).hexdigest()[:12]
        return f"pes_team_{raw_hash}"


__all__ = ["MatchPlanRunner"]
