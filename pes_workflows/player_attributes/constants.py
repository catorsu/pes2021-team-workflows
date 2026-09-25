"""Canonical PES 2021 player-attribute vocabulary and editor mappings."""

from __future__ import annotations

from collections.abc import Iterable

from pes_workflows.domain.vocabulary import (
    COM_PLAYING_STYLES,
    PLAYER_SKILLS,
    POSITION_IDS,
    STAT_NAMES,
)

PLAYER_ATTRIBUTE_SCHEMA_VERSION = "4.0"

# The model-facing pipeline has two squad artifacts. ``PlayerAttributeTeam``
# is an internal merged value used only after both model artifacts validate
PLAYER_PROFILES_ARTIFACT = "PlayerProfiles"
PLAYER_ABILITIES_ARTIFACT = "PlayerAbilities"
PLAYER_ATTRIBUTE_TEAM_ARTIFACT = "PlayerAttributeTeam"

POSITIONS = tuple(POSITION_IDS)

# Slices of the shared ability order. ``domain.vocabulary`` documents that this
# order is load-bearing precisely because of these partitions
GENERAL_ABILITY_STATS = STAT_NAMES[:25]
GK_STATS = STAT_NAMES[20:25]
TRAIT_STATS = STAT_NAMES[25:]

STRONGER_FEET = ("Left Foot", "Right Foot")

GENERAL_ABILITY_MIN = 40
GENERAL_ABILITY_MAX = 99
# Distinct from the ability floor it happens to share a value with: the engine
# leaves an outfielder's five goalkeeping ratings inert at exactly this number
NON_GK_GOALKEEPER_ABILITY = 40
WEAK_FOOT_MIN = 1
WEAK_FOOT_MAX = 4
CONDITIONING_MIN = 1
CONDITIONING_MAX = 8
INJURY_RESISTANCE_MIN = 1
INJURY_RESISTANCE_MAX = 3
ELITE_RATING_MIN = 96


def _canonical_order(
    assigned: Iterable[object], canonical: Iterable[str]
) -> tuple[str, ...]:
    rank = {name: index for index, name in enumerate(canonical)}
    seen: set[str] = set()
    known: list[str] = []
    unknown: list[str] = []
    for item in assigned:
        term = str(item)
        if term in seen:
            continue
        seen.add(term)
        (known if term in rank else unknown).append(term)
    known.sort(key=rank.__getitem__)
    return (*known, *unknown)


def order_player_skills(assigned: Iterable[object]) -> tuple[str, ...]:
    """Assigned Player Skills in ``PLAYER_SKILL_COLUMNS`` key order."""

    return _canonical_order(assigned, PLAYER_SKILLS)


def order_com_styles(assigned: Iterable[object]) -> tuple[str, ...]:
    """Assigned COM Playing Styles in ``COM_STYLE_COLUMNS`` key order."""

    return _canonical_order(assigned, COM_PLAYING_STYLES)


EDIT_FLAG_COLUMNS = (
    "EditBasics",
    "EditAbilities",
    "EditPlayingStyle",
    "EditPlayerSkills",
    "EditCOMPlayingStyles",
    "EditPosition",
    "EditPositions",
    "InEditFile",
)
