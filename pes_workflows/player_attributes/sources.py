"""Resolve attribute squads from memberships and authoritative player records."""

from __future__ import annotations

import hashlib
import re
import threading
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from pes_workflows.domain.csv_schema import MEMBERSHIP_COLUMNS
from pes_workflows.domain.vocabulary import COUNTRY_NAMES, NO_COUNTRY, TEAM_KINDS
from pes_workflows.storage.semicolon import read_semicolon_csv

_PLAYERS_COLUMNS: tuple[str, ...] = (
    "Id",
    "Name",
    "Age",
    "Height",
    "Weight",
    "Country",
    "Country2",
)
_MEMBERSHIP_COLUMNS = MEMBERSHIP_COLUMNS
_TEAM_DIMENSIONS: Mapping[str, tuple[str, str, str]] = MappingProxyType(
    {
        "club": ("Id Club", "Club", "Club"),
        "national": ("Id National", "National", "National"),
    }
)
# The editor stores "no value" as a literal zero in its numeric columns, and the
# prompt contract wants an unrecorded cell blank rather than zero
_UNRECORDED_NUMERIC: str = "0"


def _required_text(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{where} must be a string.")
    text = value.strip()
    if not text:
        raise ValueError(f"{where} must not be empty.")
    return text


def _positive_integer(value: object, where: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{where} must be a positive integer, not a boolean.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str):
        token = value.strip()
        if not token or not token.isascii() or not token.isdecimal():
            raise ValueError(
                f"{where} must be a positive base-10 integer; got {value!r}."
            )
        number = int(token)
    else:
        raise ValueError(f"{where} must be a positive base-10 integer; got {value!r}.")
    if number <= 0:
        raise ValueError(f"{where} must be greater than zero; got {value!r}.")
    return number


def _positive_id(value: object, where: str) -> str:
    _positive_integer(value, where)
    return value.strip() if isinstance(value, str) else str(value)


# The editor writes a literal zero for an unset physique column, so those two
# normalize it away. The country fields already hold resolved names by the time
# they reach a target, and an affiliation is free text; both keep what they hold
_NUMERIC_CONTEXT_FIELDS: tuple[str, ...] = ("height", "weight")
_CONTEXT_FIELDS: tuple[str, ...] = _NUMERIC_CONTEXT_FIELDS + (
    "country_1",
    "country_2",
    "national_affiliations",
    "club_affiliations",
)


def _context_cell(value: object, where: str) -> str:
    """One roster context value, flattened to a single blank-or-text cell."""

    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{where} must be a string.")
    text = " ".join(value.split())
    if where in _NUMERIC_CONTEXT_FIELDS and text == _UNRECORDED_NUMERIC:
        return ""
    return text


def _country_name(value: object, where: str) -> str:
    """Resolve one editor country code to its name, or to a blank cell.

    The editor's ``NO_COUNTRY`` code and an empty cell both mean "no country",
    which the roster contract renders blank. Any other code must be one the
    editor defines: an unknown code is a corrupt or foreign database rather
    than a missing value, and silently blanking it would hide that.
    """

    code = str(value or "").strip()
    if not code or code == NO_COUNTRY:
        return ""
    try:
        return COUNTRY_NAMES[code]
    except KeyError:
        raise ValueError(
            f"{where} holds unknown editor country code {code!r}."
        ) from None


def _normalize_team_kind(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("team_kind must be one of auto, club, national.")
    normalized = value.strip().casefold()
    if normalized not in {"auto", "club", "national"}:
        raise ValueError(
            f"team_kind must be one of auto, club, national; got {value!r}."
        )
    return normalized


@dataclass(frozen=True, slots=True)
class TeamIdentity:
    """Exact identity of one club or national team from the membership export."""

    name: str
    kind: str
    team_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required_text(self.name, "Team name"))
        kind = _required_text(self.kind, "Team kind")
        if kind not in TEAM_KINDS:
            raise ValueError("Team kind must be Club or National.")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "team_id", _positive_id(self.team_id, "Team ID"))


