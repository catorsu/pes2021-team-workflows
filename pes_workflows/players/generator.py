"""Render PLAYER_RECORDS documents from the PES editor CSV database.

Rendering transcribes the database rather than validating it: abilities, height
and weight are copied through exactly as ``Players.csv`` stores them, including
ability values outside the 40-99 range the attribute contract enforces, which
the shipped database does contain. Only what the document grammar cannot express is
refused — a numeric cell that is not a signed integer, a position code outside
the vocabulary, an unknown playing style, a familiarity level other than 0/1/2,
and a player name that is empty or carries ``|`` or a line break.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from pes_workflows.domain.csv_schema import (
    EMPTY_ROSTER_IDS,
    FORMATION_ROSTER_SIZE,
    MEMBERSHIP_COLUMNS,
    STARTER_COUNT,
)
from pes_workflows.domain.vocabulary import (
    ABILITY_COLUMN_MAP,
    COM_STYLE_COLUMNS,
    PLAYER_SKILL_COLUMNS,
    PLAYING_STYLE_MAP,
    PLAYING_STYLE_POSITIONS,
    POSITION_CODES,
)
from pes_workflows.players.records import parse_player_records_identity
from pes_workflows.storage.semicolon import read_semicolon_csv

MINIMUM_SQUAD_SIZE = STARTER_COUNT

# The familiarity column slot 0 is read from. Module-private: callers ask
# whether a squad has a keeper, never which column says so
_GOALKEEPER_CODE = "GK"

EMPTY_ROSTER_TOKENS = EMPTY_ROSTER_IDS

_ROSTER_SLOTS = FORMATION_ROSTER_SIZE
_ROSTER_COLUMNS = ("Id", "TotalPlayers") + tuple(
    f"Player{slot}" for slot in range(1, _ROSTER_SLOTS + 1)
)
_MEMBERSHIP_COLUMNS = MEMBERSHIP_COLUMNS
_PLAYER_COLUMNS = (
    ("Id", "Name", "Height", "Weight", "Foot", "PlayingStyle", "POS")
    + POSITION_CODES
    + tuple(ABILITY_COLUMN_MAP.values())
    + tuple(PLAYER_SKILL_COLUMNS.values())
    + tuple(COM_STYLE_COLUMNS.values())
)

# The five dossier ability blocks, in hand-authored order. This partition is
# the PLAYER_RECORDS document grammar, not the player-attribute report's
# grouping — the two deliberately differ
ABILITY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Attacking & Possession",
        (
            "Offensive Awareness",
            "Ball Control",
            "Dribbling",
            "Tight Possession",
            "Low Pass",
            "Lofted Pass",
            "Finishing",
            "Header",
            "Set Piece Taking",
            "Curl",
        ),
    ),
    (
        "Athleticism",
        (
            "Speed",
            "Acceleration",
            "Kicking Power",
            "Jump",
            "Physical Contact",
            "Balance",
            "Stamina",
        ),
    ),
    ("Defending", ("Defensive Awareness", "Ball Winning", "Aggression")),
    (
        "Goalkeeping",
        ("GK Awareness", "GK Catching", "GK Parrying", "GK Reflexes", "GK Reach"),
    ),
    (
        "Durability & Traits",
        (
            "Weak Foot Usage",
            "Weak Foot Accuracy",
            "Conditioning",
            "Injury Resistance",
        ),
    ),
)

# Matrix paragraphs follow the grammar documented in
# ``prompts/match_plan/player_records_example.md``.
_MATRIX_PREAMBLE = "The matrix indexes Level-2 positional core and Level-1 cover under GAME_PLAN_RULES III, together with squad-available compatible Playing Styles. Assess Level-0 fluid-state assignments under the same section's existing rules."

_MATRIX_LEGEND = "**Column legend — `Squad-Available Playing Styles (derived)`:** For each Position row, derive `Squad-Available Playing Styles (derived)` from the carried styles of that row's Level-2 and Level-1 players whose styles are compatible with the Position in PLAYER_GLOSSARY §1. Include each player in positional depth according to familiarity. A `None` dossier contributes positional depth and an empty style contribution. Read `None` in the derived style column as an empty union for that squad cross-section. Determine style activation for individual assignments through PLAYER_GLOSSARY §1."

_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SIGNED_INTEGER = re.compile(r"-?[0-9]+")

# ``PlayingStyle`` 0 means the player carries no style. The editor mapping in
# ``domain.vocabulary`` spells that ``N/A``, but the dossier grammar's own word
# for "nothing here" is ``None`` — the spelling PLAYER_GLOSSARY and the CSV data
# dictionary use, and the one every other empty line in the document already
# carries.
NO_PLAYING_STYLE = "None"


class PlayerRecordsGenerationError(ValueError):
    """A PLAYER_RECORDS document could not be derived."""


class UnknownTeamError(PlayerRecordsGenerationError):
    """No populated team matched the requested selector."""


class InsufficientSquadError(PlayerRecordsGenerationError):
    """The team's squad cannot be documented at all from this database."""


