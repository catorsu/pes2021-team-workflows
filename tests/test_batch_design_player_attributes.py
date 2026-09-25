from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from pes_workflows import batch_design_player_attributes as batch
from pes_workflows import claude_cli
from pes_workflows.player_attributes.injection import PlayerInjectionResult
from tests.attribute_fixtures import (
    abilities_artifact,
    make_targets,
    profiles_artifact,
    write_attribute_targets_csv,
)


class BatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.out = self.data / "output"
        (self.data / "Players.csv").write_text("original")
        (self.data / "Teams-Players.csv").write_text("memberships")
        self.teams = [
            {"id": str(i), "name": f"Team {i}", "kind": "Club", "player_ids": [str(i)]}
            for i in range(1, 4)
        ]
        self.failed = []
        self.runs = []

    def preflight(
        self,
        players: Path,
        memberships: Path,
        *,
        team_id: str | None = None,
        team_name: str | None = None,
    ) -> tuple[dict[str, Any], object]:
        logging.info("Offline preflight: checked")
        teams, failed = self.teams, self.failed
        selection = {}
        if team_id is not None or team_name is not None:
            candidates = [
                entry
                for entry in teams + failed
                if (
                    entry["id"] == team_id
                    if team_id is not None
                    else entry.get("name") == team_name
                )
            ]
            if len(candidates) != 1:
                raise ValueError("Team selection must match exactly one team")
            selected_id = candidates[0]["id"]
            teams = [entry for entry in teams if entry["id"] == selected_id]
            failed = [entry for entry in failed if entry["id"] == selected_id]
            selection = {"selection": selected_id}
        return {
            **selection,
            "team_count": len(teams) + len(failed),
            "player_count": sum(len(entry["player_ids"]) for entry in teams),
            "teams": teams,
            "failed": failed,
            "players_sha256": batch.digest(self.data / "Players.csv"),
            "memberships_sha256": batch.digest(self.data / "Teams-Players.csv"),
            "policy_sha256": "policy",
        }, object()

    def run_team(
        self, *, team: Any, targets: Any, players_csv: Path
    ) -> SimpleNamespace:
        before = batch.digest(players_csv)
        players_csv.write_text(players_csv.read_text() + team.name)
        self.runs.append(team.name)
        return SimpleNamespace(
            injection=PlayerInjectionResult(
                1, before, batch.digest(players_csv), False
            ),
            config_path=self.out / "config.json",
            manifest_path=self.out / "manifest.json",
            report_path=self.data / "Teams-Players.csv",
            manifest_finalized=True,
        )

    def invoke(self, *args: Any) -> tuple[int, str]:
        root = logging.getLogger()
        handlers, level = root.handlers[:], root.level
        console = io.StringIO()
        try:
            with (
                contextlib.redirect_stdout(console),
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "batch",
                        "--players-csv",
                        str(self.data / "Players.csv"),
                        "--teams-players-csv",
                        str(self.data / "Teams-Players.csv"),
                        "--output",
                        str(self.out),
                        *args,
                    ],
                ),
                mock.patch.object(batch, "preflight", side_effect=self.preflight),
                mock.patch.object(
                    batch, "verify", return_value={"verified_players": len(self.runs)}
                ),
                mock.patch.object(batch, "AuditedAdapter") as adapter,
                mock.patch.object(batch, "PlayerAttributeRunner") as runner,
                mock.patch.object(
                    batch,
                    "resolve_design_targets",
                    side_effect=lambda **kw: (
                        SimpleNamespace(name=f"Team {kw['team_id']}"),
                        [],
                    ),
                ),
            ):
                runner.return_value.run.side_effect = self.run_team
                code = batch.main()
                self.adapter_kwargs = (
                    adapter.call_args.kwargs if adapter.called else None
                )
            return code, console.getvalue()
        finally:
            for handler in root.handlers[:]:
                if handler not in handlers:
                    root.removeHandler(handler)
                    handler.close()
            root.setLevel(level)

    def state(self) -> dict[str, Any]:
        return json.loads((self.out / "batch_state.json").read_text())

    def test_model_effort_and_turn_defaults_reach_adapter(self) -> None:
        self.assertEqual(self.invoke("--no-config")[0], 0)
        self.assertEqual(self.adapter_kwargs["model"], "claude-opus-5-5")
        self.assertEqual(self.adapter_kwargs["effort"], "high")
        self.assertEqual(self.adapter_kwargs["max_turns"], 80)

    def test_configured_turn_limit_and_cli_override_reach_adapter(self) -> None:
        config = self.data / "settings.toml"
        config.write_text("[player_attributes]\nmax_turns=23\n")
        self.assertEqual(self.invoke("--config", str(config), "--max-teams", "1")[0], 1)
        self.assertEqual(self.adapter_kwargs["max_turns"], 23)
        self.assertEqual(
            self.invoke("--config", str(config), "--max-turns", "19")[0], 0
        )
        self.assertEqual(self.adapter_kwargs["max_turns"], 19)

    def test_invalid_turn_limits_and_efforts_fail_before_work(self) -> None:
        config = self.data / "settings.toml"
        for value in ("0", "-1", "true", "1.5", '"80"', "[]", "inf"):
            config.write_text(f"[player_attributes]\nmax_turns={value}\n")
            with (
                self.subTest(value=value),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                self.invoke("--config", str(config))
            self.assertEqual(error.exception.code, 2)
        for section in ("defaults", "match_plan", "match_plans"):
            config.write_text(f"[{section}]\nmax_turns=80\n")
            with (
                self.subTest(section=section),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                self.invoke("--config", str(config))
        config.write_text('[player_attributes]\neffort="invalid"\n')
        for args in (
            ("--config", str(config)),
            *(
                ("--no-config", "--max-turns", value)
                for value in ("0", "-1", "1.5", "true")
            ),
            ("--no-config", "--effort", "invalid"),
        ):
            with (
                self.subTest(args=args),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                self.invoke(*args)
        self.assertEqual(self.runs, [])
        self.assertFalse(self.out.exists())

    def test_selected_team_runs_and_resumes_by_name_or_id(self) -> None:
        self.teams[1]["player_ids"] = ["2", "20", "21"]
        self.failed = [{"id": "4", "name": "Other", "error": "invalid target"}]
        code, console = self.invoke("--team-id", "2")
        self.assertEqual(code, 0)
        self.assertEqual(self.runs, ["Team 2"])
        self.assertIn("[1/1] Team 2: 3 players", console)
        self.assertEqual(self.state()["selection"], "2")
        self.assertEqual(self.state()["player_count"], 3)
        self.assertEqual(self.state()["teams"], [self.teams[1]])
        self.assertEqual((self.data / "Players.csv").read_text(), "originalTeam 2")
        code, _ = self.invoke("--team", "Team 2")
        self.assertEqual(code, 0)
        self.assertEqual(self.runs, ["Team 2"])

    def test_selection_cannot_change_in_existing_checkpoint(self) -> None:
        self.invoke("--team-id", "2")
        for args in [("--team-id", "3"), ()]:
            with (
                self.subTest(args=args),
                self.assertRaisesRegex(RuntimeError, "Team selection changed"),
            ):
                self.invoke(*args)
        self.assertEqual(self.runs, ["Team 2"])

    def test_unknown_or_ambiguous_selection_never_models(self) -> None:
        for args in [("--team-id", "99"), ("--team", "missing")]:
            with (
                self.subTest(args=args),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                self.invoke(*args)
            self.assertEqual(error.exception.code, 2)
        self.teams[2]["name"] = "Team 2"
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.invoke("--team", "Team 2")
        self.assertEqual(self.runs, [])
        self.assertEqual((self.data / "Players.csv").read_text(), "original")

    def test_selected_preflight_failure_is_not_reported_as_success(self) -> None:
        self.failed = [{"id": "4", "name": "Bad team", "error": "invalid target"}]
        with mock.patch.object(batch, "save") as save:
            code, _ = self.invoke("--team-id", "4", "--check-only")
        self.assertEqual(code, 1)
        report = save.call_args.args[1]
        self.assertEqual(report["teams"], [])
        self.assertEqual(report["failed"], self.failed)
        self.assertEqual(self.runs, [])

    def test_two_team_commit_and_resume(self) -> None:
        code, console = self.invoke("--max-teams", "2")
        self.assertEqual(code, 1)
        state = self.state()
        self.assertEqual(set(state["completed"]), {"1", "2"})
        self.assertEqual(
            (self.out / "completed_teams_player_attributes.txt").read_text(),
            "1\tTeam 1\n2\tTeam 2\n",
        )
        self.assertEqual(
            state["current_players_sha256"], batch.digest(self.data / "Players.csv")
        )
        self.assertNotIn("extended", state["completed"]["1"])
        for output in (console, (self.out / "batch.log").read_text()):
            self.assertIn("Offline preflight: checked", output)
            self.assertIn("[1/3] Team 1", output)
        code, _ = self.invoke("--max-teams", "2")
        self.assertEqual(code, 0)
        self.assertEqual(self.state()["status"], "complete")
        self.assertEqual(self.runs, ["Team 1", "Team 2", "Team 3"])
        self.assertEqual(
            (self.out / "completed_teams_player_attributes.txt").read_text(),
            "1\tTeam 1\n2\tTeam 2\n3\tTeam 3\n",
        )

    def test_registry_without_checkpoint_does_not_claim_reports_exist(self) -> None:
        self.out.mkdir()
        record = self.out / "completed_teams_player_attributes.txt"
        record.write_text(" 1 \n\n1\n2")
        code, console = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.runs, ["Team 1", "Team 2", "Team 3"])
        self.assertEqual(record.read_text(), "1\tTeam 1\n2\tTeam 2\n3\tTeam 3\n")
        self.assertIn('"completed_teams": 3', console)

    def test_checkpoint_recovers_interrupted_registry_write(self) -> None:
        self.invoke("--max-teams", "2")
        record = self.out / "completed_teams_player_attributes.txt"
        record.unlink()
        code, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.runs, ["Team 1", "Team 2", "Team 3"])
        self.assertEqual(record.read_text(), "1\tTeam 1\n2\tTeam 2\n3\tTeam 3\n")

    def test_failure_or_interruption_before_csv_write_is_not_recorded(self) -> None:
        for error in (OSError("CSV write failed"), KeyboardInterrupt()):
            with (
                self.subTest(error=type(error).__name__),
                mock.patch.object(self, "run_team", side_effect=error),
            ):
                if isinstance(error, KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        self.invoke("--max-teams", "1")
                else:
                    code, _ = self.invoke("--max-teams", "1")
                    self.assertEqual(code, 1)
                self.assertEqual(
                    (self.out / "completed_teams_player_attributes.txt").read_text(), ""
                )
                self.assertEqual(self.state()["completed"], {})

    def test_record_is_written_after_csv_and_checkpoint_and_recovers_on_failure(
        self,
    ) -> None:
        save_record = batch.save_completed_teams

        def fail_after_commit(path: Path, team_ids: Mapping[str, str]) -> None:
            if "1" in team_ids:
                self.assertEqual(
                    (self.data / "Players.csv").read_text(), "originalTeam 1"
                )
                self.assertIn("1", self.state()["completed"])
                raise OSError("Record write failed")
            save_record(path, team_ids)

        with mock.patch.object(
            batch, "save_completed_teams", side_effect=fail_after_commit
        ):
            with self.assertRaisesRegex(OSError, "Record write failed"):
                self.invoke()
        self.assertEqual(
            (self.out / "completed_teams_player_attributes.txt").read_text(), ""
        )
        code, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.runs, ["Team 1", "Team 2", "Team 3"])
        self.assertEqual(
            (self.out / "completed_teams_player_attributes.txt").read_text(),
            "1\tTeam 1\n2\tTeam 2\n3\tTeam 3\n",
        )

    def test_preflight_failure_remains_incomplete(self) -> None:
        self.failed = [{"id": "4", "error": "invalid target"}]
        code, _ = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(len(self.state()["completed"]), 3)
        self.assertEqual(self.state()["status"], "incomplete")

    def test_usage_limit_exits_without_attempting_next_team_and_can_resume(
        self,
    ) -> None:
        self.invoke("--max-teams", "1")
        for message in (
            "Claude Code exited abnormally (Code 1):\nSTDOUT:\n"
            "You've hit your session limit · resets 11:20am (America/Los_Angeles)",
            "Usage limit reached",
            "Weekly limit reached",
        ):
            with (
                self.subTest(message=message),
                mock.patch.object(
                    self, "run_team", side_effect=RuntimeError(message)
                ) as run,
            ):
                code, console = self.invoke()
                self.assertEqual(code, 1)
                run.assert_called_once()
                self.assertIn("progress saved. Exiting.", console)
                self.assertNotIn("Traceback", console)
                self.assertNotIn('"verified_players"', console)
                self.assertEqual(self.state()["status"], "incomplete")
                self.assertEqual(set(self.state()["completed"]), {"1"})
                self.assertEqual(self.state()["failures"]["2"], message)
                self.assertEqual(
                    (self.out / "completed_teams_player_attributes.txt").read_text(),
                    "1\tTeam 1\n",
                )
        code, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.runs, ["Team 1", "Team 2", "Team 3"])

    def test_check_only_logs_to_console(self) -> None:
        with mock.patch.object(batch, "save"):
            code, console = self.invoke("--check-only")
        self.assertEqual(code, 0)
        self.assertIn("Offline preflight: checked", console)
        self.assertFalse((self.out / "batch_state.json").exists())


class ScopedPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        self.players = write_attribute_targets_csv(
            self.data / "Players.csv", make_targets(2)
        )
        self.memberships = self.data / "Teams-Players.csv"
        self.memberships.write_text(
            "Id;Name;Id Club;Club;Id National;National\n"
            "101;Player 1;71;Selected;0;\n"
            "102;Player 2;72;Other;0;\n"
        )

    def test_cli_limits_real_preflight_in_check_and_run_modes(self) -> None:
        # Unrelated invalid player IDs and team identities must never be validated.
        self.players.write_text(self.players.read_text().replace("102;", "bad;"))
        with self.memberships.open("a") as stream:
            stream.write("bad;Broken;bad;;0;\n")
        for selector in (("--team-id", "71"), ("--team", "Selected")):
            for check_only in (True, False):
                with self.subTest(selector=selector, check_only=check_only):
                    output = self.data / f"out-{selector[0]}-{check_only}"
                    args = [
                        "batch",
                        "--players-csv",
                        str(self.data / "Players.csv"),
                        "--teams-players-csv",
                        str(self.data / "Teams-Players.csv"),
                        "--output",
                        str(output),
                        *selector,
                        *(["--check-only"] if check_only else []),
                    ]
                    with (
                        mock.patch.object(sys, "argv", args),
                        mock.patch.object(
                            batch,
                            "resolve_design_targets",
                            wraps=batch.resolve_design_targets,
                        ) as resolve,
                        mock.patch.object(
                            batch.PlayerAttributePromptBuilder,
                            "build_profiles_call",
                            return_value="prompt",
                        ) as build,
                        mock.patch.object(
                            batch,
                            "preflight_player_injection",
                            wraps=batch.preflight_player_injection,
                        ) as injection,
                        mock.patch.object(batch, "AuditedAdapter"),
                        mock.patch.object(batch, "PlayerAttributeRunner") as runner,
                        contextlib.redirect_stdout(io.StringIO()) as console,
                    ):
                        runner.return_value.run.side_effect = RuntimeError(
                            "offline stop"
                        )
                        self.assertEqual(batch.main(), 0 if check_only else 1)
                    self.assertEqual(
                        [call.kwargs["team_id"] for call in resolve.call_args_list],
                        ["71"] if check_only else ["71", "71"],
                    )
                    build.assert_called_once()
                    injection.assert_called_once_with(
                        players_csv=self.players, target_ids=["101"]
                    )
                    report = json.loads((output / "preflight.json").read_text())
                    self.assertEqual(report["team_count"], 1)
                    self.assertEqual(report["player_count"], 1)
                    self.assertEqual(report["failed"], [])
                    self.assertEqual(report["selection"], "71")
                    self.assertNotIn("Other", console.getvalue())
                    if not check_only:
                        state = json.loads((output / "batch_state.json").read_text())
                        self.assertEqual(state["team_count"], 1)
                        self.assertEqual(state["verification"]["target_csv_rows"], 1)
                        self.assertNotIn(
                            "unmodeled_rows_unchanged", state["verification"]
                        )

    def test_required_file_access_is_checked_offline_before_model_setup(self) -> None:
        for key in ("players_csv", "teams_players_csv"):
            for failure in ("missing", "directory", "read", "write"):
                paths = {
                    "players_csv": self.players,
                    "teams_players_csv": self.memberships,
                }
                if failure in ("missing", "directory"):
                    paths[key] = (
                        self.data / "absent.csv" if failure == "missing" else self.data
                    )
                denied_mode = os.R_OK if failure == "read" else os.W_OK
                arguments = [
                    "attributes",
                    "--no-config",
                    "--check-only",
                    "--output-dir",
                    str(self.data / "out"),
                    *[
                        item
                        for name, path in paths.items()
                        for item in ("--" + name.replace("_", "-"), str(path))
                    ],
                ]
                with (
                    self.subTest(key=key, failure=failure),
                    mock.patch.object(sys, "argv", arguments),
                    mock.patch(
                        "pes_workflows.csv_validation.os.access",
                        side_effect=lambda path, mode: (
                            not (path == paths[key] and mode == denied_mode)
                        ),
                    ),
                    mock.patch.object(batch, "AuditedAdapter") as adapter,
                    contextlib.redirect_stderr(io.StringIO()) as errors,
                    self.assertRaises(SystemExit) as caught,
                ):
                    batch.main()
                self.assertEqual(caught.exception.code, 2)
                self.assertIn(str(paths[key]), errors.getvalue())
                adapter.assert_not_called()

    def test_selected_roster_error_is_reported_and_full_batch_checks_all(self) -> None:
        self.players.write_text(self.players.read_text().replace("102;", "999;"))
        report, _ = batch.preflight(self.players, self.memberships, team_id="72")
        self.assertEqual(report["team_count"], 1)
        self.assertEqual(report["teams"], [])
        self.assertEqual([entry["id"] for entry in report["failed"]], ["72"])
        report, _ = batch.preflight(self.players, self.memberships)
        self.assertEqual(report["team_count"], 2)
        self.assertEqual([entry["id"] for entry in report["teams"]], ["71"])
        self.assertEqual([entry["id"] for entry in report["failed"]], ["72"])

    def test_scoped_verification_ignores_unrelated_changes(self) -> None:
        output = self.data / "verify"
        output.mkdir()
        (output / "Players.before.csv").write_bytes(self.players.read_bytes())
        self.players.write_text(self.players.read_text().replace("Player 2", "Changed"))
        state = {"selection": "71", "teams": [{"player_ids": ["101"]}], "completed": {}}
        self.assertEqual(
            batch.verify(state, output, self.players)["target_csv_rows"], 1
        )
        with self.assertRaisesRegex(RuntimeError, "CSV verification mismatch"):
            batch.verify({**state, "selection": None}, output, self.players)

    def test_config_multiple_selection_and_cli_replacement(self) -> None:
        config = self.data / "settings.toml"
        output = self.data / "configured-output"
        config.write_text(
            "[defaults]\ndelay=0\nfast=true\n"
            f'players_csv="{self.players}"\n'
            f'teams_players_csv="{self.memberships}"\n'
            '[player_attributes]\noutput_dir="configured-output"\n'
            'scope="multiple"\nteams=["Other", "71", "Selected"]\n'
            'check_only=true\nmax_teams=2\nmodel="configured"\neffort="high"\n'
        )
        for extra, ids in (
            ([], ["71", "72"]),
            (["--team", "Other"], ["72"]),
            (["--scope", "all"], ["71", "72"]),
        ):
            with (
                self.subTest(extra=extra),
                mock.patch.object(
                    sys, "argv", ["batch", "--config", str(config), *extra]
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(batch.main(), 0)
            report = json.loads((output / "preflight.json").read_text())
            self.assertEqual([team["id"] for team in report["teams"]], ids)
            self.assertEqual(
                report.get("selection"),
                None
                if extra == ["--scope", "all"]
                else (ids[0] if len(ids) == 1 else ids),
            )
        with (
            mock.patch.object(
                sys,
                "argv",
                ["batch", "--config", str(config), "--no-check-only", "--no-fast"],
            ),
            mock.patch.object(batch, "AuditedAdapter") as adapter,
            mock.patch.object(batch, "PlayerAttributeRunner") as runner,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            runner.return_value.run.side_effect = RuntimeError("offline stop")
            self.assertEqual(batch.main(), 1)
        self.assertEqual(
            adapter.call_args.kwargs,
            dict(
                model="configured",
                effort="high",
                delay=0,
                fast_mode=False,
                max_turns=80,
            ),
        )
        self.assertEqual(runner.return_value.run.call_count, 2)
        with (
            mock.patch.object(
                sys,
                "argv",
                ["batch", "--config", str(config), "--no-check-only", "--team", "71"],
            ),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(RuntimeError, "Team selection changed"),
        ):
            batch.main()

    def test_multiple_selection_excludes_invalid_unrelated_team(self) -> None:
        with self.memberships.open("a") as stream:
            stream.write("bad;Broken;bad;;0;\n")
        report, _ = batch.preflight(
            self.players, self.memberships, team_queries=["Other", "71", "Selected"]
        )
        self.assertEqual([entry["id"] for entry in report["teams"]], ["71", "72"])
        self.assertEqual(report["selection"], ["71", "72"])
        self.assertEqual(report["team_count"], 2)
        self.assertEqual(report["failed"], [])


class BatchTransportTests(unittest.TestCase):
    def test_real_adapter_stages_and_repair_keep_tools_audit_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            output = data / "audit"
            players = data / "people" / "custom-attributes.csv"
            memberships = data / "clubs" / "custom-members.csv"
            players.parent.mkdir()
            memberships.parent.mkdir()
            write_attribute_targets_csv(players, make_targets(2))
            memberships.write_text(
                "Id;Name;Id Club;Club;Id National;National\n"
                "101;Player 1;71;Club;1;National One\n"
                "102;Player 2;71;Club;2;National Two\n",
                encoding="utf-8",
            )
            before = players.read_bytes()
            team, targets = batch.resolve_design_targets(
                players_csv=players,
                memberships_csv=memberships,
                team_kind="national",
                team_id="1",
            )
            replies = [
                "{}",
                json.dumps(profiles_artifact(team, targets)),
                json.dumps(abilities_artifact(team, targets)),
            ]
            processes = []

            def popen(cmd: list[str], **kwargs: Any) -> mock.Mock:
                self.assertEqual(players.read_bytes(), before)
                self.assertEqual(cmd[0], "claude")
                for flag, value in [
                    ("--tools", "WebSearch,WebFetch"),
                    ("--allowedTools", "WebSearch,WebFetch"),
                    ("--max-turns", "37"),
                    ("--disallowedTools", "mcp__*"),
                    ("--output-format", "text"),
                    ("--model", "offline-model"),
                ]:
                    self.assertEqual(cmd[cmd.index(flag) + 1], value)
                self.assertEqual(
                    Path(cmd[cmd.index("--system-prompt-file") + 1]).read_text(),
                    batch.PlayerAttributePromptBuilder()._system_prompt,
                )
                self.assertIn("-p", cmd)
                self.assertIn("--no-session-persistence", cmd)
                self.assertEqual(
                    json.loads(cmd[cmd.index("--settings") + 1]), {"fastMode": True}
                )
                self.assertEqual(kwargs["env"]["CLAUDE_CODE_EFFORT_LEVEL"], "high")
                self.assertEqual(kwargs["env"]["CI"], "true")
                self.assertNotIn("ANTHROPIC_BASE_URL", kwargs["env"])
                self.assertNotIn("shell", kwargs)
                self.assertNotIn("timeout", kwargs)
                process = mock.Mock(returncode=0)
                process.communicate.return_value = (replies[len(processes)], "")
                processes.append(process)
                return process

            config = data / "settings.toml"
            config.write_text("[player_attributes]\nmax_turns=37\n")
            args = [
                "batch",
                "--config",
                str(config),
                "--players-csv",
                str(players),
                "--teams-players-csv",
                str(memberships),
                "--team-id",
                "1",
                "--output",
                str(output),
                "--model",
                "offline-model",
                "--effort",
                "high",
                "--fast",
            ]
            with (
                mock.patch.object(sys, "argv", args),
                mock.patch.dict(
                    os.environ, {"ANTHROPIC_BASE_URL": "https://unused.invalid"}
                ),
                mock.patch.object(
                    claude_cli.subprocess, "Popen", side_effect=popen
                ) as spawn,
                mock.patch.object(claude_cli.time, "sleep") as sleep,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(batch.main(), 0)
                self.assertEqual(batch.main(), 0)
            self.assertEqual(spawn.call_count, 3)
            self.assertEqual(sleep.call_args_list, [mock.call(5)] * 3)
            requests = sorted((output / "calls").glob("*.request.json"))
            self.assertEqual(len(requests), 3)
            audited = [json.loads(path.read_text()) for path in requests]
            self.assertEqual([request["turn"] for request in audited], [1, 1, 2])
            for request, process, reply, path in zip(
                audited, processes, replies, requests
            ):
                process.communicate.assert_called_once_with(
                    input=claude_cli.ClaudeCodeSubprocessAdapter._build_user_prompt(
                        request["messages"]
                    )
                )
                self.assertEqual(
                    request["messages"][0]["content"],
                    batch.PlayerAttributePromptBuilder()._system_prompt,
                )
                self.assertEqual(
                    path.with_name(
                        path.name.replace(".request.json", ".response.txt")
                    ).read_text(),
                    reply,
                )
            self.assertIn(
                "--- CORRECTION REQUIRED ---",
                processes[1].communicate.call_args.kwargs["input"],
            )
            self.assertIn(
                "PlayerProfiles", processes[2].communicate.call_args.kwargs["input"]
            )
            self.assertFalse(list((output / "calls").glob("*.error.json")))
            state = json.loads((output / "batch_state.json").read_text())
            self.assertEqual(state["players_csv"], str(players))
            self.assertEqual(state["teams_players_csv"], str(memberships))
            self.assertEqual(set(state["completed"]), {"1"})
            self.assertEqual(state["verification"]["verified_players"], 1)
            self.assertEqual(
                batch.rows(output / "Players.before.csv")[1:], batch.rows(players)[1:]
            )
            alternate = players.with_name("same-bytes-different-path.csv")
            alternate.write_bytes(players.read_bytes())
            with (
                mock.patch.object(
                    sys, "argv", [*args, "--players-csv", str(alternate)]
                ),
                mock.patch.object(batch, "AuditedAdapter") as adapter,
                contextlib.redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(RuntimeError, "Source CSV paths changed"),
            ):
                batch.main()
            adapter.assert_not_called()
