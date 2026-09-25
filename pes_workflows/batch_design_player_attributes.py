#!/usr/bin/env python3
"""Resumable team player modeling, atomic injection and persistent reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from pes_workflows.attribute_audit import AuditedAdapter, Observer
from pes_workflows.checkpoint_io import (
    digest,
    save,
    save_completed_teams,
)
from pes_workflows.config import Config, add_scope_arguments, parse_workflow_args
from pes_workflows.csv_validation import (
    attribute_mismatches,
    rows,
    validate_csv_file,
    validate_csv_target,
)
from pes_workflows.file_lock import acquire_lock
from pes_workflows.player_attributes.generation import PlayerAttributeRunner
from pes_workflows.player_attributes.injection import (
    _apply_profile,
    preflight_player_injection,
    read_player_attribute_team,
)
from pes_workflows.player_attributes.prompts import PlayerAttributePromptBuilder
from pes_workflows.player_attributes.sources import (
    list_attribute_teams,
    resolve_design_targets,
)
from pes_workflows.prompts.assets import read_prompt_bytes
from pes_workflows.reporting.player_attributes import (
    render_player_attribute_team_markdown,
)
from pes_workflows.storage.atomic import stable_json_sha256, write_text_atomic

ROOT = Path(__file__).resolve().parent

POLICY = ROOT / "prompts/player_attributes/system_prompt.md"
COMPLETION_REGISTRY_NAME = "completed_teams_player_attributes.txt"


def prompt_digest() -> str:
    return stable_json_sha256(
        {
            asset.name: hashlib.sha256(read_prompt_bytes(asset)).hexdigest()
            for asset in sorted(
                (
                    *POLICY.parent.glob("*.md"),
                    POLICY.parent.parent / "shared/player_glossary.md",
                )
            )
        }
    )


def preflight(
    players: Path,
    memberships: Path,
    *,
    team_id: str | None = None,
    team_name: str | None = None,
    team_queries: list[str] | None = None,
) -> tuple[dict[str, Any], PlayerAttributePromptBuilder]:
    validate_csv_target(players)
    validate_csv_file(memberships, writable=True)
    source_hashes = (digest(players), digest(memberships))
    builder = PlayerAttributePromptBuilder(
        prompts_dir=ROOT / "prompts/player_attributes"
    )
    if team_queries:
        selected = {}
        for query in team_queries:
            entries = list_attribute_teams(
                players_csv=players,
                memberships_csv=memberships,
                team_id=query if query.isdecimal() else None,
                team_name=None if query.isdecimal() else query,
            )
            for entry in entries:
                selected[entry.team_id] = entry
        catalog = tuple(selected.values())
    else:
        catalog = list_attribute_teams(
            players_csv=players,
            memberships_csv=memberships,
            team_id=team_id,
            team_name=team_name,
        )
    if team_id is not None or team_name is not None:
        logging.info("Selected team: %s (ID: %s)", catalog[0].name, catalog[0].team_id)
    accepted, failed, all_ids = [], [], set()
    for index, entry in enumerate(sorted(catalog, key=lambda s: int(s.team_id)), 1):
        try:
            team, targets = resolve_design_targets(
                players_csv=players,
                memberships_csv=memberships,
                team_kind=entry.kind.lower(),
                team_id=entry.team_id,
            )
            ids = [t.player_id for t in targets]
            preflight_player_injection(players_csv=players, target_ids=ids)
            builder.build_profiles_call(team, targets)
            all_ids.update(ids)
            accepted.append(
                {
                    "id": team.team_id,
                    "name": team.name,
                    "kind": team.kind,
                    "player_ids": ids,
                }
            )
        except Exception as error:
            failed.append(
                {
                    "id": entry.team_id,
                    "name": entry.name,
                    "kind": entry.kind,
                    "error": str(error),
                }
            )
        if index % 10 == 0:
            logging.info("Offline preflight: %s/%s teams checked", index, len(catalog))
    if source_hashes != (digest(players), digest(memberships)):
        raise RuntimeError("Source CSV changed during offline preflight")
    report = {
        "team_count": len(catalog),
        "player_count": len(all_ids),
        "teams": accepted,
        "failed": failed,
        "players_sha256": digest(players),
        "memberships_sha256": digest(memberships),
        "policy_sha256": prompt_digest(),
        "players_csv": str(players.resolve()),
        "teams_players_csv": str(memberships.resolve()),
    }
    if team_id is not None or team_name is not None:
        report["selection"] = catalog[0].team_id
    elif team_queries:
        ids = sorted((entry.team_id for entry in catalog), key=int)
        report["selection"] = ids[0] if len(ids) == 1 else ids
    return report, builder


def verify(
    state: Mapping[str, Any], output: Path, players_csv: Path
) -> dict[str, int | str]:
    original = rows(output / "Players.before.csv")
    current = rows(players_csv)
    if state.get("selection") is not None:
        target_ids = {pid for team in state["teams"] for pid in team["player_ids"]}
        original = [row for row in original if row["Id"] in target_ids]
        current = [row for row in current if row["Id"] in target_ids]
    expected = {r["Id"]: dict(r) for r in original}
    covered = set()
    for item in state["completed"].values():
        team = read_player_attribute_team(Path(item["config"]))
        report_path = Path(item["report"])
        if not report_path.exists():
            write_text_atomic(report_path, render_player_attribute_team_markdown(team))
        if digest(report_path) != item["report_sha256"]:
            raise RuntimeError(f"Player Information Report changed: {report_path}")
        for profile in team.to_dict()["Players"]:
            pid = profile["Player ID"]
            _apply_profile(expected[pid], profile)
            covered.add(pid)
    mismatches = attribute_mismatches(original, current, expected)
    if mismatches:
        raise RuntimeError(f"CSV verification mismatch: {mismatches[:20]}")
    result: dict[str, int | str] = {
        "verified_players": len(covered),
        "sha256": digest(players_csv),
    }
    if state.get("selection") is not None:
        result["target_csv_rows"] = len(current)
    else:
        result["total_csv_rows"] = len(current)
        result["unmodeled_rows_unchanged"] = len(current) - len(covered)
    return result


def main() -> int:
    with ExitStack() as resources:
        return _main(resources)


def _main(resources: ExitStack) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--check-only", action=argparse.BooleanOptionalAction, default=False
    )
    parser.add_argument(
        "--output",
        "--output-dir",
        type=Path,
        help="Audit/checkpoint directory; use a separate directory for each team selection",
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--team-id", help="Exact team ID from Teams-Players.csv")
    selector.add_argument(
        "--team",
        action="append",
        help="Exact team name or ID; repeat for multiple teams",
    )
    add_scope_arguments(parser)
    parser.add_argument("--model", default=Config.DEFAULT_MODEL)
    parser.add_argument(
        "--effort", choices=Config.EFFORT_CHOICES, default=Config.DEFAULT_EFFORT
    )
    parser.add_argument("--delay", type=float, default=5.0)
    parser.add_argument(
        "--max-turns",
        type=int,
        default=Config.DEFAULT_PLAYER_ATTRIBUTE_MAX_TURNS,
        help="Positive Claude CLI turn limit per request, including tool interactions "
        f"(default: {Config.DEFAULT_PLAYER_ATTRIBUTE_MAX_TURNS}); also applies to repairs and retries",
    )
    parser.add_argument(
        "--max-teams",
        type=int,
        help="Maximum pending teams to attempt in this invocation",
    )
    parser.add_argument(
        "--fast",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable fast mode for adapter",
    )
    args = parse_workflow_args(parser, "player_attributes")
    root_logger = logging.getLogger()
    resources.callback(root_logger.setLevel, root_logger.level)
    root_logger.setLevel(logging.INFO)

    def add_handler(handler: logging.Handler) -> None:
        resources.callback(handler.close)
        resources.callback(root_logger.removeHandler, handler)
        root_logger.addHandler(handler)

    add_handler(logging.StreamHandler(sys.stdout))
    players, memberships = args.players_csv, args.teams_players_csv
    try:
        validate_csv_target(players)
        validate_csv_file(memberships, writable=True)
    except OSError as error:
        parser.error(str(error))
    out = (args.output or Path.cwd() / "outputs/player_attributes").resolve()
    if not args.check_only:
        out.mkdir(parents=True, exist_ok=True)
        acquire_lock(
            resources, players.with_name(f".{players.name}.player_attributes.lock")
        )
        acquire_lock(resources, out / "batch.lock")
        add_handler(logging.FileHandler(out / "batch.log", encoding="utf-8"))
    try:
        if len(args.teams) > 1:
            report, builder = preflight(players, memberships, team_queries=args.teams)
        else:
            query = args.teams[0] if args.teams else None
            by_id = args.team_id is not None or (
                query is not None and query.isdecimal()
            )
            report, builder = preflight(
                players,
                memberships,
                team_id=query if by_id else None,
                team_name=None if by_id else query,
            )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(
        json.dumps({k: v for k, v in report.items() if k != "teams"}, indent=2),
        flush=True,
    )
    if args.check_only:
        out.mkdir(parents=True, exist_ok=True)
        save(out / "preflight.json", report)
        return int(bool(report["failed"]))
    checkpoint = out / "batch_state.json"
    completion_record = out / COMPLETION_REGISTRY_NAME
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text())
        if any(
            state.get(key) != report.get(key)
            for key in ("players_csv", "teams_players_csv")
        ):
            raise RuntimeError(
                "Source CSV paths changed; use a separate --output directory"
            )
        if state.get("selection") != report.get("selection"):
            raise RuntimeError(
                "Team selection changed; use a separate --output directory"
            )
        if (state["model"], state["effort"]) != (args.model, args.effort):
            raise RuntimeError("Model or effort changed since batch started")
        if (
            state["memberships_sha256"] != report["memberships_sha256"]
            or state["policy_sha256"] != report["policy_sha256"]
        ):
            raise RuntimeError("Memberships or policy changed since batch started")
        if state["current_players_sha256"] != report["players_sha256"]:
            raise RuntimeError(
                "Players.csv changed outside the last checkpoint; inspect audit before resuming"
            )
        verify(state, out, players)
    else:
        shutil.copy2(players, out / "Players.before.csv")
        save(out / "preflight.json", report)
        state = {
            **report,
            "completed": {},
            "failures": {},
            "status": "running",
            "model": args.model,
            "effort": args.effort,
            "current_players_sha256": report["players_sha256"],
        }
        save(checkpoint, state)
    # Recover a completion registry write interrupted after the checkpoint commit.
    completed_teams = {tid: item["name"] for tid, item in state["completed"].items()}
    for entry in report["teams"] + report["failed"]:
        if entry["id"] in completed_teams and entry.get("name"):
            completed_teams[entry["id"]] = entry["name"]
    save_completed_teams(completion_record, completed_teams)
    audit = out / "calls"
    audit.mkdir(exist_ok=True)
    adapter = AuditedAdapter(
        audit,
        model=args.model,
        effort=args.effort,
        delay=args.delay,
        fast_mode=args.fast,
        max_turns=args.max_turns,
    )
    runner = PlayerAttributeRunner(
        output_base_dir=out / "teams",
        model=args.model,
        prompt_builder=builder,
        llm_adapter=adapter,
        observer=Observer(out / "events.jsonl"),
    )
    attempted = 0
    for index, entry in enumerate(report["teams"], 1):
        tid = entry["id"]
        if tid in completed_teams:
            continue
        if args.max_teams is not None and attempted >= args.max_teams:
            break
        attempted += 1
        if (
            digest(players) != state["current_players_sha256"]
            or digest(memberships) != state["memberships_sha256"]
        ):
            raise RuntimeError("Source changed outside batch; stopping")
        logging.info(
            "[%s/%s] %s: %s players",
            index,
            len(report["teams"]),
            entry["name"],
            len(entry["player_ids"]),
        )
        try:
            team, targets = resolve_design_targets(
                players_csv=players,
                memberships_csv=memberships,
                team_kind=entry["kind"].lower(),
                team_id=tid,
            )
            result = runner.run(team=team, targets=targets, players_csv=players)
            state["completed"][tid] = {
                "name": team.name,
                "count": result.injection.modified_count,
                "config": str(result.config_path),
                "manifest": str(result.manifest_path),
                "manifest_finalized": result.manifest_finalized,
                "report": str(result.report_path),
                "report_sha256": digest(result.report_path),
            }
            state["current_players_sha256"] = result.injection.players_sha256_after
            state["failures"].pop(tid, None)
        except Exception as error:
            state["failures"][tid] = str(error)
            if digest(players) != state["current_players_sha256"]:
                save(checkpoint, state)
                raise RuntimeError(
                    "CSV changed during failed run; stopping for audit"
                ) from error
            if any(
                term in str(error).lower()
                for term in (
                    "session limit",
                    "usage limit",
                    "weekly limit",
                    "credit balance",
                )
            ):
                state["status"] = "incomplete"
                save(checkpoint, state)
                logging.warning(
                    "Claude Code usage limit reached while processing %s; "
                    "progress saved. Exiting. Resume after the limit resets.",
                    entry["name"],
                )
                return 1
            logging.exception("Team failed: %s", entry["name"])
        save(checkpoint, state)
        if tid in state["completed"]:
            # The runner has committed the CSV and the audit checkpoint is saved.
            # Stop on record-write failure; startup can recover from the checkpoint.
            completed_teams[tid] = state["completed"][tid]["name"]
            save_completed_teams(completion_record, completed_teams)
        if any(
            term in state["failures"].get(tid, "").lower()
            for term in (
                "not logged in",
                "authentication",
                "usage limit",
                "credit balance",
                "unknown model",
                "invalid model",
            )
        ):
            break
    state["verification"] = verify(state, out, players)
    all_done = all(entry["id"] in completed_teams for entry in report["teams"])
    state["status"] = "complete" if all_done and not report["failed"] else "incomplete"
    save(checkpoint, state)
    save(out / "verification.json", state["verification"])
    print(
        json.dumps(
            {
                "status": state["status"],
                "completed_teams": sum(
                    entry["id"] in completed_teams for entry in report["teams"]
                ),
                **state["verification"],
            },
            indent=2,
        )
    )
    return 0 if state["status"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