@dataclass(frozen=True, slots=True)
class PlayerDesignTarget:
    """One immutable player identity, age anchor and modeling context row.

    The six context fields carry the physique, nationality and affiliation
    columns the prompt's ``PLAYER_INPUT`` roster table declares. Each is a
    display-ready string, empty when the editor database records no value,
    because the table renders an unrecorded cell blank. The two country fields
    hold resolved country *names*, not the editor codes they are stored as.
    """

    player_id: str
    name: str
    designated_age: int
    source_players_sha256: str | None = None
    height: str = ""
    weight: str = ""
    country_1: str = ""
    country_2: str = ""
    national_affiliations: str = ""
    club_affiliations: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "player_id", _positive_id(self.player_id, "Player ID"))
        object.__setattr__(self, "name", _required_text(self.name, "Player name"))
        object.__setattr__(
            self,
            "designated_age",
            _positive_integer(self.designated_age, "Designated Age"),
        )
        for field_name in _CONTEXT_FIELDS:
            object.__setattr__(
                self, field_name, _context_cell(getattr(self, field_name), field_name)
            )
        if self.source_players_sha256 is not None:
            digest = _required_text(
                self.source_players_sha256, "Players.csv source SHA-256"
            ).lower()
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError(
                    "Players.csv source SHA-256 must contain 64 hexadecimal characters."
                )
            object.__setattr__(self, "source_players_sha256", digest)

    def identity_contract(self) -> dict[str, str | int]:
        """Return the immutable identity fields required in both LLM artifacts."""

        return {
            "Player ID": self.player_id,
            "Player Name": self.name,
            "Age": self.designated_age,
        }


@dataclass(frozen=True, slots=True)
class _CsvRow:
    """A structurally validated CSV row and its source line number."""

    number: int
    cells: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class SourceFileStamp:
    """Filesystem identity used to invalidate cached source data."""

    path: Path
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def read(cls, path: Path) -> SourceFileStamp:
        try:
            resolved = path.resolve()
            stat = resolved.stat()
        except OSError as error:
            raise ValueError(f"Could not read CSV file {path}: {error}") from error
        return cls(
            resolved,
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            stat.st_mtime_ns,
            stat.st_ctime_ns,
        )


@dataclass(frozen=True, slots=True)
class _SourceSnapshot:
    """Read-only source indexes shared by roster resolutions."""

    players: Mapping[str, tuple[_CsvRow, ...]]
    teams_by_id: Mapping[tuple[str, str], tuple[_CsvRow, ...]]
    teams_by_name: Mapping[tuple[str, str], tuple[_CsvRow, ...]]
    memberships_by_player: Mapping[str, tuple[_CsvRow, ...]]
    players_sha256: str


_SOURCE_CACHE_LIMIT: int = 2
_SOURCE_READ_ATTEMPTS: int = 3
_SOURCE_CACHE: OrderedDict[tuple[SourceFileStamp, SourceFileStamp], _SourceSnapshot] = (
    OrderedDict()
)
_SOURCE_CACHE_LOCK: threading.Lock = threading.Lock()


def _read_csv_snapshot(
    path: Path, required_columns: Iterable[str]
) -> tuple[bytes, tuple[_CsvRow, ...]]:
    columns = tuple(required_columns)
    try:
        raw, _, source_rows = read_semicolon_csv(path, columns)
    except OSError as error:
        raise ValueError(f"Could not read CSV file {path}: {error}") from error
    return raw, tuple(
        _CsvRow(
            number,
            MappingProxyType({column: row[column].strip() for column in columns}),
        )
        for number, row in enumerate(source_rows, start=2)
        if any(value.strip() for value in row.values())
    )


