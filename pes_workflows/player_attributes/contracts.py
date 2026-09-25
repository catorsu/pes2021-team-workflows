"Strict contracts for the two squad-level player-attribute artifacts."

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from unicodedata import normalize

from pes_workflows.contracts.errors import (
    ArtifactContractError,
    ArtifactDomainError,
    ArtifactSchemaError,
)
from pes_workflows.contracts.json_codec import (
    _expect_enum,
    _expect_exact_keys,
    _expect_int,
    _expect_list,
    _expect_object,
    _expect_string,
    _path,
)
from pes_workflows.domain.vocabulary import (
    COM_PLAYING_STYLES,
    PLAYER_SKILLS,
    PLAYING_STYLE_POSITIONS,
    PLAYING_STYLES,
    TEAM_KINDS,
)

from .constants import (
    CONDITIONING_MAX,
    CONDITIONING_MIN,
    ELITE_RATING_MIN,
    GENERAL_ABILITY_MAX,
    GENERAL_ABILITY_MIN,
    GENERAL_ABILITY_STATS,
    GK_STATS,
    INJURY_RESISTANCE_MAX,
    INJURY_RESISTANCE_MIN,
    NON_GK_GOALKEEPER_ABILITY,
    PLAYER_ABILITIES_ARTIFACT,
    PLAYER_ATTRIBUTE_SCHEMA_VERSION,
    PLAYER_ATTRIBUTE_TEAM_ARTIFACT,
    PLAYER_PROFILES_ARTIFACT,
    POSITIONS,
    STRONGER_FEET,
    TRAIT_STATS,
    WEAK_FOOT_MAX,
    WEAK_FOOT_MIN,
)

SQUAD_KEYS = (
    "Schema Version",
    "Artifact",
    "Team Name",
    "Team ID",
    "Total Players",
    "Players",
)
PROFILE_KEYS = (
    "Player ID",
    "Player Name",
    "Age",
    "Registered Position",
    "Position Familiarity",
    "Stronger Foot",
    "Playing Style",
    "Player Skills",
    "COM Playing Styles",
)
_REQUIRED_ABILITY_KEYS = (
    "Player ID",
    "Player Name",
    "Age",
    "Abilities",
    "Form and Traits",
)
ABILITY_KEYS = _REQUIRED_ABILITY_KEYS + ("Elite Rationales",)
SOURCE_IDENTITY_KEYS = ("Player ID", "Player Name", "Age")
FORM_AND_TRAIT_KEYS = tuple(TRAIT_STATS)
MERGED_TEAM_KEYS = (
    "Schema Version",
    "Artifact",
    "Team Name",
    "Team Kind",
    "Team ID",
    "Total Players",
    "Players",
)
MERGED_PLAYER_KEYS = PROFILE_KEYS + (
    "Abilities",
    "Form and Traits",
    "Elite Rationales",
)


def _immutable_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    "One validated Call 1 player row."

    player_id: str
    player_name: str
    age: int
    registered_position: str
    position_familiarity: Mapping[str, int]
    stronger_foot: str
    playing_style: str | None
    """The one nullable artifact field: ``None`` means no glossary style."""
    player_skills: tuple[str, ...]
    com_playing_styles: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "position_familiarity", _immutable_mapping(self.position_familiarity)
        )
        object.__setattr__(self, "player_skills", tuple(self.player_skills))
        object.__setattr__(self, "com_playing_styles", tuple(self.com_playing_styles))

    def to_dict(self) -> dict[str, Any]:
        return {
            "Player ID": self.player_id,
            "Player Name": self.player_name,
            "Age": self.age,
            "Registered Position": self.registered_position,
            "Position Familiarity": dict(self.position_familiarity),
            "Stronger Foot": self.stronger_foot,
            "Playing Style": self.playing_style,
            "Player Skills": list(self.player_skills),
            "COM Playing Styles": list(self.com_playing_styles),
        }


