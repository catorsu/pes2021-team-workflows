"""Transactional CSV injection for compiled semantic game plans."""

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import Config
from ..storage.csv_store import _find_unique_team_row, _map_roster_indices
from .advanced import resolve_targeted_instructions
from .compile import compile_semantic_game_plan
from .errors import SemanticGridError
from .mappings import (
    FORMATION_ROSTER_SIZE,
    GLOBAL_JOIN_ATTACK_COLUMNS,
    ROLE_COLUMN_ORDER,
)
from .roles import _derive_routine_role_ids, _resolve_role_updates


def _resolve_join_attack_updates(
    join_attack_settings: Mapping[str, Any],
    id_to_index: Mapping[str, Any],
) -> dict[str, str]:
    """Resolve Main Join Attack IDs into the three global CSV columns."""
    updates = {column: "255" for column in GLOBAL_JOIN_ATTACK_COLUMNS}

    main_joiners = join_attack_settings.get("S1", [])
    if len(main_joiners) > len(GLOBAL_JOIN_ATTACK_COLUMNS):
        raise SemanticGridError(
            "Main Players to Join Attack exceeds the three global Header columns."
        )

    for column, item in zip(GLOBAL_JOIN_ATTACK_COLUMNS, main_joiners):
        player_id = str(item["Player ID"]).strip()
        if player_id not in id_to_index:
            raise SemanticGridError(
                "Main Players to Join Attack Player ID "
                f"{player_id!r} is not in the resolved Rosters.csv indices."
            )
        roster_index = str(id_to_index[player_id])
        try:
            numeric_index = int(roster_index)
        except (TypeError, ValueError) as err:
            raise SemanticGridError(
                f"Resolved Rosters.csv index {roster_index!r} for Join Attack "
                f"Player ID {player_id!r} is not an integer."
            ) from err
        if not 0 <= numeric_index < FORMATION_ROSTER_SIZE:
            raise SemanticGridError(
                f"Resolved Rosters.csv index {numeric_index} for Join Attack "
                f"Player ID {player_id!r} is outside 0-{FORMATION_ROSTER_SIZE - 1}."
            )
        updates[column] = str(numeric_index)

    return updates


