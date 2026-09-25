from __future__ import annotations

import copy
import itertools
import unittest
from typing import Any
from unittest import mock

from pes_workflows.compiler.compile import compile_semantic_game_plan
from pes_workflows.compiler.errors import SemanticGridError
from pes_workflows.compiler.geometry import (  # noqa: E402
    EDITOR_X_MAX,
    EDITOR_X_MIN,
    EDITOR_Y_MAX,
    EDITOR_Y_MIN,
    GK_ANCHOR_XY_M,
    LANE_ORDER,
    LANE_Y_M,
    MIN_EDITOR_Y_GAP,
    MIN_LATERAL_GAP_M,
    PITCH_LENGTH_M,
    PITCH_WIDTH_M,
    ROW_X_M,
    X_LEGAL_MAX,
    X_LEGAL_MIN,
    Y_LEGAL_MAX,
    Y_LEGAL_MIN,
    _convert_to_editor,
    _spread_chain,
    _validate_state_invariants,
    _validate_static_grid_definition,
)
from pes_workflows.compiler.mappings import TACTIC_KEYS  # noqa: E402
from pes_workflows.contracts.assembly import assemble_semantic_game_plan  # noqa: E402
from pes_workflows.contracts.errors import ArtifactDomainError  # noqa: E402


def _basic_instructions() -> dict[str, Any]:
    return {
        "Attacking Style": "Possession Game",
        "Build Up": "Short-pass",
        "Attacking Area": "Center",
        "Positioning": "Maintain Formation",
        "Support Range": "Level 5",
        "Numbers in Attack": "Medium",
        "Defensive Style": "All-out Defence",
        "Containment Area": "Center",
        "Pressuring": "Conservative",
        "Defensive Line": "Level 5",
        "Compactness": "Level 5",
        "Numbers in Defence": "Medium",
    }


def _state() -> list[dict[str, Any]]:
    lanes = (
        "L_Wing",
        "L_Half",
        "L_Center",
        "C_Center",
        "R_Center",
        "R_Half",
        "R_Wing",
    )
    rows = [{"Slot": 0, "Position": "GK", "Grid Assignment": "GK_Anchor"}]
    for slot in range(1, 11):
        rows.append(
            {
                "Slot": slot,
                "Position": "CB",
                "Grid Assignment": f"Row 3 - {lanes[(slot - 1) % len(lanes)]}",
            }
        )
    return rows


def _plan() -> dict[str, Any]:
    advanced = {
        slot: {"Instruction": "Blank", "Designated Player": None}
        for slot in ("Attacking 1", "Attacking 2", "Defending 1", "Defending 2")
    }
    preset = {
        "Auto Offside Trap": "Off",
        "Players to Join Attack": [],
        "Basic Instructions": _basic_instructions(),
        "Advanced Instructions": advanced,
        "States": {
            "Normal": _state(),
            "With Ball": _state(),
            "Without Ball": _state(),
        },
    }
    return {
        "Team ID": "1",
        "Squad": [
            {"Player ID": str(slot + 1), "Player": f"Player {slot + 1}"}
            for slot in range(11)
        ],
        "Presets": {
            "Main": copy.deepcopy(preset),
            "Defensive": copy.deepcopy(preset),
            "Custom": copy.deepcopy(preset),
        },
    }


