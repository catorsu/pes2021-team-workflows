"CSV-backed roster lookup and formation index mapping."

from __future__ import annotations

import csv
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from pes_workflows.domain.vocabulary import ABILITY_COLUMN_MAP, PLAYER_SKILL_COLUMNS

from ..compiler.errors import SemanticGridError
from ..compiler.mappings import (
    EMPTY_ROSTER_IDS,
    FORMATION_ROSTER_SIZE,
    STARTER_COUNT,
)


def _clean_csv_token(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _is_valid_roster_id(token: str) -> bool:
    return (
        token.lower() not in EMPTY_ROSTER_IDS
        and token.isascii()
        and token.isdigit()
        and int(token) > 0
        and int(token) != 255
    )


def _find_unique_team_row(frame: pd.DataFrame, team_id: str, label: str) -> int:
    if "Id" not in frame.columns:
        raise SemanticGridError(f"{label} is missing required 'Id' column.")
    matches = [
        index
        for index, value in frame["Id"].items()
        if _clean_csv_token(value) == team_id
    ]
    if not matches:
        raise SemanticGridError(f"Team ID {team_id!r} was not found in {label}.")
    if len(matches) != 1:
        raise SemanticGridError(
            f"Team ID {team_id!r} appears {len(matches)} times in {label}; "
            "the target row is ambiguous."
        )
    return matches[0]


def _read_roster_row(df_roster: pd.DataFrame, roster_idx: int) -> list[str]:
    required = [f"Player{i}" for i in range(1, FORMATION_ROSTER_SIZE + 1)]
    missing = [column for column in required if column not in df_roster.columns]
    if missing:
        raise SemanticGridError(
            "Rosters.csv is missing player slot column(s): " + ", ".join(missing) + "."
        )
    current = [
        _clean_csv_token(df_roster.at[roster_idx, column]) for column in required
    ]
    malformed = [
        f"Player{index}={token!r}"
        for index, token in enumerate(current, start=1)
        if token.lower() not in EMPTY_ROSTER_IDS and not _is_valid_roster_id(token)
    ]
    if malformed:
        raise SemanticGridError(
            "Rosters.csv contains malformed non-empty player ID(s): "
            + ", ".join(malformed)
            + ". Expected positive numeric source IDs; 0/255 are empty sentinels."
        )
    return current


def _map_roster_indices(
    df_roster: pd.DataFrame, roster_idx: int, team_id: str, squad_ids: Sequence[str]
) -> tuple[list[str], list[str], dict[str, int], int, int]:
    current = _read_roster_row(df_roster, roster_idx)
    id_to_index = {}
    duplicate_ids = set()
    for index, pid in enumerate(current):
        if not _is_valid_roster_id(pid):
            continue
        if pid in id_to_index:
            duplicate_ids.add(pid)
        else:
            id_to_index[pid] = index
    if duplicate_ids:
        raise SemanticGridError(
            f"Rosters.csv team {team_id} contains duplicate non-empty player ID(s): "
            + ", ".join(sorted(duplicate_ids))
            + "."
        )

    missing_matchday = [pid for pid in squad_ids if pid not in id_to_index]
    if missing_matchday:
        details = []
        for pid in missing_matchday:
            slot = squad_ids.index(pid)
            group = "starter" if slot < STARTER_COUNT else "substitute"
            details.append(f"{pid} ({group} entry {slot + 1})")
        raise SemanticGridError(
            f"All {len(squad_ids)} matchday players must already exist in Rosters.csv "
            f"for team {team_id}; missing: " + ", ".join(details) + "."
        )

    selected = set(squad_ids)
    matchday_indices = [str(id_to_index[pid]) for pid in squad_ids]
    reserve_indices = [
        str(index)
        for index, pid in enumerate(current)
        if _is_valid_roster_id(pid) and pid not in selected
    ]
    mapped = matchday_indices + reserve_indices
    if len(mapped) > FORMATION_ROSTER_SIZE:
        raise SemanticGridError(
            f"Resolved formation roster has {len(mapped)} players, exceeding "
            f"the {FORMATION_ROSTER_SIZE}-slot limit."
        )
    padding_count = FORMATION_ROSTER_SIZE - len(mapped)
    mapped.extend(["255"] * padding_count)
    return mapped, current, id_to_index, len(reserve_indices), padding_count


def load_player_stats_from_csv(
    players_csv_path: Path, player_ids: Collection[str]
) -> dict[str, dict[str, Any]]:
    """Read canonical role-selection inputs from the editor export."""
    stats: dict[str, dict[str, Any]] = {}
    with players_csv_path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream, delimiter=";"):
            player_id = row["Id"].strip()
            if player_id not in player_ids:
                continue
            abilities = {}
            for name, column in ABILITY_COLUMN_MAP.items():
                value = row.get(column, "").strip()
                abilities[name] = int(value) if value.isdecimal() else 50
            skills = set()
            for name, column in PLAYER_SKILL_COLUMNS.items():
                if row.get(column, "").strip().casefold() == "true":
                    skills.add(name)
            height = row.get("Height", "").strip()
            stats[player_id] = {
                "foot": "Left"
                if row.get("Foot", "").strip().casefold() in {"1", "true"}
                else "Right",
                "height": int(height) if height.isdecimal() else 180,
                "skills": skills,
                "abilities": abilities,
            }
    return stats
