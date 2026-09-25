"""Validate portable imports and real headless CSV commits."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Iterable, Mapping
from pathlib import Path
from unittest import mock

import setup_env
from pes_workflows import claude_cli
from pes_workflows import generate_match_plan as single
from pes_workflows.application import assembled_injection
from pes_workflows.compiler import injection as formation_injection
from pes_workflows.compiler.compile import compile_semantic_game_plan
from pes_workflows.compiler.mappings import FORMATION_ROSTER_SIZE, ROLE_COLUMN_ORDER
from pes_workflows.contracts.assembly import assemble_semantic_game_plan
from pes_workflows.contracts.bench import validate_bench_decision
from pes_workflows.contracts.preset import validate_preset_plan
from pes_workflows.contracts.strategy import validate_starting_xi_lock
from pes_workflows.domain.vocabulary import POSITION_IDS
from pes_workflows.player_attributes.sources import PlayerDesignTarget
from tests.attribute_fixtures import write_attribute_targets_csv
from tests.match_fixtures import POSITIONS, preset_raw, source_identity, strategy_raw


def write_csv(path: Path, rows: Iterable[Mapping[str, str]]) -> None:
    entries = list(rows)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(entries[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(entries)


class StandaloneTests(unittest.TestCase):
    def test_setup_creates_isolated_venv_and_preserves_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "checkout with spaces"
            project.mkdir()
            (project / "pes-workflows.example.toml").write_text(
                '[defaults]\nplayers_csv="/exports/custom.csv"\n'
            )
            real_run = subprocess.run
            installs = []

            def run(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess:
                if "pip" in command:
                    installs.append((command, kwargs))
                    return subprocess.CompletedProcess(command, 0)
                return real_run(command, **kwargs)

            with mock.patch.object(setup_env.subprocess, "run", side_effect=run):
                environment = setup_env.initialize(project)
                config = project / "pes-workflows.toml"
                self.assertEqual(
                    config.read_text(),
                    (project / "pes-workflows.example.toml").read_text(),
                )
                config.write_text("# custom settings\n")
                setup_env.initialize(project, dev=True)
            self.assertIn(
                "include-system-site-packages = false",
                (environment / "pyvenv.cfg").read_text(),
            )
            self.assertEqual(config.read_text(), "# custom settings\n")
            self.assertEqual(len(installs), 2)
            for (command, kwargs), suffix in zip(installs, ("", "[dev]")):
                self.assertEqual(
                    command,
                    [
                        str(environment / "bin/python"),
                        "-I",
                        "-m",
                        "pip",
                        "--isolated",
                        "install",
                        "--editable",
                        str(project) + suffix,
                    ],
                )
                self.assertEqual(kwargs["cwd"], project)
            result = real_run(
                [
                    str(environment / "bin/python"),
                    "-I",
                    "-c",
                    "import sys; print(sys.prefix); assert sys.prefix != sys.base_prefix",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(result.stdout.strip(), str(environment))

    def test_setup_rejects_non_venv_and_does_not_claim_success_on_install_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".venv").mkdir()
            with self.assertRaisesRegex(RuntimeError, "non-venv"):
                setup_env.initialize(project)
            (project / ".venv/pyvenv.cfg").touch()
            with (
                mock.patch.object(setup_env.venv.EnvBuilder, "create"),
                mock.patch.object(
                    setup_env.subprocess,
                    "run",
                    side_effect=subprocess.CalledProcessError(1, "pip"),
                ),
                self.assertRaises(subprocess.CalledProcessError),
            ):
                setup_env.initialize(project)
            self.assertFalse((project / "pes-workflows.toml").exists())

    def test_copied_project_executes_with_no_parent_on_import_path(self) -> None:
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "standalone"
            shutil.copytree(
                project,
                checkout,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.egg-info",
                    ".venv",
                    "build",
                    ".ruff_cache",
                    ".mypy_cache",
                ),
            )
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            probe = (
                "import importlib, pathlib, pes_workflows; "
                "root = pathlib.Path(pes_workflows.__file__).parent; "
                "modules = [p for p in root.rglob('*.py') if p.name != '__init__.py']; "
                "[importlib.import_module('pes_workflows.' + '.'.join(p.relative_to(root).with_suffix('').parts)) for p in modules]; "
                "from pes_workflows.player_attributes.prompts import PlayerAttributePromptBuilder; "
                "assert '[PASTE ' not in PlayerAttributePromptBuilder()._system_prompt"
            )
            result = subprocess.run(
                [sys.executable, "-c", probe],
                cwd=checkout,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            for command in (
                "generate_match_plan",
                "batch_generate_match_plans",
                "batch_design_player_attributes",
            ):
                result = subprocess.run(
                    [sys.executable, "-m", "pes_workflows." + command, "--help"],
                    cwd=checkout,
                    env=environment,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                for option in (
                    "--players-csv",
                    "--teams-players-csv",
                    "--rosters-csv",
                    "--formations-csv",
                ):
                    self.assertIn(option, result.stdout)

    def test_custom_club_match_plan_commits_and_dry_run_preserves_database(
        self,
    ) -> None:
        identity = source_identity()
        xi = validate_starting_xi_lock(strategy_raw(), identity)
        bench_raw = {
            "Schema Version": "2.2",
            "Artifact": "BenchDecision",
            "Substitutes": [{"Player ID": "12"}],
        }
        bench = validate_bench_decision(bench_raw, xi, identity)
        main = validate_preset_plan(preset_raw("Main"), "Main", xi)
        plan = assemble_semantic_game_plan(
            identity, xi, {"Main": main}, bench, preset_mode="single"
        )
        compiled = compile_semantic_game_plan(plan, strict=True, preset_mode="single")
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            players = data / "people" / "attributes-custom.csv"
            memberships = data / "clubs" / "members-custom.csv"
            roster_path = data / "squads" / "lineups-custom.csv"
            formations = data / "tactics" / "plans-custom.csv"
            for path in (players, memberships, roster_path, formations):
                path.parent.mkdir()
            targets = tuple(
                PlayerDesignTarget(str(index), f"Player {index}", 25)
                for index in range(1, 13)
            )
            write_attribute_targets_csv(players, targets)
            with players.open(encoding="utf-8-sig") as stream:
                player_rows = list(csv.DictReader(stream, delimiter=";"))
            for row, position in zip(player_rows, [*POSITIONS, "GK"]):
                row.update(
                    {
                        "POS": str(POSITION_IDS[position]),
                        position: "2",
                        "Height": "180",
                        "Weight": "75",
                    }
                )
            write_csv(players, player_rows)
            write_csv(
                memberships,
                (
                    {
                        "Id": target.player_id,
                        "Name": target.name,
                        "Id Club": "77",
                        "Club": "Custom Squad",
                        "Id National": "0",
                        "National": "",
                    }
                    for target in targets
                ),
            )
            roster = {"Id": "77", "TotalPlayers": "12"}
            roster.update(
                {f"Player{i}": str(i) if i <= 12 else "0" for i in range(1, 41)}
            )
            write_csv(roster_path, [roster])
            formation = {"Id": "77", **dict.fromkeys(compiled["flat_columns"], "0")}
            formation.update(dict.fromkeys(ROLE_COLUMN_ORDER, "255"))
            formation.update(
                {f"IndexPlayer{i}": "255" for i in range(1, FORMATION_ROSTER_SIZE + 1)}
            )
            write_csv(formations, [formation])
            before = formations.read_bytes()
            replies = [strategy_raw(), preset_raw("Main"), bench_raw]
            for dry_run in (True, False):
                processes = []
                for reply in replies:
                    process = mock.Mock(returncode=0)
                    process.communicate.return_value = (json.dumps(reply), "")
                    processes.append(process)
                arguments = [
                    "match",
                    "--players-csv",
                    str(players),
                    "--teams-players-csv",
                    str(memberships),
                    "--rosters-csv",
                    str(roster_path),
                    "--formations-csv",
                    str(formations),
                    "--output-dir",
                    str(data),
                    "--team",
                    "Custom Squad",
                    "--preset-mode",
                    "single",
                    "--auto-substitutions",
                    "3",
                    "--auto-change-att-def",
                    "1",
                    "--auto-switch-preset-tactics",
                    "1",
                    "--delay",
                    "0",
                ]
                if dry_run:
                    arguments.append("--dry-run")
                with (
                    mock.patch.object(sys, "argv", arguments),
                    mock.patch.object(
                        claude_cli.subprocess, "Popen", side_effect=processes
                    ),
                    mock.patch.object(
                        assembled_injection,
                        "compile_semantic_game_plan",
                        wraps=compile_semantic_game_plan,
                    ) as compile_plan,
                    mock.patch.object(
                        formation_injection,
                        "compile_semantic_game_plan",
                        side_effect=AssertionError(
                            "Already compiled plans must not be recompiled"
                        ),
                    ),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(single.main(), 0)
                compile_plan.assert_called_once()
                for key, value in {
                    "auto_substitutions": 3,
                    "auto_change_att_def": 1,
                    "auto_switch_preset_tactics": 1,
                }.items():
                    self.assertEqual(compile_plan.call_args.kwargs[key], value)
                registry = data / single.COMPLETION_REGISTRY_NAME
                if dry_run:
                    self.assertEqual(formations.read_bytes(), before)
                    self.assertFalse(registry.exists())
                else:
                    self.assertNotEqual(formations.read_bytes(), before)
                    with formations.open(encoding="utf-8-sig") as stream:
                        row = next(csv.DictReader(stream, delimiter=";"))
                    self.assertEqual(row["AutoSubstitutions"], "3")
                    self.assertEqual(row["AutoChangeAttDef"], "1")
                    self.assertEqual(row["SwitchTactics"], "1")
                    self.assertEqual(registry.read_text(), "77\tCustom Squad\n")
            output = data
            self.assertFalse(list(output.rglob("Full_Game_Plan*")))
            self.assertFalse(list(output.rglob("Turn_*.md")))
            manifests = list(output.rglob("run_manifest.json"))
            self.assertEqual(len(manifests), 2)
            for manifest_path in manifests:
                manifest = json.loads(manifest_path.read_text())
                self.assertEqual(
                    manifest["targets"],
                    {
                        "players_csv": str(players),
                        "teams_players_csv": str(memberships),
                        "rosters_csv": str(roster_path),
                        "formations_csv": str(formations),
                    },
                )
                self.assertIn(manifest["status"], ("generated", "injected"))
                self.assertEqual(
                    manifest["global_auto_options"],
                    {
                        "auto_substitutions": 3,
                        "auto_change_att_def": 1,
                        "auto_switch_preset_tactics": 1,
                    },
                )
                self.assertTrue(
                    (
                        manifest_path.parent
                        / manifest["artifacts"]["semantic_game_plan"]
                    ).is_file()
                )
            # The direct injection API must preserve explicit settings too.
            for mode, switch in (("single", 1), ("multi", 0)):
                with self.subTest(mode=mode):
                    self.assertTrue(
                        formation_injection.process_formation_data(
                            roster_path,
                            formations,
                            plan,
                            players_csv=players,
                            strict=True,
                            preset_mode=mode,
                            auto_substitutions=0,
                            auto_change_att_def=1,
                            auto_switch_preset_tactics=switch,
                            report=lambda _: None,
                        )
                    )
                    with formations.open(encoding="utf-8-sig") as stream:
                        row = next(csv.DictReader(stream, delimiter=";"))
                    self.assertEqual(row["AutoSubstitutions"], "0")
                    self.assertEqual(row["AutoChangeAttDef"], "1")
                    self.assertEqual(row["SwitchTactics"], str(switch))
            before_invalid = formations.read_bytes()
            with mock.patch.object(formation_injection.pd, "read_csv") as read_csv:
                self.assertFalse(
                    formation_injection.process_formation_data(
                        roster_path,
                        formations,
                        plan,
                        players_csv=players,
                        auto_substitutions=True,
                        report=lambda _: None,
                    )
                )
            read_csv.assert_not_called()
            self.assertEqual(formations.read_bytes(), before_invalid)
