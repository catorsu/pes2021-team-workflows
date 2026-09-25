"Deterministic, data-driven assignment of formation routine roles."

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pes_workflows.domain.vocabulary import FORWARD_POSITIONS

from .errors import SemanticGridError
from .mappings import AUTO_ROLE_COLUMNS

_CREATIVE_POSITIONS: frozenset[str] = frozenset({"AMF", "CMF", "LMF", "RMF"})
_MIDFIELD_POSITIONS: frozenset[str] = _CREATIVE_POSITIONS | {"DMF"}


@dataclass(frozen=True, slots=True)
class _StarterProfile:
    id: str
    slot: int
    position: str
    foot: str
    skills: frozenset[str]
    abilities: Mapping[str, int]


def _get_ability(profile: _StarterProfile, key: str, default: int) -> int:
    abilities = profile.abilities
    if key in abilities:
        return abilities[key]
    normalized_key = key.replace(" ", "").casefold()
    for ability_name, value in abilities.items():
        if ability_name.replace(" ", "").casefold() == normalized_key:
            return value
    return default


def _has_skill(profile: _StarterProfile, skill_name: str) -> bool:
    normalized_target = skill_name.replace(" ", "").casefold()
    return any(
        skill.replace(" ", "").casefold() == normalized_target
        for skill in profile.skills
    )


def _calculate_captain_score(profile: _StarterProfile) -> float:
    score = (
        _get_ability(profile, "Defensive Awareness", 50) * 0.20
        + _get_ability(profile, "Offensive Awareness", 50) * 0.20
        + _get_ability(profile, "Stamina", 60) * 0.25
        + _get_ability(profile, "Conditioning", 5) * 2.5
    )
    if _has_skill(profile, "Captaincy"):
        score += 35.0
    if _has_skill(profile, "Fighting Spirit"):
        score += 10.0
    if profile.slot == 0:
        score -= 10.0
    return round(score, 2)


def _calculate_short_fk_score(profile: _StarterProfile) -> float:
    score = (
        _get_ability(profile, "Set Piece Taking", 50) * 0.40
        + _get_ability(profile, "Curl", 50) * 0.25
        + _get_ability(profile, "Kicking Power", 50) * 0.20
        + _get_ability(profile, "Finishing", 50) * 0.15
    )
    if _has_skill(profile, "Knuckle Shot"):
        score += 5.0
    if _has_skill(profile, "Dipping Shot"):
        score += 4.0
    if _has_skill(profile, "Long Range Shooting"):
        score += 2.0
    return round(score, 2)


def _calculate_long_fk_score(profile: _StarterProfile) -> float:
    score = (
        _get_ability(profile, "Set Piece Taking", 50) * 0.35
        + _get_ability(profile, "Lofted Pass", 50) * 0.35
        + _get_ability(profile, "Curl", 50) * 0.15
        + _get_ability(profile, "Kicking Power", 50) * 0.15
    )
    if _has_skill(profile, "Pinpoint Crossing"):
        score += 6.0
    if _has_skill(profile, "Weighted Pass"):
        score += 4.0
    if _has_skill(profile, "Low Lofted Pass"):
        score += 2.0
    return round(score, 2)


def _calculate_corner_score(profile: _StarterProfile, *, is_left: bool) -> float:
    score = (
        _get_ability(profile, "Set Piece Taking", 50) * 0.35
        + _get_ability(profile, "Lofted Pass", 50) * 0.35
        + _get_ability(profile, "Curl", 50) * 0.30
    )
    if _has_skill(profile, "Pinpoint Crossing"):
        score += 6.0
    if _has_skill(profile, "Weighted Pass"):
        score += 3.0

    foot = profile.foot
    if (is_left and foot == "Right") or (not is_left and foot == "Left"):
        score += 2.0
    return round(score, 2)


def _calculate_penalty_score(profile: _StarterProfile) -> float:
    conditioning = _get_ability(profile, "Conditioning", 5)
    score = (
        _get_ability(profile, "Finishing", 50) * 0.45
        + _get_ability(profile, "Set Piece Taking", 50) * 0.30
        + _get_ability(profile, "Kicking Power", 50) * 0.25
    )
    if _has_skill(profile, "Penalty Specialist"):
        score += 25.0
    if conditioning > 5:
        score += float(conditioning - 5)
    return round(score, 2)


