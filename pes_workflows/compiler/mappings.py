"""PES semantic vocabulary, raw enums, aliases, and key lookups."""

import re

from pes_workflows.domain.advanced_instructions import AdvancedInstruction
from pes_workflows.domain.csv_schema import (
    EMPTY_ROSTER_IDS as EMPTY_ROSTER_IDS,
)
from pes_workflows.domain.csv_schema import (
    FORMATION_ROSTER_SIZE as FORMATION_ROSTER_SIZE,
)
from pes_workflows.domain.csv_schema import (
    STARTER_COUNT as STARTER_COUNT,
)
from pes_workflows.domain.vocabulary import POSITION_IDS

from .geometry import LANE_ORDER, N_ROWS

POSITION_NAME_TO_CODE = {name: str(code) for name, code in POSITION_IDS.items()}

TACTIC_KEYS = ["S1", "S2", "S3"]
STATE_KEYS = ["F1", "F2", "F3"]
TACTIC_NAMES = {"S1": "Main", "S2": "Defensive", "S3": "Custom"}
STATE_NAMES = {"F1": "Normal", "F2": "With Ball", "F3": "Without Ball"}


_TACTIC_ALIASES = {
    "s1": "S1",
    "main": "S1",
    "s2": "S2",
    "defensive": "S2",
    "s3": "S3",
    "custom": "S3",
}
_STATE_ALIASES = {
    "f1": "F1",
    "normal": "F1",
    "f2": "F2",
    "with ball": "F2",
    "withball": "F2",
    "f3": "F3",
    "without ball": "F3",
    "withoutball": "F3",
}

_GRID_RE = re.compile(
    rf"^Row ([1-{N_ROWS}]) - ("
    + "|".join(re.escape(lane) for lane in LANE_ORDER)
    + r")$"
)


def _norm(text: object) -> str:
    s = str(text).strip().lower()
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("-", " ")
    s = s.replace(".", "")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("defense", "defence").replace("centre", "center")
    return s


ROLE_COLUMN_ORDER = [
    "Captain",
    "LongFK",
    "ShortFK",
    "SecondKicker",
    "RightCorner",
    "LeftCorner",
    "Penalty",
    "Header1",
    "Header2",
    "Header3",
]
AUTO_ROLE_COLUMNS = [
    "Captain",
    "LongFK",
    "ShortFK",
    "SecondKicker",
    "RightCorner",
    "LeftCorner",
    "Penalty",
]
GLOBAL_JOIN_ATTACK_COLUMNS = ["Header1", "Header2", "Header3"]

_BASIC_SETTING_SPECS = [
    (
        "Attacking Style",
        "AttackingStyles",
        {"Counter Attack": "0", "Possession Game": "1"},
    ),
    ("Build Up", "BuildUp", {"Long-pass": "0", "Short-pass": "1"}),
    ("Attacking Area", "AttackingArea", {"Wide": "0", "Center": "1"}),
    ("Positioning", "Positioning", {"Maintain Formation": "0", "Flexible": "1"}),
    ("Support Range", "SupportRange", None),
    ("Numbers in Attack", "NumbersInAttack", {"Few": "1", "Medium": "2", "Many": "3"}),
    (
        "Defensive Style",
        "DefensiveStyles",
        {"Frontline Pressure": "0", "All-out Defence": "1"},
    ),
    ("Containment Area", "ContainmentArea", {"Center": "0", "Wide": "1"}),
    ("Pressuring", "Pressuring", {"Aggressive": "0", "Conservative": "1"}),
    ("Defensive Line", "DefensiveLine", None),
    ("Compactness", "Compactness", None),
    (
        "Numbers in Defence",
        "NumbersInDefense",
        {"Few": "1", "Medium": "2", "Many": "3"},
    ),
]

_BASIC_KEY_LOOKUP = {_norm(display): display for display, _, _ in _BASIC_SETTING_SPECS}
_BASIC_VALUE_MAPS = {
    display: {_norm(label): enum for label, enum in choices.items()}
    for display, _, choices in _BASIC_SETTING_SPECS
    if choices is not None
}
_BASIC_LEGAL_LABELS = {
    display: list(choices) for display, _, choices in _BASIC_SETTING_SPECS if choices
}
_SLIDER_SETTINGS = {"Support Range", "Defensive Line", "Compactness"}

_ADVANCED_SLOT_SPECS = {
    "Attacking 1": ("AdvancedAtt1", "attacking"),
    "Attacking 2": ("AdvancedAtt2", "attacking"),
    "Defending 1": ("AdvancedDef1", "defending"),
    "Defending 2": ("AdvancedDef2", "defending"),
}
_ADVANCED_KEY_LOOKUP = {_norm(key): key for key in _ADVANCED_SLOT_SPECS}
_ADVANCED_INSTRUCTIONS = {_norm(item.label): item for item in AdvancedInstruction}
_ATTACKING_ADVANCED_ENUMS = {
    _norm(item.label): str(item.code)
    for item in AdvancedInstruction
    if item.family in (None, "attacking")
}
_DEFENDING_ADVANCED_ENUMS = {
    _norm(item.label): str(item.code)
    for item in AdvancedInstruction
    if item.family in (None, "defending")
}
_ADVANCED_CANONICAL_NAMES = {
    _norm(item.label): item.label for item in AdvancedInstruction
}
_OFFSIDE_VALUE_LOOKUP = {_norm("On"): "On", _norm("Off"): "Off"}

FORCED_GLOBAL_COLUMNS = {
    "FluidS1": "1",
    "FluidS2": "1",
    "FluidS3": "1",
}

GLOBAL_AUTO_COLUMNS = {
    "auto_substitutions": "AutoSubstitutions",
    "auto_change_att_def": "AutoChangeAttDef",
    "auto_switch_preset_tactics": "SwitchTactics",
}

_TOP_KEY_LOOKUP = {
    _norm("Team ID"): "Team ID",
    _norm("Squad"): "Squad",
    _norm("Presets"): "Presets",
}
_PRESET_SECTION_KEY_LOOKUP = {
    _norm("Auto Offside Trap"): "Auto Offside Trap",
    _norm("Players to Join Attack"): "Players to Join Attack",
    _norm("Basic Instructions"): "Basic Instructions",
    _norm("Advanced Instructions"): "Advanced Instructions",
    _norm("States"): "States",
}
_SQUAD_ENTRY_KEY_LOOKUP = {
    _norm("Player ID"): "Player ID",
    _norm("Player"): "Player",
}
_STATE_ENTRY_KEY_LOOKUP = {
    _norm("Slot"): "Slot",
    _norm("Position"): "Position",
    _norm("Grid Assignment"): "Grid Assignment",
}
_ADVANCED_ENTRY_KEY_LOOKUP = {
    _norm("Instruction"): "Instruction",
    _norm("Designated Player"): "Designated Player",
}
_PLAYER_REF_KEY_LOOKUP = dict(_SQUAD_ENTRY_KEY_LOOKUP)
