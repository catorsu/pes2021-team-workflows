"""Canonical advanced instructions and their editor codes."""

from enum import Enum
from typing import Literal

__all__ = ["AdvancedInstruction"]


class AdvancedInstruction(Enum):
    BLANK = (0, "Blank", None, False)
    HUG_THE_TOUCHLINE = (1, "Hug the Touchline", "attacking", False)
    FALSE_NO_9 = (2, "False No. 9", "attacking", False)
    FALSE_FULL_BACKS = (3, "False Full Backs", "attacking", False)
    ATTACKING_FULL_BACKS = (4, "Attacking Full Backs", "attacking", False)
    WING_ROTATION = (5, "Wing Rotation", "attacking", False)
    TIKI_TAKA = (6, "Tiki-Taka", "attacking", False)
    CENTRING_TARGETS = (7, "Centring Targets", "attacking", False)
    DEFENSIVE = (8, "Defensive", "attacking", True)
    FALSE_WINGER = (9, "False Winger", "attacking", False)
    ANCHORING = (10, "Anchoring", "attacking", True)
    SWARM_THE_BOX = (11, "Swarm the Box", "defending", False)
    DEEP_DEFENSIVE_LINE = (12, "Deep Defensive Line", "defending", False)
    GEGENPRESSING = (13, "Gegenpressing", "defending", False)
    COUNTER_TARGET = (15, "Counter Target", "defending", True)
    WINGBACK = (16, "Wingback", "defending", False)

    code: int
    label: str
    family: Literal["attacking", "defending"] | None
    is_player_targeted: bool

    def supports_position(self, position: str) -> bool:
        """Check the product's tactical eligibility for a fluid-state position."""
        if self.is_player_targeted and position == "GK":
            return False
        if self is AdvancedInstruction.COUNTER_TARGET:
            return position != "CB"
        if self is AdvancedInstruction.DEFENSIVE:
            return position not in {"CF", "SS"}
        return True

    def __init__(
        self,
        code: int,
        label: str,
        family: Literal["attacking", "defending"] | None,
        is_player_targeted: bool,
    ) -> None:
        self.code = code
        self.label = label
        self.family = family
        self.is_player_targeted = is_player_targeted
