from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import itertools
import json
import logging
import os
import shutil
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from pes_workflows import batch_generate_match_plans as batch
from pes_workflows import checkpoint_io, claude_cli
from pes_workflows import generate_match_plan as single
from pes_workflows.config import parse_workflow_args
from pes_workflows.contracts.bench import BenchDecision, validate_bench_decision
from pes_workflows.contracts.errors import ArtifactDomainError, ArtifactSchemaError
from pes_workflows.contracts.strategy import validate_starting_xi_lock
from pes_workflows.domain.csv_schema import FORMATION_ROSTER_SIZE
from pes_workflows.players.generator import (
    PlayerRecordsGenerationError,
    PlayerRecordsGenerator,
)
from tests.attribute_fixtures import make_targets, write_attribute_targets_csv
from tests.match_fixtures import (
    FakeClient,
    SingleModeFakeClient,
    fixture_player_records,
    source_identity,
    strategy_raw,
)


def compact_bench(*ids: Any) -> dict[str, Any]:
    return {
        "Schema Version": "2.2",
        "Artifact": "BenchDecision",
        "Substitutes": [{"Player ID": player_id} for player_id in ids],
    }


class ScopedMatchPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.sources = argparse.Namespace(
            players_csv=self.root / "Players.csv",
            teams_players_csv=self.root / "Teams-Players.csv",
            rosters_csv=self.root / "Rosters.csv",
        )
        (self.root / "Formations.csv").write_text("Id\n77\n")
        players = write_attribute_targets_csv(
            self.root / "Players.csv", make_targets(12)
        )
        with players.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        for index, row in enumerate(rows):
            row.update(Height="180", Weight="75", POS="0" if index == 0 else "1")
            row["GK" if index == 0 else "CB"] = "2"
        rows.extend([{**rows[-1], "Id": "bad"}, {**rows[-1], "Id": "999"}] * 2)
        self.write_csv(players, rows)
        self.root.joinpath("Teams-Players.csv").write_text(
            "Id;Name;Id Club;Club;Id National;National\n"
            "101;Player 1;77;Selected*;0;\n"
            "101;Player 1;88;Selected**;0;\n"
            "999;Broken;99;Broken|Name;0;\n"
            "bad;Broken;bad;;0;\n"
        )
        roster = {"Id": "77", "TotalPlayers": "12"}
        roster.update(
            {
                f"Player{i}": str(100 + i) if i <= 12 else "0"
                for i in range(1, FORMATION_ROSTER_SIZE + 1)
            }
        )
        self.write_csv(
            self.root / "Rosters.csv",
            [
                roster,
                {**roster, "Id": "88"},
                {**roster, "Id": "99", "Player1": "malformed"},
            ],
        )

    @staticmethod
    def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

    def test_single_and_batch_select_before_validation(self) -> None:
        cases = [
            (single, ["--team", "77"], ["77"]),
            (single, ["--team", "Selected*"], ["77"]),
            (batch, ["--team", "77", "--check-only"], ["77"]),
            (batch, ["--team", "Selected*"], ["77"]),
            (
                batch,
                [
                    "--team",
                    "77",
                    "--team",
                    "Selected**",
                    "--team",
                    "77",
                    "--check-only",
                ],
                ["77", "88"],
            ),
        ]
        for module, selectors, expected in cases:
            with (
                self.subTest(module=module.__name__, selectors=selectors),
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "script",
                        "--players-csv",
                        str(self.root / "Players.csv"),
                        "--teams-players-csv",
                        str(self.root / "Teams-Players.csv"),
                        "--rosters-csv",
                        str(self.root / "Rosters.csv"),
                        "--formations-csv",
                        str(self.root / "Formations.csv"),
                        "--output-dir",
                        str(self.root),
                        "--preset-mode",
                        "single",
                        "--dry-run",
                        *selectors,
                    ],
                ),
                mock.patch.object(module, "MatchPlanRunner") as runner,
                mock.patch.object(
                    PlayerRecordsGenerator,
                    "generate",
                    autospec=True,
                    side_effect=PlayerRecordsGenerator.generate,
                ) as generate,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(module.main(), 0)
                self.assertEqual(
                    [call.args[1] for call in generate.call_args_list], expected
                )
                if "--check-only" in selectors:
                    runner.return_value.run_team.assert_not_called()
                if module is batch:
                    output, _ = single.match_plan_paths(self.root, "single")
                    report = json.loads(
                        max(output.glob("preflight_*.json")).read_text()
                    )
                    self.assertEqual(report["team_count"], len(expected))
                    self.assertEqual(
                        [team["team_id"] for team in report["queued"]], expected
                    )
                    self.assertEqual(report["disqualified"], [])
                # The same-name unselected team must still disambiguate output paths.
                self.assertEqual(
                    generate.call_args_list[0].args[0].teams["77"].output_name,
                    "Selected_77",
                )

    def test_registry_only_scope_and_empty_scope(self) -> None:
        registry = self.root / "attributes.txt"
        for content, expected in (("77\n88\n", ["77", "88"]), ("", [])):
            registry.write_text(content)
            with (
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "batch",
                        "--players-csv",
                        str(self.root / "Players.csv"),
                        "--teams-players-csv",
                        str(self.root / "Teams-Players.csv"),
                        "--rosters-csv",
                        str(self.root / "Rosters.csv"),
                        "--formations-csv",
                        str(self.root / "Formations.csv"),
                        "--output-dir",
                        str(self.root),
                        "--preset-mode",
                        "single",
                        "--check-only",
                        "--attributes-completed-teams",
                        str(registry),
                    ],
                ),
                mock.patch.object(batch, "MatchPlanRunner"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(batch.main(), 0)
            output, _ = single.match_plan_paths(self.root, "single")
            report = json.loads(max(output.glob("preflight_*.json")).read_text())
            self.assertEqual(report["team_count"], len(expected))
            self.assertEqual([team["team_id"] for team in report["queued"]], expected)
            self.assertEqual(report["skipped_unlisted"], [])

    def test_each_required_file_is_checked_before_generation(self) -> None:
        paths = {**vars(self.sources), "formations_csv": self.root / "Formations.csv"}
        for module, key, failure in itertools.product(
            (single, batch), paths, ("missing", "directory", "read", "write")
        ):
            selected = dict(paths)
            if failure in ("missing", "directory"):
                selected[key] = (
                    self.root / "missing.csv" if failure == "missing" else self.root
                )
            arguments = [
                "script",
                "--no-config",
                "--team",
                "77",
                "--preset-mode",
                "single",
                *[
                    item
                    for name, path in selected.items()
                    for item in ("--" + name.replace("_", "-"), str(path))
                ],
                *(["--check-only"] if module is batch else []),
            ]
            denied_mode = os.R_OK if failure == "read" else os.W_OK
            with (
                self.subTest(module=module.__name__, path=key, failure=failure),
                mock.patch.object(sys, "argv", arguments),
                mock.patch(
                    "pes_workflows.csv_validation.os.access",
                    side_effect=lambda path, mode: (
                        not (path == selected[key] and mode == denied_mode)
                    ),
                ),
                mock.patch.object(module, "PlayerRecordsGenerator") as generator,
                mock.patch.object(single, "create_match_plan_adapter") as adapter,
                contextlib.redirect_stderr(io.StringIO()) as errors,
                self.assertRaises(SystemExit) as caught,
            ):
                module.main()
            self.assertEqual(caught.exception.code, 2)
            self.assertIn(str(selected[key]), errors.getvalue())
            generator.assert_not_called()
            adapter.assert_not_called()

    def test_full_batch_and_selected_corruption_still_fail(self) -> None:
        for selectors in (
            {},
            {"team_queries": ["99"]},
            {"team_queries": ["missing"]},
            {"team_queries": ["Selected"]},
        ):
            with (
                self.subTest(selectors=selectors),
                self.assertRaises(PlayerRecordsGenerationError),
            ):
                PlayerRecordsGenerator(
                    **single.player_records_sources(self.sources), **selectors
                )

    def test_selected_team_still_requires_sufficient_players_and_goalkeeper(
        self,
    ) -> None:
        for no_keeper in (False, True):
            with self.subTest(no_keeper=no_keeper):
                generator = PlayerRecordsGenerator(
                    **single.player_records_sources(self.sources), team_queries=["77"]
                )
                if no_keeper:
                    generator._players["101"]["GK"] = "0"
                else:
                    generator._roster["77"] = ("101",)
                with self.assertRaises(single.InsufficientSquadError):
                    generator.generate("77")


class MatchPlanScriptsTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for filename in (
            "Players.csv",
            "Teams-Players.csv",
            "Rosters.csv",
            "Formations.csv",
        ):
            (self.root / filename).write_text("placeholder")
        self.registry = self.root / single.COMPLETION_REGISTRY_NAME
        self.batch_registry = self.root / batch.COMPLETION_REGISTRY_NAME
        self.team = SimpleNamespace(
            team_name="China*", team_id="77", kind="National", output_name="China"
        )
        self.mounted_policy = self.root / "mounted policy.md"
        self.policy = single.TemplateLoader(
            single.PROJECT_ROOT / "prompts/match_plan", preset_mode="single"
        ).build_system_prompt()
        self.mounted_policy.write_text(self.policy, encoding="utf-8")

    def test_config_only_entry_points_use_selected_team_and_output(self) -> None:
        config = self.root / "settings.toml"
        config.write_text(
            "[defaults]\ndelay=0\n"
            f'players_csv="{self.root / "Players.csv"}"\n'
            f'teams_players_csv="{self.root / "Teams-Players.csv"}"\n'
            f'rosters_csv="{self.root / "Rosters.csv"}"\n'
            f'formations_csv="{self.root / "Formations.csv"}"\n'
            '[match_plan]\npreset_mode="single"\nteams=["77"]\n'
            'output_dir="single-reports"\ndry_run=true\n'
            '[match_plans]\npreset_mode="multi"\nteams=["77"]\n'
            'output_dir="batch-reports"\ndry_run=true\n'
        )
        for module, output in ((single, "single-reports"), (batch, "batch-reports")):
            with (
                self.subTest(module=module.__name__),
                mock.patch.object(sys, "argv", ["script", "--config", str(config)]),
                mock.patch.object(module, "PlayerRecordsGenerator") as generator,
                mock.patch.object(module, "MatchPlanRunner") as runner,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                generator.return_value.teams = {"77": self.team}
                runner.return_value.dry_run = True
                self.assertEqual(module.main(), 0)
                self.assertEqual(generator.call_args.kwargs["team_queries"], ["77"])
                self.assertEqual(
                    runner.call_args.kwargs["output_base_dir"], self.root / output
                )
                self.assertTrue(runner.call_args.kwargs["dry_run"])
                runner.return_value.run_team.assert_called_once()
                self.assertFalse(self.registry.exists())

    def test_entry_points_select_engine_and_preserve_defaults(self) -> None:
        for module in (single, batch):
            for engine_args, cls, model, effort in (
                ([], claude_cli.ClaudeCodeSubprocessAdapter, "claude-opus-5-5", "high"),
                (
                    ["--engine", "claude-code", "--fast"],
                    claude_cli.ClaudeCodeSubprocessAdapter,
                    "claude-opus-5-5",
                    "high",
                ),
                (
                    ["--engine", "codex"],
                    claude_cli.CodexSubprocessAdapter,
                    "gpt-6-astra",
                    "high",
                ),
                (
                    ["--engine", "codex", "--fast"],
                    claude_cli.CodexSubprocessAdapter,
                    "gpt-6-astra",
                    "high",
                ),
                *[
                    (
                        ["--engine", "codex", "--model", "gpt-6-sol", *fast_args],
                        claude_cli.CodexSubprocessAdapter,
                        "gpt-6-sol",
                        "high",
                    )
                    for fast_args in ([], ["--fast"])
                ],
                (
                    [
                        "--engine",
                        "codex",
                        "--fast",
                        "--model",
                        "custom",
                        "--effort",
                        "high",
                    ],
                    claude_cli.CodexSubprocessAdapter,
                    "custom",
                    "high",
                ),
                *[
                    (
                        ["--engine", "codex", "--effort", level],
                        claude_cli.CodexSubprocessAdapter,
                        "gpt-6-astra",
                        level,
                    )
                    for level in ("low", "medium", "high", "xhigh", "max")
                ],
                (
                    ["--engine", "codex", "--model", "custom", "--effort", "high"],
                    claude_cli.CodexSubprocessAdapter,
                    "custom",
                    "high",
                ),
            ):
                with (
                    self.subTest(module=module.__name__, args=engine_args),
                    mock.patch.object(
                        sys,
                        "argv",
                        [
                            "script",
                            "--team",
                            "77",
                            "--preset-mode",
                            "single",
                            "--players-csv",
                            str(self.root / "Players.csv"),
                            "--teams-players-csv",
                            str(self.root / "Teams-Players.csv"),
                            "--rosters-csv",
                            str(self.root / "Rosters.csv"),
                            "--formations-csv",
                            str(self.root / "Formations.csv"),
                            "--output-dir",
                            str(self.root),
                            "--dry-run",
                            "--delay",
                            "0",
                            *engine_args,
                        ],
                    ),
                    mock.patch.object(
                        module,
                        "configure_file_logging",
                        side_effect=lambda path, resources: path.mkdir(exist_ok=True),
                    ),
                    mock.patch.object(module, "PlayerRecordsGenerator") as generator,
                    mock.patch.object(module, "MatchPlanRunner") as runner,
                    mock.patch.object(claude_cli.subprocess, "Popen") as popen,
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    generator.return_value.teams = {"77": self.team}
                    module.main()
                    adapter = runner.call_args.kwargs["llm_adapter"]
                    self.assertIs(type(adapter), cls)
                    self.assertEqual(
                        (adapter.model, adapter.effort, adapter.delay),
                        (model, effort, 0),
                    )
                    self.assertEqual(runner.call_args.kwargs["model"], model)
                    self.assertIsNone(adapter.system_prompt_file)
                    self.assertEqual(adapter.fast_mode, "--fast" in engine_args)
                    runner.return_value.run_team.assert_called_once()
                    popen.assert_not_called()

    def test_custom_target_controls_backup_lock_and_report(self) -> None:
        target = self.root / "tactics" / "custom-plans.txt"
        target.parent.mkdir()
        target.write_text("unchanged")
        for name in ("first-output", "second-output"):
            output = self.root / name
            with mock.patch.object(
                batch, "acquire_lock", wraps=batch.acquire_lock
            ) as lock:
                result, _, runner = self.invoke_batch(
                    "--formations-csv", str(target), "--output-dir", str(output)
                )
            self.assertEqual(result, 0)
            self.assertEqual(
                lock.call_args.args[1],
                target.with_name(".custom-plans.txt.match_plans.lock"),
            )
            self.assertEqual(runner.call_args.kwargs["formations_path"], target)
            backups = list(output.glob("custom-plans_backup_batch_*.txt"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), "unchanged")
            report = json.loads(next(output.glob("preflight_*.json")).read_text())
            self.assertEqual(report["formations_csv"], str(target))
            self.assertEqual(report["rosters_csv"], str(self.root / "Rosters.csv"))

    def test_invalid_engine_options_fail_before_database_access(self) -> None:
        for module in (single, batch):
            for args in (
                ["--engine", "unknown"],
                ["--engine", "codex", "--effort", "invalid"],
                ["--team-type", "invalid"],
            ):
                with (
                    self.subTest(module=module.__name__, args=args),
                    mock.patch.object(
                        sys,
                        "argv",
                        ["script", "--team", "77", "--preset-mode", "single", *args],
                    ),
                    mock.patch.object(module, "PlayerRecordsGenerator") as generator,
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit) as caught,
                ):
                    module.main()
                self.assertEqual(caught.exception.code, 2)
                generator.assert_not_called()

    def test_preset_mode_is_required_and_validated_before_io(self) -> None:
        for module, args in itertools.product(
            (single, batch), ([], ["--preset-mode"], ["--preset-mode", "invalid"])
        ):
            with (
                self.subTest(module=module.__name__, args=args),
                mock.patch.object(sys, "argv", ["script", *args]),
                mock.patch.object(module, "PlayerRecordsGenerator") as generator,
                mock.patch.object(module, "configure_file_logging") as logging_setup,
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as caught,
            ):
                module.main()
            self.assertEqual(caught.exception.code, 2)
            generator.assert_not_called()
            logging_setup.assert_not_called()

    def test_both_entry_points_propagate_modes_and_isolate_completion(self) -> None:
        for module, mode, engine in itertools.product(
            (single, batch), ("single", "multi"), ("claude-code", "codex")
        ):
            with self.subTest(module=module.__name__, mode=mode, engine=engine):
                data = self.root / module.__name__ / mode / engine
                data.mkdir(parents=True)
                for filename in ("Players.csv", "Teams-Players.csv", "Rosters.csv"):
                    (data / filename).write_text("placeholder")
                (data / "Formations.csv").write_text("unchanged")
                other_mode = "multi" if mode == "single" else "single"
                workflow = "match_plan" if module is single else "match_plans"
                other_workflow = "match_plans" if module is single else "match_plan"
                _, other_registry = single.match_plan_paths(
                    data, other_mode, workflow=workflow
                )
                single.append_completed_team(other_registry, self.team)
                _, other_command_registry = single.match_plan_paths(
                    data, mode, workflow=other_workflow
                )
                single.append_completed_team(other_command_registry, self.team)
                output, registry = single.match_plan_paths(
                    data, mode, workflow=workflow
                )
                for attempt in range(2):
                    with (
                        mock.patch.object(
                            sys,
                            "argv",
                            [
                                "script",
                                "--team",
                                "77",
                                "--preset-mode",
                                mode,
                                "--engine",
                                engine,
                                "--players-csv",
                                str(data / "Players.csv"),
                                "--teams-players-csv",
                                str(data / "Teams-Players.csv"),
                                "--rosters-csv",
                                str(data / "Rosters.csv"),
                                "--formations-csv",
                                str(data / "Formations.csv"),
                                "--output-dir",
                                str(data),
                            ],
                        ),
                        mock.patch.object(
                            module,
                            "configure_file_logging",
                            side_effect=lambda path, resources: path.mkdir(
                                exist_ok=True
                            ),
                        ),
                        mock.patch.object(
                            module, "PlayerRecordsGenerator"
                        ) as generator,
                        mock.patch.object(module, "MatchPlanRunner") as runner,
                        contextlib.redirect_stdout(io.StringIO()),
                    ):
                        generator.return_value.teams = {"77": self.team}
                        runner.return_value.dry_run = False
                        module.main()
                        if attempt == 0:
                            kwargs = runner.call_args.kwargs
                            self.assertEqual(kwargs["preset_mode"], mode)
                            self.assertEqual(kwargs["loader"].preset_mode, mode)
                            self.assertEqual(
                                len(kwargs["loader"].user_templates),
                                3 if mode == "single" else 5,
                            )
                            self.assertEqual(kwargs["output_base_dir"], output)
                            self.assertIsNone(kwargs["llm_adapter"].system_prompt_file)
                            runner.return_value.run_team.assert_called_once()
                        else:
                            generator.return_value.generate.assert_not_called()
                            runner.return_value.run_team.assert_not_called()
                self.assertEqual(single.read_completed_teams(registry), {"77"})
                self.assertEqual(other_registry.read_text(), "77\tChina*\n")
                self.assertEqual(other_command_registry.read_text(), "77\tChina*\n")
                if module is batch:
                    report = json.loads(
                        max(output.glob("preflight_*.json")).read_text()
                    )
                    self.assertEqual(report["preset_mode"], mode)
                    self.assertEqual(report["completion_registry"], str(registry))

    def test_multi_batch_check_only_dry_run_and_failure_do_not_complete(self) -> None:
        (self.root / "Formations.csv").write_text("unchanged")
        output, registry = single.match_plan_paths(
            self.root, "multi", workflow="match_plans"
        )
        for engine in ("claude-code", "codex"):
            args = ("--preset-mode", "multi", "--engine", engine)
            _, _, runner = self.invoke_batch(*args, "--check-only")
            runner.return_value.run_team.assert_not_called()
            self.invoke_batch(*args, "--dry-run")
            result, _, _ = self.invoke_batch(*args, fail=True)
            self.assertEqual(result, 1)
            self.assertFalse(registry.exists())
            self.assertFalse(self.batch_registry.exists())
            report = json.loads(max(output.glob("preflight_*.json")).read_text())
            self.assertEqual(report["preset_mode"], "multi")

    def test_squad_failure_is_reported_without_generation(self) -> None:
        result, _, runner = self.invoke_batch(disqualified=True)
        self.assertEqual(result, 1)
        runner.return_value.run_team.assert_not_called()
        self.assertFalse(self.batch_registry.exists())
        report = json.loads(max(self.root.glob("preflight_*.json")).read_text())
        self.assertEqual(report["queued"], [])
        self.assertEqual(report["disqualified"], [["China*", "no goalkeeper"]])

    def test_selection_supports_club_national_and_custom_squads(self) -> None:
        club = SimpleNamespace(team_name="Club*", team_id="88", kind="Club")
        custom = SimpleNamespace(team_name="Custom Squad", team_id="99", kind="Club")
        teams = {r.team_id: r for r in (self.team, club, custom)}
        generator = SimpleNamespace(teams=teams)
        for team in teams.values():
            self.assertIs(single.resolve_team(generator, team.team_id), team)
            self.assertIs(single.resolve_team(generator, team.team_name), team)
        result, generated, _ = self.invoke_batch("--check-only", teams=teams)
        self.assertEqual(result, 0)
        self.assertEqual(
            generated.return_value.generate.call_args_list,
            [mock.call("77"), mock.call("88"), mock.call("99")],
        )
        _, generated, _ = self.invoke_batch(
            "--check-only", "--team", "Club*", teams=teams
        )
        generated.return_value.generate.assert_called_once_with("88")

    def test_codex_batch_preflight_dry_run_failure_and_resume(self) -> None:
        (self.root / "Formations.csv").write_text("unchanged")
        args = ("--engine", "codex", "--fast")
        with mock.patch.object(claude_cli.subprocess, "Popen") as popen:
            _, _, runner = self.invoke_batch(*args, "--check-only")
            runner.return_value.run_team.assert_not_called()
            self.invoke_batch(*args, "--dry-run")
            self.assertFalse(self.batch_registry.exists())
            result, _, _ = self.invoke_batch(*args, fail=True)
            self.assertEqual(result, 1)
            self.assertFalse(self.batch_registry.exists())
            self.invoke_batch(*args)
            self.assertEqual(single.read_completed_teams(self.batch_registry), {"77"})
            _, _, runner = self.invoke_batch("--engine", "claude-code")
            runner.return_value.run_team.assert_not_called()
            popen.assert_not_called()

    def test_both_engines_run_same_contract_pipeline_with_repair(self) -> None:
        artifacts = {"single": [], "multi": []}
        for mode, cls in itertools.product(
            ("single", "multi"),
            (claude_cli.ClaudeCodeSubprocessAdapter, claude_cli.CodexSubprocessAdapter),
        ):
            with self.subTest(mode=mode, engine=cls.provider_name):
                client = SingleModeFakeClient() if mode == "single" else FakeClient()
                loader = single.TemplateLoader(
                    single.PROJECT_ROOT / "prompts/match_plan", preset_mode=mode
                )
                policy = loader.build_system_prompt()
                policy_paths = []
                requests = []
                bench_requests = []

                def popen(cmd: list[str], **kwargs: Any) -> mock.Mock:
                    if cmd[0] == "claude":
                        policy_path = Path(cmd[cmd.index("--system-prompt-file") + 1])
                    else:
                        settings = dict(
                            cmd[i + 1].split("=", 1)
                            for i, arg in enumerate(cmd)
                            if arg == "-c"
                        )
                        policy_path = Path(
                            json.loads(settings["model_instructions_file"])
                        )
                    policy_paths.append(policy_path)
                    self.assertEqual(policy_path.read_bytes(), policy.encode("utf-8"))
                    process = mock.Mock(returncode=0)

                    def communicate(*, input: str) -> tuple[str, str]:
                        requests.append(input)
                        response = client.completions.create(
                            messages=[
                                {"role": "system", "content": policy},
                                {"role": "user", "content": input},
                            ]
                        )
                        raw = json.loads(response.choices[0].message.content)
                        if len(requests) == 1:
                            raw["Schema Version"] = "invalid"
                        if raw["Artifact"] == "BenchDecision":
                            bench_requests.append(input)
                            # Reject the former verbose schema, then accept IDs only.
                            if len(bench_requests) > 1:
                                raw = compact_bench("12")
                        text = json.dumps(raw)
                        if cmd[0] == "codex":
                            Path(
                                cmd[cmd.index("--output-last-message") + 1]
                            ).write_text(text)
                            return "progress output", ""
                        return text, ""

                    process.communicate.side_effect = communicate
                    return process

                output = self.root / mode / cls.provider_name
                runner = single.MatchPlanRunner(
                    llm_adapter=cls(delay=0),
                    loader=loader,
                    output_base_dir=output,
                    roster_path=self.root / "Rosters.csv",
                    formations_path=self.root / "Formations.csv",
                    players_path=None,
                    teams_players_path=None,
                    preset_mode=mode,
                    dry_run=True,
                )
                runner._execute_assembled_injection = mock.Mock()
                with mock.patch.object(
                    claude_cli.subprocess, "Popen", side_effect=popen
                ):
                    runner.run_team(fixture_player_records())
                self.assertEqual(len(requests), len(loader.user_templates) + 2)
                self.assertTrue(all(not path.exists() for path in policy_paths))
                self.assertIn("CORRECTION REQUIRED", requests[1])
                self.assertIn("invalid", requests[1])
                path = next(output.glob("fixture/run_*/conversation_history.json"))
                history = json.loads(path.read_text())
                self.assertEqual(
                    [row["artifact_type"] for row in history],
                    ["StartingXILock"]
                    + ["PresetPlan"] * (1 if mode == "single" else 3)
                    + ["BenchDecision"],
                )
                self.assertEqual(len(history[0]["format_repairs"]), 1)
                self.assertEqual(history[-1]["accepted_artifact"], compact_bench("12"))
                self.assertEqual(len(history[-1]["format_repairs"]), 1)
                self.assertIn("CORRECTION REQUIRED", bench_requests[-1])
                frozen_block = bench_requests[0].split("<FROZEN_ARTIFACTS>")[1]
                frozen = json.loads(
                    frozen_block.split("```json\n")[1].split("\n```")[0]
                )
                self.assertEqual(
                    [
                        item["Preset"]
                        for item in frozen
                        if item["Artifact"] == "PresetPlan"
                    ],
                    ["Main"] if mode == "single" else ["Main", "Defensive", "Custom"],
                )
                if mode == "multi":
                    self.assertEqual(
                        [row["accepted_artifact"]["Preset"] for row in history[1:4]],
                        ["Main", "Defensive", "Custom"],
                    )
                digest = hashlib.sha256(policy.encode("utf-8")).hexdigest()
                self.assertEqual(
                    [row["policy_sha256"] for row in history], [digest] * len(history)
                )
                snapshot = path.parent / "00_Final_System_Prompt.md"
                self.assertEqual(snapshot.read_text().partition("\n\n")[2], policy)
                artifacts[mode].append([row["accepted_artifact"] for row in history])
                runner._execute_assembled_injection.assert_called_once()
        for mode in artifacts:
            self.assertEqual(artifacts[mode][0], artifacts[mode][1])

    def test_only_successful_apply_is_registered(self) -> None:
        runner = mock.Mock(dry_run=True)
        single.run_and_record(runner, object(), self.team, self.registry)
        self.assertFalse(self.registry.exists())
        runner.dry_run = False
        runner.run_team.side_effect = RuntimeError("atomic replace failed")
        with self.assertRaises(RuntimeError):
            single.run_and_record(runner, object(), self.team, self.registry)
        self.assertFalse(self.registry.exists())
        runner.run_team.side_effect = lambda _: self.assertFalse(self.registry.exists())
        single.run_and_record(runner, object(), self.team, self.registry)
        self.assertEqual(single.read_completed_teams(self.registry), {"77"})
        self.assertEqual(self.registry.read_text(), "77\tChina*\n")
        single.append_completed_team(self.registry, self.team)
        self.assertEqual(len(self.registry.read_text().splitlines()), 1)

    def test_registry_normalizes_duplicates_and_names(self) -> None:
        self.registry.write_text(
            "\ufeff 77 \t China \n77\n2\tTwo\n10\tOld\nbad row\n0\tInvalid\n\n3",
            encoding="utf-8",
        )
        self.assertEqual(
            checkpoint_io.load_completed_teams(self.registry),
            {"77": "China", "2": "Two", "10": "Old", "3": ""},
        )
        self.team.team_name = "China*\t National\nTeam"
        single.append_completed_team(self.registry, self.team)
        self.assertEqual(
            self.registry.read_text(), "10\tOld\n2\tTwo\n3\n77\tChina* National Team\n"
        )

    def test_registry_replace_failure_preserves_previous_content(self) -> None:
        from pes_workflows.storage.atomic import write_text_atomic

        self.registry.write_text("1\tDone\n", encoding="utf-8")

        def failed_write(path: Path, content: str) -> None:
            write_text_atomic(
                path, content, replace=mock.Mock(side_effect=OSError("failed"))
            )

        with mock.patch.object(
            checkpoint_io, "write_text_atomic", side_effect=failed_write
        ):
            with self.assertRaises(OSError):
                single.append_completed_team(self.registry, self.team)
        self.assertEqual(self.registry.read_text(), "1\tDone\n")
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_attribute_filter_restricts_queue_even_with_force(self) -> None:
        attributes = self.root / "attributes.txt"
        for content, expected in (
            ("77\tRenamed\n88\tClub\n999\n", True),
            ("77", True),
            ("88\n999\n", False),
            ("", False),
        ):
            with self.subTest(content=content):
                attributes.write_text(content, encoding="utf-8")
                result, generator, runner = self.invoke_batch(
                    "--attributes-completed-teams",
                    str(attributes),
                    "--force",
                    "--check-only",
                )
                self.assertEqual(result, 0)
                self.assertEqual(
                    generator.return_value.generate.call_count, int(expected)
                )
                runner.return_value.run_team.assert_not_called()
                report = max(self.root.glob("preflight_*.json"))
                data = json.loads(report.read_text())
                self.assertEqual(len(data["queued"]), int(expected))
                self.assertEqual(data["skipped_unlisted"], [])
                self.assertEqual(data["team_count"], int(expected))
                self.assertEqual(attributes.read_text(), content)

    def test_missing_attribute_filter_fails_before_database_load(self) -> None:
        for module in (single, batch):
            with (
                self.subTest(module=module.__name__),
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "script",
                        "--team",
                        "77",
                        "--preset-mode",
                        "single",
                        "--attributes-completed-teams",
                        str(self.root / "missing.txt"),
                    ],
                ),
                mock.patch.object(module, "PlayerRecordsGenerator") as generator,
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                module.main()
            self.assertEqual(error.exception.code, 2)
            generator.assert_not_called()

    def test_single_attribute_filter_precedes_force_and_generation(self) -> None:
        attributes = self.root / "attributes.txt"
        attributes.write_text("88\tClub\n", encoding="utf-8")
        with (
            mock.patch.object(
                sys,
                "argv",
                [
                    "single",
                    "--team",
                    "77",
                    "--preset-mode",
                    "single",
                    "--players-csv",
                    str(self.root / "Players.csv"),
                    "--teams-players-csv",
                    str(self.root / "Teams-Players.csv"),
                    "--rosters-csv",
                    str(self.root / "Rosters.csv"),
                    "--formations-csv",
                    str(self.root / "Formations.csv"),
                    "--output-dir",
                    str(self.root),
                    "--attributes-completed-teams",
                    str(attributes),
                    "--force",
                ],
            ),
            mock.patch.object(single, "configure_file_logging"),
            mock.patch.object(single, "PlayerRecordsGenerator") as generator,
            mock.patch.object(single, "MatchPlanRunner") as runner,
        ):
            generator.return_value.teams = {"77": self.team}
            single.main()
            generator.return_value.generate.assert_not_called()
            runner.assert_not_called()

    def invoke_batch(
        self,
        *args: Any,
        fail: bool = False,
        teams: Mapping[str, Any] | None = None,
        disqualified: bool = False,
    ) -> tuple[int, mock.MagicMock, mock.MagicMock]:
        teams = teams if teams is not None else {"77": self.team}
        handlers = logging.getLogger().handlers[:]
        try:
            with (
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "batch",
                        "--preset-mode",
                        "single",
                        "--players-csv",
                        str(self.root / "Players.csv"),
                        "--teams-players-csv",
                        str(self.root / "Teams-Players.csv"),
                        "--rosters-csv",
                        str(self.root / "Rosters.csv"),
                        "--formations-csv",
                        str(self.root / "Formations.csv"),
                        "--output-dir",
                        str(self.root),
                        *args,
                    ],
                ),
                mock.patch.object(batch, "PlayerRecordsGenerator") as generator,
                mock.patch.object(batch, "MatchPlanRunner") as runner,
                mock.patch.object(batch.time, "sleep"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                generator.return_value.teams = teams
                if disqualified:
                    generator.return_value.generate.side_effect = (
                        single.UnbuildableSquadError("no goalkeeper")
                    )
                runner.return_value.dry_run = "--dry-run" in args
                if fail:
                    runner.return_value.run_team.side_effect = RuntimeError(
                        "commit failed"
                    )
                result = batch.main()
                return result, generator, runner
        finally:
            for handler in logging.getLogger().handlers[:]:
                if handler not in handlers:
                    logging.getLogger().removeHandler(handler)
                    handler.close()

    def test_batch_selection_resume_and_force(self) -> None:
        (self.root / "Formations.csv").write_text("unchanged")
        attributes = self.root / "attributes.txt"
        attributes.write_text("77\tChina*\n", encoding="utf-8")
        filter_args = ("--attributes-completed-teams", str(attributes))
        result, generator, runner = self.invoke_batch(*filter_args)
        self.assertEqual(result, 0)
        generator.return_value.generate.assert_called_once_with("77")
        self.assertEqual(runner.call_args.kwargs["preset_mode"], "single")
        self.assertEqual(
            runner.call_args.kwargs["output_base_dir"],
            self.root,
        )
        self.assertEqual(
            runner.call_args.kwargs["formations_path"], self.root / "Formations.csv"
        )
        self.assertEqual(
            generator.call_args.kwargs["teams_players_csv"],
            self.root / "Teams-Players.csv",
        )
        _, generator, runner = self.invoke_batch(*filter_args)
        generator.return_value.generate.assert_not_called()
        runner.return_value.run_team.assert_not_called()
        _, _, runner = self.invoke_batch(*filter_args, "--force")
        runner.return_value.run_team.assert_called_once()
        self.assertEqual(len(self.batch_registry.read_text().splitlines()), 1)

    def test_check_only_dry_run_and_failure_leave_registry_empty(self) -> None:
        (self.root / "Formations.csv").write_text("unchanged")
        _, _, runner = self.invoke_batch("--check-only")
        runner.return_value.run_team.assert_not_called()
        self.invoke_batch("--dry-run")
        self.assertFalse(self.batch_registry.exists())
        result, _, _ = self.invoke_batch(fail=True)
        self.assertEqual(result, 1)
        self.assertFalse(self.batch_registry.exists())

    def test_single_team_skips_registry_entry_before_generation(self) -> None:
        single.append_completed_team(self.registry, self.team)
        with (
            mock.patch.object(
                sys,
                "argv",
                [
                    "single",
                    "--team",
                    "77",
                    "--preset-mode",
                    "single",
                    "--players-csv",
                    str(self.root / "Players.csv"),
                    "--teams-players-csv",
                    str(self.root / "Teams-Players.csv"),
                    "--rosters-csv",
                    str(self.root / "Rosters.csv"),
                    "--formations-csv",
                    str(self.root / "Formations.csv"),
                    "--output-dir",
                    str(self.root),
                ],
            ),
            mock.patch.object(single, "configure_file_logging"),
            mock.patch.object(single, "PlayerRecordsGenerator") as generator,
            mock.patch.object(single, "MatchPlanRunner") as runner,
        ):
            generator.return_value.teams = {"77": self.team}
            single.main()
            generator.return_value.generate.assert_not_called()
            runner.assert_not_called()

    def test_real_runner_isolates_team_artifacts_and_preserves_attempts(self) -> None:
        output = self.root / single.OUTPUT_DIRECTORY_NAME
        client = SingleModeFakeClient()
        create = client.completions.create

        def compact_create(**kwargs: Any) -> SimpleNamespace:
            response = create(**kwargs)
            message = response.choices[0].message
            if json.loads(message.content)["Artifact"] == "BenchDecision":
                message.content = json.dumps(compact_bench("12"))
            return response

        client.completions.create = compact_create
        runner = single.MatchPlanRunner(
            llm_adapter=SimpleNamespace(
                generate=lambda messages, *args, **kwargs: (
                    client.completions.create(messages=messages)
                    .choices[0]
                    .message.content,
                    "",
                )
            ),
            loader=single.TemplateLoader(
                single.PROJECT_ROOT / "prompts/match_plan", preset_mode="single"
            ),
            output_base_dir=output,
            roster_path=self.root / "Rosters.csv",
            formations_path=self.root / "Formations.csv",
            players_path=None,
            teams_players_path=None,
            preset_mode="single",
            dry_run=True,
        )
        captured = []

        def injection(**kwargs: Any) -> None:
            captured.append(kwargs["semantic_plan"])
            (kwargs["team_output_dir"] / "semantic.json").write_text(
                json.dumps(kwargs["semantic_plan"])
            )

        runner._execute_assembled_injection = injection
        for _ in range(2):
            runner.run_team(fixture_player_records())
        self.assertEqual([path.name for path in output.iterdir()], ["fixture"])
        attempts = list((output / "fixture").iterdir())
        self.assertEqual(len(attempts), 2)
        self.assertTrue(
            all(path.is_dir() and path.name.startswith("run_") for path in attempts)
        )
        policy = self.mounted_policy.read_text()
        digest = hashlib.sha256(policy.encode("utf-8")).hexdigest()
        for attempt in attempts:
            self.assertTrue((attempt / "run_manifest.json").is_file())
            self.assertTrue((attempt / "semantic.json").is_file())
            snapshot = (attempt / "00_Final_System_Prompt.md").read_text()
            self.assertEqual(snapshot.partition("\n\n")[2], policy)
            manifest = json.loads((attempt / "run_manifest.json").read_text())
            self.assertEqual(manifest["source"]["policy_sha256"], digest)
        histories = list(output.glob("fixture/run_*/conversation_history.json"))
        self.assertEqual(len(histories), 2)
        for path in histories:
            history = json.loads(path.read_text())
            self.assertEqual(
                [row["artifact_type"] for row in history],
                ["StartingXILock", "PresetPlan", "BenchDecision"],
            )
            self.assertEqual(history[2]["accepted_artifact"], compact_bench("12"))
            self.assertEqual([row["policy_sha256"] for row in history], [digest] * 3)
        self.assertEqual(len(client.completions.user_prompts), 6)
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0]["Squad"][11]["Player ID"], "12")
        policies = client.completions.system_prompts
        self.assertEqual(policies, [policy] * 6)

    def test_canonical_sources_render_dynamically_in_both_modes(self) -> None:
        canonical = single.PROJECT_ROOT / "prompts/match_plan"
        for mode in ("single", "multi"):
            base = single.TemplateLoader(canonical, preset_mode=mode)
            local = single.TemplateLoader(canonical, preset_mode=mode)
            last_turn = len(base.user_templates)
            self.assertEqual(local.user_templates[:-1], base.user_templates[:-1])
            self.assertEqual(
                local.user_template_titles[:-1], base.user_template_titles[:-1]
            )
            for turn in range(1, last_turn):
                kwargs = {"player_records_content": "records"}
                if turn > 1:
                    kwargs["frozen_artifacts_json"] = "[]"
                self.assertEqual(
                    local.get_turn_user_prompt(turn, **kwargs),
                    base.get_turn_user_prompt(turn, **kwargs),
                )
            marker = f"### Call {last_turn} — `BenchDecision`"
            self.assertEqual(
                local.build_system_prompt().partition(marker)[0],
                base.build_system_prompt().partition(marker)[0],
            )
            for name in (
                "system_prompt.md",
                "game_plan_rules.md",
                "../shared/player_glossary.md",
                "user_message_templates.md",
            ):
                with self.subTest(mode=mode, source=name):
                    directory = self.root / mode / Path(name).name / "match_plan"
                    shutil.copytree(canonical.parent, directory.parent)
                    target = directory / name
                    content = target.read_text()
                    marker = "CANONICAL_SOURCE_UPDATE"
                    if name == "user_message_templates.md":
                        content = content.replace(
                            "</PLAYER_RECORDS>", "</PLAYER_RECORDS>\n" + marker
                        )
                    else:
                        content = marker + "\n\n" + content
                    target.write_text(content)
                    updated = single.TemplateLoader(directory, preset_mode=mode)
                    rendered = (
                        updated.user_templates[0]
                        if name == "user_message_templates.md"
                        else updated.build_system_prompt()
                    )
                    self.assertIn(marker, rendered)
                    self.assertNotIn("[IF_MODE:", updated.build_system_prompt())
                    self.assertNotIn("[PASTE ", updated.build_system_prompt())

    def test_final_bench_prompts_share_schema_and_match_frozen_scope(self) -> None:
        policies = []
        user_contracts = []
        for mode, turn, names in (
            ("single", 3, "Main"),
            ("multi", 5, "Main, Defensive, and Custom"),
        ):
            loader = single.TemplateLoader(
                single.PROJECT_ROOT / "prompts/match_plan", preset_mode=mode
            )
            policy = loader.build_system_prompt()
            bench_policy = policy.partition(f"### Call {turn} — `BenchDecision`")[2]
            self.assertIn(f"frozen Starting XI duties of {names}", bench_policy)
            self.assertIn("all three frozen states", bench_policy)
            self.assertIn("alternative deployments", bench_policy)
            self.assertNotIn("### BenchDecision coverage assessment", policy)
            policies.append(
                bench_policy.partition("Return exactly one bare JSON object")[2]
            )
            prompt, title = loader.get_turn_user_prompt(
                turn, player_records_content="records", frozen_artifacts_json="[]"
            )
            self.assertTrue(title.startswith(f"STEP {turn} OF {turn}"))
            self.assertIn(f"frozen duties of {names}", prompt)
            self.assertIn(f"Call {turn} system contract", prompt)
            self.assertIn("each substitute contains only Player ID", prompt)
            self.assertNotIn("{bench_turn}", policy + prompt)
            self.assertNotIn("{preset_names}", policy + prompt)
            self.assertNotIn("{duty_label}", prompt)
            user_contracts.append(
                prompt.partition("Return only")[2].replace(f"Call {turn}", "Call N")
            )
        self.assertTrue(policies[0])
        self.assertEqual(policies[0], policies[1])
        self.assertEqual(user_contracts[0], user_contracts[1])

    def test_compact_validation_preserves_order_and_roster_checks(self) -> None:
        for mode in ("single", "multi"):
            source = source_identity()
            xi = validate_starting_xi_lock(strategy_raw(), source)
            source["players"]["13"] = "Player 13"
            source["total_players"] = 13

            def validate(raw: dict[str, Any]) -> BenchDecision:
                return validate_bench_decision(raw, xi, source)

            valid = validate(compact_bench("13", "12"))
            self.assertEqual(
                [row["Player ID"] for row in valid.compiler_refs(source)], ["13", "12"]
            )
            for ids in (("12",), ("12", "12"), ("1", "12"), ("99", "12"), (12, "13")):
                with (
                    self.subTest(ids=ids),
                    self.assertRaises((ArtifactDomainError, ArtifactSchemaError)),
                ):
                    validate(compact_bench(*ids))
            for field in ("Rationale", "Reason", "Demands Served"):
                raw = compact_bench("12", "13")
                raw["Substitutes"][0][field] = "extra"
                with self.assertRaises(ArtifactSchemaError):
                    validate(raw)
            for field in (
                "Demand Profile",
                "Demands Served",
                "Coverage Gaps",
                "Rationale",
                "Reason",
            ):
                raw = compact_bench("12", "13")
                raw[field] = []
                with (
                    self.subTest(mode=mode, field=field),
                    self.assertRaises(ArtifactSchemaError),
                ):
                    validate(raw)
            source["total_players"] = 11
            self.assertEqual(validate(compact_bench()).selections, ())

    def test_subprocess_uses_mounted_policy_for_all_calls_including_repairs(
        self,
    ) -> None:
        adapter = single.ClaudeCodeSubprocessAdapter(
            delay=0, system_prompt_file=self.mounted_policy
        )
        process = mock.Mock(returncode=0)
        process.communicate.return_value = (json.dumps(compact_bench("12")), "")
        with mock.patch.object(
            claude_cli.subprocess, "Popen", return_value=process
        ) as popen:
            for turn in (1, 2, 3, 3):
                messages = [
                    {"role": "system", "content": "local policy"},
                    {"role": "user", "content": "task"},
                ]
                if popen.call_count == 3:
                    messages += [
                        {"role": "assistant", "content": "bad attempt"},
                        {"role": "user", "content": "repair"},
                    ]
                adapter._generate_once(
                    messages=messages, turn=turn, team_name="fixture", user_id=None
                )
                cmd = popen.call_args.args[0]
                self.assertEqual(cmd[0], "claude")
                self.assertEqual(
                    cmd[cmd.index("--system-prompt-file") + 1], str(self.mounted_policy)
                )
                self.assertEqual(cmd[cmd.index("--tools") + 1], "")
                self.assertNotIn("--system-prompt", cmd)
            self.assertIn(
                "CORRECTION REQUIRED", process.communicate.call_args.kwargs["input"]
            )


class ConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / "pes-workflows.toml"
        self.config.write_text(
            '[defaults]\nmodel="shared"\nfast=true\ndelay=3\n'
            f'players_csv="{self.root / "people" / "attributes.csv"}"\n'
            f'teams_players_csv="{self.root / "clubs" / "members.csv"}"\n'
            f'rosters_csv="{self.root / "squads" / "selected.csv"}"\n'
            f'formations_csv="{self.root / "tactics" / "plans.csv"}"\n'
            '[match_plan]\npreset_mode="single"\nscope="single"\nteams=["77"]\n'
            '[match_plans]\npreset_mode="multi"\nmodel="batch"\n'
            'scope="multiple"\nteams=["77", "Other"]\ndry_run=true\nforce=true\n'
            'output_dir="reports"\nattributes_completed_teams="completed.txt"\n'
        )

    def parse(self, *args: str, single_team: bool = False) -> argparse.Namespace:
        parser = argparse.ArgumentParser(allow_abbrev=False)
        single.add_match_plan_arguments(parser)
        parser.add_argument("--team", **({} if single_team else {"action": "append"}))
        return parse_workflow_args(
            parser, "match_plan" if single_team else "match_plans", list(args)
        )

    def test_global_auto_option_precedence_and_runner_passthrough(self) -> None:
        original = self.config.read_text()
        options = {
            "auto_substitutions": (3, 1, 0),
            "auto_change_att_def": (1, 0, 1),
            "auto_switch_preset_tactics": (1, 0, 1),
        }
        for single_team, section in ((True, "match_plan"), (False, "match_plans")):
            for key, (shared, workflow, cli) in options.items():
                with self.subTest(section=section, key=key):
                    content = original.replace(
                        "[defaults]", f"[defaults]\n{key}={shared}"
                    )
                    self.config.write_text(content)
                    args = self.parse(
                        "--config", str(self.config), single_team=single_team
                    )
                    self.assertEqual(getattr(args, key), shared)
                    content = content.replace(
                        f"[{section}]", f"[{section}]\n{key}={workflow}"
                    )
                    self.config.write_text(content)
                    args = self.parse(
                        "--config", str(self.config), single_team=single_team
                    )
                    self.assertEqual(getattr(args, key), workflow)
                    args = self.parse(
                        "--config",
                        str(self.config),
                        "--" + key.replace("_", "-"),
                        str(cli),
                        single_team=single_team,
                    )
                    self.assertEqual(getattr(args, key), cli)
                    single.resolve_match_plan_engine_arguments(args)
                    with mock.patch.object(single, "create_match_plan_adapter"):
                        kwargs = single.match_plan_runner_options(args, self.root)
                    self.assertEqual(kwargs[key], cli)
                    runner = single.MatchPlanRunner(**kwargs)
                    with mock.patch(
                        "pes_workflows.application.build_team.execute_assembled_injection"
                    ) as inject:
                        runner._execute_assembled_injection(
                            output_name="fixture",
                            team_name="Fixture",
                            semantic_plan={},
                            team_output_dir=self.root,
                            step_idx=1,
                            source_identity={},
                        )
                    self.assertEqual(inject.call_args.kwargs[key], cli)
                    with self.assertRaisesRegex(ValueError, key):
                        single.MatchPlanRunner(**{**kwargs, key: True})

    def test_global_auto_options_accept_all_values_in_config_and_cli(self) -> None:
        original = self.config.read_text()
        for key, values in (
            ("auto_substitutions", range(4)),
            ("auto_change_att_def", range(2)),
            ("auto_switch_preset_tactics", range(2)),
        ):
            for value in values:
                for single_team, section in (
                    (True, "match_plan"),
                    (False, "match_plans"),
                ):
                    with self.subTest(key=key, value=value, section=section):
                        self.config.write_text(
                            original.replace(
                                f"[{section}]", f"[{section}]\n{key}={value}"
                            )
                        )
                        args = self.parse(
                            "--config", str(self.config), single_team=single_team
                        )
                        self.assertEqual(getattr(args, key), value)
                        self.config.write_text(original)
                        args = self.parse(
                            "--config",
                            str(self.config),
                            "--" + key.replace("_", "-"),
                            str(value),
                            single_team=single_team,
                        )
                        self.assertEqual(getattr(args, key), value)

    def test_auto_switch_fallback_uses_final_cli_preset_mode(self) -> None:
        for mode, switch in (("single", 0), ("multi", 1)):
            args = self.parse("--config", str(self.config), "--preset-mode", mode)
            self.assertEqual(args.auto_substitutions, 2)
            self.assertEqual(args.auto_change_att_def, 0)
            self.assertEqual(args.auto_switch_preset_tactics, switch)

    def test_global_auto_options_reject_invalid_input_before_io(self) -> None:
        original = self.config.read_text()
        for module, section in ((single, "match_plan"), (batch, "match_plans")):
            for key, upper in (
                ("auto_substitutions", 4),
                ("auto_change_att_def", 2),
                ("auto_switch_preset_tactics", 2),
            ):
                for value in ("-1", str(upper), "true", "false", "1.0", '"1"'):
                    for source in ("defaults", section, "cli"):
                        with self.subTest(
                            module=module.__name__, key=key, value=value, source=source
                        ):
                            content = original
                            argv = ["match", "--config", str(self.config)]
                            if source == "cli":
                                argv += ["--" + key.replace("_", "-"), value]
                            else:
                                content = content.replace(
                                    f"[{source}]", f"[{source}]\n{key}={value}"
                                )
                            self.config.write_text(content)
                            with (
                                mock.patch.object(sys, "argv", argv),
                                mock.patch.object(
                                    module, "preflight_match_files"
                                ) as preflight,
                                mock.patch.object(module, "MatchPlanRunner") as runner,
                                contextlib.redirect_stderr(io.StringIO()),
                                self.assertRaises(SystemExit) as error,
                            ):
                                module.main()
                            self.assertEqual(error.exception.code, 2)
                            preflight.assert_not_called()
                            runner.assert_not_called()

    def test_config_defaults_paths_and_cli_overrides(self) -> None:
        args = self.parse("--config", str(self.config))
        self.assertEqual(args.model, "batch")
        self.assertEqual(args.team, ["77", "Other"])
        self.assertEqual(args.players_csv, self.root / "people" / "attributes.csv")
        self.assertEqual(args.teams_players_csv, self.root / "clubs" / "members.csv")
        self.assertEqual(args.rosters_csv, self.root / "squads" / "selected.csv")
        self.assertEqual(args.formations_csv, self.root / "tactics" / "plans.csv")
        self.assertEqual(args.output_dir, self.root / "reports")
        self.assertEqual(args.attributes_completed_teams, self.root / "completed.txt")
        args = self.parse(
            "--config",
            str(self.config),
            "--model",
            "cli",
            "--delay",
            "0",
            "--players-csv",
            str(self.root / "override.csv"),
            "--output-dir",
            "local-output",
            "--no-fast",
            "--no-force",
            "--no-dry-run",
            "--preset-mode",
            "single",
            "--team",
            "New",
            "--team",
            "88",
        )
        self.assertEqual(
            (args.model, args.delay, args.preset_mode), ("cli", 0, "single")
        )
        self.assertEqual((args.fast, args.force, args.dry_run), (False, False, False))
        self.assertEqual(args.players_csv, self.root / "override.csv")
        self.assertEqual(args.rosters_csv, self.root / "squads" / "selected.csv")
        self.assertEqual(args.output_dir, Path("local-output"))
        self.assertEqual(args.team, ["New", "88"])
        self.assertEqual(
            self.parse("--config", str(self.config), "--scope", "all").team, None
        )
        self.assertEqual(
            self.parse("--config", str(self.config), single_team=True).team, "77"
        )

    def test_discovery_opt_out_and_engine_defaults(self) -> None:
        with mock.patch("pes_workflows.config.Path.cwd", return_value=self.root):
            self.assertEqual(self.parse().model, "batch")
            args = self.parse(
                "--no-config",
                "--players-csv",
                str(self.root / "p.csv"),
                "--teams-players-csv",
                str(self.root / "m.csv"),
                "--rosters-csv",
                str(self.root / "r.csv"),
                "--formations-csv",
                str(self.root / "f.csv"),
                "--preset-mode",
                "single",
                "--engine",
                "codex",
            )
        single.resolve_match_plan_engine_arguments(args)
        self.assertEqual(args.model, claude_cli.CodexSubprocessAdapter.DEFAULT_MODEL)
        self.assertEqual(args.effort, claude_cli.CodexSubprocessAdapter.DEFAULT_EFFORT)
        self.assertFalse(args.fast)

    def test_each_csv_path_has_independent_workflow_and_cli_overrides(self) -> None:
        original = self.config.read_text()
        for key in (
            "players_csv",
            "teams_players_csv",
            "rosters_csv",
            "formations_csv",
        ):
            with self.subTest(key=key):
                configured = self.root / "workflow" / f"{key}.txt"
                self.config.write_text(original + f'{key}="{configured}"\n')
                before = self.parse("--config", str(self.config))
                self.assertEqual(getattr(before, key), configured)
                override = self.root / "cli" / f"{key}.txt"
                after = self.parse(
                    "--config",
                    str(self.config),
                    "--" + key.replace("_", "-"),
                    str(override),
                )
                self.assertEqual(getattr(after, key), override)
                for other in (
                    "players_csv",
                    "teams_players_csv",
                    "rosters_csv",
                    "formations_csv",
                ):
                    if other != key:
                        self.assertEqual(getattr(before, other), getattr(after, other))
                with (
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit),
                ):
                    self.parse(
                        "--config",
                        str(self.config),
                        "--" + key.replace("_", "-"),
                        "relative.csv",
                    )

    def test_invalid_configuration_and_scope_fail_before_execution(self) -> None:
        for content in (
            "[defaults]\nunknown=1",
            '[defaults]\nfast="false"',
            "[defaults]\ndelay=-1",
            "[defaults]\ndelay=nan",
            "[defaults]\nplayers_csv=12",
            '[defaults]\nplayers_csv="relative.csv"',
            "[typo]\nfast=true",
            "[broken",
            '[match_plans]\nscope="single"\nteams=[]',
            '[match_plans]\nscope="all"\nteams=["77"]',
            '[match_plans]\nengine="invalid"',
            "[match_plans]\nteams=[77]",
            '[match_plans]\neffort="invalid"',
        ):
            self.config.write_text(content)
            with (
                self.subTest(content=content),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                self.parse(
                    "--config",
                    str(self.config),
                    "--players-csv",
                    str(self.root / "p.csv"),
                    "--teams-players-csv",
                    str(self.root / "m.csv"),
                    "--rosters-csv",
                    str(self.root / "r.csv"),
                    "--formations-csv",
                    str(self.root / "f.csv"),
                    "--preset-mode",
                    "single",
                )
            self.assertEqual(error.exception.code, 2)
        self.config.unlink()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parse("--config", str(self.config))

    def test_scope_cli_conflicts_and_single_command_rejects_batches(self) -> None:
        for extra in (
            ("--scope", "all", "--team", "77"),
            ("--scope", "multiple", "--team", "77"),
        ):
            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                self.parse("--config", str(self.config), *extra)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parse("--config", str(self.config), "--scope", "all", single_team=True)


if __name__ == "__main__":
    unittest.main()