@dataclass(frozen=True, slots=True)
class PlayerProfiles:
    "The complete, ordered Call 1 artifact."

    schema_version: str
    team_name: str
    team_id: str
    players: tuple[PlayerProfile, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "players", tuple(self.players))

    def to_dict(self) -> dict[str, Any]:
        return {
            "Schema Version": self.schema_version,
            "Artifact": PLAYER_PROFILES_ARTIFACT,
            "Team Name": self.team_name,
            "Team ID": self.team_id,
            "Total Players": len(self.players),
            "Players": [player.to_dict() for player in self.players],
        }


@dataclass(frozen=True, slots=True)
class PlayerAbility:
    "One validated Call 2 player row."

    player_id: str
    player_name: str
    age: int
    abilities: Mapping[str, int]
    form_and_traits: Mapping[str, int]
    elite_rationales: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "abilities", _immutable_mapping(self.abilities))
        object.__setattr__(
            self, "form_and_traits", _immutable_mapping(self.form_and_traits)
        )
        object.__setattr__(
            self, "elite_rationales", _immutable_mapping(self.elite_rationales)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "Player ID": self.player_id,
            "Player Name": self.player_name,
            "Age": self.age,
            "Abilities": dict(self.abilities),
            "Form and Traits": dict(self.form_and_traits),
            "Elite Rationales": dict(self.elite_rationales),
        }


@dataclass(frozen=True, slots=True)
class PlayerAbilities:
    "The complete, ordered Call 2 artifact."

    schema_version: str
    team_name: str
    team_id: str
    players: tuple[PlayerAbility, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "players", tuple(self.players))

    def to_dict(self) -> dict[str, Any]:
        return {
            "Schema Version": self.schema_version,
            "Artifact": PLAYER_ABILITIES_ARTIFACT,
            "Team Name": self.team_name,
            "Team ID": self.team_id,
            "Total Players": len(self.players),
            "Players": [player.to_dict() for player in self.players],
        }


@dataclass(frozen=True, slots=True)
class PlayerAttributeRecord:
    "Internal merged profile used by reporting and CSV injection."

    player_id: str
    player_name: str
    age: int
    registered_position: str
    position_familiarity: Mapping[str, int]
    stronger_foot: str
    playing_style: str | None
    player_skills: tuple[str, ...]
    com_playing_styles: tuple[str, ...]
    abilities: Mapping[str, int]
    form_and_traits: Mapping[str, int]
    elite_rationales: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "position_familiarity", _immutable_mapping(self.position_familiarity)
        )
        object.__setattr__(self, "player_skills", tuple(self.player_skills))
        object.__setattr__(self, "com_playing_styles", tuple(self.com_playing_styles))
        object.__setattr__(self, "abilities", _immutable_mapping(self.abilities))
        object.__setattr__(
            self, "form_and_traits", _immutable_mapping(self.form_and_traits)
        )
        object.__setattr__(
            self, "elite_rationales", _immutable_mapping(self.elite_rationales)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "Player ID": self.player_id,
            "Player Name": self.player_name,
            "Age": self.age,
            "Registered Position": self.registered_position,
            "Position Familiarity": dict(self.position_familiarity),
            "Stronger Foot": self.stronger_foot,
            "Playing Style": self.playing_style,
            "Player Skills": list(self.player_skills),
            "COM Playing Styles": list(self.com_playing_styles),
            "Abilities": dict(self.abilities),
            "Form and Traits": dict(self.form_and_traits),
            "Elite Rationales": dict(self.elite_rationales),
        }


@dataclass(frozen=True, slots=True)
class PlayerAttributeTeam:
    "Internal, validated merge of Call 1 and Call 2."

    schema_version: str
    team_name: str
    team_kind: str
    team_id: str
    players: tuple[PlayerAttributeRecord, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "players", tuple(self.players))

    def to_dict(self) -> dict[str, Any]:
        return {
            "Schema Version": self.schema_version,
            "Artifact": PLAYER_ATTRIBUTE_TEAM_ARTIFACT,
            "Team Name": self.team_name,
            "Team Kind": self.team_kind,
            "Team ID": self.team_id,
            "Total Players": len(self.players),
            "Players": [player.to_dict() for player in self.players],
        }


