"Model-artifact contract versions and canonical vocabulary."

from pes_workflows.compiler.geometry import LANE_ORDER
from pes_workflows.compiler.mappings import (
    _ADVANCED_SLOT_SPECS,
    _BASIC_SETTING_SPECS,
    TACTIC_NAMES,
)
from pes_workflows.compiler.mappings import (
    STATE_NAMES as EDITOR_STATE_NAMES,
)
from pes_workflows.domain.advanced_instructions import AdvancedInstruction

SCHEMA_VERSION = "2.2"
# Only freshly generated model artifacts declare a schema version. A saved
# semantic game plan carries none — it holds Team ID, Squad and Presets — and
# reinjection compiles it without re-running these validators, so this tuple
# gates model responses alone and never has to admit a stored plan
SUPPORTED_SCHEMA_VERSIONS = (SCHEMA_VERSION,)
PRESET_NAMES = tuple(TACTIC_NAMES.values())
# GAME_PLAN_RULES II fixes one Risk Budget per preset; the field must equal it.
PRESET_RISK_BUDGETS = {"Main": "Medium", "Defensive": "Low", "Custom": "High"}
STATE_NAMES = tuple(EDITOR_STATE_NAMES.values())
GRID_LANES = tuple(LANE_ORDER)
BASIC_SETTING_ORDER = tuple(name for name, _, _ in _BASIC_SETTING_SPECS)
BASIC_LEGAL_VALUES = {
    name: tuple(choices)
    for name, _, choices in _BASIC_SETTING_SPECS
    if choices is not None
}
SLIDER_SETTINGS = {name for name, _, choices in _BASIC_SETTING_SPECS if choices is None}
ADVANCED_SLOT_ORDER = tuple(_ADVANCED_SLOT_SPECS)
ATTACKING_ADVANCED = tuple(
    instruction.label
    for instruction in AdvancedInstruction
    if instruction.family in (None, "attacking")
)
DEFENDING_ADVANCED = tuple(
    instruction.label
    for instruction in AdvancedInstruction
    if instruction.family in (None, "defending")
)
PLAYER_SPECIFIC_ADVANCED = frozenset(
    instruction.label
    for instruction in AdvancedInstruction
    if instruction.is_player_targeted
)
