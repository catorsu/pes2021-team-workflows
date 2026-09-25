"Deterministically assemble validated artifacts into compiler input."

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from .constants import PRESET_NAMES
from .errors import ArtifactDomainError


def assemble_semantic_game_plan(
    source_identity: Mapping[str, Any],
    xi_lock: Any,
    presets: Mapping[str, Any],
    bench: Any,
    *,
    preset_mode: str = "multi",
) -> dict[str, Any]:
    "Create the sole compiler input without retranscribing frozen artifacts."

    if preset_mode not in ("multi", "single"):
        raise ArtifactDomainError(
            "SemanticGamePlan",
            "$.PresetMode",
            "preset_mode must be exactly 'multi' or 'single'",
        )
    expected_presets = PRESET_NAMES if preset_mode == "multi" else ("Main",)
    if set(presets) != set(expected_presets):
        requirement = (
            "all three presets are required"
            if preset_mode == "multi"
            else "only the Main preset is required in single mode"
        )
        raise ArtifactDomainError("SemanticGamePlan", "$.Presets", requirement)
    squad = xi_lock.compiler_refs(source_identity) + bench.compiler_refs(
        source_identity
    )
    expected_count = int(source_identity["total_players"])
    if len(squad) != expected_count:
        raise ArtifactDomainError(
            "SemanticGamePlan",
            "$.Squad",
            f"assembled squad has {len(squad)} players; expected {expected_count}",
        )
    if preset_mode == "single":
        main = presets["Main"].to_compiler_dict(xi_lock, source_identity)
        compiled_presets = {name: copy.deepcopy(main) for name in PRESET_NAMES}
    else:
        compiled_presets = {
            name: presets[name].to_compiler_dict(xi_lock, source_identity)
            for name in PRESET_NAMES
        }
    return {
        "Team ID": str(source_identity["team_id"]),
        "Squad": squad,
        "Presets": compiled_presets,
    }