class ContractV2CompilerTests(unittest.TestCase):
    def test_strict_canonical_plan_compiles(self) -> None:
        compiled = compile_semantic_game_plan(_plan(), strict=True)
        self.assertEqual(compiled["team_id"], "1")
        self.assertEqual(compiled["matchday_count"], 11)
        self.assertEqual(compiled["flat_columns"]["Header1"], "255")
        self.assertEqual(compiled["flat_columns"]["Header2"], "255")
        self.assertEqual(compiled["flat_columns"]["Header3"], "255")
        self.assertEqual(compiled["flat_columns"]["OffsideTrap"], "0")
        self.assertEqual(
            compiled["auto_offside_trap_settings"],
            {key: "Off" for key in TACTIC_KEYS},
        )

    def test_single_mode_mirrors_main(self) -> None:
        plan = _plan()
        plan["Presets"]["Defensive"]["Basic Instructions"]["Support Range"] = "Level 2"
        plan["Presets"]["Defensive"]["Auto Offside Trap"] = "On"
        plan["Presets"]["Custom"]["States"]["Normal"][1]["Grid Assignment"] = (
            "Row 5 - L_Wing"
        )

        default_multi = compile_semantic_game_plan(plan, strict=True)
        explicit_multi = compile_semantic_game_plan(
            plan, strict=True, preset_mode="multi"
        )
        single = compile_semantic_game_plan(plan, strict=True, preset_mode="single")

        self.assertEqual(default_multi, explicit_multi)
        self.assertEqual(single["flat_columns"]["OffsideTrap"], "0")
        self.assertNotEqual(
            default_multi["flat_columns"]["SupportRangeS1"],
            default_multi["flat_columns"]["SupportRangeS2"],
        )
        self.assertEqual(
            single["auto_offside_trap_settings"],
            {key: "Off" for key in TACTIC_KEYS},
        )
        for main_column, value in single["flat_columns"].items():
            if not main_column.endswith("S1"):
                continue
            prefix = main_column[:-2]
            self.assertEqual(single["flat_columns"][prefix + "S2"], value)
            self.assertEqual(single["flat_columns"][prefix + "S3"], value)
        self.assertEqual(
            plan["Presets"]["Defensive"]["Basic Instructions"]["Support Range"],
            "Level 2",
        )

    def test_global_auto_options_emit_every_valid_combination_in_both_modes(
        self,
    ) -> None:
        for mode, substitutions, att_def, switch in itertools.product(
            ("single", "multi"), range(4), range(2), range(2)
        ):
            with self.subTest(mode=mode, values=(substitutions, att_def, switch)):
                flat = compile_semantic_game_plan(
                    _plan(),
                    strict=True,
                    preset_mode=mode,
                    auto_substitutions=substitutions,
                    auto_change_att_def=att_def,
                    auto_switch_preset_tactics=switch,
                )["flat_columns"]
                self.assertEqual(flat["AutoSubstitutions"], str(substitutions))
                self.assertEqual(flat["AutoChangeAttDef"], str(att_def))
                self.assertEqual(flat["SwitchTactics"], str(switch))

    def test_omitted_global_auto_options_keep_legacy_defaults(self) -> None:
        for mode, switch in (("single", "0"), ("multi", "1")):
            flat = compile_semantic_game_plan(_plan(), preset_mode=mode)["flat_columns"]
            self.assertEqual(flat["AutoSubstitutions"], "2")
            self.assertEqual(flat["AutoChangeAttDef"], "0")
            self.assertEqual(flat["SwitchTactics"], switch)

    def test_invalid_global_auto_options_are_rejected(self) -> None:
        for key, upper in (
            ("auto_substitutions", 4),
            ("auto_change_att_def", 2),
            ("auto_switch_preset_tactics", 2),
        ):
            for value in (-1, upper, True, False, 1.0, "1"):
                with (
                    self.subTest(key=key, value=value),
                    self.assertRaisesRegex(SemanticGridError, key),
                ):
                    compile_semantic_game_plan(_plan(), **{key: value})

    def test_all_modes_compile_main_offside_trap_into_global_column(self) -> None:
        plan = _plan()
        plan["Presets"]["Main"]["Auto Offside Trap"] = "On"

        default_multi = compile_semantic_game_plan(plan, strict=True)
        explicit_multi = compile_semantic_game_plan(
            plan, strict=True, preset_mode="multi"
        )
        single = compile_semantic_game_plan(plan, strict=True, preset_mode="single")

        self.assertEqual(default_multi, explicit_multi)
        self.assertEqual(default_multi["flat_columns"]["OffsideTrap"], "1")
        self.assertEqual(single["flat_columns"]["OffsideTrap"], "1")
        self.assertEqual(
            single["auto_offside_trap_settings"],
            {key: "On" for key in TACTIC_KEYS},
        )
        for column in ("Header1", "Header2", "Header3"):
            self.assertEqual(default_multi["flat_columns"][column], "255")
            self.assertEqual(single["flat_columns"][column], "255")

    def test_invalid_compiler_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            SemanticGridError, "preset_mode must be exactly 'multi' or 'single'"
        ):
            compile_semantic_game_plan(_plan(), preset_mode="switch_off")

    def test_single_mode_assembly_expands_only_main_without_aliasing(self) -> None:
        plan = _plan()
        xi_lock = mock.Mock()
        xi_lock.compiler_refs.return_value = copy.deepcopy(plan["Squad"])
        bench = mock.Mock()
        bench.compiler_refs.return_value = []
        main = mock.Mock()
        main.to_compiler_dict.return_value = copy.deepcopy(plan["Presets"]["Main"])

        assembled = assemble_semantic_game_plan(
            {"team_id": "1", "total_players": 11},
            xi_lock,
            {"Main": main},
            bench,
            preset_mode="single",
        )

        self.assertEqual(set(assembled), {"Team ID", "Squad", "Presets"})
        self.assertEqual(set(assembled["Presets"]), {"Main", "Defensive", "Custom"})
        self.assertEqual(
            assembled["Presets"]["Main"], assembled["Presets"]["Defensive"]
        )
        self.assertEqual(assembled["Presets"]["Main"], assembled["Presets"]["Custom"])
        assembled["Presets"]["Defensive"]["Auto Offside Trap"] = "On"
        self.assertEqual(assembled["Presets"]["Main"]["Auto Offside Trap"], "Off")
        compile_semantic_game_plan(
            assembled,
            strict=True,
            preset_mode="single",
        )

        with self.assertRaisesRegex(
            ArtifactDomainError, "only the Main preset is required in single mode"
        ):
            assemble_semantic_game_plan(
                {"team_id": "1", "total_players": 11},
                xi_lock,
                {"Main": main, "Defensive": main},
                bench,
                preset_mode="single",
            )

    def test_a_non_canonical_alias_is_tolerated_only_outside_strict_mode(self) -> None:
        plan = _plan()
        plan["team id"] = plan.pop("Team ID")
        self.assertEqual(compile_semantic_game_plan(plan)["team_id"], "1")
        with self.assertRaisesRegex(SemanticGridError, "non-canonical"):
            compile_semantic_game_plan(plan, strict=True)

    def test_non_canonical_global_and_preset_settings_are_rejected(self) -> None:
        plan = _plan()
        plan["Players to Join Attack"] = []
        with self.assertRaisesRegex(SemanticGridError, "unexpected/non-canonical"):
            compile_semantic_game_plan(plan, strict=True)

        plan = _plan()
        main = plan["Presets"]["Main"]
        main["Offside Trap"] = main.pop("Auto Offside Trap")
        with self.assertRaisesRegex(SemanticGridError, "unexpected/non-canonical"):
            compile_semantic_game_plan(plan, strict=True)

    def test_join_attack_is_independent_and_accepts_outfielders_in_each_preset(
        self,
    ) -> None:
        plan = _plan()
        plan["Presets"]["Main"]["Players to Join Attack"] = [
            {"Player ID": "2", "Player": "Player 2"}
        ]
        plan["Presets"]["Custom"]["Players to Join Attack"] = [
            {"Player ID": "3", "Player": "Player 3"}
        ]
        plan["Presets"]["Custom"]["States"]["Normal"][2]["Position"] = "CF"

        compiled = compile_semantic_game_plan(plan, strict=True)

        self.assertEqual(
            compiled["join_attack_settings"]["S1"],
            [{"Player ID": "2", "Player": "Player 2"}],
        )
        self.assertEqual(
            compiled["join_attack_settings"]["S3"],
            [{"Player ID": "3", "Player": "Player 3"}],
        )

    def test_join_attack_rejects_the_goalkeeper(self) -> None:
        plan = _plan()
        plan["Presets"]["Custom"]["Players to Join Attack"] = [
            {"Player ID": "1", "Player": "Player 1"}
        ]

        with self.assertRaisesRegex(
            SemanticGridError,
            "the goalkeeper cannot be selected for Players to Join Attack",
        ):
            compile_semantic_game_plan(plan, strict=True)

    def test_counter_target_accepts_midfielder_but_not_the_goalkeeper(self) -> None:
        plan = _plan()
        main = plan["Presets"]["Main"]
        main["States"]["Normal"][1]["Position"] = "AMF"
        main["States"]["With Ball"][1]["Position"] = "AMF"
        main["States"]["Without Ball"][1]["Position"] = "AMF"
        main["Advanced Instructions"]["Defending 1"] = {
            "Instruction": "Counter Target",
            "Designated Player": {"Player ID": "2", "Player": "Player 2"},
        }

        compiled = compile_semantic_game_plan(plan, strict=True)
        self.assertEqual(compiled["main_normal_entries"][1]["pos_name"], "AMF")
        self.assertTrue(
            any(
                row.instruction.label == "Counter Target" and row.player_id == "2"
                for row in compiled["targeted_instructions"]
            )
        )

        main["Advanced Instructions"]["Defending 1"]["Designated Player"] = {
            "Player ID": "1",
            "Player": "Player 1",
        }
        with self.assertRaisesRegex(SemanticGridError, "goalkeeper cannot be"):
            compile_semantic_game_plan(plan, strict=True)

    def test_rows_one_through_nine_span_the_documented_pitch_depth(self) -> None:
        plan = _plan()
        main_normal = plan["Presets"]["Main"]["States"]["Normal"]
        for slot, row in enumerate(range(1, 10), start=1):
            main_normal[slot]["Grid Assignment"] = f"Row {row} - C_Center"

        compiled = compile_semantic_game_plan(plan, strict=True)

        expected_editor_x = {
            1: 6,
            2: 11,
            3: 16,
            4: 21,
            5: 26,
            6: 31,
            7: 36,
            8: 41,
            9: 46,
        }
        for slot, row in enumerate(range(1, 10), start=1):
            self.assertEqual(
                compiled["flat_columns"][f"LocationX{slot + 1}F1S1"],
                str(expected_editor_x[row]),
            )

    def test_static_grid_is_symmetric_and_projects_inside_both_envelopes(self) -> None:
        _validate_static_grid_definition()

        self.assertEqual(
            ROW_X_M,
            {
                1: 12.5,
                2: 22.5,
                3: 32.5,
                4: 42.5,
                5: 52.5,
                6: 62.5,
                7: 72.5,
                8: 82.5,
                9: 92.5,
            },
        )
        self.assertEqual(
            LANE_Y_M,
            {
                "L_Wing": 7.0,
                "L_Half": 19.0,
                "L_Center": 27.5,
                "C_Center": 34.0,
                "R_Center": 40.5,
                "R_Half": 49.0,
                "R_Wing": 61.0,
            },
        )
        self.assertEqual(list(LANE_Y_M), LANE_ORDER)
        self.assertEqual(GK_ANCHOR_XY_M, (X_LEGAL_MIN, PITCH_WIDTH_M / 2))
        self.assertEqual(ROW_X_M[5], PITCH_LENGTH_M / 2)
        self.assertTrue(
            all(
                right - left == 10.0
                for left, right in zip(ROW_X_M.values(), list(ROW_X_M.values())[1:])
            )
        )
        for row in range(1, 5):
            self.assertEqual(ROW_X_M[row] + ROW_X_M[10 - row], PITCH_LENGTH_M)
        for left, right in zip(LANE_ORDER, reversed(LANE_ORDER)):
            self.assertEqual(LANE_Y_M[left] + LANE_Y_M[right], PITCH_WIDTH_M)

        physical_points = [GK_ANCHOR_XY_M]
        physical_points.extend(
            (x_m, y_m) for x_m in ROW_X_M.values() for y_m in LANE_Y_M.values()
        )
        for x_m, y_m in physical_points:
            with self.subTest(x_m=x_m, y_m=y_m):
                self.assertTrue(X_LEGAL_MIN <= x_m <= X_LEGAL_MAX)
                self.assertTrue(Y_LEGAL_MIN <= y_m <= Y_LEGAL_MAX)
                x_editor, y_editor = _convert_to_editor(x_m, y_m, "test grid")
                self.assertTrue(EDITOR_X_MIN <= x_editor <= EDITOR_X_MAX)
                self.assertTrue(EDITOR_Y_MIN <= y_editor <= EDITOR_Y_MAX)

        lane_editor_y = [
            _convert_to_editor(ROW_X_M[5], LANE_Y_M[lane], lane)[1]
            for lane in LANE_ORDER
        ]
        self.assertEqual(lane_editor_y, [11, 29, 42, 52, 62, 75, 93])
        self.assertTrue(
            all(
                right - left >= MIN_EDITOR_Y_GAP
                for left, right in zip(lane_editor_y, lane_editor_y[1:])
            )
        )

    def test_physical_envelope_boundaries_are_inclusive_and_enforced(self) -> None:
        expected_corners = {
            (X_LEGAL_MIN, Y_LEGAL_MIN): (3, 11),
            (X_LEGAL_MIN, Y_LEGAL_MAX): (3, 93),
            (X_LEGAL_MAX, Y_LEGAL_MIN): (46, 11),
            (X_LEGAL_MAX, Y_LEGAL_MAX): (46, 93),
        }
        for physical, editor in expected_corners.items():
            with self.subTest(physical=physical):
                self.assertEqual(_convert_to_editor(*physical, "boundary"), editor)

        for physical in (
            (X_LEGAL_MIN - 0.1, 34.0),
            (X_LEGAL_MAX + 0.1, 34.0),
            (52.5, Y_LEGAL_MIN - 0.1),
            (52.5, Y_LEGAL_MAX + 0.1),
        ):
            with self.subTest(physical=physical):
                with self.assertRaisesRegex(SemanticGridError, "physical coordinates"):
                    _convert_to_editor(*physical, "outside boundary")

    def test_state_invariants_reject_subminimum_same_row_physical_gap(self) -> None:
        entries = [
            {"kind": "gk", "slot": 0, "x": 6.0, "y": 34.0},
            {"kind": "grid", "slot": 1, "row": 3, "x": 32.5, "y": 34.0},
            {"kind": "grid", "slot": 2, "row": 3, "x": 32.5, "y": 36.9},
        ]

        with self.assertRaisesRegex(SemanticGridError, "only 2.9 m apart"):
            _validate_state_invariants(entries, "test state")

    def test_row_ten_is_rejected_in_strict_and_tolerant_compilation(self) -> None:
        for strict in (False, True):
            with self.subTest(strict=strict):
                plan = _plan()
                plan["Presets"]["Main"]["States"]["Normal"][1]["Grid Assignment"] = (
                    "Row 10 - C_Center"
                )
                with self.assertRaisesRegex(SemanticGridError, "Row 1-9"):
                    compile_semantic_game_plan(plan, strict=strict)

    def test_duplicate_cell_spreading_is_deterministic(self) -> None:
        self.assertEqual(_spread_chain([34, 34], 3, 7, 61), [32.5, 35.5])

        resolved = _spread_chain([7.0] * 10, 3.0, 7.0, 61.0)
        self.assertIsNotNone(resolved)
        self.assertGreaterEqual(resolved[0], Y_LEGAL_MIN)
        self.assertLessEqual(resolved[-1], Y_LEGAL_MAX)
        for left, right in zip(resolved, resolved[1:]):
            self.assertGreaterEqual(right - left, MIN_LATERAL_GAP_M)
            left_editor = _convert_to_editor(ROW_X_M[3], left, "left collision")[1]
            right_editor = _convert_to_editor(ROW_X_M[3], right, "right collision")[1]
            self.assertGreaterEqual(right_editor - left_editor, MIN_EDITOR_Y_GAP)


if __name__ == "__main__":
    unittest.main()
