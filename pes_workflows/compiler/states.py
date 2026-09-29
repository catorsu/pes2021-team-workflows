"""Semantic formation-state parsing and GAME_PLAN compilation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pes_workflows.domain.formation_grid import (
    GRID_LANES,
    GRID_ROW_MAX,
    GRID_ROW_MIN,
    grid_row_bounds,
)

from .errors import SemanticGridError
from .geometry import (
    _convert_to_editor,
    _nominal_grid_xy,
    _resolve_state_geometry,
    _validate_static_grid_definition,
)
from .mappings import (
    _GRID_RE,
    _STATE_ENTRY_KEY_LOOKUP,
    POSITION_NAME_TO_CODE,
    STARTER_COUNT,
    STATE_KEYS,
    STATE_NAMES,
    TACTIC_KEYS,
    TACTIC_NAMES,
)
from .schema import _canon_keys, _rekey_states


def _parse_position(raw: object, where: str) -> tuple[str, str]:
    token = str(raw).strip()
    upper = token.upper()
    if upper in POSITION_NAME_TO_CODE:
        return POSITION_NAME_TO_CODE[upper], upper
    raise SemanticGridError(
        f"{where}: unknown semantic position {raw!r}. Legal positions: "
        + ", ".join(POSITION_NAME_TO_CODE)
        + "."
    )


def _parse_grid_label(raw: object, where: str) -> tuple[int, str]:
    token = str(raw).strip()

    m = _GRID_RE.fullmatch(token)
    if m:
        row = int(m.group(1))
        return row, m.group(2)

    raise SemanticGridError(
        f"{where}: illegal grid assignment {raw!r}. Expected "
        f"'Row {GRID_ROW_MIN}-{GRID_ROW_MAX} - <Lane>' "
        f"with lanes {', '.join(GRID_LANES)}."
    )


def state_label(tactic: str, fluid: str) -> str:
    """The canonical ``S1·F1 (Main · Normal)`` prefix used in validation errors."""

    return f"{tactic}·{fluid} ({TACTIC_NAMES[tactic]} · {STATE_NAMES[fluid]})"


def _compile_state(
    tactic: str,
    fluid: str,
    state: list[dict[str, Any]],
    flat: dict[str, str],
) -> list[dict[str, Any]]:
    where = state_label(tactic, fluid)
    if not isinstance(state, list) or len(state) != STARTER_COUNT:
        count = len(state) if hasattr(state, "__len__") else "?"
        raise SemanticGridError(
            f"{where}: state must contain exactly {STARTER_COUNT} player rows (got {count})."
        )

    entries: list[dict[str, Any]] = []
    for index, item in enumerate(state):
        slot = index
        slot_1based = index + 1
        pwhere = f"{where} Slot {slot}"
        values = _canon_keys(item, _STATE_ENTRY_KEY_LOOKUP, pwhere)
        missing = [key for key in _STATE_ENTRY_KEY_LOOKUP.values() if key not in values]
        if missing:
            raise SemanticGridError(
                f"{pwhere}: missing field(s): " + ", ".join(missing) + "."
            )
        if not isinstance(values["Slot"], int) or isinstance(values["Slot"], bool):
            raise SemanticGridError(f"{pwhere}: Slot must be the integer {slot}.")
        emitted_slot = values["Slot"]
        if emitted_slot != slot:
            raise SemanticGridError(
                f"{pwhere}: expected Slot {slot}, got {values['Slot']!r}."
            )

        pos_raw = values["Position"]
        grid_raw = values["Grid Assignment"]
        pos_code, pos_name = _parse_position(pos_raw, pwhere)
        row, lane = _parse_grid_label(grid_raw, pwhere)

        if slot == 0:
            if pos_code != "0":
                raise SemanticGridError(
                    f"{pwhere}: must use Position 'GK'; got {pos_raw!r}."
                )
        else:
            if pos_code == "0":
                raise SemanticGridError(
                    f"{pwhere}: a second GK position code is illegal."
                )
        lower, upper = grid_row_bounds(slot, STATE_NAMES[fluid])
        if not lower <= row <= upper:
            raise SemanticGridError(
                f"{pwhere}: Row must be between {lower} and {upper}; got {row}."
            )
        x0, y0 = _nominal_grid_xy(row, lane)

        entries.append(
            {
                "slot": slot,
                "slot_1based": slot_1based,
                "pos_code": pos_code,
                "pos_name": pos_name,
                "kind": "gk" if slot == 0 else "grid",
                "row": row,
                "lane": lane,
                "y0": float(y0),
                "x": float(x0),
                "y": float(y0),
            }
        )

    _resolve_state_geometry(entries, where)

    suffix = f"{fluid}{tactic}"
    for entry in entries:
        x_editor, y_editor = _convert_to_editor(
            entry["x"], entry["y"], f"{where} Slot {entry['slot']}"
        )
        flat[f"Position{entry['slot_1based']}{suffix}"] = entry["pos_code"]
        flat[f"LocationX{entry['slot_1based']}{suffix}"] = str(x_editor)
        flat[f"LocationY{entry['slot_1based']}{suffix}"] = str(y_editor)

    return entries


def _compile_game_plan(
    presets: Mapping[str, Any],
    flat: dict[str, str],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    _validate_static_grid_definition()

    state_entries = {}
    for tactic in TACTIC_KEYS:
        states = _rekey_states(tactic, presets[tactic]["States"])
        per_state = {}
        for fluid in STATE_KEYS:
            per_state[fluid] = _compile_state(
                tactic,
                fluid,
                states[fluid],
                flat,
            )
        state_entries[tactic] = per_state
    return state_entries
