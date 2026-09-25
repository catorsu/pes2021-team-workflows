"Queries over the authoritative source-player identity mapping."

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import ArtifactDomainError


def _source_name(source_identity: Mapping[str, Any], player_id: str) -> str:
    name = source_identity["players"].get(player_id)
    if name is None:
        raise ArtifactDomainError(
            "Artifact", "$.Player ID", f"unknown source Player ID {player_id!r}"
        )
    return name
