"Compile semantic basic, advanced, and preset-local tactical settings."

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pes_workflows.config import GlobalAutoOptions

from .advanced import TargetedInstruction
from .errors import SemanticGridError
from .mappings import (
    _ADVANCED_CANONICAL_NAMES,
    _ADVANCED_ENTRY_KEY_LOOKUP,
    _ADVANCED_INSTRUCTIONS,
    _ADVANCED_KEY_LOOKUP,
    _ADVANCED_SLOT_SPECS,
    _ATTACKING_ADVANCED_ENUMS,
    _BASIC_KEY_LOOKUP,
    _BASIC_LEGAL_LABELS,
    _BASIC_SETTING_SPECS,
    _BASIC_VALUE_MAPS,
    _DEFENDING_ADVANCED_ENUMS,
    _OFFSIDE_VALUE_LOOKUP,
    _PLAYER_REF_KEY_LOOKUP,
    _SLIDER_SETTINGS,
    FORCED_GLOBAL_COLUMNS,
    GLOBAL_AUTO_COLUMNS,
    GLOBAL_JOIN_ATTACK_COLUMNS,
    STARTER_COUNT,
    STATE_NAMES,
    TACTIC_KEYS,
    TACTIC_NAMES,
    _norm,
)
from .schema import _canon_keys


def _compile_basic_value(display: str, value: object, where: str) -> str:
    if not isinstance(value, str):
        raise SemanticGridError(f"{where}: {display} must be a semantic JSON string.")
    if display in _SLIDER_SETTINGS:
        match = re.fullmatch(r"Level\s+([1-9]|10)", value.strip(), re.I)
        if not match:
            raise SemanticGridError(
                f"{where}: {display} must be 'Level 1' through 'Level 10', got {value!r}."
            )
        return match.group(1)

    normalized = _norm(value)
    value_map = _BASIC_VALUE_MAPS[display]
    if normalized not in value_map:
        raise SemanticGridError(
            f"{where}: {display} = {value!r}. Legal values: "
            + ", ".join(_BASIC_LEGAL_LABELS[display])
            + "."
        )
    return value_map[normalized]


def _compile_player_ref(
    raw: object, where: str, squad_ids: Sequence[str], squad_names: Sequence[str]
) -> tuple[str, str, int]:
    values = _canon_keys(raw, _PLAYER_REF_KEY_LOOKUP, where)
    missing = [key for key in _PLAYER_REF_KEY_LOOKUP.values() if key not in values]
    if missing:
        raise SemanticGridError(
            f"{where}: missing field(s): " + ", ".join(missing) + "."
        )
    if not isinstance(values["Player ID"], str) or not isinstance(
        values["Player"], str
    ):
        raise SemanticGridError(f"{where}: Player ID and Player must be JSON strings.")
    player_id = values["Player ID"].strip()
    player_name = values["Player"].strip()
    if player_id not in squad_ids[:STARTER_COUNT]:
        raise SemanticGridError(
            f"{where}: Player ID {player_id!r} is not in the Starting XI."
        )
    slot = squad_ids.index(player_id)
    if player_name != squad_names[slot]:
        raise SemanticGridError(
            f"{where}: Player {player_name!r} does not match ID {player_id!r} "
            f"({squad_names[slot]!r})."
        )
    return player_id, player_name, slot


def _compile_advanced_slot(
    slot_name: str,
    raw: object,
    where: str,
    squad_ids: Sequence[str],
    squad_names: Sequence[str],
    targeted_instructions: list[TargetedInstruction],
    *,
    tactic: str,
    state_positions: Mapping[str, Sequence[str]],
) -> tuple[str, str | None]:
    values = _canon_keys(raw, _ADVANCED_ENTRY_KEY_LOOKUP, where)
    missing = [key for key in _ADVANCED_ENTRY_KEY_LOOKUP.values() if key not in values]
    if missing:
        raise SemanticGridError(
            f"{where}: missing field(s): " + ", ".join(missing) + "."
        )

    column, category = _ADVANCED_SLOT_SPECS[slot_name]
    if not isinstance(values["Instruction"], str):
        raise SemanticGridError(f"{where}: Instruction must be a semantic JSON string.")
    instruction_norm = _norm(values["Instruction"])
    value_map = (
        _ATTACKING_ADVANCED_ENUMS
        if category == "attacking"
        else _DEFENDING_ADVANCED_ENUMS
    )
    if instruction_norm not in value_map:
        legal = [
            name
            for norm, name in _ADVANCED_CANONICAL_NAMES.items()
            if norm in value_map
        ]
        raise SemanticGridError(
            f"{where}: {values['Instruction']!r} is not a legal {category} instruction. "
            "Legal values: " + ", ".join(legal) + "."
        )
    canonical_instruction = _ADVANCED_CANONICAL_NAMES[instruction_norm]
    designated = values["Designated Player"]

    instruction = _ADVANCED_INSTRUCTIONS[instruction_norm]
    if instruction.is_player_targeted:
        if designated is None:
            raise SemanticGridError(
                f"{where}: {canonical_instruction} requires one Designated Player."
            )
        player_id, player_name, slot = _compile_player_ref(
            designated,
            f"{where}.Designated Player",
            squad_ids,
            squad_names,
        )
        if slot == 0:
            raise SemanticGridError(
                f"{where}: the goalkeeper cannot be the Designated Player."
            )
        for state, positions in state_positions.items():
            position = positions[slot]
            if not instruction.supports_position(position):
                raise SemanticGridError(
                    f"{where}: {canonical_instruction} cannot designate "
                    f"{player_name} [Slot {slot}]: {STATE_NAMES[state]} "
                    f"Position {position} is not eligible."
                )
        if any(
            item.column.endswith(tactic)
            and item.instruction is instruction
            and item.player_id == player_id
            for item in targeted_instructions
        ):
            raise SemanticGridError(
                f"{where}: {canonical_instruction} cannot designate {player_name} "
                "again in the same preset; use a distinct player or leave the slot Blank."
            )
        targeted_instructions.append(
            TargetedInstruction(column + tactic, instruction, player_id)
        )
        return column, None
    if designated is not None:
        raise SemanticGridError(
            f"{where}: {canonical_instruction} is team-wide and Designated Player must be null."
        )
    return column, value_map[instruction_norm]


