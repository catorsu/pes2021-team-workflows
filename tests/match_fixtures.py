from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from pes_workflows.contracts.constants import (
    PRESET_RISK_BUDGETS,
    SCHEMA_VERSION,
)
from pes_workflows.players.generator import GeneratedPlayerRecords
from tests.prompt_support import task_text

POSITIONS = ["GK", "CB", "CB", "DMF", "LB", "RB", "CMF", "AMF", "LWF", "RWF", "CF"]


def source_identity() -> dict[str, Any]:
    players = {str(index): f"Player {index}" for index in range(1, 13)}
    registered = {str(index): POSITIONS[index - 1] for index in range(1, 12)}
    registered["12"] = "GK"
    familiarity = {
        str(index): {"L2": {POSITIONS[index - 1]}, "L1": set()}
        for index in range(1, 12)
    }
    familiarity["12"] = {"L2": {"GK"}, "L1": set()}
    return {
        "team_id": "77",
        "total_players": 12,
        "players": players,
        "registered_positions": registered,
        "familiarity": familiarity,
    }


def strategy_raw() -> dict[str, Any]:
    return {
        "Schema Version": SCHEMA_VERSION,
        "Artifact": "StartingXILock",
        "Team ID": "77",
        "Starting XI": [
            {"Slot": slot, "Player ID": str(slot + 1)} for slot in range(11)
        ],
    }


def basic_instructions() -> dict[str, Any]:
    return {
        "Attacking Style": "Possession Game",
        "Build Up": "Short-pass",
        "Attacking Area": "Center",
        "Positioning": "Maintain Formation",
        "Support Range": 5,
        "Numbers in Attack": "Medium",
        "Defensive Style": "Frontline Pressure",
        "Containment Area": "Center",
        "Pressuring": "Aggressive",
        "Defensive Line": 5,
        "Compactness": 7,
        "Numbers in Defence": "Medium",
    }


def preset_raw(name: str, join_player_ids: tuple[str, ...] = ("2",)) -> dict[str, Any]:
    def state_rows() -> list[dict[str, Any]]:
        rows = []
        for slot, position in enumerate(POSITIONS):
            grid = (
                {"Row": 0, "Lane": "C_Center"}
                if slot == 0
                else {"Row": min(9, slot), "Lane": "C_Center"}
            )
            rows.append(
                {
                    "Slot": slot,
                    "Position": position,
                    "Grid": grid,
                    "Tactical Duty": f"Perform the assigned {position} function.",
                }
            )
        return rows

    minimum = 1 if name == "Custom" else 2
    return {
        "Schema Version": SCHEMA_VERSION,
        "Artifact": "PresetPlan",
        "Preset": name,
        "Scenario Response": "Use a coherent scenario-specific structure.",
        "Risk Budget": PRESET_RISK_BUDGETS[name],
        "Formation Signature": "balanced synthetic fixture",
        "States": {
            "Normal": state_rows(),
            "With Ball": state_rows(),
            "Without Ball": state_rows(),
        },
        "Rest Defence Contract": {
            "Retained Protector Slots": [
                slot
                for slot in (1, 2, 3, 4)
                if slot not in {int(player_id) - 1 for player_id in join_player_ids}
            ],
            "Minimum Retained": minimum,
            "Rationale": "The retained central unit protects direct transitions.",
        },
        "Basic Instructions": basic_instructions(),
        "Advanced Instructions": {
            slot: {"Instruction": "Blank", "Designated Slot": None}
            for slot in ("Attacking 1", "Attacking 2", "Defending 1", "Defending 2")
        },
        "Players to Join Attack": [
            {
                "Order": order,
                "Slot": int(player_id) - 1,
                "Player ID": player_id,
                "Aerial Rationale": "Supplied aerial attributes justify this marginal contribution.",
            }
            for order, player_id in enumerate(join_player_ids, start=1)
        ],
        "Auto Offside Trap": "Off",
        "Mechanisms": [
            "wide outlet plus central occupation",
            "screen plus counterpressure",
        ],
        "Binding Constraints": [],
    }