def _starter_profiles(
    squad_ids: Sequence[str],
    entries: Sequence[Mapping[str, Any]],
    player_stats: Mapping[str, Mapping[str, Any]],
) -> list[_StarterProfile]:
    profiles: list[_StarterProfile] = []
    for slot, entry in enumerate(entries):
        player_id = squad_ids[slot]
        stats = player_stats.get(player_id, {})
        profiles.append(
            _StarterProfile(
                id=player_id,
                slot=slot,
                position=entry["pos_name"],
                foot=stats.get("foot", "Right"),
                skills=frozenset(stats.get("skills", ())),
                abilities=MappingProxyType(dict(stats.get("abilities", {}))),
            )
        )
    return profiles


def _set_piece_key(
    profile: _StarterProfile, score: float, *, role: str
) -> tuple[float, int, int, str]:
    groups: tuple[frozenset[str], ...]
    if role == "Penalty":
        groups = (FORWARD_POSITIONS, _CREATIVE_POSITIONS, _MIDFIELD_POSITIONS)
    elif role in {"ShortFK", "SecondKicker"}:
        groups = (FORWARD_POSITIONS | _CREATIVE_POSITIONS, _MIDFIELD_POSITIONS)
    else:
        groups = (_CREATIVE_POSITIONS, _MIDFIELD_POSITIONS, FORWARD_POSITIONS)
    for index, positions in enumerate(groups):
        if profile.position in positions:
            return score, len(groups) - index, -profile.slot, profile.id
    return score, 0, -profile.slot, profile.id


def _derive_routine_role_ids(
    squad_ids: Sequence[str],
    main_normal_entries: Sequence[Mapping[str, Any]],
    *,
    join_attack_player_ids: Collection[str] = (),
    player_stats: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    profiles = _starter_profiles(
        squad_ids,
        main_normal_entries,
        {} if player_stats is None else player_stats,
    )
    outfielders = [profile for profile in profiles if profile.slot != 0]
    delivery_candidates = [
        profile for profile in outfielders if profile.id not in join_attack_player_ids
    ]
    long_fk_candidates = [
        profile
        for profile in delivery_candidates
        if profile.position not in FORWARD_POSITIONS
    ]
    if not long_fk_candidates:
        raise SemanticGridError(
            "LongFK requires a starting defender or midfielder outside Players to "
            "Join Attack across the active presets; revise the formation or aerial targets."
        )
    resolved: dict[str, str] = {}

    def assign(
        role: str,
        candidates: Sequence[_StarterProfile],
        score: Callable[[_StarterProfile], float],
    ) -> _StarterProfile:
        if role == "Captain":
            selected = max(candidates, key=lambda p: (score(p), -p.slot, p.id))
        else:
            selected = max(
                candidates, key=lambda p: _set_piece_key(p, score(p), role=role)
            )
        resolved[role] = selected.id
        return selected

    assign("Captain", profiles, _calculate_captain_score)
    short_fk = assign("ShortFK", outfielders, _calculate_short_fk_score)
    assign("LongFK", long_fk_candidates, _calculate_long_fk_score)

    def second_kicker_score(profile: _StarterProfile) -> float:
        score = (
            _calculate_short_fk_score(profile) + _calculate_long_fk_score(profile)
        ) / 2.0
        return score + (6.0 if profile.foot != short_fk.foot else 0.0)

    second_candidates = [
        profile for profile in outfielders if profile.id != short_fk.id
    ]
    assign("SecondKicker", second_candidates, second_kicker_score)
    for role, is_left in (("LeftCorner", True), ("RightCorner", False)):
        assign(
            role,
            delivery_candidates,
            lambda profile: _calculate_corner_score(profile, is_left=is_left),
        )
    assign("Penalty", outfielders, _calculate_penalty_score)
    return resolved


def _resolve_role_updates(
    routine_role_ids: Mapping[str, str],
    id_to_index: Mapping[str, int],
) -> dict[str, str]:
    updates: dict[str, str] = {}
    for role in AUTO_ROLE_COLUMNS:
        pid = routine_role_ids[role]
        if pid not in id_to_index:
            raise SemanticGridError(
                f"Internal role-resolution error: {role} Player ID {pid!r} is "
                "not in the resolved roster indices."
            )
        roster_index = str(id_to_index[pid])
        updates[role] = roster_index
    return updates
