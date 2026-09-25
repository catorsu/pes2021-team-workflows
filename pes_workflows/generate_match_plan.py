#!/usr/bin/env python3
"""Generate a PES 2021 match plan for one team using Claude Code or Codex."""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from pes_workflows.application.build_team import MatchPlanRunner
from pes_workflows.checkpoint_io import (
    append_completed_team,
    read_completed_teams,
)
from pes_workflows.claude_cli import ClaudeCodeSubprocessAdapter, CodexSubprocessAdapter
from pes_workflows.config import (
    GLOBAL_AUTO_CHOICES,
    Config,
    add_global_auto_arguments,
    add_scope_arguments,
    parse_workflow_args,
)
from pes_workflows.csv_validation import validate_csv_file, validate_csv_target
from pes_workflows.file_lock import acquire_lock
from pes_workflows.llm.base import BaseLLMAdapter
from pes_workflows.players.generator import (
    GeneratedPlayerRecords,
    InsufficientSquadError,
    PlayerRecordsGenerator,
    TeamRecord,
    UnbuildableSquadError,
    select_team,
)
from pes_workflows.prompts.loader import TemplateLoader

PROJECT_ROOT = Path(__file__).resolve().parent

logger = logging.getLogger("Generate_Match_Plan")


OUTPUT_DIRECTORY_NAME = "outputs/match_plan"
COMPLETION_REGISTRY_NAME = "completed_teams_match_plan_single.txt"


def add_preset_mode_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--preset-mode",
        choices=Config.SUPPORTED_PRESET_MODES,
        required=True,
        help="single (Main, 3 calls) or multi (Main/Defensive/Custom, 5 calls); can be set in the config file",
    )


def match_plan_paths(
    output_dir: Path | None, preset_mode: str, *, workflow: str = "match_plan"
) -> tuple[Path, Path]:
    if preset_mode not in ("single", "multi"):
        raise ValueError(f"Unknown preset mode: {preset_mode}")
    if workflow not in ("match_plan", "match_plans"):
        raise ValueError(f"Unknown match-plan workflow: {workflow}")
    output_dir = (output_dir or Path.cwd() / "outputs" / workflow).resolve()
    return output_dir, output_dir / f"completed_teams_{workflow}_{preset_mode}.txt"


def add_match_plan_engine_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--engine",
        choices=("claude-code", "codex"),
        default="claude-code",
        help="Execution engine (default: claude-code)",
    )
    parser.add_argument(
        "--model",
        help=f"Model (Claude default: {Config.DEFAULT_MODEL}; Codex default: {CodexSubprocessAdapter.DEFAULT_MODEL}; "
        "override with --model claude-fable-5-1 or gpt-6-sol)",
    )
    parser.add_argument(
        "--effort",
        choices=Config.EFFORT_CHOICES,
        help=f"Reasoning effort (default: {Config.DEFAULT_EFFORT})",
    )


def resolve_match_plan_engine_arguments(args: argparse.Namespace) -> None:
    if args.engine == "codex":
        args.model = (
            args.model
            if args.model is not None
            else CodexSubprocessAdapter.DEFAULT_MODEL
        )
        args.effort = (
            args.effort
            if args.effort is not None
            else CodexSubprocessAdapter.DEFAULT_EFFORT
        )
    else:
        args.model = args.model if args.model is not None else Config.DEFAULT_MODEL
        args.effort = args.effort if args.effort is not None else Config.DEFAULT_EFFORT
    if (
        args.engine == "claude-code"
        and args.fast
        and not args.model.startswith("claude-opus")
    ):
        logger.warning(
            "Fast mode only supports Opus 5.5/5/4.8; the current model %s does not support this setting.",
            args.model,
        )


def create_match_plan_adapter(args: argparse.Namespace) -> BaseLLMAdapter:
    kwargs = dict(
        model=args.model, effort=args.effort, delay=args.delay, fast_mode=args.fast
    )
    if args.engine == "codex":
        return CodexSubprocessAdapter(**kwargs)
    return ClaudeCodeSubprocessAdapter(**kwargs)


def add_attribute_registry_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--attributes-completed-teams",
        type=Path,
        help="Only generate plans for teams in this player attributes completion registry (UTF-8: Team ID\tTeam Name or Team ID)",
    )


def attribute_target_ids(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> set[str] | None:
    if args.attributes_completed_teams is None:
        return None
    try:
        return read_completed_teams(args.attributes_completed_teams, required=True)
    except (OSError, UnicodeError) as exc:
        parser.error(f"Cannot read --attributes-completed-teams: {exc}")


def run_and_record(
    runner: MatchPlanRunner,
    records_doc: GeneratedPlayerRecords,
    team_rec: TeamRecord,
    registry: Path,
) -> None:
    runner.run_team(records_doc)  # Raises on generation, validation or commit failure.
    if not runner.dry_run:
        append_completed_team(registry, team_rec)


def configure_file_logging(output_dir: Path, resources: ExitStack) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(
        output_dir / (output_dir.name.removeprefix("outputs_") + ".log"),
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root_logger = logging.getLogger()
    resources.callback(root_logger.setLevel, root_logger.level)
    root_logger.setLevel(logging.INFO)
    resources.callback(handler.close)
    resources.callback(root_logger.removeHandler, handler)
    root_logger.addHandler(handler)


def resolve_team(generator: PlayerRecordsGenerator, team_query: str) -> TeamRecord:
    return select_team(generator.teams.values(), team_query)


def configure_console_logging(resources: ExitStack) -> None:
    root = logging.getLogger()
    resources.callback(root.setLevel, root.level)
    root.setLevel(logging.INFO)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
            )
        )
        root.addHandler(handler)
        resources.callback(handler.close)
        resources.callback(root.removeHandler, handler)