def _inject_compiled_formation(
    rosters_csv: Path,
    formations_csv: Path,
    compiled: Mapping[str, Any],
    *,
    dry_run: bool = False,
    player_stats: Mapping[str, dict[str, Any]] | None = None,
    players_csv: Path | None,
    preset_mode: str = "multi",
    report: Callable[[str], None] | None = None,
) -> bool:
    if report is None:
        report = print
    team_id = compiled["team_id"]

    report(">>> Reading data files...")
    try:
        df_roster = pd.read_csv(rosters_csv, sep=";", dtype=str, encoding="utf-8-sig")
        df_formations = pd.read_csv(
            formations_csv, sep=";", dtype=str, encoding="utf-8-sig"
        )
    except FileNotFoundError as err:
        report(f"❌ Error: Could not find required CSV file: {err.filename}")
        return False

    warnings: list[str] = []
    try:
        roster_idx = _find_unique_team_row(df_roster, team_id, "Rosters.csv")
        form_idx = _find_unique_team_row(df_formations, team_id, "Formations.csv")
        mapped_indices, _current_roster, id_to_index, reserve_count, padding_count = (
            _map_roster_indices(
                df_roster,
                roster_idx,
                team_id,
                compiled["squad_ids"],
            )
        )
        missing_role_columns = [
            column
            for column in ROLE_COLUMN_ORDER
            if column not in df_formations.columns
        ]
        if missing_role_columns:
            raise SemanticGridError(
                "Formations.csv is missing role column(s): "
                + ", ".join(missing_role_columns)
                + "."
            )

        if preset_mode == "single":
            all_join_attack_ids = {
                str(item["Player ID"]).strip()
                for item in compiled["join_attack_settings"]["S1"]
            }
        else:
            all_join_attack_ids = {
                item["Player ID"]
                for joiners in compiled["join_attack_settings"].values()
                for item in joiners
            }
        if not player_stats and players_csv is not None:
            from ..storage.csv_store import load_player_stats_from_csv

            player_stats = load_player_stats_from_csv(
                players_csv, set(compiled["squad_ids"])
            )
        if not player_stats:
            # Warn rather than raise: the roles are still written, and a user
            # who has configured no players CSV would otherwise be blocked
            warnings.append(
                "No player attributes were available, so the captain and the "
                "six set-piece takers were resolved by default scores and formation positions; "
                "check the players CSV configured for this run."
            )

        routine_role_ids = _derive_routine_role_ids(
            compiled["squad_ids"],
            compiled["main_normal_entries"],
            join_attack_player_ids=all_join_attack_ids,
            player_stats=player_stats,
        )
        role_updates = _resolve_role_updates(
            routine_role_ids,
            id_to_index,
        )

        updates = {
            f"IndexPlayer{i}": mapped_indices[i - 1]
            for i in range(1, FORMATION_ROSTER_SIZE + 1)
        }
        updates.update(compiled["flat_columns"])
        updates.update(
            resolve_targeted_instructions(
                compiled["targeted_instructions"], id_to_index
            )
        )
        updates.update(role_updates)
        updates.update(
            _resolve_join_attack_updates(
                compiled["join_attack_settings"],
                id_to_index,
            )
        )

        missing_columns = [
            column for column in updates if column not in df_formations.columns
        ]
        if missing_columns:
            raise SemanticGridError(
                "Formations.csv is missing required output column(s): "
                + ", ".join(sorted(missing_columns))
                + "."
            )
    except SemanticGridError as err:
        report(f"❌ CSV resolution failed — nothing was written.\n   {err}")
        return False
    report(f"✅ Successfully located team ID {team_id} in both CSV files.")
    report(
        f"✅ Formation roster resolved: {compiled['matchday_count']} matchday + "
        f"{reserve_count} automatic reserve(s) + {padding_count} trailing pad(s)."
    )

    report(
        "✅ Semantic Row 0-9 assignments resolved into deterministic coordinates; "
        "injectable tactical values, positions, fluid-state coordinates, auto settings, "
        "and role assignments mapped successfully in memory."
    )

    for warning in warnings:
        report(f"⚠️ {warning}")

    if preset_mode == "multi":
        report(
            "Auto Offside Trap and Players to Join Attack use Main's global CSV fields; "
            "adjust these two settings in-game for Defensive/Custom overrides."
        )
    if dry_run:
        report(
            f"\n🧪 DRY RUN — validation and resolution succeeded; '{formations_csv}' was NOT modified."
        )
    else:
        temp_formations = formations_csv.with_name(formations_csv.name + ".tmp")
        try:
            for column, value in updates.items():
                df_formations.at[form_idx, column] = str(value)
            df_formations.to_csv(
                temp_formations, sep=";", index=False, encoding="utf-8-sig"
            )
            os.replace(temp_formations, formations_csv)
            report(
                f"\n🎉 Done! All tactical parameters and coordinates have been directly overwritten to '{formations_csv}'."
            )
        finally:
            if temp_formations.exists():
                temp_formations.unlink()

    return True


def process_formation_data(
    rosters_csv: Path,
    formations_csv: Path,
    config: Mapping[str, Any],
    *,
    dry_run: bool = False,
    strict: bool = False,
    auto_substitutions: int = Config.DEFAULT_AUTO_SUBSTITUTIONS,
    auto_change_att_def: int = Config.DEFAULT_AUTO_CHANGE_ATT_DEF,
    auto_switch_preset_tactics: int | None = None,
    player_stats: Mapping[str, dict[str, Any]] | None = None,
    players_csv: Path | None,
    preset_mode: str = "multi",
    report: Callable[[str], None] | None = None,
) -> bool:
    """Compile and atomically replace the team's formation row unless dry_run.

    players_csv must explicitly name the attribute source or be None; missing
    attributes produce a warning and routine roles are chosen from default scores and formation positions.
    """

    sink = report or print
    try:
        compiled = compile_semantic_game_plan(
            config,
            strict=strict,
            preset_mode=preset_mode,
            auto_substitutions=auto_substitutions,
            auto_change_att_def=auto_change_att_def,
            auto_switch_preset_tactics=auto_switch_preset_tactics,
        )
    except SemanticGridError as error:
        sink(f"❌ Semantic game plan rejected — nothing was written.\n   {error}")
        return False
    return _inject_compiled_formation(
        rosters_csv,
        formations_csv,
        compiled,
        dry_run=dry_run,
        player_stats=player_stats,
        players_csv=players_csv,
        preset_mode=preset_mode,
        report=report,
    )


__all__ = ["process_formation_data"]
