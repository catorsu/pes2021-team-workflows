"""Behavioral boundaries shared by the consolidated workflow implementations."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import logging
import shutil
import tempfile
import unittest
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from pes_workflows import batch_design_player_attributes as batch
from pes_workflows import generate_match_plan as single
from pes_workflows.application.artifact_generation import request_artifact
from pes_workflows.compiler import injection
from pes_workflows.config import Config
from pes_workflows.contracts.errors import ArtifactContractError, ArtifactDomainError
from pes_workflows.contracts.preset import validate_preset_plan
from pes_workflows.contracts.strategy import validate_starting_xi_lock
from pes_workflows.player_attributes import sources
from pes_workflows.player_attributes.generation import _request_validated_artifact
from pes_workflows.player_attributes.injection import (
    _read_players_csv,
    _required_columns,
)
from pes_workflows.player_attributes.sources import _read_csv_snapshot
from pes_workflows.players.generator import (
    PlayerRecordsGenerationError,
    PlayerRecordsGenerator,
    TeamRecord,
    _read_semicolon_csv,
)
from pes_workflows.prompts.assets import read_prompt_bytes, read_prompt_text
from pes_workflows.storage.atomic import (
    stable_json_sha256,
    write_bytes_atomic,
    write_text_atomic,
)
from tests.attribute_fixtures import make_targets, write_attribute_targets_csv
from tests.match_fixtures import preset_raw, source_identity, strategy_raw


class ConsolidatedInfrastructureTests(unittest.TestCase):
    def test_simplified_preset_retains_raw_contract_and_validates_metadata(
        self,
    ) -> None:
        xi = validate_starting_xi_lock(strategy_raw(), source_identity())
        raw = preset_raw("Main", join_player_ids=("6",))
        accepted = validate_preset_plan(raw, "Main", xi)
        self.assertEqual(accepted.to_model_dict(), raw)
        exported = accepted.to_model_dict()
        exported["States"]["Normal"][1]["Tactical Duty"] = "changed"
        self.assertEqual(accepted.to_model_dict(), raw)

        cases = (
            ("States", "Normal", 1, "Tactical Duty"),
            ("Players to Join Attack", 0, "Aerial Rationale"),
            ("Rest Defence Contract", "Minimum Retained"),
            ("Rest Defence Contract", "Retained Protector Slots"),
        )
        for path in cases:
            with self.subTest(path=path):
                invalid = copy.deepcopy(raw)
                parent = invalid
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = None
                with self.assertRaises(ArtifactContractError):
                    validate_preset_plan(invalid, "Main", xi)

    def test_sources_preserve_csv_ages_affiliations_and_invalidate_on_changes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            players = write_attribute_targets_csv(root / "Players.csv", make_targets(2))
            memberships = root / "Teams-Players.csv"
            memberships.write_text(
                "Id;Name;Id Club;Club;Id National;National\n"
                "101;Player 1;1;Club;2;National\n"
                "102;Player 2;1;Club;0;\n"
            )
            inputs = dict(players_csv=players, memberships_csv=memberships)
            team, targets = sources.resolve_design_targets(**inputs, team_id="1")
            self.assertEqual([t.player_id for t in targets], ["101", "102"])
            self.assertEqual(
                [t.designated_age for t in targets],
                [t.designated_age for t in make_targets(2)],
            )
            self.assertEqual(targets[0].club_affiliations, "Club")
            self.assertEqual(targets[0].national_affiliations, "National")
            self.assertEqual(
                sources.list_attribute_teams(**inputs),
                (team, sources.TeamIdentity("National", "National", "2")),
            )
            # Unchanged files reuse their parsed snapshot.
            with mock.patch.object(sources, "_build_source_snapshot") as rebuild:
                self.assertEqual(
                    sources.resolve_design_targets(**inputs, team_id="1"),
                    (team, targets),
                )
                rebuild.assert_not_called()
            memberships.write_text(
                "Id;Name;Id Club;Club;Id National;National\n"
                "101;Player 1;1;Club;2;Country\n"
                "102;Player 2;1;Club;0;\n"
            )
            _, updated = sources.resolve_design_targets(**inputs, team_id="1")
            self.assertEqual(updated[0].national_affiliations, "Country")
            write_attribute_targets_csv(players, make_targets(1))
            with self.assertRaisesRegex(ValueError, "102.*not found"):
                sources.resolve_design_targets(**inputs, team_id="1")

    def test_csv_readers_reject_the_same_structural_errors(self) -> None:
        readers = (
            lambda p: _read_semicolon_csv(p, ("Id", "Name")),
            lambda p: _read_csv_snapshot(p, ("Id", "Name")),
            _read_players_csv,
        )
        fields = sorted(_required_columns() | {"Name"})
        values = ["1"] * len(fields)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Players.csv"
            for header, row, error in (
                ([*fields, ""], [*values, "x"], "empty column name"),
                ([*fields, "Id"], [*values, "x"], "duplicate column"),
                (fields, values[:-1], "fewer fields"),
                (fields, [*values, "x"], "more fields"),
            ):
                path.write_text(";".join(header) + "\n" + ";".join(row) + "\n")
                for reader in readers:
                    with (
                        self.subTest(error=error, reader=reader),
                        self.assertRaisesRegex(ValueError, error),
                    ):
                        reader(path)

    def test_csv_injection_reader_preserves_bom_cells_and_record_terminators(
        self,
    ) -> None:
        fields = sorted(_required_columns() | {"Name"})
        row = dict.fromkeys(fields, "40")
        row.update(Id="1", Name="  Player; quoted\r\nname  ")
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(
            stream, fieldnames=fields, delimiter=";", lineterminator="\r\n"
        )
        writer.writeheader()
        writer.writerow(row)
        original = stream.getvalue().encode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Players.csv"
            path.write_bytes(original)
            raw, headers, rows, terminator = _read_players_csv(path)
        self.assertEqual(
            (raw, headers, rows, terminator), (original, fields, [row], "\r\n")
        )

    def test_both_team_resolvers_use_exact_names_before_aliases(self) -> None:
        generator = object.__new__(PlayerRecordsGenerator)
        exact = TeamRecord("1", "United", "Club", "United_1")
        marked = TeamRecord("2", "United*", "Club", "United_2")
        generator.teams = {"1": exact, "2": marked}
        generator.teams_players_path = Path("Teams-Players.csv")
        for query, expected in (
            ("United", exact),
            (" United* ", marked),
            ("2", marked),
        ):
            self.assertIs(single.resolve_team(generator, query), expected)
            self.assertIs(generator.resolve_team(team=query), expected)
        generator.teams["1"] = TeamRecord("1", "United**", "Club", "United_1")
        for resolve in (
            lambda: single.resolve_team(generator, "United"),
            lambda: generator.resolve_team(team="United"),
        ):
            with self.assertRaises(PlayerRecordsGenerationError):
                resolve()
        self.assertIs(generator.resolve_team(team_id="2"), marked)

    def test_public_injection_still_validates_before_reading_csv(self) -> None:
        with mock.patch.object(injection.pd, "read_csv") as read:
            self.assertFalse(
                injection.process_formation_data(
                    Path("Rosters.csv"),
                    Path("Formations.csv"),
                    {},
                    players_csv=None,
                    strict=True,
                    report=lambda _: None,
                )
            )
        read.assert_not_called()

    def test_atomic_writers_preserve_existing_target_on_failed_replace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact"
            for writer, content in (
                (write_text_atomic, "Player’s attributes\r\n"),
                (write_bytes_atomic, b"\xef\xbb\xbfraw\r\n"),
            ):
                path.write_bytes(b"original")
                with self.assertRaises(OSError):
                    writer(
                        path,
                        content,
                        replace=mock.Mock(side_effect=OSError("disk error")),
                    )
                self.assertEqual(path.read_bytes(), b"original")
                self.assertEqual(list(path.parent.iterdir()), [path])
                writer(path, content)
                self.assertEqual(
                    path.read_bytes(),
                    content.encode() if isinstance(content, str) else content,
                )

    def test_prompt_fragments_preserve_bytes_and_participate_in_resume_hash(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "policy/system_prompt.md"
            policy.parent.mkdir()
            shared = root / "shared/player_glossary.md"
            shared.parent.mkdir()
            shared.write_bytes(b"shared\r\n\r\n")
            policy.write_bytes(
                b"before\r\n<!-- INCLUDE ../shared/player_glossary.md -->\r\nafter\r\n"
            )
            expanded = b"before\r\nshared\r\n\r\nafter\r\n"
            self.assertEqual(read_prompt_bytes(policy), expanded)
            self.assertEqual(
                read_prompt_text(policy), expanded.decode().replace("\r\n", "\n")
            )
            with mock.patch.object(batch, "POLICY", policy):
                original_digest = batch.prompt_digest()
                self.assertEqual(
                    original_digest,
                    stable_json_sha256(
                        {
                            policy.name: hashlib.sha256(expanded).hexdigest(),
                            shared.name: hashlib.sha256(
                                shared.read_bytes()
                            ).hexdigest(),
                        }
                    ),
                )
                shared.write_text("changed\n")
                self.assertNotEqual(batch.prompt_digest(), original_digest)
            shared.write_text("<!-- INCLUDE ../policy/system_prompt.md -->\n")
            with self.assertRaisesRegex(ValueError, "Circular prompt include"):
                read_prompt_bytes(policy)
            shared.unlink()
            with self.assertRaises(FileNotFoundError):
                read_prompt_bytes(policy)

    def test_relocated_shared_glossary_reaches_both_workflows_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "prompts"
            shutil.copytree(batch.ROOT / "prompts", root)
            glossary = root / "shared/player_glossary.md"
            policy = root / "player_attributes/system_prompt.md"
            with mock.patch.object(batch, "POLICY", policy):
                original_digest = batch.prompt_digest()
                glossary.write_text(glossary.read_text() + "\nSHARED_GLOSSARY_UPDATE\n")
                self.assertNotEqual(batch.prompt_digest(), original_digest)
            shared = glossary.read_text().strip()
            attributes = batch.PlayerAttributePromptBuilder(prompts_dir=policy.parent)
            self.assertEqual(attributes.glossary_path, glossary)
            self.assertIn(shared, attributes._system_prompt)
            self.assertNotIn("[PASTE ", attributes._system_prompt)
            for mode in ("single", "multi"):
                with self.subTest(mode=mode):
                    match = single.TemplateLoader(root / "match_plan", preset_mode=mode)
                    self.assertEqual(match.player_glossary, shared)
                    self.assertIn(shared, match.build_system_prompt())
                    self.assertNotIn("[PASTE ", match.build_system_prompt())


class SharedRepairTests(unittest.TestCase):
    def test_both_workflows_honor_repair_budget_and_scope(self) -> None:
        for attributes in (False, True):
            for budget in (0, 1, 2):
                with self.subTest(attributes=attributes, budget=budget):
                    observer = SimpleNamespace(on_event=mock.Mock())
                    artifact = "PlayerProfiles" if attributes else "StartingXILock"
                    reply = json.dumps({"Schema Version": "2.2", "Artifact": artifact})
                    transport = mock.Mock(return_value=(reply, "reasoning"))
                    error = ArtifactDomainError(artifact, "$.Players", "invalid roster")
                    validator = mock.Mock(side_effect=error)
                    common = dict(
                        call_model=transport,
                        system_prompt="policy",
                        user_prompt="roster",
                        artifact_name=artifact,
                        validator=validator,
                        turn=1,
                        team_name="Team",
                        user_id="id",
                        observer=observer,
                    )
                    if attributes:
                        call = partial(
                            _request_validated_artifact,
                            **common,
                            immutable_context={"Team ID": "77"},
                            event_logger=logging.getLogger(__name__),
                        )
                    else:
                        call = partial(
                            request_artifact,
                            **common,
                            output_name="team_output",
                            logger=logging.getLogger(__name__),
                        )
                    with (
                        mock.patch.object(Config, "MAX_FORMAT_REPAIRS", budget),
                        self.assertRaises(ValueError),
                    ):
                        call()
                    self.assertEqual(transport.call_count, budget + 1)
                    events = [c.args[0] for c in observer.on_event.call_args_list]
                    self.assertEqual(
                        [e.kind for e in events],
                        ["artifact_repair"] * budget + ["artifact_failed"],
                    )
                    self.assertEqual(
                        events[-1].team, "Team" if attributes else "team_output"
                    )
                    for request in transport.call_args_list[1:]:
                        messages = request.args[0]
                        self.assertEqual(
                            [m["role"] for m in messages],
                            ["system", "user", "assistant", "user"],
                        )
                        self.assertEqual(messages[2]["content"], reply)
                        self.assertIn("$.Players", messages[3]["content"])
                        if attributes:
                            self.assertIn('"Team ID": "77"', messages[3]["content"])