def _select_team(
    *,
    snapshot: _SourceSnapshot,
    memberships_csv: Path,
    team_name: str | None,
    team_id: str | None,
    team_kind: str,
) -> tuple[TeamIdentity, tuple[str, ...]]:
    selected_name = (
        _required_text(team_name, "team_name") if team_name is not None else None
    )
    selected_id = _positive_id(team_id, "team_id") if team_id is not None else None
    if (selected_name is None) == (selected_id is None):
        raise ValueError("Provide exactly one selector: team_name or team_id.")

    normalized_kind = _normalize_team_kind(team_kind)
    candidates = _team_candidates(
        snapshot,
        memberships_csv,
        team_name=selected_name,
        team_id=selected_id,
        team_kind=normalized_kind,
    )
    selector = (
        f"name {selected_name!r}"
        if selected_name is not None
        else f"ID {selected_id!r}"
    )
    if not candidates:
        scope = normalized_kind if normalized_kind != "auto" else "club or national"
        raise ValueError(
            f"No {scope} team matched exact {selector} in {memberships_csv}."
        )
    if len(candidates) != 1:
        descriptions = sorted(
            f"{identity.kind} {identity.name!r} (ID {identity.team_id})"
            for identity in candidates.values()
        )
        raise ValueError(
            f"Team selector {selector} is ambiguous in {memberships_csv}: "
            + "; ".join(descriptions)
            + ". Specify team_kind or an unambiguous selector."
        )

    (selected_kind, _, _), identity = next(iter(candidates.items()))
    _, name_column, _ = _TEAM_DIMENSIONS[selected_kind]
    rows = snapshot.teams_by_id[(selected_kind, identity.team_id)]
    player_ids = _team_player_ids(rows, memberships_csv, identity, name_column)
    return identity, player_ids


def _team_candidates(
    snapshot: _SourceSnapshot,
    memberships_csv: Path,
    *,
    team_name: str | None,
    team_id: str | None,
    team_kind: str,
) -> dict[tuple[str, str, str], TeamIdentity]:
    searchable = tuple(_TEAM_DIMENSIONS) if team_kind == "auto" else (team_kind,)
    index = snapshot.teams_by_name if team_name is not None else snapshot.teams_by_id
    selector = team_name if team_name is not None else team_id
    assert selector is not None
    candidates: dict[tuple[str, str, str], TeamIdentity] = {}
    for raw_kind in searchable:
        id_column, name_column, kind_label = _TEAM_DIMENSIONS[raw_kind]
        for entry in index.get((raw_kind, selector), ()):
            canonical_id = _positive_id(
                entry.cells[id_column],
                f"{memberships_csv}: row {entry.number} {id_column}",
            )
            canonical_name = _required_text(
                entry.cells[name_column],
                f"{memberships_csv}: row {entry.number} {name_column}",
            )
            identity = TeamIdentity(canonical_name, kind_label, canonical_id)
            candidates[(raw_kind, canonical_id, canonical_name)] = identity
    return candidates


def _team_player_ids(
    rows: Iterable[_CsvRow],
    memberships_csv: Path,
    identity: TeamIdentity,
    name_column: str,
) -> tuple[str, ...]:
    player_ids: list[str] = []
    seen: dict[str, int] = {}
    for entry in rows:
        row_number, row = entry.number, entry.cells
        if row[name_column] != identity.name:
            raise ValueError(
                f"{memberships_csv}: {identity.kind} ID {identity.team_id} has "
                f"inconsistent names {identity.name!r} and {row[name_column]!r} "
                f"(row {row_number})."
            )
        player_id = _positive_id(row["Id"], f"{memberships_csv}: row {row_number} Id")
        if player_id in seen:
            raise ValueError(
                f"{memberships_csv}: duplicate Player ID {player_id} in selected "
                f"{identity.kind} roster at rows {seen[player_id]} and {row_number}."
            )
        seen[player_id] = row_number
        player_ids.append(player_id)

    if not player_ids:
        raise ValueError(
            f"Selected team {identity.name!r} (ID {identity.team_id}) has no "
            f"players in {memberships_csv}."
        )
    return tuple(player_ids)


def _players_index(
    rows: Iterable[_CsvRow], players_csv: Path, *, validate: bool = True
) -> Mapping[str, tuple[_CsvRow, ...]]:
    index: dict[str, list[_CsvRow]] = {}
    for entry in rows:
        player_id = entry.cells["Id"]
        if validate:
            _positive_id(player_id, f"{players_csv}: row {entry.number} Id")
        index.setdefault(player_id, []).append(entry)
    if not index:
        raise ValueError(f"{players_csv}: Players.csv contains no player rows.")
    return MappingProxyType(
        {player_id: tuple(rows) for player_id, rows in index.items()}
    )