def _validate_header(
    raw: Mapping[str, Any], artifact: str, expected_keys: Sequence[str]
) -> str:
    _expect_exact_keys(raw, expected_keys, artifact, "$")
    schema_version = _expect_string(raw["Schema Version"], artifact, "$.Schema Version")
    if schema_version != PLAYER_ATTRIBUTE_SCHEMA_VERSION:
        raise ArtifactSchemaError(
            artifact,
            "$.Schema Version",
            f"must equal {PLAYER_ATTRIBUTE_SCHEMA_VERSION!r}",
        )
    if raw["Artifact"] != artifact:
        raise ArtifactSchemaError(artifact, "$.Artifact", f"must equal {artifact!r}")
    return schema_version


def _positive_player_id(value: Any, artifact: str, path: str) -> str:
    player_id = _expect_string(value, artifact, path)
    if not player_id.isascii() or not player_id.isdecimal() or int(player_id) <= 0:
        raise ArtifactSchemaError(
            artifact, path, "must be a decimal string representing a positive integer"
        )
    return player_id


def _positive_age(value: Any, artifact: str, path: str) -> int:
    age = _expect_int(value, artifact, path)
    if age <= 0:
        raise ArtifactSchemaError(artifact, path, "must be a positive integer")
    return age


def _bounded_int(
    value: Any, minimum: int, maximum: int, artifact: str, path: str
) -> int:
    parsed = _expect_int(value, artifact, path)
    if not minimum <= parsed <= maximum:
        raise ArtifactSchemaError(
            artifact, path, f"must be between {minimum} and {maximum} inclusive"
        )
    return parsed


def _optional_playing_style(
    value: Any, registered_position: str, artifact: str, path: str
) -> str | None:
    """Accept JSON ``null`` or one glossary name that activates where deployed.

    ``null`` is the sole nullable value in either artifact. The string sentinels
    a model might reach for instead — ``"None"``, ``"N/A"`` — are rejected by
    the glossary enum, so no no-style value can arrive as text.
    """

    if value is None:
        return None
    style = _expect_enum(value, PLAYING_STYLES, artifact, path)
    if registered_position not in PLAYING_STYLE_POSITIONS[style]:
        raise ArtifactDomainError(
            artifact,
            path,
            f"is not compatible with Registered Position {registered_position!r}",
        )
    return style


def _ordered_unique_enums(
    value: Any, legal: Sequence[str], artifact: str, path: str
) -> tuple[str, ...]:
    rows = _expect_list(value, artifact, path)
    accepted = []
    seen = set()
    for index, item in enumerate(rows):
        item_path = _path(path, index)
        parsed = _expect_enum(item, legal, artifact, item_path)
        if parsed in seen:
            raise ArtifactSchemaError(
                artifact, item_path, "must not duplicate an earlier item"
            )
        seen.add(parsed)
        accepted.append(parsed)
    return tuple(accepted)


def _expected_team_values(expected_team: Any) -> tuple[str, str]:
    if isinstance(expected_team, Mapping):
        name = expected_team.get("Team Name")
        team_id = expected_team.get("Team ID")
    else:
        name = getattr(expected_team, "name", None)
        team_id = getattr(expected_team, "team_id", None)
    if not isinstance(name, str) or not name:
        raise ValueError("expected_team must provide a non-empty team name")
    if not isinstance(team_id, str) or not team_id:
        raise ValueError("expected_team must provide a non-empty team ID string")
    return name, team_id


def _expected_identity(value: Mapping[str, Any]) -> tuple[str, str, int]:
    if not isinstance(value, Mapping):
        raise ValueError("each expected source identity must be a mapping")
    expected_keys = {"Player ID", "Player Name", "Age"}
    if set(value) != expected_keys:
        raise ValueError(
            "expected source identity keys must be Player ID, Player Name, and Age"
        )
    player_id = value["Player ID"]
    player_name = value["Player Name"]
    age = value["Age"]
    if not isinstance(player_id, str) or not player_id:
        raise ValueError("expected Player ID must be a non-empty string")
    if not isinstance(player_name, str) or not player_name:
        raise ValueError("expected Player Name must be a non-empty string")
    if isinstance(age, bool) or not isinstance(age, int) or age <= 0:
        raise ValueError("expected Age must be a positive integer")
    return player_id, player_name, age