def add_match_plan_arguments(parser: argparse.ArgumentParser) -> None:
    add_preset_mode_argument(parser)
    add_global_auto_arguments(parser)
    add_match_plan_engine_arguments(parser)
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="Cooldown delay after receiving a model response, in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--fast",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable fast mode for the selected engine",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Dry-run mode (do not write to Formations.csv)",
    )
    parser.add_argument(
        "--force",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Regenerate plans for completed teams",
    )
    parser.add_argument(
        "--output-dir", type=Path, help="Directory for logs and generated artifacts"
    )
    add_scope_arguments(parser)
    add_attribute_registry_argument(parser)


def player_records_sources(args: argparse.Namespace) -> dict[str, Path]:
    return dict(
        rosters_csv=args.rosters_csv,
        players_csv=args.players_csv,
        teams_players_csv=args.teams_players_csv,
    )


def preflight_match_files(args: argparse.Namespace) -> None:
    for path in player_records_sources(args).values():
        validate_csv_file(path, writable=True)
    validate_csv_target(args.formations_csv)


def match_plan_runner_options(
    args: argparse.Namespace, output_dir: Path
) -> dict[str, Any]:
    sources = player_records_sources(args)
    return dict(
        llm_adapter=create_match_plan_adapter(args),
        loader=TemplateLoader(
            PROJECT_ROOT / "prompts/match_plan", preset_mode=args.preset_mode
        ),
        output_base_dir=output_dir,
        roster_path=sources["rosters_csv"],
        formations_path=args.formations_csv,
        players_path=sources["players_csv"],
        teams_players_path=sources["teams_players_csv"],
        model=args.model,
        preset_mode=args.preset_mode,
        dry_run=args.dry_run,
        **{key: getattr(args, key) for key in GLOBAL_AUTO_CHOICES},
    )


def main() -> int:
    with ExitStack() as resources:
        configure_console_logging(resources)
        return _main(resources)


def _main(resources: ExitStack) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a match plan for one team", allow_abbrev=False
    )
    parser.add_argument("--team", help="Exact team name or Team ID")
    add_match_plan_arguments(parser)
    args = parse_workflow_args(parser, "match_plan")
    resolve_match_plan_engine_arguments(args)
    target_ids = attribute_target_ids(args, parser)

    try:
        preflight_match_files(args)
    except OSError as exc:
        parser.error(str(exc))
    formations_csv = args.formations_csv
    output_dir, registry = match_plan_paths(args.output_dir, args.preset_mode)
    completed = read_completed_teams(registry)
    acquire_lock(
        resources, formations_csv.with_name(f".{formations_csv.name}.match_plans.lock")
    )
    configure_file_logging(output_dir, resources)

    logger.info("Loading database indexes...")
    generator = PlayerRecordsGenerator(
        **player_records_sources(args), team_queries=[args.team], team_ids=None
    )

    team_rec = resolve_team(generator, args.team)
    if target_ids is not None and team_rec.team_id not in target_ids:
        logger.info(
            "Skipping team absent from the player attributes completion registry: %s",
            team_rec.team_name,
        )
        return 0
    if not args.force and team_rec.team_id in completed:
        logger.info(
            "Already committed; skipping on resume: %s (ID: %s)",
            team_rec.team_name,
            team_rec.team_id,
        )
        return 0
    logger.info(f"🎯 Selected team: {team_rec.team_name} (ID: {team_rec.team_id})")

    logger.info(
        "🔍 Running offline eligibility preflight (at least 11 players and an eligible goalkeeper)..."
    )
    try:
        records_doc = generator.generate(team_rec.team_id)
        logger.info(
            f"✅ Team is eligible: loaded records for {len(records_doc.player_ids)} players."
        )
    except (InsufficientSquadError, UnbuildableSquadError) as e:
        logger.error(f"❌ Team is ineligible: {e}")
        sys.exit(1)

    runner_options = match_plan_runner_options(args, output_dir)
    loader = runner_options["loader"]
    runner = MatchPlanRunner(**runner_options)

    logger.info(
        "🚀 Starting %s match-plan generation (%s calls)...",
        args.preset_mode,
        len(loader.user_templates),
    )
    run_and_record(runner, records_doc, team_rec, registry)

    print("\n" + "=" * 70)
    mode_text = "Dry-Run" if args.dry_run else "Apply"
    print(
        f"🎉 [{mode_text}] {args.preset_mode} match plan completed for {team_rec.team_name}!"
    )
    if not args.dry_run:
        print(f"📝 Formations written atomically to: {formations_csv}")
    print(f"📁 Detailed plans and audit records: {output_dir / team_rec.output_name}")
    print("=" * 70 + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
