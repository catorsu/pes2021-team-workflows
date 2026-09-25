"PresetPlan model and Contract 2.2 validator."

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pes_workflows.domain.advanced_instructions import AdvancedInstruction
from pes_workflows.domain.vocabulary import POSITION_CODES

from .constants import (
    ADVANCED_SLOT_ORDER,
    ATTACKING_ADVANCED,
    BASIC_LEGAL_VALUES,
    BASIC_SETTING_ORDER,
    DEFENDING_ADVANCED,
    GRID_LANES,
    PLAYER_SPECIFIC_ADVANCED,
    PRESET_NAMES,
    PRESET_RISK_BUDGETS,
    SLIDER_SETTINGS,
    STATE_NAMES,
)
from .errors import ArtifactDomainError, ArtifactSchemaError
from .json_codec import (
    _expect_enum,
    _expect_int,
    _expect_list,
    _expect_object,
    _expect_ordered_keys,
    _expect_string,
    _expect_string_list,
    _path,
    _validate_common,
)
from .strategy import StartingXILock


@dataclass(frozen=True, slots=True)
class StateRow:
    slot: int
    position: str
    grid_assignment: str


@dataclass(frozen=True, slots=True)
class PresetPlan:
    name: str
    basic: Mapping[str, str]
    advanced: Mapping[str, Mapping[str, Any]]
    states: Mapping[str, tuple[StateRow, ...]]
    join_attack_slots: tuple[int, ...]
    _raw: Mapping[str, Any]

    def to_model_dict(self) -> dict[str, Any]:
        return copy.deepcopy(dict(self._raw))

    def to_compiler_dict(
        self, xi_lock: StartingXILock, source_identity: Mapping[str, Any]
    ) -> dict[str, Any]:
        xi_refs = xi_lock.compiler_refs(source_identity)
        advanced: dict[str, dict[str, Any]] = {}
        for slot_name in ADVANCED_SLOT_ORDER:
            item = self.advanced[slot_name]
            designated_slot = item["Designated Slot"]
            advanced[slot_name] = {
                "Instruction": item["Instruction"],
                "Designated Player": (
                    None
                    if designated_slot is None
                    else copy.deepcopy(xi_refs[designated_slot])
                ),
            }
        return {
            "Auto Offside Trap": self._raw["Auto Offside Trap"],
            "Players to Join Attack": [
                copy.deepcopy(xi_refs[slot]) for slot in self.join_attack_slots
            ],
            "Basic Instructions": dict(self.basic),
            "Advanced Instructions": advanced,
            "States": {
                state_name: [
                    {
                        "Slot": row.slot,
                        "Position": row.position,
                        "Grid Assignment": row.grid_assignment,
                    }
                    for row in self.states[state_name]
                ]
                for state_name in STATE_NAMES
            },
        }


def _grid_assignment(value: Any, artifact: str, path: str, slot: int) -> str:
    grid = _expect_object(value, artifact, path)
    _expect_ordered_keys(grid, ("Row", "Lane"), artifact, path)
    row = _expect_int(grid["Row"], artifact, _path(path, "Row"))
    lane = _expect_enum(grid["Lane"], GRID_LANES, artifact, _path(path, "Lane"))
    if slot == 0:
        if row != 0 or lane != "C_Center":
            raise ArtifactDomainError(
                artifact,
                path,
                'Slot 0 Grid must be exactly {"Row":0,"Lane":"C_Center"}',
            )
        return "GK_Anchor"
    if not 1 <= row <= 9:
        raise ArtifactSchemaError(
            artifact, _path(path, "Row"), "outfield Row must be between 1 and 9"
        )
    return f"Row {row} - {lane}"