def _validate_squad_identity(
    raw: Mapping[str, Any],
    *,
    artifact: str,
    expected_team: Any | None,
) -> tuple[str, str, int, list[Any]]:
    team_name = _expect_string(raw["Team Name"], artifact, "$.Team Name")
    team_id = _expect_string(raw["Team ID"], artifact, "$.Team ID")
    total_players = _expect_int(raw["Total Players"], artifact, "$.Total Players")
    if total_players <= 0:
        raise ArtifactSchemaError(
            artifact, "$.Total Players", "must be a positive integer"
        )
    rows = _expect_list(raw["Players"], artifact, "$.Players")
    if len(rows) != total_players:
        raise ArtifactDomainError(
            artifact,
            "$.Total Players",
            f"must equal the Players array length {len(rows)}",
        )
    if expected_team is not None:
        expected_name, expected_id = _expected_team_values(expected_team)
        if team_name != expected_name:
            raise ArtifactDomainError(
                artifact, "$.Team Name", f"must equal {expected_name!r}"
            )
        if team_id != expected_id:
            raise ArtifactDomainError(
                artifact, "$.Team ID", f"must equal {expected_id!r}"
            )
    return team_name, team_id, total_players, rows


def _canonical_player_identity(
    identity: tuple[str, str, int],
) -> tuple[str, str, int]:
    """Normalize only the name for comparison without rewriting artifact text."""
    player_id, player_name, age = identity
    return player_id, normalize("NFC", player_name), age


def _enforce_source_identity(
    *,
    artifact: str,
    player_path: str,
    actual: tuple[str, str, int],
    expected: Mapping[str, Any],
) -> None:
    source = _expected_identity(expected)
    for field, actual_value, expected_value in zip(
        SOURCE_IDENTITY_KEYS,
        _canonical_player_identity(actual),
        _canonical_player_identity(source),
    ):
        if actual_value != expected_value:
            raise ArtifactDomainError(
                artifact,
                _path(player_path, field),
                f"must exactly match expected source value {expected_value!r}",
            )


def _nested_error(
    error: ArtifactContractError, *, artifact: str, player_path: str
) -> ArtifactContractError:
    nested_path = player_path if error.path == "$" else player_path + error.path[1:]
    return type(error)(artifact, nested_path, error.detail)


def _validate_profile_row(raw: Mapping[str, Any]) -> PlayerProfile:
    artifact = PLAYER_PROFILES_ARTIFACT
    raw = _expect_object(raw, artifact, "$")
    _expect_exact_keys(raw, PROFILE_KEYS, artifact, "$")
    player_id = _positive_player_id(raw["Player ID"], artifact, "$.Player ID")
    player_name = _expect_string(raw["Player Name"], artifact, "$.Player Name")
    age = _positive_age(raw["Age"], artifact, "$.Age")
    registered_position = _expect_enum(
        raw["Registered Position"], POSITIONS, artifact, "$.Registered Position"
    )

    familiarity_raw = _expect_object(
        raw["Position Familiarity"], artifact, "$.Position Familiarity"
    )
    if not familiarity_raw:
        raise ArtifactSchemaError(
            artifact, "$.Position Familiarity", "must contain at least one position"
        )
    familiarity: dict[str, int] = {}
    for position, value in familiarity_raw.items():
        position_path = _path("$.Position Familiarity", position)
        if position not in POSITIONS:
            raise ArtifactSchemaError(
                artifact,
                position_path,
                "position must be one of "
                + ", ".join(repr(item) for item in POSITIONS),
            )
        familiarity[position] = _bounded_int(value, 1, 2, artifact, position_path)
    if registered_position not in familiarity:
        raise ArtifactDomainError(
            artifact,
            "$.Position Familiarity",
            f"must include registered position {registered_position!r} at level 2",
        )
    if familiarity[registered_position] != 2:
        raise ArtifactDomainError(
            artifact,
            _path("$.Position Familiarity", registered_position),
            "registered position familiarity must equal 2",
        )

    stronger_foot = _expect_enum(
        raw["Stronger Foot"], STRONGER_FEET, artifact, "$.Stronger Foot"
    )
    playing_style = _optional_playing_style(
        raw["Playing Style"], registered_position, artifact, "$.Playing Style"
    )
    player_skills = _ordered_unique_enums(
        raw["Player Skills"], PLAYER_SKILLS, artifact, "$.Player Skills"
    )
    com_playing_styles = _ordered_unique_enums(
        raw["COM Playing Styles"],
        COM_PLAYING_STYLES,
        artifact,
        "$.COM Playing Styles",
    )
    return PlayerProfile(
        player_id=player_id,
        player_name=player_name,
        age=age,
        registered_position=registered_position,
        position_familiarity=familiarity,
        stronger_foot=stronger_foot,
        playing_style=playing_style,
        player_skills=player_skills,
        com_playing_styles=com_playing_styles,
    )


