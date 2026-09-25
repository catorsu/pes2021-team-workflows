"BenchDecision model and Contract 2.2 validator."

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .errors import ArtifactDomainError, ArtifactSchemaError
from .identity import _source_name
from .json_codec import (
    _expect_list,
    _expect_object,
    _expect_ordered_keys,
    _expect_string,
    _path,
    _validate_common,
)


@dataclass(frozen=True, slots=True)
class BenchSelection:
    player_id: str


@dataclass(frozen=True, slots=True)
class BenchDecision:
    selections: tuple[BenchSelection, ...]
    _raw: Mapping[str, Any]

    def to_model_dict(self) -> dict[str, Any]:
        return copy.deepcopy(dict(self._raw))

    def compiler_refs(self, source_identity: Mapping[str, Any]) -> list[dict[str, str]]:
        return [
            {
                "Player ID": item.player_id,
                "Player": _source_name(source_identity, item.player_id),
            }
            for item in self.selections
        ]


def validate_bench_decision(
    raw: Mapping[str, Any],
    xi_lock: Any,
    source_identity: Mapping[str, Any],
) -> BenchDecision:
    artifact = "BenchDecision"
    raw = _expect_object(raw, artifact, "$")
    keys = (
        "Schema Version",
        "Artifact",
        "Substitutes",
    )
    schema_version = _validate_common(raw, artifact, keys)
    xi_schema_version = xi_lock._raw["Schema Version"]
    if schema_version != xi_schema_version:
        raise ArtifactDomainError(
            artifact,
            "$.Schema Version",
            f"must match StartingXILock Schema Version {xi_schema_version!r}",
        )

    rows = _expect_list(raw["Substitutes"], artifact, "$.Substitutes")
    expected_count = int(source_identity["total_players"]) - 11
    if len(rows) != expected_count:
        raise ArtifactSchemaError(
            artifact,
            "$.Substitutes",
            f"must contain exactly {expected_count} substitutes",
        )
    starter_ids = {item.player_id for item in xi_lock.starting_xi}
    seen = set()
    selections: list[BenchSelection] = []
    for index, item in enumerate(rows):
        path = _path("$.Substitutes", index)
        row = _expect_object(item, artifact, path)
        _expect_ordered_keys(row, ("Player ID",), artifact, path)
        player_id = _expect_string(row["Player ID"], artifact, _path(path, "Player ID"))
        if player_id not in source_identity["players"]:
            raise ArtifactDomainError(
                artifact, _path(path, "Player ID"), "is not in PLAYER_RECORDS"
            )
        if player_id in starter_ids:
            raise ArtifactDomainError(
                artifact, _path(path, "Player ID"), "is already in the Starting XI"
            )
        if player_id in seen:
            raise ArtifactDomainError(
                artifact,
                _path(path, "Player ID"),
                "duplicates another substitute",
            )
        seen.add(player_id)
        selections.append(BenchSelection(player_id))

    return BenchDecision(
        tuple(selections),
        MappingProxyType(copy.deepcopy(dict(raw))),
    )
