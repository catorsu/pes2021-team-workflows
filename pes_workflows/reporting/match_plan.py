"""Deterministic Markdown presentation of finalized match-plan decisions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pes_workflows.config import GlobalAutoOptions
from pes_workflows.contracts.constants import PRESET_NAMES, STATE_NAMES
from pes_workflows.contracts.preset import PresetPlan
from pes_workflows.reporting.markdown import escape_markdown


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *(
            "| " + " | ".join(escape_markdown(cell) for cell in row) + " |"
            for row in rows
        ),
        "",
    ]


def render_match_plan_report(
    *,
    team_name: str,
    semantic_plan: Mapping[str, Any],
    presets: Mapping[str, PresetPlan],
    routine_role_ids: Mapping[str, str],
    global_auto_options: GlobalAutoOptions,
    preset_mode: str,
) -> str:
    """Render accepted decisions without generating new tactical explanations."""
    squad = semantic_plan["Squad"]
    names = {row["Player ID"]: row["Player"] for row in squad}

    def player(player_id: str) -> str:
        return f"{names[player_id]} (ID: {player_id})"

    def slot_player(slot: int) -> str:
        return f"Slot {slot}: {player(squad[slot]['Player ID'])}"

    lines = [
        f"# Match Plan Report — {escape_markdown(team_name)}",
        "",
        f"Team ID: {escape_markdown(semantic_plan['Team ID'])}  ",
        f"Preset mode: {preset_mode}  ",
        "",
        "Finalized tactical decisions, published before CSV injection. "
        "See run_manifest.json for the final execution status.",
        "",
        "## Locked Starting XI",
        "",
        "Slots 0–10 identify the same players in every preset and fluid state.",
        "",
    ]
    lines += _table(
        ("Slot", "Player ID", "Player"),
        (
            (slot, row["Player ID"], row["Player"])
            for slot, row in enumerate(squad[:11])
        ),
    )
    lines += ["## Global Auto Options", ""]
    options = (
        (
            "Automatic substitutions",
            global_auto_options["auto_substitutions"],
            ("Off", "Very Late", "Flexible", "Very Early"),
        ),
        (
            "Automatic attack/defence adjustment",
            global_auto_options["auto_change_att_def"],
            ("Off", "On"),
        ),
        (
            "Automatic preset switching",
            global_auto_options["auto_switch_preset_tactics"],
            ("Off", "On"),
        ),
    )
    lines += _table(
        ("Option", "Value", "Meaning"),
        ((label, value, meanings[value]) for label, value, meanings in options),
    )
    lines += ["## Presets and Fluid Formations", ""]
    if preset_mode == "single":
        lines += [
            "Main is copied identically to the Main, Defensive, and Custom editor "
            "preset slots, including all three fluid states.",
            "",
        ]
    else:
        lines += [
            "Auto Offside Trap and Players to Join Attack use Main's global CSV "
            "fields. Apply Defensive/Custom overrides in-game.",
            "",
        ]
    for name in PRESET_NAMES:
        if name not in presets:
            continue
        raw = presets[name].to_model_dict()
        lines += [f"### {name}", ""]
        for key in ("Scenario Response", "Risk Budget", "Formation Signature"):
            lines += [f"**{key}:** {escape_markdown(raw[key])}", ""]
        for state in STATE_NAMES:
            lines += [f"#### {state}", ""]
            lines += _table(
                (
                    "Slot",
                    "Player",
                    "Position",
                    "Grid row",
                    "Grid lane",
                    "Tactical duty",
                ),
                (
                    (
                        row["Slot"],
                        player(squad[row["Slot"]]["Player ID"]),
                        row["Position"],
                        row["Grid"]["Row"],
                        row["Grid"]["Lane"],
                        row["Tactical Duty"],
                    )
                    for row in raw["States"][state]
                ),
            )
        lines += ["#### Basic Instructions", ""]
        lines += _table(("Setting", "Value"), raw["Basic Instructions"].items())
        lines += ["#### Advanced Instructions", ""]
        lines += _table(
            ("Instruction slot", "Instruction", "Designated player"),
            (
                (
                    slot,
                    row["Instruction"],
                    "None"
                    if row["Designated Slot"] is None
                    else slot_player(row["Designated Slot"]),
                )
                for slot, row in raw["Advanced Instructions"].items()
            ),
        )
        rest = raw["Rest Defence Contract"]
        lines += [
            "#### Rest Defence Contract",
            "",
            f"**Minimum Retained:** {rest['Minimum Retained']}",
            "",
            "**Retained protectors:** "
            + escape_markdown(
                "; ".join(
                    slot_player(slot) for slot in rest["Retained Protector Slots"]
                )
                or "None"
            ),
            "",
            f"**Rationale:** {escape_markdown(rest['Rationale'])}",
            "",
            "#### Players to Join Attack",
            "",
        ]
        if raw["Players to Join Attack"]:
            lines += _table(
                ("Order", "Player", "Aerial rationale"),
                (
                    (row["Order"], slot_player(row["Slot"]), row["Aerial Rationale"])
                    for row in raw["Players to Join Attack"]
                ),
            )
        else:
            lines += ["None.", ""]
        lines += [
            f"**Auto Offside Trap:** {escape_markdown(raw['Auto Offside Trap'])}",
            "",
        ]
        for key in ("Mechanisms", "Binding Constraints"):
            lines += [f"#### {key}", ""]
            lines += [f"- {escape_markdown(value)}" for value in raw[key]] or ["None."]
            lines.append("")
    lines += [
        "## Set-Piece Roles and Captain",
        "",
        "Selected deterministically from the locked XI using player attributes "
        "and Main Normal positions. Long free kicks and corners exclude players "
        "joining attack in any active preset.",
        "",
    ]
    role_labels = {
        "Captain": "Captain",
        "ShortFK": "Short free kick",
        "LongFK": "Long free kick",
        "SecondKicker": "Second kicker",
        "LeftCorner": "Left corner",
        "RightCorner": "Right corner",
        "Penalty": "Penalty",
    }
    lines += _table(
        ("Role", "Player"),
        ((label, player(routine_role_ids[key])) for key, label in role_labels.items()),
    )
    lines += [
        "## Prioritized Substitute Bench",
        "",
        "Listed in the finalized BenchDecision order; priority 1 is first.",
        "",
    ]
    if squad[11:]:
        lines += _table(
            ("Priority", "Player ID", "Player"),
            (
                (priority, row["Player ID"], row["Player"])
                for priority, row in enumerate(squad[11:], start=1)
            ),
        )
    else:
        lines += ["No substitutes (the squad contains only the locked XI).", ""]
    return "\n".join(lines)
