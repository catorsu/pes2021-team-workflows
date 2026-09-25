"""Attribute reports survive successful commits, resume, and publication failures."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pes_workflows import batch_design_player_attributes as batch
from pes_workflows import claude_cli
from pes_workflows.player_attributes import generation
from pes_workflows.player_attributes.sources import resolve_design_targets
from tests.attribute_fixtures import (
    abilities_artifact,
    make_targets,
    profiles_artifact,
    write_attribute_targets_csv,
)


class ReportRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name)
        self.output = self.data / "output"
        self.players = self.data / "Players.csv"
        write_attribute_targets_csv(self.players, make_targets(2))
        # One player may belong to both a custom club squad and a national team.
        (self.data / "Teams-Players.csv").write_text(
            "Id;Name;Id Club;Club;Id National;National\n"
            "101;Player 1;1;Custom Squad;2;National Team\n"
            "102;Player 2;1;Custom Squad;0;\n",
            encoding="utf-8",
        )

    def invoke(self) -> int:
        arguments = [
            "attributes",
            "--players-csv",
            str(self.data / "Players.csv"),
            "--teams-players-csv",
            str(self.data / "Teams-Players.csv"),
            "--output",
            str(self.output),
            "--team-id",
            "1",
        ]
        with (
            mock.patch.object(sys, "argv", arguments),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            return batch.main()

    def responses(self) -> list[mock.Mock]:
        team, targets = resolve_design_targets(
            players_csv=self.players,
            memberships_csv=self.data / "Teams-Players.csv",
            team_id="1",
        )
        responses = []
        for artifact in (
            profiles_artifact(team, targets),
            abilities_artifact(team, targets),
        ):
            process = mock.Mock(returncode=0)
            process.communicate.return_value = (json.dumps(artifact), "")
            responses.append(process)
        return responses

    def test_preflight_accepts_overlapping_club_and_national_rosters(self) -> None:
        report, _ = batch.preflight(self.players, self.data / "Teams-Players.csv")
        self.assertEqual(report["failed"], [])
        self.assertEqual(
            [team["kind"] for team in report["teams"]], ["Club", "National"]
        )
        self.assertEqual(report["player_count"], 2)

    def test_report_is_retained_and_restored_on_resume_without_model_calls(
        self,
    ) -> None:
        with (
            mock.patch.object(
                claude_cli.subprocess, "Popen", side_effect=self.responses()
            ),
            mock.patch.object(claude_cli.time, "sleep"),
        ):
            self.assertEqual(self.invoke(), 0)
        checkpoint = json.loads((self.output / "batch_state.json").read_text())
        saved = checkpoint["completed"]["1"]
        report = Path(saved["report"])
        original = report.read_bytes()
        self.assertIn(b"Player Information Report", original)
        self.assertIn(b"Player 1", original)
        self.assertIn(b"Player 2", original)
        self.assertEqual(batch.digest(report), saved["report_sha256"])
        before = self.players.read_bytes()
        report.unlink()
        with mock.patch.object(claude_cli.subprocess, "Popen") as spawn:
            self.assertEqual(self.invoke(), 0)
            spawn.assert_not_called()
        self.assertEqual(report.read_bytes(), original)
        self.assertEqual(self.players.read_bytes(), before)
        self.assertEqual(
            sorted(path.name for path in report.parent.glob("*.md")),
            ["00_Final_System_Prompt.md", "player_attributes.md"],
        )
        self.assertFalse(list(report.parent.glob("Turn_*")))

    def test_report_write_failure_prevents_csv_commit_and_completion(self) -> None:
        before = self.players.read_bytes()
        publish = generation.write_text_atomic

        def fail_report(path: Path, content: str) -> None:
            if path.name == "player_attributes.md":
                raise OSError("report disk full")
            publish(path, content)

        with (
            mock.patch.object(
                claude_cli.subprocess, "Popen", side_effect=self.responses()
            ),
            mock.patch.object(claude_cli.time, "sleep"),
            mock.patch.object(generation, "write_text_atomic", side_effect=fail_report),
        ):
            self.assertEqual(self.invoke(), 1)
        state = json.loads((self.output / "batch_state.json").read_text())
        self.assertEqual(state["completed"], {})
        self.assertEqual(self.players.read_bytes(), before)
        self.assertEqual(
            (self.output / "completed_teams_player_attributes.txt").read_text(), ""
        )
