"""Position eligibility at generated-artifact and saved-plan boundaries."""

import unittest
from itertools import product

from pes_workflows.compiler.compile import compile_semantic_game_plan
from pes_workflows.compiler.errors import SemanticGridError
from pes_workflows.contracts.errors import ArtifactDomainError
from pes_workflows.contracts.preset import validate_preset_plan
from pes_workflows.contracts.strategy import validate_starting_xi_lock
from tests.match_fixtures import preset_raw, source_identity, strategy_raw
from tests.test_formation_contract_v2 import _plan


class TacticalPositionValidationTests(unittest.TestCase):
    def test_generated_presets_reject_ineligible_targets_in_each_state(self) -> None:
        source = source_identity()
        xi = validate_starting_xi_lock(strategy_raw(), source)
        cases = (
            ("Counter Target", "Defending 1", "CB"),
            ("Defensive", "Attacking 1", "CF"),
            ("Defensive", "Attacking 1", "SS"),
        )
        for preset, state, case in product(
            ("Main", "Defensive", "Custom"),
            ("Normal", "With Ball", "Without Ball"),
            cases,
        ):
            instruction, instruction_slot, position = case
            with self.subTest(
                preset=preset, state=state, instruction=instruction, position=position
            ):
                raw = preset_raw(preset)
                raw["Advanced Instructions"][instruction_slot] = {
                    "Instruction": instruction,
                    "Designated Slot": 7,
                }
                raw["States"][state][7]["Position"] = position
                with self.assertRaisesRegex(
                    ArtifactDomainError, f"{state} Position {position}"
                ):
                    validate_preset_plan(raw, preset, xi)

    def test_saved_plans_reject_ineligible_targets_in_each_state(self) -> None:
        cases = (
            ("Counter Target", "Defending 1", "CB"),
            ("Defensive", "Attacking 1", "CF"),
            ("Defensive", "Attacking 1", "SS"),
        )
        for preset, state, strict, case in product(
            ("Main", "Defensive", "Custom"),
            ("Normal", "With Ball", "Without Ball"),
            (False, True),
            cases,
        ):
            instruction, instruction_slot, position = case
            with self.subTest(
                preset=preset, state=state, strict=strict, position=position
            ):
                plan = _plan()
                selected = plan["Presets"][preset]
                for rows in selected["States"].values():
                    rows[1]["Position"] = "AMF"
                selected["States"][state][1]["Position"] = position
                selected["Advanced Instructions"][instruction_slot] = {
                    "Instruction": instruction,
                    "Designated Player": {"Player ID": "2", "Player": "Player 2"},
                }
                with self.assertRaisesRegex(
                    SemanticGridError, f"{state} Position {position}"
                ):
                    compile_semantic_game_plan(plan, strict=strict)

    def test_valid_target_positions_survive_both_boundaries(self) -> None:
        source = source_identity()
        xi = validate_starting_xi_lock(strategy_raw(), source)
        cases = (
            ("Counter Target", "Defending 1", "AMF"),
            ("Counter Target", "Defending 1", "CF"),
            ("Defensive", "Attacking 1", "DMF"),
            ("Defensive", "Attacking 1", "LB"),
            ("Anchoring", "Attacking 1", "CB"),
            ("Anchoring", "Attacking 1", "CF"),
        )
        for instruction, instruction_slot, position in cases:
            with self.subTest(instruction=instruction, position=position):
                raw = preset_raw("Main")
                for rows in raw["States"].values():
                    rows[7]["Position"] = position
                raw["Advanced Instructions"][instruction_slot] = {
                    "Instruction": instruction,
                    "Designated Slot": 7,
                }
                preset = validate_preset_plan(raw, "Main", xi)
                plan = _plan()
                plan["Presets"]["Main"] = preset.to_compiler_dict(xi, source)
                compiled = compile_semantic_game_plan(
                    plan, strict=True, preset_mode="single"
                )
                self.assertEqual(len(compiled["targeted_instructions"]), 3)