def validate_preset_plan(
    raw: Mapping[str, Any],
    expected_preset: str,
    xi_lock: StartingXILock,
    *,
    preset_mode: str = "multi",
) -> PresetPlan:
    if preset_mode not in {"multi", "single"}:
        raise ValueError(
            f"preset_mode must be either 'multi' or 'single'; got {preset_mode!r}"
        )
    artifact = "PresetPlan"
    raw = _expect_object(raw, artifact, "$")
    # The order follows the construction pipeline of GAME_PLAN_RULES X and is
    # part of the hard output contract, not a presentation choice
    keys = (
        "Schema Version",
        "Artifact",
        "Preset",
        "Scenario Response",
        "Risk Budget",
        "Formation Signature",
        "States",
        "Rest Defence Contract",
        "Basic Instructions",
        "Advanced Instructions",
        "Players to Join Attack",
        "Auto Offside Trap",
        "Mechanisms",
        "Binding Constraints",
    )
    schema_version = _validate_common(raw, artifact, keys)
    xi_schema_version = xi_lock._raw["Schema Version"]
    if schema_version != xi_schema_version:
        raise ArtifactDomainError(
            artifact,
            "$.Schema Version",
            f"must match StartingXILock Schema Version {xi_schema_version!r}",
        )
    preset_name = _expect_enum(raw["Preset"], PRESET_NAMES, artifact, "$.Preset")
    if preset_name != expected_preset:
        raise ArtifactDomainError(
            artifact, "$.Preset", f"must equal requested preset {expected_preset!r}"
        )
    if preset_mode == "single" and preset_name != "Main":
        raise ArtifactDomainError(
            artifact, "$.Preset", "single mode permits only the Main preset"
        )
    _expect_string(raw["Scenario Response"], artifact, "$.Scenario Response")
    risk_budget = _expect_enum(
        raw["Risk Budget"], ("Low", "Medium", "High"), artifact, "$.Risk Budget"
    )
    required_budget = PRESET_RISK_BUDGETS[preset_name]
    if risk_budget != required_budget:
        raise ArtifactDomainError(
            artifact,
            "$.Risk Budget",
            f"{preset_name} must use the {required_budget} risk budget",
        )
    _expect_string(raw["Formation Signature"], artifact, "$.Formation Signature")
    _expect_enum(
        raw["Auto Offside Trap"],
        ("On", "Off"),
        artifact,
        "$.Auto Offside Trap",
    )
    _expect_string_list(raw["Mechanisms"], artifact, "$.Mechanisms", min_items=1)
    _expect_string_list(raw["Binding Constraints"], artifact, "$.Binding Constraints")

    basic_obj = _expect_object(
        raw["Basic Instructions"], artifact, "$.Basic Instructions"
    )
    _expect_ordered_keys(
        basic_obj, BASIC_SETTING_ORDER, artifact, "$.Basic Instructions"
    )
    basic: dict[str, str] = {}
    for setting in BASIC_SETTING_ORDER:
        path = _path("$.Basic Instructions", setting)
        if setting in SLIDER_SETTINGS:
            level = _expect_int(basic_obj[setting], artifact, path)
            if not 1 <= level <= 10:
                raise ArtifactDomainError(
                    artifact, path, "must be an integer from 1 through 10"
                )
            basic[setting] = f"Level {level}"
            continue

        value = _expect_string(basic_obj[setting], artifact, path)
        if value not in BASIC_LEGAL_VALUES[setting]:
            raise ArtifactSchemaError(
                artifact,
                path,
                "must be one of "
                + ", ".join(repr(item) for item in BASIC_LEGAL_VALUES[setting]),
            )
        basic[setting] = value

    state_obj = _expect_object(raw["States"], artifact, "$.States")
    _expect_ordered_keys(state_obj, STATE_NAMES, artifact, "$.States")
    states: dict[str, tuple[StateRow, ...]] = {}
    for state_name in STATE_NAMES:
        state_path = _path("$.States", state_name)
        rows = _expect_list(state_obj[state_name], artifact, state_path)
        if len(rows) != 11:
            raise ArtifactSchemaError(
                artifact, state_path, "must contain exactly 11 rows"
            )
        parsed_rows: list[StateRow] = []
        for slot, item in enumerate(rows):
            path = _path(state_path, slot)
            row = _expect_object(item, artifact, path)
            _expect_ordered_keys(
                row,
                ("Slot", "Position", "Grid", "Tactical Duty"),
                artifact,
                path,
            )
            actual_slot = _expect_int(row["Slot"], artifact, _path(path, "Slot"))
            if actual_slot != slot:
                raise ArtifactSchemaError(
                    artifact, _path(path, "Slot"), f"must equal {slot}"
                )
            position = _expect_enum(
                row["Position"], POSITION_CODES, artifact, _path(path, "Position")
            )
            if slot == 0 and position != "GK":
                raise ArtifactDomainError(
                    artifact, _path(path, "Position"), "Slot 0 must use GK"
                )
            if slot > 0 and position == "GK":
                raise ArtifactDomainError(
                    artifact, _path(path, "Position"), "outfield slots cannot use GK"
                )
            grid = _grid_assignment(row["Grid"], artifact, _path(path, "Grid"), slot)
            _expect_string(row["Tactical Duty"], artifact, _path(path, "Tactical Duty"))
            parsed_rows.append(StateRow(slot, position, grid))
        states[state_name] = tuple(parsed_rows)

    advanced_obj = _expect_object(
        raw["Advanced Instructions"], artifact, "$.Advanced Instructions"
    )
    _expect_ordered_keys(
        advanced_obj, ADVANCED_SLOT_ORDER, artifact, "$.Advanced Instructions"
    )
    advanced: dict[str, Mapping[str, Any]] = {}
    seen_specific = set()
    seen_team_wide = set()
    for slot_name in ADVANCED_SLOT_ORDER:
        path = _path("$.Advanced Instructions", slot_name)
        item = _expect_object(advanced_obj[slot_name], artifact, path)
        _expect_ordered_keys(item, ("Instruction", "Designated Slot"), artifact, path)
        family = "Attacking" if slot_name.startswith("Attacking") else "Defending"
        legal = ATTACKING_ADVANCED if family == "Attacking" else DEFENDING_ADVANCED
        instruction = _expect_enum(
            item["Instruction"], legal, artifact, _path(path, "Instruction")
        )
        designated = item["Designated Slot"]
        if instruction in PLAYER_SPECIFIC_ADVANCED:
            designated = _expect_int(
                designated, artifact, _path(path, "Designated Slot")
            )
            if not 1 <= designated <= 10:
                raise ArtifactDomainError(
                    artifact,
                    _path(path, "Designated Slot"),
                    "must be an outfield slot 1..10",
                )
            definition = next(
                item for item in AdvancedInstruction if item.label == instruction
            )
            for state_name, state_rows in states.items():
                position = state_rows[designated].position
                if not definition.supports_position(position):
                    raise ArtifactDomainError(
                        artifact,
                        _path(path, "Designated Slot"),
                        f"{instruction} cannot designate Slot {designated}: "
                        f"{state_name} Position {position} is not eligible",
                    )
            key = (instruction, designated)
            if key in seen_specific:
                raise ArtifactDomainError(
                    artifact,
                    path,
                    "duplicates the same player-specific instruction and slot",
                )
            seen_specific.add(key)
        elif designated is not None:
            raise ArtifactDomainError(
                artifact,
                _path(path, "Designated Slot"),
                "must be null for Blank or team-wide instructions",
            )
        elif instruction != "Blank":
            # GAME_PLAN_RULES VI: team-wide instructions cannot be duplicated
            # within the same slot family. Blank is the deliberate no-op and is
            # explicitly valid in both slots of a family
            if (family, instruction) in seen_team_wide:
                raise ArtifactDomainError(
                    artifact,
                    path,
                    f"duplicates the team-wide {instruction!r} instruction "
                    f"already assigned in the {family} slot family",
                )
            seen_team_wide.add((family, instruction))
        advanced[slot_name] = MappingProxyType(
            {"Instruction": instruction, "Designated Slot": designated}
        )

    rest_path = "$.Rest Defence Contract"
    rest = _expect_object(raw["Rest Defence Contract"], artifact, rest_path)
    protector_key = "Retained Protector Slots"
    _expect_ordered_keys(
        rest, (protector_key, "Minimum Retained", "Rationale"), artifact, rest_path
    )
    protector_path = _path(rest_path, protector_key)
    protector_values = _expect_list(rest[protector_key], artifact, protector_path)
    declared_protectors: list[int] = []
    for index, value in enumerate(protector_values):
        slot = _expect_int(value, artifact, _path(protector_path, index))
        if not 1 <= slot <= 10:
            raise ArtifactDomainError(
                artifact,
                _path(protector_path, index),
                "must be an outfield slot 1..10",
            )
        if slot in declared_protectors:
            raise ArtifactSchemaError(
                artifact, protector_path, "must not contain duplicates"
            )
        declared_protectors.append(slot)
    if not declared_protectors:
        raise ArtifactDomainError(
            artifact,
            protector_path,
            "must contain at least one outfield slot",
        )
    minimum = _expect_int(
        rest["Minimum Retained"], artifact, _path(rest_path, "Minimum Retained")
    )
    if not 1 <= minimum <= len(declared_protectors):
        raise ArtifactDomainError(
            artifact,
            _path(rest_path, "Minimum Retained"),
            f"must be between 1 and the {len(declared_protectors)} declared protectors",
        )
    _expect_string(rest["Rationale"], artifact, _path(rest_path, "Rationale"))

    join_path = "$.Players to Join Attack"
    join_rows = _expect_list(raw["Players to Join Attack"], artifact, join_path)
    if len(join_rows) > 3:
        raise ArtifactSchemaError(
            artifact, join_path, "may contain at most 3 selections"
        )
    id_by_slot = {item.slot: item.player_id for item in xi_lock.starting_xi}
    seen_join_slots = set()
    join_slots: list[int] = []
    for index, item in enumerate(join_rows):
        path = _path(join_path, index)
        row = _expect_object(item, artifact, path)
        _expect_ordered_keys(
            row, ("Order", "Slot", "Player ID", "Aerial Rationale"), artifact, path
        )
        order = _expect_int(row["Order"], artifact, _path(path, "Order"))
        if order != index + 1:
            raise ArtifactSchemaError(
                artifact, _path(path, "Order"), f"must equal {index + 1}"
            )
        slot = _expect_int(row["Slot"], artifact, _path(path, "Slot"))
        if not 1 <= slot <= 10:
            raise ArtifactDomainError(
                artifact,
                _path(path, "Slot"),
                "must be a starting outfielder slot 1..10",
            )
        if slot in seen_join_slots:
            raise ArtifactDomainError(
                artifact, _path(path, "Slot"), "duplicates another selection"
            )
        seen_join_slots.add(slot)
        player_id = _expect_string(row["Player ID"], artifact, _path(path, "Player ID"))
        if player_id != id_by_slot[slot]:
            raise ArtifactDomainError(
                artifact,
                _path(path, "Player ID"),
                f"must be the identity locked to Slot {slot} in the frozen "
                f"Starting XI, {id_by_slot[slot]!r}",
            )
        _expect_string(
            row["Aerial Rationale"], artifact, _path(path, "Aerial Rationale")
        )
        join_slots.append(slot)

    retained_protectors = tuple(declared_protectors)
    # GAME_PLAN_RULES VIII Rest Defence Retention Invariant (hard constraint):
    # |J ∩ Protectors| <= |Protectors| - Minimum Retained
    joining_protectors = seen_join_slots & set(retained_protectors)
    allowed_to_join = len(retained_protectors) - minimum
    if len(joining_protectors) > allowed_to_join:
        raise ArtifactDomainError(
            artifact,
            join_path,
            f"breaks the Rest Defence Retention Invariant: "
            f"{len(joining_protectors)} of the {len(retained_protectors)} "
            f"Retained Protector Slots join the attack, leaving fewer than the "
            f"{minimum} that Minimum Retained requires to hold",
        )

    return PresetPlan(
        name=preset_name,
        basic=MappingProxyType(basic),
        advanced=MappingProxyType(advanced),
        states=MappingProxyType(states),
        join_attack_slots=tuple(join_slots),
        _raw=MappingProxyType(copy.deepcopy(dict(raw))),
    )