def validate_player_profiles(
    raw: Mapping[str, Any],
    *,
    expected_sources: Sequence[Mapping[str, Any]] | None = None,
    expected_team: Any | None = None,
) -> PlayerProfiles:
    "Validate Call 1, including exact authoritative roster coverage/order."

    artifact = PLAYER_PROFILES_ARTIFACT
    raw = _expect_object(raw, artifact, "$")
    schema_version = _validate_header(raw, artifact, SQUAD_KEYS)
    team_name, team_id, _total, rows = _validate_squad_identity(
        raw, artifact=artifact, expected_team=expected_team
    )

    expected = tuple(expected_sources) if expected_sources is not None else None
    if expected is not None:
        for source in expected:
            _expected_identity(source)
        if len(rows) != len(expected):
            raise ArtifactDomainError(
                artifact,
                "$.Players",
                f"must contain exactly {len(expected)} source players in source order",
            )

    players = []
    seen_ids = set()
    for index, item in enumerate(rows):
        player_path = _path("$.Players", index)
        try:
            player = _validate_profile_row(item)
        except ArtifactContractError as error:
            raise _nested_error(
                error, artifact=artifact, player_path=player_path
            ) from error
        if player.player_id in seen_ids:
            raise ArtifactDomainError(
                artifact,
                _path(player_path, "Player ID"),
                "duplicates another Players row",
            )
        seen_ids.add(player.player_id)
        if expected is not None:
            _enforce_source_identity(
                artifact=artifact,
                player_path=player_path,
                actual=(player.player_id, player.player_name, player.age),
                expected=expected[index],
            )
        players.append(player)
    return PlayerProfiles(schema_version, team_name, team_id, tuple(players))


