"""Deterministic Row 0-9 pitch geometry and editor-coordinate projection."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from .errors import SemanticGridError

PITCH_LENGTH_M = 105
PITCH_WIDTH_M = 68

X_LEGAL_MIN, X_LEGAL_MAX = 6.0, 93.0
Y_LEGAL_MIN, Y_LEGAL_MAX = 7.0, 61.0

EDITOR_X_MIN, EDITOR_X_MAX = 3, 46
EDITOR_Y_MIN, EDITOR_Y_MAX = 10, 94

N_ROWS = 9

ROW_X_M = {
    1: 12.5,
    2: 22.5,
    3: 32.5,
    4: 42.5,
    5: 52.5,
    6: 62.5,
    7: 72.5,
    8: 82.5,
    9: 92.5,
}

LANE_ORDER = [
    "L_Wing",
    "L_Half",
    "L_Center",
    "C_Center",
    "R_Center",
    "R_Half",
    "R_Wing",
]

LANE_Y_M = {
    "L_Wing": 7.0,
    "L_Half": 19.0,
    "L_Center": 27.5,
    "C_Center": 34.0,
    "R_Center": 40.5,
    "R_Half": 49.0,
    "R_Wing": 61.0,
}

GK_ANCHOR_LABEL = "GK_Anchor"
GK_ANCHOR_XY_M = (6.0, 34.0)
MIN_LATERAL_GAP_M = 3.0
MIN_EDITOR_Y_GAP = 2


def _validate_static_grid_definition() -> None:
    expected_rows = [12.5, 22.5, 32.5, 42.5, 52.5, 62.5, 72.5, 82.5, 92.5]
    actual_rows = [ROW_X_M.get(index) for index in range(1, N_ROWS + 1)]
    if actual_rows != expected_rows:
        raise SemanticGridError(
            f"Internal static-grid error: row centres must be {expected_rows}, "
            f"got {actual_rows}."
        )
    if list(ROW_X_M) != list(range(1, N_ROWS + 1)):
        raise SemanticGridError(
            f"Internal static-grid error: row keys must be 1 through {N_ROWS}."
        )

    if list(LANE_Y_M) != LANE_ORDER:
        raise SemanticGridError(
            "Internal static-grid error: lane keys must retain the canonical "
            f"order {LANE_ORDER}."
        )

    expected_lanes = [7.0, 19.0, 27.5, 34.0, 40.5, 49.0, 61.0]
    lane_centres = [LANE_Y_M.get(lane) for lane in LANE_ORDER]
    if lane_centres != expected_lanes:
        raise SemanticGridError(
            f"Internal static-grid error: lane centres must be {expected_lanes}, "
            f"got {lane_centres}."
        )
    if GK_ANCHOR_XY_M != (6.0, 34.0):
        raise SemanticGridError(
            "Internal static-grid error: GK_Anchor must be (6.0, 34.0), "
            f"got {GK_ANCHOR_XY_M}."
        )

    if any(
        abs(ROW_X_M[index + 1] - ROW_X_M[index] - 10.0) > 1e-9
        for index in range(1, N_ROWS)
    ):
        raise SemanticGridError(
            "Internal static-grid error: adjacent outfield rows must be 10.0 m apart."
        )
    if abs(ROW_X_M[5] - PITCH_LENGTH_M / 2) > 1e-9 or any(
        abs(ROW_X_M[row] + ROW_X_M[N_ROWS + 1 - row] - PITCH_LENGTH_M) > 1e-9
        for row in range(1, 5)
    ):
        raise SemanticGridError(
            "Internal static-grid error: outfield rows must mirror around X=52.5 m."
        )
    if abs(LANE_Y_M["C_Center"] - PITCH_WIDTH_M / 2) > 1e-9 or any(
        abs(LANE_Y_M[left] + LANE_Y_M[right] - PITCH_WIDTH_M) > 1e-9
        for left, right in (
            ("L_Wing", "R_Wing"),
            ("L_Half", "R_Half"),
            ("L_Center", "R_Center"),
        )
    ):
        raise SemanticGridError(
            "Internal static-grid error: lane centres must mirror around Y=34.0 m."
        )

    for row, x_m in ROW_X_M.items():
        _convert_to_editor(x_m, LANE_Y_M["C_Center"], f"Row {row}")
    lane_editor_y = [
        _convert_to_editor(ROW_X_M[5], LANE_Y_M[lane], lane)[1] for lane in LANE_ORDER
    ]
    if any(
        right - left < MIN_EDITOR_Y_GAP
        for left, right in zip(lane_editor_y, lane_editor_y[1:])
    ):
        raise SemanticGridError(
            "Internal static-grid error: adjacent lane anchors overlap in editor space."
        )
    _convert_to_editor(*GK_ANCHOR_XY_M, GK_ANCHOR_LABEL)


def _nominal_outfield_xy(row: int, lane: str) -> tuple[float, float]:
    return float(ROW_X_M[row]), float(LANE_Y_M[lane])


def _pava_non_decreasing(values: Sequence[float]) -> list[float]:
    blocks: list[list[float]] = []
    for value in values:
        blocks.append([float(value), 1])
        while (
            len(blocks) > 1
            and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1] + 1e-12
        ):
            total, count = blocks.pop()
            blocks[-1][0] += total
            blocks[-1][1] += count

    result = []
    for total, count in blocks:
        result.extend([total / count] * int(count))
    return result


def _spread_chain(
    targets: Sequence[float], gap: float, lower: float, upper: float
) -> list[float] | None:
    count = len(targets)
    if count == 1:
        return [min(max(float(targets[0]), lower), upper)]
    if (count - 1) * gap > upper - lower + 1e-9:
        return None

    shifted = [float(target) - index * gap for index, target in enumerate(targets)]
    shifted = _pava_non_decreasing(shifted)
    values = [value + index * gap for index, value in enumerate(shifted)]

    values[0] = max(values[0], lower)
    for index in range(1, count):
        values[index] = max(values[index], values[index - 1] + gap)
    values[-1] = min(values[-1], upper)
    for index in range(count - 2, -1, -1):
        values[index] = min(values[index], values[index + 1] - gap)
    values[0] = max(values[0], lower)
    for index in range(1, count):
        values[index] = max(values[index], values[index - 1] + gap)
    return values


def _resolve_row_collisions(entries: list[dict[str, Any]], where: str) -> None:
    by_row: dict[int, list[dict[str, Any]]] = {}
    for entry in entries:
        if entry["kind"] == "grid":
            by_row.setdefault(entry["row"], []).append(entry)

    for row in sorted(by_row):
        members = sorted(by_row[row], key=lambda entry: (entry["y0"], entry["slot"]))
        nominal_cells = [(entry["row"], entry["lane"]) for entry in members]
        if len(nominal_cells) == len(set(nominal_cells)):
            continue

        resolved_y = _spread_chain(
            [entry["y0"] for entry in members],
            MIN_LATERAL_GAP_M,
            float(Y_LEGAL_MIN),
            float(Y_LEGAL_MAX),
        )
        if resolved_y is None:
            raise SemanticGridError(
                f"{where}: Row {row} cannot fit {len(members)} outfielders "
                "inside the legal width."
            )

        for entry, y_value in zip(members, resolved_y):
            entry["y"] = float(y_value)


def _validate_state_invariants(entries: list[dict[str, Any]], where: str) -> None:
    goalkeepers = [entry for entry in entries if entry["kind"] == "gk"]
    if len(goalkeepers) != 1:
        raise SemanticGridError(
            f"{where}: internal error - expected one GK_Anchor, got {len(goalkeepers)}."
        )
    goalkeeper = goalkeepers[0]
    if (goalkeeper["x"], goalkeeper["y"]) != GK_ANCHOR_XY_M:
        raise SemanticGridError(
            f"{where}: internal error - GK_Anchor moved from {GK_ANCHOR_XY_M}."
        )

    physical_rows: dict[int, list[tuple[float, int]]] = {}
    for entry in entries:
        if not X_LEGAL_MIN <= entry["x"] <= X_LEGAL_MAX:
            raise SemanticGridError(
                f"{where} Slot {entry['slot']}: resolved X={entry['x']} m escapes "
                f"[{X_LEGAL_MIN}, {X_LEGAL_MAX}] m."
            )
        if not Y_LEGAL_MIN <= entry["y"] <= Y_LEGAL_MAX:
            raise SemanticGridError(
                f"{where} Slot {entry['slot']}: resolved Y={entry['y']} m escapes "
                f"[{Y_LEGAL_MIN}, {Y_LEGAL_MAX}] m."
            )
        if entry["kind"] == "gk":
            continue
        expected_x = float(ROW_X_M[entry["row"]])
        if abs(entry["x"] - expected_x) > 1e-9:
            raise SemanticGridError(
                f"{where} Slot {entry['slot']}: Row {entry['row']} moved from "
                f"fixed X={expected_x} m."
            )
        physical_rows.setdefault(entry["row"], []).append((entry["y"], entry["slot"]))

    for row, line in sorted(physical_rows.items()):
        line.sort()
        for (y_a, slot_a), (y_b, slot_b) in zip(line, line[1:]):
            if y_b - y_a < MIN_LATERAL_GAP_M - 1e-9:
                raise SemanticGridError(
                    f"{where}: Slots {slot_a} and {slot_b} on Row {row} resolve "
                    f"only {y_b - y_a:g} m apart."
                )

    editor_columns: dict[int, list[tuple[int, int]]] = {}
    for entry in entries:
        x_editor, y_editor = _convert_to_editor(
            entry["x"], entry["y"], f"{where} Slot {entry['slot']}"
        )
        editor_columns.setdefault(x_editor, []).append((y_editor, entry["slot"]))

    for x_editor, column in sorted(editor_columns.items()):
        column.sort()
        for (y_a, slot_a), (y_b, slot_b) in zip(column, column[1:]):
            if y_b - y_a < MIN_EDITOR_Y_GAP:
                raise SemanticGridError(
                    f"{where}: Slots {slot_a} and {slot_b} resolve into editor "
                    f"column X={x_editor} only {y_b - y_a} Y unit(s) apart."
                )


def _resolve_state_geometry(entries: list[dict[str, Any]], where: str) -> None:
    _resolve_row_collisions(entries, where)
    _validate_state_invariants(entries, where)


def _convert_to_editor(x_m: float, y_m: float, where: str) -> tuple[int, int]:
    x_m = float(x_m)
    y_m = float(y_m)
    if not (X_LEGAL_MIN <= x_m <= X_LEGAL_MAX and Y_LEGAL_MIN <= y_m <= Y_LEGAL_MAX):
        raise SemanticGridError(
            f"{where}: physical coordinates ({x_m}, {y_m}) m escape "
            f"X=[{X_LEGAL_MIN}, {X_LEGAL_MAX}] m or "
            f"Y=[{Y_LEGAL_MIN}, {Y_LEGAL_MAX}] m."
        )

    x_editor = math.floor(52 * x_m / PITCH_LENGTH_M + 0.5)
    y_editor = math.floor(104 * y_m / PITCH_WIDTH_M + 0.5)
    if not (
        EDITOR_X_MIN <= x_editor <= EDITOR_X_MAX
        and EDITOR_Y_MIN <= y_editor <= EDITOR_Y_MAX
    ):
        raise SemanticGridError(
            f"{where}: editor conversion of ({x_m}, {y_m}) m gave "
            f"({x_editor}, {y_editor}), outside panel envelope."
        )
    return x_editor, y_editor