class UnbuildableSquadError(InsufficientSquadError):
    """The squad is large enough but can never satisfy ``StartingXILock``."""


@dataclass(frozen=True, slots=True)
class TeamRecord:
    """One populated team and its unique artifact directory name."""

    team_id: str
    team_name: str
    """Exact ``teams-players.csv`` spelling, trailing ``*``/``**`` preserved."""
    kind: str
    """``"Club"`` or ``"National"``."""
    output_name: str
    """The team's ``<output-root>/<name>/`` directory name — unique across all
    populated teams, path-safe, and id-suffixed where two marker-free names
    collide.  It is the *only* identity a run's artifacts are named after, so
    it is derived here rather than in each consumer."""

    @property
    def label(self) -> str:
        """How this team is named in a diagnostic about its own document."""

        return f"{self.team_name} (ID {self.team_id})"


@dataclass(frozen=True, slots=True)
class GeneratedPlayerRecords:
    """One complete, already round-tripped PLAYER_RECORDS document."""

    team_id: str
    team_name: str
    kind: str
    output_name: str
    content: str
    player_ids: tuple[str, ...]
    """Squad ids actually documented, ascending numerically."""
    players_sha256: str
    """SHA-256 of the ``Players.csv`` bytes this document was derived from."""
    roster_sha256: str
    """SHA-256 of the ``Rosters.csv`` bytes the squad membership came from."""

    @property
    def team(self) -> TeamRecord:
        return TeamRecord(
            team_id=self.team_id,
            team_name=self.team_name,
            kind=self.kind,
            output_name=self.output_name,
        )

    @property
    def label(self) -> str:
        return self.team.label


def _read_semicolon_csv(
    path: Path, required_columns: Iterable[str]
) -> tuple[bytes, list[dict[str, str]]]:
    """Read validated rows and normalize cells for dossier rendering."""
    try:
        raw, _, source_rows = read_semicolon_csv(path, required_columns)
    except OSError as error:
        raise PlayerRecordsGenerationError(
            f"Could not read CSV file {path}: {error}"
        ) from error
    except ValueError as error:
        raise PlayerRecordsGenerationError(str(error)) from error
    rows = [{key: value.strip() for key, value in row.items()} for row in source_rows]
    return raw, [row for row in rows if any(row.values())]


def strip_team_markers(name: str) -> str:
    """Drop the trailing ``*``/``**`` licence markers and surrounding space.

    A **path, lookup and sort-order** helper only — it feeds the output-name
    stem, the name selector in :meth:`PlayerRecordsGenerator.resolve_team` and
    output directory naming. It is never a display transform: every
    human-facing string carries the raw ``teams-players.csv`` spelling.
    """

    return name.rstrip("* \t").strip()