def _affiliation_index(
    rows: Iterable[_CsvRow],
) -> Mapping[str, tuple[str, str]]:
    """Index normalized prompt affiliations.

    The prompt contract wants comma-separated lists, so a player carried by
    several membership rows contributes every distinct team, in file order.
    """

    collected: dict[str, tuple[dict[str, None], dict[str, None]]] = {}
    for entry in rows:
        row = entry.cells
        player_id = row["Id"]
        national, club = collected.setdefault(player_id, ({}, {}))
        for column, seen in (("National", national), ("Club", club)):
            name = " ".join(str(row.get(column) or "").split())
            if name:
                seen[name] = None
    affiliations = MappingProxyType(
        {
            player_id: (", ".join(national), ", ".join(club))
            for player_id, (national, club) in collected.items()
        }
    )
    return affiliations


def _build_source_snapshot(players_csv: Path, memberships_csv: Path) -> _SourceSnapshot:
    players_raw, player_rows = _read_csv_snapshot(players_csv, _PLAYERS_COLUMNS)
    _, membership_rows = _read_csv_snapshot(memberships_csv, _MEMBERSHIP_COLUMNS)
    teams_by_id: dict[tuple[str, str], list[_CsvRow]] = {}
    teams_by_name: dict[tuple[str, str], list[_CsvRow]] = {}
    memberships_by_player: dict[str, list[_CsvRow]] = {}
    for entry in membership_rows:
        memberships_by_player.setdefault(entry.cells["Id"], []).append(entry)
        for kind, (id_column, name_column, _) in _TEAM_DIMENSIONS.items():
            name_key = (kind, entry.cells[name_column])
            teams_by_name.setdefault(name_key, []).append(entry)
            # Index raw keys only; validation belongs to the selected roster.
            team_id = entry.cells[id_column]
            teams_by_id.setdefault((kind, team_id), []).append(entry)
    return _SourceSnapshot(
        players=_players_index(player_rows, players_csv, validate=False),
        teams_by_id=MappingProxyType(
            {key: tuple(rows) for key, rows in teams_by_id.items()}
        ),
        teams_by_name=MappingProxyType(
            {key: tuple(rows) for key, rows in teams_by_name.items()}
        ),
        memberships_by_player=MappingProxyType(
            {key: tuple(rows) for key, rows in memberships_by_player.items()}
        ),
        players_sha256=hashlib.sha256(players_raw).hexdigest(),
    )


def _load_source_snapshot(players_csv: Path, memberships_csv: Path) -> _SourceSnapshot:
    # Serialize cache misses so concurrent squad requests share one parse.
    with _SOURCE_CACHE_LOCK:
        for _ in range(_SOURCE_READ_ATTEMPTS):
            key = (
                SourceFileStamp.read(players_csv),
                SourceFileStamp.read(memberships_csv),
            )
            cached = _SOURCE_CACHE.get(key)
            if cached is not None:
                _SOURCE_CACHE.move_to_end(key)
                return cached
            snapshot = _build_source_snapshot(players_csv, memberships_csv)
            current_key = (
                SourceFileStamp.read(players_csv),
                SourceFileStamp.read(memberships_csv),
            )
            if key != current_key:
                continue
            _SOURCE_CACHE[key] = snapshot
            if len(_SOURCE_CACHE) > _SOURCE_CACHE_LIMIT:
                _SOURCE_CACHE.popitem(last=False)
            return snapshot
    raise ValueError(
        "Player attribute source CSV files changed while being read. Try again."
    )


