"""Resolve validated advanced-instruction targets against the team's roster."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from pes_workflows.domain.advanced_instructions import AdvancedInstruction

from .errors import SemanticGridError
from .mappings import FORMATION_ROSTER_SIZE

__all__ = ["TargetedInstruction", "resolve_targeted_instructions"]

_PLAYER_INDEX_SHIFT = 32


@dataclass(frozen=True, slots=True)
class TargetedInstruction:
    column: str
    instruction: AdvancedInstruction
    player_id: str


def resolve_targeted_instructions(
    instructions: Iterable[TargetedInstruction],
    id_to_index: Mapping[str, int],
) -> dict[str, str]:
    """Encode targets as decimal CSV values; reject unresolved roster references."""
    updates: dict[str, str] = {}
    for target in instructions:
        if target.player_id not in id_to_index:
            raise SemanticGridError(
                f"{target.column}: Player ID {target.player_id!r} is not in Rosters.csv."
            )
        roster_index = id_to_index[target.player_id]
        if not 0 <= roster_index < FORMATION_ROSTER_SIZE:
            raise SemanticGridError(
                f"{target.column}: roster index {roster_index} is outside "
                f"0-{FORMATION_ROSTER_SIZE - 1}."
            )
        if not target.instruction.is_player_targeted:
            raise SemanticGridError(
                f"{target.column}: {target.instruction.label} cannot designate a player."
            )
        # The upper word references Rosters.csv, independently of starting-slot order.
        updates[target.column] = str(
            (roster_index << _PLAYER_INDEX_SHIFT) | target.instruction.code
        )
    return updates
