"""Atomic checkpoint JSON and ID-first completion registries."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from pathlib import Path

from pes_workflows.players.generator import TeamRecord
from pes_workflows.storage.atomic import write_text_atomic

logger = logging.getLogger("Generate_Match_Plan")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: object) -> None:
    write_text_atomic(
        path, json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"
    )


def save_completed_teams(path: Path, teams: Mapping[str, str]) -> None:
    lines = []
    for tid, name in sorted(teams.items()):
        name = " ".join(name.split())  # Keep each record on a single line.
        lines.append(f"{tid}\t{name}\n" if name else f"{tid}\n")
    write_text_atomic(path, "".join(lines))


def load_completed_teams(registry: Path, *, required: bool = False) -> dict[str, str]:
    """Read positive IDs with optional tab-separated team names."""
    try:
        content = registry.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        if required:
            raise
        return {}
    completed: dict[str, str] = {}
    for line_number, line in enumerate(content.splitlines(keepends=True), 1):
        if not line.strip():
            continue
        team_id, _, name = line.strip().partition("\t")
        team_id, name = team_id.strip(), name.strip()
        if not team_id.isdecimal() or int(team_id) <= 0:
            logger.warning(
                "Ignoring malformed registry entry %s:%s", registry, line_number
            )
            continue
        team_id = str(int(team_id))
        completed[team_id] = name.strip() or completed.get(team_id, "")
    return completed


def read_completed_teams(registry: Path, *, required: bool = False) -> set[str]:
    return set(load_completed_teams(registry, required=required))


def append_completed_team(registry: Path, team_rec: TeamRecord) -> None:
    """Atomically merge completion after the formations commit has returned."""
    completed = load_completed_teams(registry)
    team_id = str(int(team_rec.team_id))
    completed[team_id] = team_rec.team_name or completed.get(team_id, "")
    registry.parent.mkdir(parents=True, exist_ok=True)
    save_completed_teams(registry, completed)
