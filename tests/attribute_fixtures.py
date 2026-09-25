"""Player attribute fixtures derived from domain column definitions."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pes_workflows.domain.vocabulary import (
    ABILITY_COLUMN_MAP,
    COM_STYLE_COLUMNS,
    PLAYER_SKILL_COLUMNS,
    POSITION_IDS,
)
from pes_workflows.player_attributes.constants import (
    EDIT_FLAG_COLUMNS,
    GENERAL_ABILITY_STATS,
    GK_STATS,
)
from pes_workflows.player_attributes.sources import PlayerDesignTarget, TeamIdentity

ATTRIBUTE_PLAYER_COLUMNS = (
    (
        "Id",
        "Name",
        "Height",
        "Weight",
        "Country",
        "Country2",
        "Age",
        "Foot",
        "PlayingStyle",
        "POS",
    )
    + tuple(POSITION_IDS)
    + tuple(ABILITY_COLUMN_MAP.values())
    + tuple(PLAYER_SKILL_COLUMNS.values())
    + tuple(COM_STYLE_COLUMNS.values())
    + EDIT_FLAG_COLUMNS
)


def profiles_artifact(
    team: TeamIdentity, targets: Sequence[PlayerDesignTarget]
) -> dict[str, Any]:
    return {
        "Schema Version": "4.0",
        "Artifact": "PlayerProfiles",
        "Team Name": team.name,
        "Team ID": team.team_id,
        "Total Players": len(targets),
        "Players": [
            {
                "Player ID": target.player_id,
                "Player Name": target.name,
                "Age": target.designated_age,
                "Registered Position": "CB",
                "Position Familiarity": {"CB": 2, "DMF": 1},
                "Stronger Foot": "Right Foot",
                "Playing Style": "Build Up",
                # Not in column order, so the report is proved to reorder
                "Player Skills": ["Captaincy", "Interception"],
                "COM Playing Styles": ["Long Ball Expert"],
            }
            for target in targets
        ],
    }


def abilities_artifact(
    team: TeamIdentity, targets: Sequence[PlayerDesignTarget]
) -> dict[str, Any]:
    abilities = {name: 70 for name in GENERAL_ABILITY_STATS}
    abilities.update({name: 40 for name in GK_STATS})
    return {
        "Schema Version": "4.0",
        "Artifact": "PlayerAbilities",
        "Team Name": team.name,
        "Team ID": team.team_id,
        "Total Players": len(targets),
        "Players": [
            {
                "Player ID": target.player_id,
                "Player Name": target.name,
                "Age": target.designated_age,
                "Abilities": dict(abilities),
                "Form and Traits": {
                    "Weak Foot Usage": 2,
                    "Weak Foot Accuracy": 3,
                    "Conditioning": 7,
                    "Injury Resistance": 3,
                },
            }
            for target in targets
        ],
    }


def make_targets(count: int) -> tuple[PlayerDesignTarget, ...]:
    return tuple(
        PlayerDesignTarget(str(100 + index), f"Player {index}", 20 + index)
        for index in range(1, count + 1)
    )


def write_attribute_targets_csv(
    path: Path, targets: Sequence[PlayerDesignTarget]
) -> Path:
    fieldnames = list(ATTRIBUTE_PLAYER_COLUMNS + ("Untouched",))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            delimiter=";",
            lineterminator="\r\n",
        )
        writer.writeheader()
        for target in targets:
            row = {name: "" for name in fieldnames}
            row.update(
                {
                    "Id": target.player_id,
                    "Name": target.name,
                    "Age": str(target.designated_age),
                    "Foot": "False",
                    "PlayingStyle": "0",
                    "POS": "1",
                    "Untouched": f"sentinel-{target.player_id}",
                }
            )
            row.update({position: "0" for position in POSITION_IDS})
            row.update({column: "40" for column in ABILITY_COLUMN_MAP.values()})
            row.update({column: "False" for column in PLAYER_SKILL_COLUMNS.values()})
            row.update({column: "False" for column in COM_STYLE_COLUMNS.values()})
            row.update({column: "False" for column in EDIT_FLAG_COLUMNS})
            writer.writerow(row)
    return path
