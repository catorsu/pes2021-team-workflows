#!/usr/bin/env python3
"""Generate PES 2021 match plans in batches using Claude Code or Codex."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

from pes_workflows.config import GLOBAL_AUTO_CHOICES, parse_workflow_args
from pes_workflows.file_lock import acquire_lock
from pes_workflows.generate_match_plan import (
    MatchPlanRunner,
    add_match_plan_arguments,
    attribute_target_ids,
    configure_console_logging,
    configure_file_logging,
    match_plan_paths,
    match_plan_runner_options,
    player_records_sources,
    preflight_match_files,
    read_completed_teams,
    resolve_match_plan_engine_arguments,
    resolve_team,
    run_and_record,
)
from pes_workflows.players.generator import (
    InsufficientSquadError,
    PlayerRecordsGenerator,
    UnbuildableSquadError,
)

logger = logging.getLogger("Batch_Generate_Match_Plans")

COMPLETION_REGISTRY_NAME = "completed_teams_match_plans_single.txt"


def backup_formations_csv(formations_csv: Path, output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = (
        output_dir
        / f"{formations_csv.stem}_backup_batch_{timestamp}{formations_csv.suffix}"
    )
    shutil.copy2(formations_csv, backup_path)
    logger.info("CSV backup of %s: %s", formations_csv, backup_path)
    return backup_path


def main() -> int:
    with ExitStack() as resources:
        configure_console_logging(resources)
        return _main(resources)


def _main(resources: ExitStack) -> int:
    parser = argparse.ArgumentParser(
        description="Generate team match plans in batches", allow_abbrev=False
    )
    add_match_plan_arguments(parser)
    parser.add_argument(
        "--check-only",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Run offline eligibility preflight only, then report and exit (no tokens used)",
    )
    parser.add_argument(
        "--team",
        action="append",
        help="Exact name or ID; repeat to select several teams",
    )
    args = parse_workflow_args(parser, "match_plans")
    resolve_match_plan_engine_arguments(args)
    target_ids = attribute_target_ids(args, parser)

    try:
        preflight_match_files(args)
    except OSError as exc:
        parser.error(str(exc))
    formations_csv = args.formations_csv
    output_dir, registry = match_plan_paths(
        args.output_dir, args.preset_mode, workflow="match_plans"
    )
    completed = read_completed_teams(registry)
    acquire_lock(
        resources, formations_csv.with_name(f".{formations_csv.name}.match_plans.lock")
    )
    configure_file_logging(output_dir, resources)

    logger.info("Loading the database and building team roster indexes...")
    generator = PlayerRecordsGenerator(
        **player_records_sources(args),
        team_queries=args.team,
        team_ids=target_ids if not args.team else None,
    )

    teams = (
        list(generator.teams.values())
        if not args.team
        else list(
            {
                team.team_id: team
                for query in args.team
                for team in (resolve_team(generator, query),)
            }.values()
        )
    )
    if not args.team and target_ids is not None:
        teams = [team for team in teams if team.team_id in target_ids]

    runner = MatchPlanRunner(**match_plan_runner_options(args, output_dir))

    # Phase 1: Offline eligibility preflight.
    logger.info("=" * 60)
    logger.info(f"📋 Starting offline eligibility preflight for {len(teams)} teams...")
    logger.info("=" * 60)

    queue = []
    skipped_disqualified = []
    skipped_completed = []
    skipped_unlisted = []

    for team_rec in teams:
        if target_ids is not None and team_rec.team_id not in target_ids:
            skipped_unlisted.append(team_rec.team_name)
            continue
        if not args.force and team_rec.team_id in completed:
            skipped_completed.append(team_rec.team_name)
            continue

        try:
            records_doc = generator.generate(team_rec.team_id)
            queue.append((team_rec, records_doc))
        except (InsufficientSquadError, UnbuildableSquadError) as err:
            skipped_disqualified.append((team_rec.team_name, str(err)))

    print("\n" + "-" * 50)
    print("📊 Offline eligibility preflight summary:")
    print(f" • Total target teams: {len(teams)}")
    print(
        f" • Absent from the player attributes completion registry: {len(skipped_unlisted)} teams"
    )
    print(f" • Already committed (skipped on resume): {len(skipped_completed)} teams")
    print(
        f" • Ineligible due to insufficient squad size or no goalkeeper: {len(skipped_disqualified)} teams"
    )
    for tname, reason in skipped_disqualified:
        print(f"   --> [{tname}]: {reason}")
    print(f" • Queued for match-plan generation: {len(queue)} teams")
    print("-" * 50 + "\n")

    report_path = output_dir / f"preflight_{datetime.now():%Y%m%d_%H%M%S_%f}.json"
    report_path.write_text(
        json.dumps(
            {
                "team_count": len(teams),
                "queued": [
                    {"team_name": rec.team_name, "team_id": rec.team_id}
                    for rec, _ in queue
                ],
                "skipped_completed": skipped_completed,
                "skipped_unlisted": skipped_unlisted,
                "attributes_completed_teams": (
                    str(args.attributes_completed_teams)
                    if args.attributes_completed_teams is not None
                    else None
                ),
                "disqualified": skipped_disqualified,
                "preset_mode": args.preset_mode,
                "global_auto_options": {
                    key: getattr(args, key) for key in GLOBAL_AUTO_CHOICES
                },
                "dry_run": args.dry_run,
                "formations_csv": str(formations_csv),
                **{
                    key: str(path) for key, path in player_records_sources(args).items()
                },
                "completion_registry": str(registry),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if args.check_only:
        logger.info("Completed --check-only preflight; exiting safely.")
        return 1 if skipped_disqualified else 0

    if not queue:
        logger.info("The queue is empty (all plans may already be complete); exiting.")
        return 1 if skipped_disqualified else 0

    if not args.dry_run:
        backup_formations_csv(formations_csv, output_dir)

    # Phase 2: Sequential match-plan generation.
    succeeded = 0
    failed = 0
    start_all = time.time()

    for idx, (team_rec, records_doc) in enumerate(queue, start=1):
        logger.info("\n" + "=" * 60)
        logger.info(
            f"⚽ [{idx}/{len(queue)}] Generating a match plan for: {team_rec.team_name} (ID: {team_rec.team_id})"
        )
        logger.info("=" * 60)

        t_start = time.time()
        try:
            run_and_record(runner, records_doc, team_rec, registry)
            succeeded += 1
            logger.info(
                f"✅ [{idx}/{len(queue)}] {team_rec.team_name} completed in {int(time.time() - t_start)}s"
            )
        except Exception as e:
            failed += 1
            logger.error(
                f"❌ [{idx}/{len(queue)}] {team_rec.team_name} failed: {e}",
                exc_info=True,
            )
            logger.info(
                "⏳ Failure isolated; continuing to the next team in 5 seconds..."
            )
            time.sleep(5)

    elapsed_min = round((time.time() - start_all) / 60, 1)
    logger.info("\n" + "=" * 60)
    logger.info("🏁 Batch match-plan generation complete!")
    logger.info(
        f"Total queued: {len(queue)} | Succeeded: {succeeded} | Failed: {failed} | Total time: {elapsed_min} minutes"
    )
    if not args.dry_run:
        logger.info(f"💾 Formation and role data synchronized to: {formations_csv}")
    logger.info("=" * 60)
    return 1 if failed or skipped_disqualified else 0


if __name__ == "__main__":
    sys.exit(main())