def _validate_ability_row(
    raw: Mapping[str, Any], *, profile: PlayerProfile
) -> PlayerAbility:
    artifact = PLAYER_ABILITIES_ARTIFACT
    raw = _expect_object(raw, artifact, "$")
    # Elite Rationales is omissible, not nullable: an explicit null still fails
    # the object check below
    expected_keys = (
        ABILITY_KEYS if "Elite Rationales" in raw else _REQUIRED_ABILITY_KEYS
    )
    _expect_exact_keys(raw, expected_keys, artifact, "$")
    player_id = _positive_player_id(raw["Player ID"], artifact, "$.Player ID")
    player_name = _expect_string(raw["Player Name"], artifact, "$.Player Name")
    age = _positive_age(raw["Age"], artifact, "$.Age")
    expected_identity = (profile.player_id, profile.player_name, profile.age)
    for field, actual, expected in zip(
        SOURCE_IDENTITY_KEYS,
        _canonical_player_identity((player_id, player_name, age)),
        _canonical_player_identity(expected_identity),
    ):
        if actual != expected:
            raise ArtifactDomainError(
                artifact,
                _path("$", field),
                f"must equal frozen profile value {expected!r}",
            )

    abilities_raw = _expect_object(raw["Abilities"], artifact, "$.Abilities")
    _expect_exact_keys(abilities_raw, GENERAL_ABILITY_STATS, artifact, "$.Abilities")
    abilities = {
        name: _bounded_int(
            abilities_raw[name],
            GENERAL_ABILITY_MIN,
            GENERAL_ABILITY_MAX,
            artifact,
            _path("$.Abilities", name),
        )
        for name in GENERAL_ABILITY_STATS
    }
    if profile.registered_position != "GK":
        for stat_name in GK_STATS:
            if abilities[stat_name] != NON_GK_GOALKEEPER_ABILITY:
                raise ArtifactDomainError(
                    artifact,
                    _path("$.Abilities", stat_name),
                    f"must equal {NON_GK_GOALKEEPER_ABILITY} for the non-GK "
                    f"Registered Position {profile.registered_position!r}",
                )

    traits_raw = _expect_object(raw["Form and Traits"], artifact, "$.Form and Traits")
    _expect_exact_keys(traits_raw, FORM_AND_TRAIT_KEYS, artifact, "$.Form and Traits")
    traits = {
        "Weak Foot Usage": _bounded_int(
            traits_raw["Weak Foot Usage"],
            WEAK_FOOT_MIN,
            WEAK_FOOT_MAX,
            artifact,
            "$.Form and Traits.Weak Foot Usage",
        ),
        "Weak Foot Accuracy": _bounded_int(
            traits_raw["Weak Foot Accuracy"],
            WEAK_FOOT_MIN,
            WEAK_FOOT_MAX,
            artifact,
            "$.Form and Traits.Weak Foot Accuracy",
        ),
        "Conditioning": _bounded_int(
            traits_raw["Conditioning"],
            CONDITIONING_MIN,
            CONDITIONING_MAX,
            artifact,
            "$.Form and Traits.Conditioning",
        ),
        "Injury Resistance": _bounded_int(
            traits_raw["Injury Resistance"],
            INJURY_RESISTANCE_MIN,
            INJURY_RESISTANCE_MAX,
            artifact,
            "$.Form and Traits.Injury Resistance",
        ),
    }

    rationales_raw = _expect_object(
        raw.get("Elite Rationales", {}), artifact, "$.Elite Rationales"
    )
    rationales: dict[str, str] = {}
    for name, value in rationales_raw.items():
        rationale_path = _path("$.Elite Rationales", name)
        if name not in GENERAL_ABILITY_STATS:
            raise ArtifactSchemaError(
                artifact,
                rationale_path,
                "key must be a canonical general ability name",
            )
        rationales[name] = _expect_string(value, artifact, rationale_path)
    # A rating this high asserts a historically exceptional capability, so the
    # contract requires the evidence note rather than accepting a bare number
    for stat_name in GENERAL_ABILITY_STATS:
        if abilities[stat_name] >= ELITE_RATING_MIN and stat_name not in rationales:
            raise ArtifactDomainError(
                artifact,
                _path("$.Elite Rationales", stat_name),
                f"is required because {stat_name!r} is rated "
                f"{abilities[stat_name]}, at or above {ELITE_RATING_MIN}",
            )
    return PlayerAbility(
        player_id,
        player_name,
        age,
        abilities,
        traits,
        rationales,
    )


def validate_player_abilities(
    raw: Mapping[str, Any],
    *,
    profiles: PlayerProfiles,
) -> PlayerAbilities:
    "Validate Call 2 against the frozen, accepted Call 1 artifact."

    if not isinstance(profiles, PlayerProfiles):
        raise TypeError("profiles must be a validated PlayerProfiles artifact")
    profiles = validate_player_profiles(profiles.to_dict())
    artifact = PLAYER_ABILITIES_ARTIFACT
    raw = _expect_object(raw, artifact, "$")
    schema_version = _validate_header(raw, artifact, SQUAD_KEYS)
    team_name, team_id, _total, rows = _validate_squad_identity(
        raw,
        artifact=artifact,
        expected_team={"Team Name": profiles.team_name, "Team ID": profiles.team_id},
    )
    if len(rows) != len(profiles.players):
        raise ArtifactDomainError(
            artifact,
            "$.Players",
            f"must contain exactly {len(profiles.players)} frozen-profile players",
        )

    players = []
    seen_ids = set()
    for index, (item, profile) in enumerate(zip(rows, profiles.players)):
        player_path = _path("$.Players", index)
        try:
            player = _validate_ability_row(item, profile=profile)
        except ArtifactContractError as error:
            raise _nested_error(
                error, artifact=artifact, player_path=player_path
            ) from error
        if player.player_id in seen_ids:
            raise ArtifactDomainError(
                artifact,
                _path(player_path, "Player ID"),
                "duplicates another Players row",
            )
        seen_ids.add(player.player_id)
        players.append(player)
    return PlayerAbilities(schema_version, team_name, team_id, tuple(players))


