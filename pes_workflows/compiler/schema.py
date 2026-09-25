"""Semantic plan schema normalization and strict structural validation."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .errors import SemanticGridError
from .geometry import GK_ANCHOR_LABEL, N_ROWS
from .mappings import (
    _ADVANCED_CANONICAL_NAMES,
    _ADVANCED_SLOT_SPECS,
    _ATTACKING_ADVANCED_ENUMS,
    _BASIC_LEGAL_LABELS,
    _BASIC_SETTING_SPECS,
    _DEFENDING_ADVANCED_ENUMS,
    _GRID_RE,
    _PRESET_SECTION_KEY_LOOKUP,
    _SLIDER_SETTINGS,
    _SQUAD_ENTRY_KEY_LOOKUP,
    _STATE_ALIASES,
    _TACTIC_ALIASES,
    GLOBAL_JOIN_ATTACK_COLUMNS,
    POSITION_NAME_TO_CODE,
    STARTER_COUNT,
    STATE_KEYS,
    STATE_NAMES,
    TACTIC_KEYS,
    TACTIC_NAMES,
    _norm,
)


def _canon_keys(
    mapping: object, lookup: Mapping[str, str], where: str
) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        raise SemanticGridError(f"{where} must be a dict.")
    out = {}
    for key, value in mapping.items():
        canon = lookup.get(_norm(key))
        if canon is None:
            raise SemanticGridError(
                f"{where}: unknown key {key!r}. Legal keys: "
                + ", ".join(sorted(set(lookup.values())))
                + "."
            )
        if canon in out:
            raise SemanticGridError(f"{where}: duplicate key for {canon}.")
        out[canon] = value
    return out


def _strict_keys(mapping: dict[str, Any], expected: Iterable[str], where: str) -> None:
    """Require canonical machine keys without applying the manual-ingest aliases."""
    if not isinstance(mapping, dict):
        raise SemanticGridError(f"{where} must be an object.")
    expected_set = set(expected)
    actual_set = set(mapping)
    if actual_set == expected_set:
        return
    details = []
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    if missing:
        details.append("missing: " + ", ".join(missing))
    if extra:
        details.append("unexpected/non-canonical: " + ", ".join(map(str, extra)))
    raise SemanticGridError(f"{where}: " + "; ".join(details) + ".")


def _strict_player_ref_shape(raw: dict[str, Any], where: str) -> None:
    _strict_keys(raw, ("Player ID", "Player"), where)
    if not isinstance(raw["Player ID"], str) or not isinstance(raw["Player"], str):
        raise SemanticGridError(f"{where}: Player ID and Player must be JSON strings.")


def _strict_validate_semantic_plan_shape(config: dict[str, Any]) -> None:
    """Validate Contract-v2 canonical spelling before tolerant compilation."""
    _strict_keys(
        config,
        ("Team ID", "Squad", "Presets"),
        "Semantic game plan",
    )

    squad = config["Squad"]
    if not isinstance(squad, list):
        raise SemanticGridError("Squad must be an array.")
    for index, ref in enumerate(squad, start=1):
        _strict_player_ref_shape(ref, f"Squad entry {index}")

    presets = config["Presets"]
    _strict_keys(presets, tuple(TACTIC_NAMES.values()), "Presets")
    for tactic in TACTIC_KEYS:
        preset_name = TACTIC_NAMES[tactic]
        where = f"Presets.{preset_name}"
        preset = presets[preset_name]
        _strict_keys(
            preset,
            (
                "Auto Offside Trap",
                "Players to Join Attack",
                "Basic Instructions",
                "Advanced Instructions",
                "States",
            ),
            where,
        )
        if preset["Auto Offside Trap"] not in {"On", "Off"}:
            raise SemanticGridError(
                f"{where}.Auto Offside Trap must be exactly 'On' or 'Off'."
            )
        joiners = preset["Players to Join Attack"]
        if not isinstance(joiners, list) or len(joiners) > len(
            GLOBAL_JOIN_ATTACK_COLUMNS
        ):
            raise SemanticGridError(
                f"{where}.Players to Join Attack must be an array containing "
                "zero to three player references."
            )
        for index, ref in enumerate(joiners, start=1):
            _strict_player_ref_shape(
                ref, f"{where}.Players to Join Attack entry {index}"
            )

        basic = preset["Basic Instructions"]
        _strict_keys(
            basic,
            tuple(display for display, _, _ in _BASIC_SETTING_SPECS),
            f"{where}.Basic Instructions",
        )
        for display, _, _ in _BASIC_SETTING_SPECS:
            value = basic[display]
            if display in _SLIDER_SETTINGS:
                if not isinstance(value, str) or not re.fullmatch(
                    r"Level ([1-9]|10)", value
                ):
                    raise SemanticGridError(
                        f"{where}.Basic Instructions.{display} must be the canonical "
                        "string 'Level 1' through 'Level 10'."
                    )
            elif value not in _BASIC_LEGAL_LABELS[display]:
                raise SemanticGridError(
                    f"{where}.Basic Instructions.{display} must be one of the canonical "
                    f"values: {', '.join(_BASIC_LEGAL_LABELS[display])}."
                )

        advanced = preset["Advanced Instructions"]
        _strict_keys(
            advanced, tuple(_ADVANCED_SLOT_SPECS), f"{where}.Advanced Instructions"
        )
        for slot_name, (_, category) in _ADVANCED_SLOT_SPECS.items():
            item_where = f"{where}.Advanced Instructions.{slot_name}"
            item = advanced[slot_name]
            _strict_keys(item, ("Instruction", "Designated Player"), item_where)
            value_map = (
                _ATTACKING_ADVANCED_ENUMS
                if category == "attacking"
                else _DEFENDING_ADVANCED_ENUMS
            )
            legal_names = {
                _ADVANCED_CANONICAL_NAMES[normalized] for normalized in value_map
            }
            if item["Instruction"] not in legal_names:
                raise SemanticGridError(
                    f"{item_where}.Instruction is not a canonical {category} instruction."
                )
            designated = item["Designated Player"]
            if designated is not None:
                _strict_player_ref_shape(designated, f"{item_where}.Designated Player")

        states = preset["States"]
        _strict_keys(states, tuple(STATE_NAMES.values()), f"{where}.States")
        for fluid in STATE_KEYS:
            state_name = STATE_NAMES[fluid]
            state_where = f"{where}.States.{state_name}"
            state = states[state_name]
            if not isinstance(state, list) or len(state) != STARTER_COUNT:
                raise SemanticGridError(
                    f"{state_where} must contain exactly {STARTER_COUNT} rows."
                )
            for slot, item in enumerate(state):
                row_where = f"{state_where}[{slot}]"
                _strict_keys(item, ("Slot", "Position", "Grid Assignment"), row_where)
                if isinstance(item["Slot"], bool) or item["Slot"] != slot:
                    raise SemanticGridError(
                        f"{row_where}.Slot must be the integer {slot}."
                    )
                if item["Position"] not in POSITION_NAME_TO_CODE:
                    raise SemanticGridError(f"{row_where}.Position is not canonical.")
                grid = item["Grid Assignment"]
                if slot == 0:
                    if item["Position"] != "GK" or grid != GK_ANCHOR_LABEL:
                        raise SemanticGridError(
                            f"{row_where} must use Position 'GK' and Grid Assignment "
                            f"'{GK_ANCHOR_LABEL}'."
                        )
                elif not isinstance(grid, str) or not _GRID_RE.fullmatch(grid):
                    raise SemanticGridError(
                        f"{row_where}.Grid Assignment must use the canonical "
                        f"Row 1-{N_ROWS} and 7-lane grammar."
                    )


def _rekey_presets(top: dict[str, Any]) -> dict[str, dict[str, Any]]:
    presets_raw = top["Presets"]
    if not isinstance(presets_raw, dict):
        raise SemanticGridError("Presets must be an object.")

    presets = {}
    for key, preset_raw in presets_raw.items():
        tactic = _TACTIC_ALIASES.get(_norm(key))
        if tactic is None:
            raise SemanticGridError(f"Presets: unknown preset {key!r}.")
        if tactic in presets:
            raise SemanticGridError(
                f"Presets: duplicate preset {TACTIC_NAMES[tactic]}."
            )
        sections = _canon_keys(
            preset_raw,
            _PRESET_SECTION_KEY_LOOKUP,
            f"Presets.{TACTIC_NAMES[tactic]}",
        )
        missing = [
            key for key in _PRESET_SECTION_KEY_LOOKUP.values() if key not in sections
        ]
        if missing:
            raise SemanticGridError(
                f"Presets.{TACTIC_NAMES[tactic]}: missing section(s): "
                + ", ".join(missing)
                + "."
            )
        presets[tactic] = sections

    missing = [TACTIC_NAMES[t] for t in TACTIC_KEYS if t not in presets]
    if missing:
        raise SemanticGridError(
            "Presets: missing preset(s): " + ", ".join(missing) + "."
        )
    return presets


def _rekey_states(tactic: str, states_raw: dict[str, Any]) -> dict[str, Any]:
    where = f"Presets.{TACTIC_NAMES[tactic]}.States"
    if not isinstance(states_raw, dict):
        raise SemanticGridError(f"{where} must be an object.")
    states = {}
    for key, state in states_raw.items():
        fluid = _STATE_ALIASES.get(_norm(key))
        if fluid is None:
            raise SemanticGridError(f"{where}: unknown state {key!r}.")
        if fluid in states:
            raise SemanticGridError(f"{where}: duplicate state {STATE_NAMES[fluid]}.")
        states[fluid] = state
    missing = [STATE_NAMES[f] for f in STATE_KEYS if f not in states]
    if missing:
        raise SemanticGridError(
            f"{where}: missing state(s): " + ", ".join(missing) + "."
        )
    return states


def _compile_squad(top: dict[str, Any]) -> tuple[list[str], list[str]]:
    squad_raw = top["Squad"]
    if not isinstance(squad_raw, list) or len(squad_raw) < STARTER_COUNT:
        count = len(squad_raw) if hasattr(squad_raw, "__len__") else "?"
        raise SemanticGridError(
            f"Squad must contain at least {STARTER_COUNT} entries "
            f"({STARTER_COUNT} starters followed by substitutes); got {count}."
        )
    ids, names = [], []
    for i, entry in enumerate(squad_raw):
        where = f"Squad entry {i + 1}"
        values = _canon_keys(entry, _SQUAD_ENTRY_KEY_LOOKUP, where)
        missing = [key for key in _SQUAD_ENTRY_KEY_LOOKUP.values() if key not in values]
        if missing:
            raise SemanticGridError(
                f"{where}: missing field(s): " + ", ".join(missing) + "."
            )
        if not isinstance(values["Player ID"], str) or not isinstance(
            values["Player"], str
        ):
            raise SemanticGridError(
                f"{where}: Player ID and Player must be JSON strings."
            )
        pid = values["Player ID"].strip()
        name = values["Player"].strip()
        if not pid.isascii() or not pid.isdigit() or int(pid) <= 0 or int(pid) == 255:
            raise SemanticGridError(
                f"{where}: Player ID {values['Player ID']!r} must be a positive source Player ID."
            )
        if not name:
            raise SemanticGridError(f"{where}: player name is empty.")
        ids.append(pid)
        names.append(name)
    if len(set(ids)) != len(ids):
        dupes = sorted({pid for pid in ids if ids.count(pid) > 1})
        raise SemanticGridError(
            "Squad: duplicate Player ID(s): " + ", ".join(dupes) + "."
        )
    return ids, names
