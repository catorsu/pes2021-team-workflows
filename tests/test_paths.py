"""WSL path translation, generated configuration, and workflow output contracts."""

import argparse
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import setup_env
from pes_workflows import paths
from pes_workflows.config import load_configuration, parse_workflow_args
from pes_workflows.csv_validation import validate_csv_target
from pes_workflows.generate_match_plan import add_match_plan_arguments, match_plan_paths


class PathTests(unittest.TestCase):
    def test_linux_and_home_paths_do_not_invoke_translation(self) -> None:
        with mock.patch.object(paths.subprocess, "run") as run:
            for value in (
                "/home/user/Players.csv",
                "~/data",
            ):
                self.assertEqual(paths.normalize_path(value), Path(value).expanduser())
            expected_mnt = (
                Path("C:/PES Data/Players.csv")
                if os.name == "nt"
                else Path("/mnt/c/PES Data/Players.csv")
            )
            self.assertEqual(
                paths.normalize_path("/mnt/c/PES Data/Players.csv"),
                expected_mnt,
            )
            self.assertEqual(paths.normalize_path("reports"), Path("reports"))
        run.assert_not_called()

    @unittest.skipIf(os.name == "nt", "Windows paths are already native on Windows")
    def test_windows_paths_use_wsl_mount_translation(self) -> None:
        for value in (
            r"C:\PES Data\Players.csv",
            "D:/PES Data/Players.csv",
            r"\\server\share\Players.csv",
        ):
            with (
                self.subTest(value=value),
                mock.patch.object(paths, "is_wsl", return_value=True),
                mock.patch.object(
                    paths.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        [], 0, "/custom-mount/PES Data/Players.csv\n", ""
                    ),
                ) as run,
            ):
                self.assertEqual(
                    paths.normalize_path(value),
                    Path("/custom-mount/PES Data/Players.csv"),
                )
                self.assertEqual(run.call_args.args[0], ["wslpath", "-u", value])
                self.assertNotIn("shell", run.call_args.kwargs)

    @unittest.skipIf(os.name == "nt", "Translation applies on Linux")
    def test_invalid_or_untranslatable_windows_paths_fail_clearly(self) -> None:
        with mock.patch.object(paths, "is_wsl", return_value=False):
            with self.assertRaisesRegex(ValueError, "absolute Linux path"):
                paths.normalize_path("C:/data/Players.csv")
        with mock.patch.object(paths, "is_wsl", return_value=True):
            with self.assertRaisesRegex(ValueError, "drive root"):
                paths.normalize_path("C:Players.csv")
            for failure in (
                FileNotFoundError(),
                subprocess.CalledProcessError(1, "wslpath"),
            ):
                with mock.patch.object(paths.subprocess, "run", side_effect=failure):
                    with self.assertRaisesRegex(ValueError, "mounted WSL path"):
                        paths.normalize_path("C:/Players.csv")

    @unittest.skipIf(os.name == "nt", "Tests the WSL parser boundary")
    def test_toml_and_cli_paths_are_translated_before_file_validation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="PES paths ") as directory:
            root = Path(directory)
            csv = root / "Players.csv"
            csv.write_text("Id;Name\n1;Player\n")
            settings = root / "settings.toml"
            settings.write_text(
                "[defaults]\n"
                + "".join(
                    f"{key}='C:\\PES Data\\Players.csv'\n"
                    for key in (
                        "players_csv",
                        "teams_players_csv",
                        "rosters_csv",
                        "formations_csv",
                    )
                )
                + "[match_plan]\npreset_mode='single'\nteams=['77']\n"
                + "output_dir='C:/PES Data/reports'\n"
                + "attributes_completed_teams='C:/PES Data/done.txt'\n"
            )

            def translate(
                cmd: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                mapped = root / Path(cmd[-1].replace("\\", "/")).name
                return subprocess.CompletedProcess(cmd, 0, str(mapped) + "\n", "")

            with (
                mock.patch.object(paths, "is_wsl", return_value=True),
                mock.patch.object(paths.subprocess, "run", side_effect=translate),
            ):
                parser = argparse.ArgumentParser()
                add_match_plan_arguments(parser)
                parser.add_argument("--team")
                args = parse_workflow_args(
                    parser,
                    "match_plan",
                    [
                        "--config",
                        str(settings),
                        "--rosters-csv",
                        "D:/PES Data/Players.csv",
                        "--output-dir",
                        "D:/PES Data/override",
                        "--attributes-completed-teams",
                        "D:/PES Data/new.txt",
                    ],
                )
            self.assertEqual(args.players_csv, csv)
            self.assertEqual(args.rosters_csv, csv)
            self.assertEqual(args.output_dir, root / "override")
            self.assertEqual(args.attributes_completed_teams, root / "new.txt")
            validate_csv_target(args.players_csv)
            self.assertEqual(csv.read_text(), "Id;Name\n1;Player\n")

    @unittest.skipUnless(paths.is_wsl(), "Requires actual WSL mounted storage")
    def test_real_windows_hosted_file_can_be_translated_and_validated(self) -> None:
        project = Path(__file__).resolve().parents[1]
        if not project.as_posix().startswith("/mnt/"):
            self.skipTest("Checkout is not on a Windows-mounted drive")
        with tempfile.TemporaryDirectory(
            prefix=".wsl-path-test-", dir=project
        ) as directory:
            csv = Path(directory) / "Players with spaces.csv"
            csv.write_text("Id;Name\n1;Player\n")
            windows = subprocess.run(
                ["wslpath", "-w", str(csv)], check=True, capture_output=True, text=True
            ).stdout.strip()
            translated = paths.normalize_path(windows)
            self.assertEqual(translated, csv)
            validate_csv_target(translated)
            self.assertEqual(csv.read_text(), "Id;Name\n1;Player\n")

    def test_windows_drive_relative_rejected_and_agy_executable_resolved(self) -> None:
        with self.assertRaisesRegex(ValueError, "drive root"):
            paths.normalize_path("C:Players.csv")
        self.assertFalse(paths.is_absolute_path(Path("relative/Players.csv")))
        self.assertTrue(paths.is_absolute_path(Path("/mnt/c/PES Data/Players.csv")))
        with tempfile.TemporaryDirectory() as directory:
            fake_bin = Path(directory) / "agy" / "bin"
            fake_bin.mkdir(parents=True)
            exe_name = "agy.exe" if os.name == "nt" else "agy"
            fake_exe = fake_bin / exe_name
            fake_exe.write_text("binary", encoding="utf-8")
            with (
                mock.patch.object(paths.shutil, "which", return_value=None),
                mock.patch.dict(
                    os.environ, {"LOCALAPPDATA": directory, "PATH": ""}, clear=False
                ),
            ):
                if os.name == "nt":
                    self.assertEqual(paths.resolve_agy_executable(), fake_exe)
                    env = {"PATH": ""}
                    resolved = paths.ensure_agy_on_path(env)
                    self.assertEqual(resolved, "agy")
                    self.assertIn(str(fake_bin), env["PATH"])

    def test_claude_and_codex_executable_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local_bin = root / "home" / ".local" / "bin"
            local_bin.mkdir(parents=True)
            claude_exe = local_bin / ("claude.exe" if os.name == "nt" else "claude")
            claude_exe.write_text("binary", encoding="utf-8")

            codex_bin = root / "localappdata" / "OpenAI" / "Codex" / "bin" / "rev123"
            codex_bin.mkdir(parents=True)
            codex_exe = codex_bin / ("codex.exe" if os.name == "nt" else "codex")
            codex_exe.write_text("binary", encoding="utf-8")

            npm_dir = root / "appdata" / "npm"
            npm_dir.mkdir(parents=True)
            codex_cmd = npm_dir / "codex.cmd"
            codex_cmd.write_text("@echo off\n", encoding="utf-8")

            override_dir = root / "custom_override"
            override_dir.mkdir(parents=True)
            override_claude = override_dir / "claude-custom.exe"
            override_claude.write_text("binary", encoding="utf-8")
            override_codex = override_dir / "codex.exe"
            override_codex.write_text("binary", encoding="utf-8")
            override_agy = override_dir / "agy.cmd"
            override_agy.write_text("@echo off\n", encoding="utf-8")

            path_hit = root / "path_bin" / "claude.exe"
            path_hit.parent.mkdir(parents=True)
            path_hit.write_text("binary", encoding="utf-8")

            with (
                mock.patch.object(paths.shutil, "which", return_value=str(path_hit)),
                mock.patch.dict(
                    os.environ,
                    {
                        "PES_CLAUDE_BIN": str(override_claude),
                        "PES_CODEX_BIN": str(override_codex),
                        "PES_AGY_BIN": str(override_agy),
                        "PATH": "",
                    },
                    clear=False,
                ),
            ):
                # Priority 1: Explicit PES_*_BIN environment variable overrides PATH and fallbacks
                self.assertEqual(paths.resolve_claude_executable(), override_claude)
                env_override_claude = {"PATH": ""}
                self.assertEqual(
                    paths.ensure_claude_on_path(env_override_claude),
                    str(override_claude),
                )
                self.assertTrue(
                    env_override_claude["PATH"].startswith(str(override_dir))
                )

                self.assertEqual(paths.resolve_codex_executable(), override_codex)
                env_override_codex = {"PATH": r"C:\other\bin"}
                self.assertEqual(
                    paths.ensure_codex_on_path(env_override_codex), "codex"
                )
                self.assertEqual(
                    env_override_codex["PATH"].split(os.pathsep)[0], str(override_dir)
                )

                self.assertEqual(paths.resolve_agy_executable(), override_agy)
                env_override_agy = {"PATH": ""}
                self.assertEqual(
                    paths.ensure_agy_on_path(env_override_agy), str(override_agy)
                )

            with (
                mock.patch.object(paths.shutil, "which", return_value=str(path_hit)),
                mock.patch.dict(
                    os.environ,
                    {
                        "PES_CLAUDE_BIN": "",
                        "PES_CODEX_BIN": "",
                        "PES_AGY_BIN": "",
                        "USERPROFILE": str(root / "home"),
                        "PATH": "",
                    },
                    clear=False,
                ),
            ):
                # Priority 2: System PATH lookup via shutil.which takes precedence over standard fallbacks
                self.assertEqual(paths.resolve_claude_executable(), path_hit)

            with (
                mock.patch.object(paths.shutil, "which", return_value=None),
                mock.patch.dict(
                    os.environ,
                    {
                        "PES_CLAUDE_BIN": "",
                        "PES_CODEX_BIN": "",
                        "PES_AGY_BIN": "",
                        "USERPROFILE": str(root / "home"),
                        "LOCALAPPDATA": str(root / "localappdata"),
                        "APPDATA": str(root / "appdata"),
                        "ProgramFiles": str(root / "programfiles"),
                        "PATH": "",
                    },
                    clear=False,
                ),
            ):
                # Priority 3: Standard Windows installation directory fallbacks
                if os.name == "nt":
                    self.assertEqual(paths.resolve_claude_executable(), claude_exe)
                    env_claude = {"PATH": ""}
                    self.assertEqual(paths.ensure_claude_on_path(env_claude), "claude")
                    self.assertIn(str(local_bin), env_claude["PATH"])

                    self.assertEqual(paths.resolve_codex_executable(), codex_exe)
                    env_codex = {"PATH": ""}
                    self.assertEqual(paths.ensure_codex_on_path(env_codex), "codex")
                    self.assertIn(str(codex_bin), env_codex["PATH"])

                    codex_exe.unlink()
                    self.assertEqual(paths.resolve_codex_executable(), codex_cmd)
                    env_cmd = {"PATH": ""}
                    self.assertEqual(
                        paths.ensure_codex_on_path(env_cmd), str(codex_cmd)
                    )
                    self.assertIn(str(npm_dir), env_cmd["PATH"])


class OutputConfigurationTests(unittest.TestCase):
    def test_setup_copies_active_output_paths_and_preserves_local_settings(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            template = (
                Path(__file__).resolve().parents[1] / "pes-workflows.example.toml"
            )
            shutil.copy2(template, project / template.name)
            with (
                mock.patch.object(setup_env.venv.EnvBuilder, "create"),
                mock.patch.object(setup_env.subprocess, "run"),
            ):
                setup_env.initialize(project)
                configuration = project / "pes-workflows.toml"
                loaded = load_configuration(configuration)
                for key, filename in (
                    ("players_csv", "Players.csv"),
                    ("teams_players_csv", "Teams-Players.csv"),
                    ("rosters_csv", "Rosters.csv"),
                    ("formations_csv", "Formations.csv"),
                ):
                    self.assertEqual(
                        loaded["defaults"][key],
                        (Path.home() / "PES2021" / filename).resolve(),
                    )
                for workflow in ("match_plan", "match_plans", "player_attributes"):
                    self.assertEqual(
                        loaded[workflow]["output_dir"], project / "outputs" / workflow
                    )
                configuration.write_text("# user settings\n")
                setup_env.initialize(project)
                self.assertEqual(configuration.read_text(), "# user settings\n")

    def test_default_outputs_and_registries_distinguish_workflows_and_modes(
        self,
    ) -> None:
        registries = set()
        for workflow in ("match_plan", "match_plans"):
            for mode in ("single", "multi"):
                output, registry = match_plan_paths(None, mode, workflow=workflow)
                self.assertEqual(output, Path.cwd() / "outputs" / workflow)
                self.assertEqual(
                    registry.name, f"completed_teams_{workflow}_{mode}.txt"
                )
                registries.add(registry.name)
        self.assertEqual(len(registries), 4)