def bench_raw() -> dict[str, Any]:
    return {
        "Schema Version": SCHEMA_VERSION,
        "Artifact": "BenchDecision",
        "Demand Profile": [
            {
                "Demand": demand,
                "Frozen Source": source,
                "Required Profile": profile,
            }
            for demand, source, profile in (
                (
                    "goalkeeper cover",
                    ["Main Normal Slot 0 Tactical Duty"],
                    "Level 1 or Level 2 familiarity at GK",
                ),
                (
                    "central cover",
                    [
                        "Main Normal Slot 3 Tactical Duty",
                        "Defensive Without Ball Slot 3 Tactical Duty",
                    ],
                    "a familiar central role",
                ),
                (
                    "wide cover",
                    ["Main With Ball Slot 8 Tactical Duty"],
                    "a familiar wide role",
                ),
                (
                    "late scoring",
                    ["Custom With Ball Slot 10 Tactical Duty"],
                    "a credible scoring role",
                ),
            )
        ],
        "Substitutes": [
            {
                "Player ID": "12",
                "Demands Served": ["goalkeeper cover"],
                "Rationale": "Provides the only eligible goalkeeper cover.",
            }
        ],
        "Coverage Gaps": [
            {
                "Demand": "central cover",
                "Status": "Unserved",
                "Reason": "no non-starting player provides the declared central profile",
            },
            {
                "Demand": "wide cover",
                "Status": "Unserved",
                "Reason": "no non-starting player provides the declared wide profile",
            },
            {
                "Demand": "late scoring",
                "Status": "Unserved",
                "Reason": "no non-starting player provides the declared scoring profile",
            },
        ],
    }


def runtime_player_records() -> str:
    matrix = "\n".join(
        f"| **{position}** | None | None | None |"
        for position in (
            "GK",
            "CB",
            "LB",
            "RB",
            "DMF",
            "CMF",
            "LMF",
            "RMF",
            "AMF",
            "LWF",
            "RWF",
            "SS",
            "CF",
        )
    )
    dossiers = []
    for index in range(1, 13):
        position = POSITIONS[index - 1] if index <= 11 else "GK"
        dossiers.append(
            "\n".join(
                (
                    f"### Player: Player {index} (ID: {index})",
                    "",
                    f"- Basic Profile: Registered Position: {position}",
                    "- Familiarity:",
                    f"  - Fully Familiar (Level 2): {position}",
                    "  - Partially Familiar (Level 1): None",
                    "- Detailed Abilities: Height: 180, Physical Contact: 75, "
                    "Jump: 75, Header: 75",
                )
            )
        )
    return (
        "# Runtime fixture\n\n"
        "Team: Fixture FC (ID: 77) | Total Players: 12\n\n"
        "## PRE-CALCULATED POSITIONAL SQUAD MATRIX\n\n"
        "| Position | Level-2 Players (ID) | Level-1 Players (ID) | "
        "Squad-Available Playing Styles (derived) |\n"
        "| :--- | :--- | :--- | :--- |\n"
        f"{matrix}\n\n"
        "## DETAILED PLAYER DOSSIERS\n\n" + "\n\n".join(dossiers) + "\n"
    )


def fixture_player_records(
    output_name: str = "fixture", team_id: str = "77"
) -> GeneratedPlayerRecords:

    return GeneratedPlayerRecords(
        team_id=team_id,
        team_name=output_name,
        kind="National",
        output_name=output_name,
        content=runtime_player_records().replace("(ID: 77)", f"(ID: {team_id})", 1),
        player_ids=tuple(str(index) for index in range(1, 13)),
        players_sha256="0" * 64,
        roster_sha256="1" * 64,
    )


class FakeCompletions:
    def __init__(self) -> None:
        self.user_prompts = []
        self.system_prompts = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        user_prompt = kwargs["messages"][1]["content"]
        self.user_prompts.append(user_prompt)
        self.system_prompts.append(kwargs["messages"][0]["content"])
        task = task_text(user_prompt)
        if task.startswith("STEP 1"):
            raw = strategy_raw()
        elif task.startswith("STEP 2"):
            raw = preset_raw("Main")
        elif task.startswith("STEP 3"):
            raw = preset_raw("Defensive")
        elif task.startswith("STEP 4"):
            raw = preset_raw("Custom")
        elif task.startswith("STEP 5"):
            raw = bench_raw()
        else:
            raise AssertionError("unexpected fake-API request")
        message = SimpleNamespace(
            content=json.dumps(raw),
            reasoning_content="private reasoning must never be persisted",
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self) -> None:
        self.completions = FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


class SingleModeFakeCompletions:
    def __init__(self) -> None:
        self.user_prompts = []
        self.system_prompts = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        user_prompt = kwargs["messages"][1]["content"]
        self.user_prompts.append(user_prompt)
        self.system_prompts.append(kwargs["messages"][0]["content"])
        task = task_text(user_prompt)
        if task.startswith("STEP 1 OF 3"):
            raw = strategy_raw()
        elif task.startswith("STEP 2 OF 3"):
            raw = preset_raw("Main")
            raw["Auto Offside Trap"] = "On"
        elif task.startswith("STEP 3 OF 3"):
            raw = bench_raw()
            for slot, demand in enumerate(raw["Demand Profile"], start=1):
                demand["Frozen Source"] = [f"Main Normal Slot {slot} Tactical Duty"]
        else:
            raise AssertionError("unexpected fake single-mode API request")
        message = SimpleNamespace(
            content=json.dumps(raw),
            reasoning_content="private reasoning must never be persisted",
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class SingleModeFakeClient:
    def __init__(self) -> None:
        self.completions = SingleModeFakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)
