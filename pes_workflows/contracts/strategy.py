"StartingXILock model and validator."

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .errors import ArtifactDomainError, ArtifactSchemaError
from .identity import _source_name
from .json_codec import (
    _expect_int,
    _expect_list,
    _expect_object,
    _expect_ordered_keys,
    _expect_string,
    _path,
    _validate_common,
)


@dataclass(frozen=True, slots=True)
class XiSlot:
    slot: int
    player_id: str


@dataclass(frozen=True, slots=True)
class StartingXILock:
    team_id: str
    starting_xi: tuple[XiSlot, ...]
    _raw: Mapping[str, Any]

    def to_model_dict(self) -> dict[str, Any]:
        return copy.deepcopy(dict(self._raw))

    def compiler_refs(self, source_identity: Mapping[str, Any]) -> list[dict[str, str]]:
        return [
            {
                "Player ID": item.player_id,
                "Player": _source_name(source_identity, item.player_id),
            }
            for item in self.starting_xi
        ]


def validate_starting_xi_lock(
    raw: Mapping[str, Any], source_identity: Mapping[str, Any]
) -> StartingXILock:
    artifact = "StartingXILock"
    raw = _expect_object(raw, artifact, "$")
    keys = (
        "Schema Version",
        "Artifact",
        "Team ID",
        "Starting XI",
    )
    _validate_common(raw, artifact, keys)
    team_id = _expect_string(raw["Team ID"], artifact, "$.Team ID")
    if team_id != str(source_identity["team_id"]):
        raise ArtifactDomainError(
            artifact,
            "$.Team ID",
            f"does not match PLAYER_RECORDS Team ID {source_identity['team_id']!r}",
        )

    xi_rows = _expect_list(raw["Starting XI"], artifact, "$.Starting XI")
    if len(xi_rows) != 11:
        raise ArtifactSchemaError(
            artifact, "$.Starting XI", "must contain exactly 11 rows"
        )
    xi: list[XiSlot] = []
    seen_ids = set()
    for index, item in enumerate(xi_rows):
        path = _path("$.Starting XI", index)
        row = _expect_object(item, artifact, path)
        _expect_ordered_keys(row, ("Slot", "Player ID"), artifact, path)
        slot = _expect_int(row["Slot"], artifact, _path(path, "Slot"))
        if slot != index:
            raise ArtifactSchemaError(
                artifact, _path(path, "Slot"), f"must equal {index}"
            )
        player_id = _expect_string(row["Player ID"], artifact, _path(path, "Player ID"))
        if player_id not in source_identity["players"]:
            raise ArtifactDomainError(
                artifact, _path(path, "Player ID"), "is not in PLAYER_RECORDS"
            )
        if player_id in seen_ids:
            raise ArtifactDomainError(
                artifact,
                _path(path, "Player ID"),
                "duplicates another Starting XI player",
            )
        seen_ids.add(player_id)
        xi.append(XiSlot(slot, player_id))

    goalkeeper_familiarity = source_identity["familiarity"].get(xi[0].player_id, {})
    if not any("GK" in goalkeeper_familiarity.get(level, ()) for level in ("L2", "L1")):
        raise ArtifactDomainError(
            artifact,
            "$.Starting XI[0].Player ID",
            "Slot 0 must have Level 1 or Level 2 familiarity at GK",
        )
    for item in xi[1:]:
        if source_identity["registered_positions"].get(item.player_id) == "GK":
            raise ArtifactDomainError(
                artifact,
                f"$.Starting XI[{item.slot}].Player ID",
                "Slots 1..10 must be outfield identities, not registered goalkeepers",
            )

    return StartingXILock(
        team_id=team_id,
        starting_xi=tuple(xi),
        _raw=MappingProxyType(copy.deepcopy(dict(raw))),
    )