def list_attribute_teams(
    *,
    players_csv: Path,
    memberships_csv: Path,
    team_id: str | None = None,
    team_name: str | None = None,
) -> tuple[TeamIdentity, ...]:
    """Select identities before roster validation, or audit the full catalog."""
    if team_id is not None or team_name is not None:
        if team_id is not None and team_name is not None:
            raise ValueError("Provide exactly one selector: team_name or team_id.")
        _, membership_rows = _read_csv_snapshot(memberships_csv, _MEMBERSHIP_COLUMNS)
        candidates = {
            TeamIdentity(entry.cells[name_column], kind, entry.cells[id_column])
            for entry in membership_rows
            for id_column, name_column, kind in _TEAM_DIMENSIONS.values()
            if (
                entry.cells[id_column] == team_id
                if team_id is not None
                else entry.cells[name_column] == team_name
            )
        }
        if len(candidates) != 1:
            raise ValueError(
                "Team selection must match exactly one team; use its exact name or --team-id"
            )
        return tuple(candidates)
    _, player_rows = _read_csv_snapshot(players_csv, _PLAYERS_COLUMNS)
    _, membership_rows = _read_csv_snapshot(memberships_csv, _MEMBERSHIP_COLUMNS)
    _players_index(player_rows, players_csv)
    members: dict[TeamIdentity, set[str]] = {}
    identities: dict[str, TeamIdentity] = {}
    for entry in membership_rows:
        row_number, row = entry.number, entry.cells
        player_id = _positive_id(row["Id"], f"{memberships_csv}: row {row_number} Id")
        for id_column, name_column, kind in _TEAM_DIMENSIONS.values():
            if row[id_column] in {"", "0"}:
                continue
            team = TeamIdentity(row[name_column], kind, row[id_column])
            previous = identities.setdefault(team.team_id, team)
            if previous != team:
                raise ValueError(
                    f"{memberships_csv}: inconsistent team ID {team.team_id}."
                )
            squad = members.setdefault(team, set())
            if player_id in squad:
                raise ValueError(
                    f"{memberships_csv}: duplicate Player ID {player_id} in {team.name}."
                )
            squad.add(player_id)
    return tuple(members)


def resolve_design_targets(
    *,
    players_csv: Path,
    memberships_csv: Path,
    team_name: str | None = None,
    team_id: str | None = None,
    team_kind: str = "auto",
) -> tuple[TeamIdentity, tuple[PlayerDesignTarget, ...]]:
    """Resolve the full squad in membership order using current CSV ages."""
    players_path = Path(players_csv).resolve()
    memberships_path = Path(memberships_csv).resolve()
    snapshot = _load_source_snapshot(players_path, memberships_path)
    identity, ordered_ids = _select_team(
        snapshot=snapshot,
        memberships_csv=memberships_path,
        team_name=team_name,
        team_id=team_id,
        team_kind=team_kind,
    )

    targets = tuple(
        _design_target(snapshot, players_path, player_id) for player_id in ordered_ids
    )
    return identity, targets


def _design_target(
    snapshot: _SourceSnapshot,
    players_csv: Path,
    player_id: str,
) -> PlayerDesignTarget:
    matches = snapshot.players.get(player_id, ())
    if not matches:
        raise ValueError(
            f"Player ID {player_id} from the selected roster was not found "
            f"in {players_csv}."
        )
    if len(matches) != 1:
        row_numbers = ", ".join(str(entry.number) for entry in matches)
        raise ValueError(
            f"Player ID {player_id} must appear exactly once in {players_csv}; "
            f"found {len(matches)} rows ({row_numbers})."
        )
    row_number, row = matches[0].number, matches[0].cells
    name = _required_text(row["Name"], f"{players_csv}: row {row_number} Name")
    current_age = _positive_integer(row["Age"], f"{players_csv}: row {row_number} Age")
    national, club = _affiliation_index(
        snapshot.memberships_by_player.get(player_id, ())
    ).get(player_id, ("", ""))
    return PlayerDesignTarget(
        player_id=player_id,
        name=name,
        designated_age=current_age,
        source_players_sha256=snapshot.players_sha256,
        height=row["Height"],
        weight=row["Weight"],
        country_1=_country_name(
            row["Country"], f"{players_csv}: row {row_number} Country"
        ),
        country_2=_country_name(
            row["Country2"], f"{players_csv}: row {row_number} Country2"
        ),
        national_affiliations=national,
        club_affiliations=club,
    )


__all__ = [
    "list_attribute_teams",
    "PlayerDesignTarget",
    "SourceFileStamp",
    "TeamIdentity",
    "resolve_design_targets",
]