def _sanitize_path_component(text: str) -> str:
    """Make one team name safe as an export-directory path component."""

    cleaned = _ILLEGAL_FILENAME_CHARS.sub("_", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.rstrip(" .")
    return cleaned or "team"


def _positive_id(value: str, where: str) -> str:
    token = value.strip()
    if not token.isascii() or not token.isdecimal() or int(token) <= 0:
        raise PlayerRecordsGenerationError(
            f"{where} must be a positive base-10 integer; got {value!r}."
        )
    return token


def _int_field(row: Mapping[str, str], column: str, player_id: str) -> int:
    token = row.get(column, "").strip()
    # A full match: a token like "--5" must be rejected here rather than reach
    # int(), which would raise a bare ValueError no caller catches
    if _SIGNED_INTEGER.fullmatch(token) is None:
        raise PlayerRecordsGenerationError(
            f"Players.csv player {player_id}: column {column!r} is not an "
            f"integer (got {token!r})."
        )
    return int(token)


def _reject_unrepresentable(text: str, where: str) -> str:
    """Refuse text the dossier grammar cannot carry on a single line."""

    if "|" in text or text.splitlines() != [text]:
        raise PlayerRecordsGenerationError(
            f"{where}: {text!r} contains a character the dossier grammar "
            "cannot represent (a table separator or a line break)."
        )
    return text


def _is_true(row: Mapping[str, str], column: str) -> bool:
    return row.get(column, "").strip().casefold() == "true"


class PlayerRecordsGenerator:
    """Parse CSVs once, validating only selected teams when selectors are given.

    ``None`` selects the full catalog; an empty selector collection selects none.
    """

    def __init__(
        self,
        *,
        rosters_csv: Path,
        players_csv: Path,
        teams_players_csv: Path,
        team_queries: Sequence[str] | None = None,
        team_ids: set[str] | None = None,
    ) -> None:
        self.roster_path: Path = Path(rosters_csv)
        self.players_path: Path = Path(players_csv)
        self.teams_players_path: Path = Path(teams_players_csv)

        players_raw, player_rows = _read_semicolon_csv(
            self.players_path, _PLAYER_COLUMNS
        )
        roster_raw, roster_rows = _read_semicolon_csv(self.roster_path, _ROSTER_COLUMNS)
        _, membership_rows = _read_semicolon_csv(
            self.teams_players_path, _MEMBERSHIP_COLUMNS
        )

        self.players_sha256: str = hashlib.sha256(players_raw).hexdigest()
        self.roster_sha256: str = hashlib.sha256(roster_raw).hexdigest()
        self.teams: Mapping[str, TeamRecord] = MappingProxyType(
            self._index_teams(
                membership_rows, team_queries=team_queries, team_ids=team_ids
            )
        )
        scoped = team_queries is not None or team_ids is not None
        if scoped:
            roster_rows = [row for row in roster_rows if row["Id"] in self.teams]
        self._roster: dict[str, tuple[str, ...]] = self._index_roster(roster_rows)
        if scoped:
            player_ids = {pid for squad in self._roster.values() for pid in squad}
            player_rows = [row for row in player_rows if row["Id"] in player_ids]
        self._players: dict[str, dict[str, str]] = (
            self._index_players(player_rows) if player_rows or not scoped else {}
        )

    def _index_players(
        self, rows: Sequence[Mapping[str, str]]
    ) -> dict[str, dict[str, str]]:
        index: dict[str, dict[str, str]] = {}
        for row in rows:
            player_id = _positive_id(row["Id"], f"{self.players_path}: Id")
            if player_id in index:
                raise PlayerRecordsGenerationError(
                    f"{self.players_path}: duplicate Player ID {player_id}."
                )
            index[player_id] = dict(row)
        if not index:
            raise PlayerRecordsGenerationError(
                f"{self.players_path}: contains no player rows."
            )
        return index

    def _index_roster(
        self, rows: Sequence[Mapping[str, str]]
    ) -> dict[str, tuple[str, ...]]:
        index: dict[str, tuple[str, ...]] = {}
        for row in rows:
            team_id = _positive_id(row["Id"], f"{self.roster_path}: Id")
            if team_id in index:
                raise PlayerRecordsGenerationError(
                    f"{self.roster_path}: duplicate team row for ID {team_id}."
                )
            slots: list[str] = []
            for slot in range(1, _ROSTER_SLOTS + 1):
                token = row.get(f"Player{slot}", "").strip()
                if token.casefold() in EMPTY_ROSTER_TOKENS:
                    continue
                if not token.isascii() or not token.isdecimal():
                    raise PlayerRecordsGenerationError(
                        f"{self.roster_path}: team {team_id} slot Player{slot} "
                        f"holds a malformed player id {token!r}."
                    )
                # Duplicates are kept here and rejected per team in ``squad``
                # one malformed row must fail its own team, not the catalogue
                slots.append(token)
            index[team_id] = tuple(slots)
        return index

    def _index_teams(
        self,
        rows: Sequence[Mapping[str, str]],
        *,
        team_queries: Sequence[str] | None = None,
        team_ids: set[str] | None = None,
    ) -> dict[str, TeamRecord]:
        """Collect the populated Club and National teams from both dimensions."""

        # Raw identity discovery supports name lookup and stable output paths.
        # It must not validate any unselected team's identity or roster.
        dimensions = (
            ("Id Club", "Club", "Club"),
            ("Id National", "National", "National"),
        )
        catalog = {
            (row.get(id_column, ""), row.get(name_column, ""), kind)
            for row in rows
            for id_column, name_column, kind in dimensions
            if row.get(id_column, "") not in {"", "0"}
        }
        selected_ids = team_ids
        if team_queries is not None:
            identities = [
                TeamRecord(tid, name, kind, "") for tid, name, kind in catalog
            ]
            selected_ids = {
                select_team(identities, query).team_id for query in team_queries
            }
            if team_ids is not None:
                selected_ids &= team_ids
        stems: dict[str, set[str]] = {}
        for team_id, name, _kind in catalog:
            stem = _sanitize_path_component(strip_team_markers(name))
            stems.setdefault(stem.casefold(), set()).add(team_id)

        found: dict[str, tuple[str, str]] = {}
        for row in rows:
            for id_column, name_column, kind in dimensions:
                token = row.get(id_column, "").strip()
                if not token or token == "0":
                    continue
                if selected_ids is not None and token not in selected_ids:
                    continue
                team_id = _positive_id(token, f"{self.teams_players_path}: {id_column}")
                name = row.get(name_column, "").strip()
                if not name:
                    raise PlayerRecordsGenerationError(
                        f"{self.teams_players_path}: {kind} ID {team_id} has an "
                        "empty team name."
                    )
                previous = found.get(team_id)
                if previous is None:
                    found[team_id] = (name, kind)
                elif previous != (name, kind):
                    raise PlayerRecordsGenerationError(
                        f"{self.teams_players_path}: team ID {team_id} is "
                        f"described as {previous} and as {(name, kind)}."
                    )

        # Two clubs can share a marker-free name (MANCHESTER UNITED* and
        # MANCHESTER UNITED**). Both members of such a group get the id
        # appended, so an output directory never depends on which team ran
        # first; each output team name remains unique
        teams: dict[str, TeamRecord] = {}
        for team_id in sorted(found, key=int):
            name, kind = found[team_id]
            # The raw spelling is what reaches the document's H1 and header
            # row, so it is the string the dossier grammar has to be able to
            # carry — not the marker-free form the output stem is built from
            _reject_unrepresentable(
                name,
                f"{self.teams_players_path}: {kind} ID {team_id} team name",
            )
            stem = _sanitize_path_component(strip_team_markers(name))
            if len(stems[stem.casefold()]) > 1:
                stem = f"{stem}_{team_id}"
            teams[team_id] = TeamRecord(
                team_id=team_id,
                team_name=name,
                kind=kind,
                output_name=stem,
            )
        return teams

    def resolve_team(
        self, *, team: str | None = None, team_id: str | None = None
    ) -> TeamRecord:
        """Find one populated team by exact id or by name."""

        if (team is None) == (team_id is None):
            raise PlayerRecordsGenerationError(
                "Provide exactly one selector: team or team_id."
            )
        if team_id is not None:
            token = str(team_id).strip()
            record = self.teams.get(token)
            if record is None:
                raise UnknownTeamError(
                    f"No populated team has ID {team_id!r} in "
                    f"{self.teams_players_path}."
                )
            return record

        return select_team(self.teams.values(), str(team))

    def squad(self, team_id: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Split a team's roster row into resolvable and missing player ids."""

        slots = self._roster.get(team_id)
        if slots is None:
            raise UnknownTeamError(
                f"Team ID {team_id} has no row in {self.roster_path}."
            )
        duplicates = sorted({pid for pid in slots if slots.count(pid) > 1}, key=int)
        if duplicates:
            # ``csv_store._map_roster_indices`` hard-errors on this same row, so
            # a document built from it could never be injected. Catching it
            # here costs nothing; catching it there costs a full 5-call build
            raise PlayerRecordsGenerationError(
                f"{self.roster_path}: team {team_id} lists player id(s) "
                + ", ".join(duplicates)
                + " in more than one slot; injection rejects such a row."
            )
        ordered = sorted(slots, key=int)
        resolved = tuple(pid for pid in ordered if pid in self._players)
        missing = tuple(pid for pid in ordered if pid not in self._players)
        return resolved, missing

    def _is_goalkeeper(self, player_id: str) -> bool:
        """Level 1 or Level 2 familiarity at GK — slot 0's only requirement."""

        return _int_field(self._players[player_id], _GOALKEEPER_CODE, player_id) in (
            1,
            2,
        )

    def _require_fieldable_xi(
        self, record: TeamRecord, player_ids: Sequence[str]
    ) -> None:
        """Refuse a squad that ``validate_starting_xi_lock`` could never accept."""

        keepers = [pid for pid in player_ids if self._is_goalkeeper(pid)]
        outfielders = [
            pid
            for pid in player_ids
            if self._registered_position(pid) != _GOALKEEPER_CODE
        ]
        label = f"{record.kind} {record.team_name!r} (ID {record.team_id})"
        if not keepers:
            raise UnbuildableSquadError(
                f"{label} has {len(player_ids)} documented players but none "
                "with Level 1 or Level 2 familiarity at GK, so no legal "
                "Starting XI exists."
            )
        # A keeper who is a registered GK can fill slot 0 without spending an
        # outfield identity; otherwise slot 0 costs one of them
        needed = (
            10
            if any(
                self._registered_position(pid) == _GOALKEEPER_CODE for pid in keepers
            )
            else 11
        )
        if len(outfielders) < needed:
            raise UnbuildableSquadError(
                f"{label} has only {len(outfielders)} non-goalkeeper "
                f"identities; a legal Starting XI needs {needed} here "
                "(slots 1-10 may not be registered goalkeepers)."
            )

    def generate(self, team_id: str) -> GeneratedPlayerRecords:
        """Render, self-verify and return one team's PLAYER_RECORDS document."""

        record = self.resolve_team(team_id=str(team_id).strip())
        player_ids, missing = self.squad(record.team_id)
        if len(player_ids) < MINIMUM_SQUAD_SIZE:
            shown = ", ".join(missing[:10]) + ("…" if len(missing) > 10 else "")
            raise InsufficientSquadError(
                f"{record.kind} {record.team_name!r} (ID {record.team_id}) "
                f"resolves only {len(player_ids)} of its "
                f"{len(player_ids) + len(missing)} roster players against "
                f"{self.players_path.name}; a PLAYER_RECORDS document needs at "
                f"least {MINIMUM_SQUAD_SIZE}. Missing player id(s): "
                f"{shown or 'none'}."
            )
        self._require_fieldable_xi(record, player_ids)

        content = self._render(record, player_ids)
        self._verify_round_trip(record, player_ids, content)
        return GeneratedPlayerRecords(
            team_id=record.team_id,
            team_name=record.team_name,
            kind=record.kind,
            output_name=record.output_name,
            content=content,
            player_ids=player_ids,
            players_sha256=self.players_sha256,
            roster_sha256=self.roster_sha256,
        )

    def _familiarity(self, player_id: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        row = self._players[player_id]
        level_2: list[str] = []
        level_1: list[str] = []
        for code in POSITION_CODES:
            value = _int_field(row, code, player_id)
            if value == 2:
                level_2.append(code)
            elif value == 1:
                level_1.append(code)
            elif value != 0:
                raise PlayerRecordsGenerationError(
                    f"Players.csv player {player_id}: familiarity column {code} "
                    f"must be 0, 1 or 2; got {value}."
                )
        return tuple(level_2), tuple(level_1)

    def _playing_style(self, player_id: str) -> str:
        row = self._players[player_id]
        token = row.get("PlayingStyle", "").strip()
        style = PLAYING_STYLE_MAP.get(token)
        if style is None:
            raise PlayerRecordsGenerationError(
                f"Players.csv player {player_id}: PlayingStyle {token!r} is not "
                "one of the 21 editor styles (or 0 for none)."
            )
        # The editor's id 0 is spelled ``N/A`` in the attribute vocabulary, a
        # token PLAYER_GLOSSARY does not define; the dossier says ``None``
        return NO_PLAYING_STYLE if token == "0" else style

    def _registered_position(self, player_id: str) -> str:
        value = _int_field(self._players[player_id], "POS", player_id)
        if not 0 <= value < len(POSITION_CODES):
            raise PlayerRecordsGenerationError(
                f"Players.csv player {player_id}: POS {value} is outside 0-12."
            )
        return POSITION_CODES[value]

    def _player_name(self, player_id: str) -> str:
        name = self._players[player_id].get("Name", "").strip()
        if not name:
            raise PlayerRecordsGenerationError(
                f"Players.csv player {player_id}: Name is empty."
            )
        return _reject_unrepresentable(name, f"Players.csv player {player_id}: Name")

    def _render(self, record: TeamRecord, player_ids: Sequence[str]) -> str:
        kind_label = "National Team" if record.kind == "National" else "Club"
        lines: list[str] = [
            f"# {record.team_name} {kind_label} Player Database",
            "",
            (
                f"Team: {record.team_name} (ID: {record.team_id}) | "
                f"Total Players: {len(player_ids)}"
            ),
            "",
            "## PRE-CALCULATED POSITIONAL SQUAD MATRIX",
            "",
            _MATRIX_PREAMBLE,
            "",
            _MATRIX_LEGEND,
            "",
        ]
        lines.extend(self._render_matrix(player_ids))
        lines.extend(["", "## DETAILED PLAYER DOSSIERS", ""])
        for player_id in player_ids:
            lines.extend(self._render_dossier(player_id))
            lines.append("")
        return "\n".join(lines[:-1]) + "\n"

    def _render_matrix(self, player_ids: Sequence[str]) -> list[str]:
        familiarity = {pid: self._familiarity(pid) for pid in player_ids}
        styles = {pid: self._playing_style(pid) for pid in player_ids}
        rows = [
            (
                "| Position | Level-2 Players (ID) | Level-1 Players (ID) | "
                "Squad-Available Playing Styles (derived) |"
            ),
            "| :--- | :--- | :--- | :--- |",
        ]
        for position in POSITION_CODES:
            level_2 = [pid for pid in player_ids if position in familiarity[pid][0]]
            level_1 = [pid for pid in player_ids if position in familiarity[pid][1]]
            available = sorted(
                {
                    styles[pid]
                    for pid in level_2 + level_1
                    if position in PLAYING_STYLE_POSITIONS.get(styles[pid], ())
                }
            )
            rows.append(
                f"| **{position}** | {self._name_list(level_2)} | "
                f"{self._name_list(level_1)} | "
                f"{', '.join(available) or 'None'} |"
            )
        return rows

    def _name_list(self, player_ids: Sequence[str]) -> str:
        return (
            ", ".join(f"{self._player_name(pid)} ({pid})" for pid in player_ids)
            or "None"
        )

    def _render_dossier(self, player_id: str) -> list[str]:
        row = self._players[player_id]
        level_2, level_1 = self._familiarity(player_id)
        style = self._playing_style(player_id)

        foot = (
            "Left"
            if row.get("Foot", "").strip().casefold() in {"1", "true"}
            else "Right"
        )
        skills = [
            name
            for name, column in PLAYER_SKILL_COLUMNS.items()
            if _is_true(row, column)
        ]
        com_styles = [
            name for name, column in COM_STYLE_COLUMNS.items() if _is_true(row, column)
        ]

        lines: list[str] = [
            f"### Player: {self._player_name(player_id)} (ID: {player_id})",
            "",
            (
                "- **Basic Profile**: Registered Position: "
                f"{self._registered_position(player_id)} | Preferred Foot: "
                f"{foot} | Height: {_int_field(row, 'Height', player_id)} cm | "
                f"Weight: {_int_field(row, 'Weight', player_id)} kg"
            ),
            "- **Familiarity**:",
            f"  - Fully Familiar (Level 2): {', '.join(level_2) or 'None'}",
            f"  - Partially Familiar (Level 1): {', '.join(level_1) or 'None'}",
            f"- **Playing Style & Compatibility**: {style}",
        ]
        # A player carrying no style has nothing to partition his familiar
        # Positions by, so both lines are omitted rather than rendered empty.
        # This is the format's only structural variation between dossiers
        # (player_records_example.md, Dossier conventions)
        if style != NO_PLAYING_STYLE:
            compatible_positions = PLAYING_STYLE_POSITIONS[style]
            familiar = level_2 + level_1
            compatible = [code for code in familiar if code in compatible_positions]
            not_listed = [code for code in familiar if code not in compatible_positions]
            lines.append(
                f"  - Compatible Familiar Positions: {', '.join(compatible) or 'None'}"
            )
            lines.append(
                f"  - Not-listed Familiar Positions: {', '.join(not_listed) or 'None'}"
            )
        lines.extend(
            [
                f"- **Player Skills**: {', '.join(skills) or 'None'}",
                f"- **COM Playing Styles**: {', '.join(com_styles) or 'None'}",
                "- **Detailed Abilities**:",
            ]
        )
        for label, ability_names in ABILITY_GROUPS:
            rendered = ", ".join(
                f"{name}: {_int_field(row, ABILITY_COLUMN_MAP[name], player_id)}"
                for name in ability_names
            )
            lines.append(f"  - *{label}*: {rendered}")
        return lines

    def _verify_round_trip(
        self, record: TeamRecord, player_ids: Sequence[str], content: str
    ) -> None:
        """Re-parse the document with the production parser."""

        try:
            parsed = parse_player_records_identity(content, record.label)
        except ValueError as error:
            raise PlayerRecordsGenerationError(
                f"Rendered records for {record.team_name!r} "
                f"(ID {record.team_id}) failed the PLAYER_RECORDS parser: "
                f"{error}"
            ) from error

        expected_names = {pid: self._player_name(pid) for pid in player_ids}
        expected_positions = {pid: self._registered_position(pid) for pid in player_ids}
        expected_familiarity: dict[str, dict[str, set]] = {}
        for pid in player_ids:
            level_2, level_1 = self._familiarity(pid)
            expected_familiarity[pid] = {"L2": set(level_2), "L1": set(level_1)}
        mismatches: list[str] = []
        if parsed["team_id"] != record.team_id:
            mismatches.append(f"team id {parsed['team_id']!r} != {record.team_id!r}")
        if parsed["total_players"] != len(player_ids):
            mismatches.append(
                f"player count {parsed['total_players']} != {len(player_ids)}"
            )
        if parsed["players"] != expected_names:
            mismatches.append("player id/name set differs from Players.csv")
        if parsed["registered_positions"] != expected_positions:
            mismatches.append("registered positions differ from Players.csv")
        if parsed["familiarity"] != expected_familiarity:
            mismatches.append("familiarity levels differ from Players.csv")
        if mismatches:
            raise PlayerRecordsGenerationError(
                f"Rendered records for {record.team_name!r} "
                f"(ID {record.team_id}) did not round-trip: "
                + "; ".join(mismatches)
                + "."
            )


def select_team(teams: Iterable[TeamRecord], team_query: str) -> TeamRecord:
    needle = team_query.strip().casefold()
    teams = list(teams)
    # Exact spelling (including markers) and IDs take precedence over aliases.
    candidates = [
        rec for rec in teams if needle in (rec.team_id, rec.team_name.casefold())
    ]
    if not candidates and needle and "*" not in needle:
        candidates = [
            rec
            for rec in teams
            if needle == strip_team_markers(rec.team_name).casefold()
        ]

    if not candidates:
        fuzzy = [
            rec.team_name
            for rec in teams
            if needle and needle in rec.team_name.casefold()
        ]
        hint = f"; teams containing this keyword: {', '.join(fuzzy)}" if fuzzy else ""
        raise UnknownTeamError(
            f"Team not found in teams-players.csv: {team_query!r}{hint}"
        )

    if len(candidates) > 1:
        details = ", ".join(f"{c.team_name} (ID: {c.team_id})" for c in candidates)
        raise PlayerRecordsGenerationError(
            f"Ambiguous team query: {details}; specify a unique name or Team ID."
        )

    return candidates[0]


__all__ = [
    "ABILITY_GROUPS",
    "EMPTY_ROSTER_TOKENS",
    "MINIMUM_SQUAD_SIZE",
    "NO_PLAYING_STYLE",
    "GeneratedPlayerRecords",
    "InsufficientSquadError",
    "UnbuildableSquadError",
    "PlayerRecordsGenerationError",
    "PlayerRecordsGenerator",
    "TeamRecord",
    "UnknownTeamError",
    "strip_team_markers",
]