def _compile_tactics(
    presets: Mapping[str, Any],
    flat: dict[str, str],
    squad_ids: Sequence[str],
    squad_names: Sequence[str],
    state_positions: Mapping[str, Mapping[str, Sequence[str]]],
    global_auto_options: GlobalAutoOptions,
) -> tuple[dict[str, str], dict[str, list[dict[str, str]]], list[TargetedInstruction]]:
    flat.update(FORCED_GLOBAL_COLUMNS)
    flat.update(
        {
            GLOBAL_AUTO_COLUMNS[key]: str(value)
            for key, value in global_auto_options.items()
        }
    )
    flat.update({column: "255" for column in GLOBAL_JOIN_ATTACK_COLUMNS})
    auto_offside_trap_settings = {}
    join_attack_settings = {}
    targeted_instructions: list[TargetedInstruction] = []

    for tactic in TACTIC_KEYS:
        preset_name = TACTIC_NAMES[tactic]
        where = f"Presets.{preset_name}"
        sections = presets[tactic]

        basic = _canon_keys(
            sections["Basic Instructions"],
            _BASIC_KEY_LOOKUP,
            f"{where}.Basic Instructions",
        )
        missing_basic = [
            display for display, _, _ in _BASIC_SETTING_SPECS if display not in basic
        ]
        if missing_basic:
            raise SemanticGridError(
                f"{where}.Basic Instructions: missing setting(s): "
                + ", ".join(missing_basic)
                + "."
            )

        for display, column, _ in _BASIC_SETTING_SPECS:
            enum = _compile_basic_value(
                display,
                basic[display],
                f"{where}.Basic Instructions",
            )
            flat[column + tactic] = enum

        advanced = _canon_keys(
            sections["Advanced Instructions"],
            _ADVANCED_KEY_LOOKUP,
            f"{where}.Advanced Instructions",
        )
        missing_advanced = [key for key in _ADVANCED_SLOT_SPECS if key not in advanced]
        if missing_advanced:
            raise SemanticGridError(
                f"{where}.Advanced Instructions: missing slot(s): "
                + ", ".join(missing_advanced)
                + "."
            )
        for slot_name in _ADVANCED_SLOT_SPECS:
            column, advanced_enum = _compile_advanced_slot(
                slot_name,
                advanced[slot_name],
                f"{where}.Advanced Instructions.{slot_name}",
                squad_ids,
                squad_names,
                targeted_instructions,
                tactic=tactic,
                state_positions=state_positions[tactic],
            )
            if advanced_enum is not None:
                flat[column + tactic] = advanced_enum

        if not isinstance(sections["Auto Offside Trap"], str):
            raise SemanticGridError(
                f"{where}.Auto Offside Trap must be the string 'On' or 'Off'."
            )
        offside_norm = _norm(sections["Auto Offside Trap"])
        if offside_norm not in _OFFSIDE_VALUE_LOOKUP:
            raise SemanticGridError(
                f"{where}.Auto Offside Trap must be 'On' or 'Off', got "
                f"{sections['Auto Offside Trap']!r}."
            )
        auto_offside_trap_settings[tactic] = _OFFSIDE_VALUE_LOOKUP[offside_norm]
        join_attack_settings[tactic] = _compile_join_attack(
            sections["Players to Join Attack"],
            preset_name,
            squad_ids,
            squad_names,
        )

    flat["OffsideTrap"] = "1" if auto_offside_trap_settings["S1"] == "On" else "0"

    return auto_offside_trap_settings, join_attack_settings, targeted_instructions


def _compile_join_attack(
    selected_raw: object,
    preset_name: str,
    squad_ids: Sequence[str],
    squad_names: Sequence[str],
) -> list[dict[str, str]]:
    where = f"Presets.{preset_name}.Players to Join Attack"
    if not isinstance(selected_raw, list) or len(selected_raw) > len(
        GLOBAL_JOIN_ATTACK_COLUMNS
    ):
        count = len(selected_raw) if hasattr(selected_raw, "__len__") else "?"
        raise SemanticGridError(
            f"{where} must be a list containing zero to three player references "
            f"(got {count})."
        )

    selected = set()
    compiled = []
    for index, raw in enumerate(selected_raw):
        player_id, player_name, slot = _compile_player_ref(
            raw,
            f"{where} entry {index + 1}",
            squad_ids,
            squad_names,
        )
        if player_id in selected:
            raise SemanticGridError(
                f"{where} entry {index + 1}: duplicate Player ID {player_id!r}."
            )
        if slot == 0:
            raise SemanticGridError(
                f"{where} entry {index + 1}: the goalkeeper cannot be selected "
                "for Players to Join Attack; select from starting outfielders "
                "(Slots 1–10)."
            )
        selected.add(player_id)
        compiled.append({"Player ID": player_id, "Player": player_name})
    return compiled
