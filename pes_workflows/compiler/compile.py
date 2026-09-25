"""Pure semantic game-plan compilation."""

import copy
from typing import Any

from pes_workflows.config import Config, resolve_global_auto_options

from .errors import SemanticGridError
from .mappings import _TOP_KEY_LOOKUP, TACTIC_KEYS
from .schema import (
    _canon_keys,
    _compile_squad,
    _rekey_presets,
    _strict_validate_semantic_plan_shape,
)
from .states import _compile_game_plan
from .tactics import _compile_tactics


def compile_semantic_game_plan(
    config: object,
    *,
    strict: bool = False,
    preset_mode: str = "multi",
    auto_substitutions: int = Config.DEFAULT_AUTO_SUBSTITUTIONS,
    auto_change_att_def: int = Config.DEFAULT_AUTO_CHANGE_ATT_DEF,
    auto_switch_preset_tactics: int | None = None,
) -> dict[str, Any]:
    """Compile and validate a semantic plan for CSV injection."""
    if preset_mode not in ("multi", "single"):
        raise SemanticGridError("preset_mode must be exactly 'multi' or 'single'.")
    try:
        global_auto_options = resolve_global_auto_options(
            preset_mode=preset_mode,
            auto_substitutions=auto_substitutions,
            auto_change_att_def=auto_change_att_def,
            auto_switch_preset_tactics=auto_switch_preset_tactics,
        )
    except ValueError as error:
        raise SemanticGridError(str(error)) from error
    if not isinstance(config, dict):
        raise SemanticGridError("The semantic game plan must be an object.")
    if strict:
        _strict_validate_semantic_plan_shape(config)
    top = _canon_keys(config, _TOP_KEY_LOOKUP, "Semantic game plan")
    missing = [key for key in _TOP_KEY_LOOKUP.values() if key not in top]
    if missing:
        raise SemanticGridError(
            "Semantic game plan: missing top-level field(s): "
            + ", ".join(missing)
            + "."
        )

    if not isinstance(top["Team ID"], str):
        raise SemanticGridError("Team ID must be a JSON string.")
    team_id = top["Team ID"].strip()
    if not team_id.isascii() or not team_id.isdigit() or int(team_id) <= 0:
        raise SemanticGridError(
            f"Team ID {top['Team ID']!r} is not a valid positive numeric team ID."
        )

    squad_ids, squad_names = _compile_squad(top)
    presets = _rekey_presets(top)
    if preset_mode == "single":
        presets = {tactic: copy.deepcopy(presets["S1"]) for tactic in TACTIC_KEYS}

    flat: dict[str, str] = {}
    state_entries = _compile_game_plan(presets, flat)
    state_positions: dict[str, dict[str, list[str]]] = {}
    for tactic, states in state_entries.items():
        state_positions[tactic] = {}
        for state, entries in states.items():
            state_positions[tactic][state] = [entry["pos_name"] for entry in entries]
    auto_offside_trap_settings, join_attack_settings, targeted = _compile_tactics(
        presets,
        flat,
        squad_ids,
        squad_names,
        state_positions,
        global_auto_options,
    )
    main_normal_entries = state_entries["S1"]["F1"]

    return {
        "team_id": team_id,
        "flat_columns": flat,
        "squad_ids": squad_ids,
        "squad_names": squad_names,
        "main_normal_entries": main_normal_entries,
        "state_entries": state_entries,
        "auto_offside_trap_settings": auto_offside_trap_settings,
        "join_attack_settings": join_attack_settings,
        "targeted_instructions": targeted,
        "matchday_count": len(squad_ids),
    }
