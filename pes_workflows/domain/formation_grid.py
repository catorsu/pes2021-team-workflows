"""Contract v2.2 coordinate vocabulary and half-pitch bounds (rules IV)."""

GRID_ROW_MIN = 0
GRID_ROW_MAX = 9
GRID_LANES = (
    "L_Wing",
    "L_Half",
    "L_Center",
    "C_Center",
    "R_Center",
    "R_Half",
    "R_Wing",
)

OUTFIELD_ROW_BOUNDS = {
    "Normal": (1, 9),
    "With Ball": (6, 9),
    "Without Ball": (1, 4),
}


def grid_row_bounds(slot: int, state_name: str) -> tuple[int, int]:
    """Slot 0 is exempt from the outfield half-pitch restrictions."""
    return (GRID_ROW_MIN, GRID_ROW_MAX) if slot == 0 else OUTFIELD_ROW_BOUNDS[state_name]