def merge_player_artifacts(
    profiles: PlayerProfiles,
    abilities: PlayerAbilities,
    *,
    team_kind: str,
) -> PlayerAttributeTeam:
    "Merge the two accepted artifacts by their already-validated source order."

    if team_kind not in TEAM_KINDS:
        raise ValueError("team_kind must be Club or National")
    profiles = validate_player_profiles(profiles.to_dict())
    abilities = validate_player_abilities(abilities.to_dict(), profiles=profiles)
    players = tuple(
        PlayerAttributeRecord(
            player_id=profile.player_id,
            player_name=profile.player_name,
            age=profile.age,
            registered_position=profile.registered_position,
            position_familiarity=profile.position_familiarity,
            stronger_foot=profile.stronger_foot,
            playing_style=profile.playing_style,
            player_skills=profile.player_skills,
            com_playing_styles=profile.com_playing_styles,
            abilities=ability.abilities,
            form_and_traits=ability.form_and_traits,
            elite_rationales=ability.elite_rationales,
        )
        for profile, ability in zip(profiles.players, abilities.players)
    )
    return PlayerAttributeTeam(
        PLAYER_ATTRIBUTE_SCHEMA_VERSION,
        profiles.team_name,
        team_kind,
        profiles.team_id,
        players,
    )


def validate_player_attribute_team(raw: Mapping[str, Any]) -> PlayerAttributeTeam:
    "Validate a persisted internal merge by reconstructing both public calls."

    artifact = PLAYER_ATTRIBUTE_TEAM_ARTIFACT
    raw = _expect_object(raw, artifact, "$")
    schema_version = _validate_header(raw, artifact, MERGED_TEAM_KEYS)
    team_name = _expect_string(raw["Team Name"], artifact, "$.Team Name")
    team_kind = _expect_enum(raw["Team Kind"], TEAM_KINDS, artifact, "$.Team Kind")
    team_id = _expect_string(raw["Team ID"], artifact, "$.Team ID")
    total = _expect_int(raw["Total Players"], artifact, "$.Total Players")
    rows = _expect_list(raw["Players"], artifact, "$.Players")
    if total != len(rows) or total <= 0:
        raise ArtifactDomainError(
            artifact, "$.Total Players", "must equal the non-empty Players array length"
        )

    profile_rows = []
    ability_rows = []
    for index, item in enumerate(rows):
        player_path = _path("$.Players", index)
        item = _expect_object(item, artifact, player_path)
        # Machine-written by PlayerAttributeRecord.to_dict, so this artifact
        # always carries Elite Rationales and stays strict where Call 2 is not
        _expect_exact_keys(item, MERGED_PLAYER_KEYS, artifact, player_path)
        profile_rows.append({key: item[key] for key in PROFILE_KEYS})
        ability_rows.append({key: item[key] for key in ABILITY_KEYS})
    profiles = validate_player_profiles(
        {
            "Schema Version": schema_version,
            "Artifact": PLAYER_PROFILES_ARTIFACT,
            "Team Name": team_name,
            "Team ID": team_id,
            "Total Players": total,
            "Players": profile_rows,
        }
    )
    abilities = validate_player_abilities(
        {
            "Schema Version": schema_version,
            "Artifact": PLAYER_ABILITIES_ARTIFACT,
            "Team Name": team_name,
            "Team ID": team_id,
            "Total Players": total,
            "Players": ability_rows,
        },
        profiles=profiles,
    )
    return merge_player_artifacts(profiles, abilities, team_kind=team_kind)


__all__ = [
    "ABILITY_KEYS",
    "FORM_AND_TRAIT_KEYS",
    "MERGED_PLAYER_KEYS",
    "MERGED_TEAM_KEYS",
    "PROFILE_KEYS",
    "SOURCE_IDENTITY_KEYS",
    "SQUAD_KEYS",
    "PlayerAbilities",
    "PlayerAbility",
    "PlayerAttributeRecord",
    "PlayerAttributeTeam",
    "PlayerProfile",
    "PlayerProfiles",
    "merge_player_artifacts",
    "validate_player_abilities",
    "validate_player_attribute_team",
    "validate_player_profiles",
]
