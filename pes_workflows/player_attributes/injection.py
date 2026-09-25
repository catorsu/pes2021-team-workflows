"""Validated, atomic PES ``Players.csv`` attribute injection."""

from __future__ import annotations

import csv
import fcntl
import hashlib
import io
import json
import os
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from pes_workflows.csv_validation import validate_csv_target
from pes_workflows.domain.vocabulary import (
    ABILITY_COLUMN_MAP,
    COM_STYLE_COLUMNS,
    NO_PLAYING_STYLE,
    PLAYER_SKILL_COLUMNS,
    PLAYING_STYLE_IDS,
    POSITION_IDS,
)
from pes_workflows.storage.atomic import write_bytes_atomic
from pes_workflows.storage.semicolon import read_semicolon_csv

from .constants import EDIT_FLAG_COLUMNS
from .contracts import PlayerAttributeTeam, validate_player_attribute_team


@dataclass(frozen=True, slots=True)
class PlayerInjectionResult:
    """Summary of a complete team-level injection attempt."""

    modified_count: int
    players_sha256_before: str
    players_sha256_after: str
    dry_run: bool


@contextmanager
def _exclusive_commit_lock(players_csv: Path) -> Iterator[None]:
    """Serialize compare-and-replace commits across Linux processes."""
    lock_path = players_csv.with_name(f".{players_csv.name}.attributes.lock")
    with lock_path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _required_columns() -> set[str]:
    return {
        "Id",
        "Foot",
        "PlayingStyle",
        "POS",
        *POSITION_IDS,
        *ABILITY_COLUMN_MAP.values(),
        *PLAYER_SKILL_COLUMNS.values(),
        *COM_STYLE_COLUMNS.values(),
        *EDIT_FLAG_COLUMNS,
    }


def _detect_record_terminator(text: str) -> str:
    """Return the first CSV record terminator outside a quoted field."""

    in_quotes = False
    index = 0
    while index < len(text):
        character = text[index]
        if character == '"':
            if in_quotes and index + 1 < len(text) and text[index + 1] == '"':
                index += 2
                continue
            in_quotes = not in_quotes
        elif not in_quotes:
            if character == "\r":
                return "\r\n" if text[index : index + 2] == "\r\n" else "\r"
            if character == "\n":
                return "\n"
        index += 1
    return "\n"


def _read_players_csv(
    path: Path,
) -> tuple[bytes, list[str], list[dict[str, str]], str]:
    try:
        original, fieldnames, rows = read_semicolon_csv(
            path, sorted(_required_columns())
        )
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Players.csv does not exist: {path}") from error
    line_terminator = _detect_record_terminator(original.decode("utf-8-sig"))
    return original, fieldnames, rows, line_terminator


def _index_target_rows(
    rows: Iterable[Mapping[str, str]], target_ids: set[str], path: Path
) -> dict[str, int]:
    counts = {player_id: 0 for player_id in target_ids}
    for row in rows:
        player_id = row.get("Id", "")
        if player_id in counts:
            counts[player_id] += 1
    missing = sorted(player_id for player_id, count in counts.items() if count == 0)
    duplicates = sorted(player_id for player_id, count in counts.items() if count > 1)
    details = []
    if missing:
        details.append("missing IDs: " + ", ".join(missing))
    if duplicates:
        details.append("duplicate IDs: " + ", ".join(duplicates))
    if details:
        raise ValueError(f"{path}: target coverage failed; " + "; ".join(details))
    return counts


def preflight_player_injection(
    *,
    players_csv: Path,
    target_ids: Iterable[str],
    require_commit: bool = False,
) -> str:
    """Validate target coverage and return the exact source-file SHA-256."""

    players_csv = Path(players_csv)
    normalized = tuple(str(player_id) for player_id in target_ids)
    if not normalized:
        raise ValueError("player injection target IDs must not be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError("player injection target IDs must not contain duplicates")
    original, _fieldnames, rows, _line_terminator = _read_players_csv(players_csv)
    _index_target_rows(rows, set(normalized), players_csv)
    if require_commit:
        validate_csv_target(players_csv)
        with _exclusive_commit_lock(players_csv):
            if players_csv.read_bytes() != original:
                raise RuntimeError(
                    f"{players_csv}: changed during commit preflight; retry the run"
                )
    return hashlib.sha256(original).hexdigest()


def _apply_profile(row: dict[str, str], profile: Mapping[str, object]) -> None:
    stronger_foot = str(profile["Stronger Foot"])
    registered = str(profile["Registered Position"])
    row["Foot"] = "True" if stronger_foot == "Left Foot" else "False"
    playing_style = profile["Playing Style"]
    # A null Playing Style is the contract's one nullable value; the editor
    # spells the same absence with its own no-style name
    row["PlayingStyle"] = PLAYING_STYLE_IDS[
        NO_PLAYING_STYLE if playing_style is None else str(playing_style)
    ]

    abilities = profile["Abilities"]
    form_and_traits = profile["Form and Traits"]
    assert isinstance(abilities, Mapping)
    assert isinstance(form_and_traits, Mapping)
    for stat_name, value in abilities.items():
        row[ABILITY_COLUMN_MAP[str(stat_name)]] = str(value)
    for stat_name, value in form_and_traits.items():
        row[ABILITY_COLUMN_MAP[str(stat_name)]] = str(value)

    # No ordering here: a CSV row is a set of independently named columns, so
    # the order the terms are visited in is not observable in the result
    for column in PLAYER_SKILL_COLUMNS.values():
        row[column] = "False"
    skills = profile["Player Skills"]
    assert isinstance(skills, list)
    for skill in skills:
        row[PLAYER_SKILL_COLUMNS[str(skill)]] = "True"

    for column in COM_STYLE_COLUMNS.values():
        row[column] = "False"
    com_styles = profile["COM Playing Styles"]
    assert isinstance(com_styles, list)
    for style in com_styles:
        row[COM_STYLE_COLUMNS[str(style)]] = "True"

    row["POS"] = POSITION_IDS[registered]
    for position in POSITION_IDS:
        row[position] = "0"
    familiarity = profile["Position Familiarity"]
    assert isinstance(familiarity, Mapping)
    for position, rating in familiarity.items():
        row[str(position)] = str(rating)
    # The registered position is an engine invariant even if a future caller
    # reorders or reconstructs the familiarity mapping
    row[registered] = "2"

    for column in EDIT_FLAG_COLUMNS:
        row[column] = "True"


def _render_players_csv(
    fieldnames: list[str], rows: list[dict[str, str]], line_terminator: str
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=fieldnames,
        delimiter=";",
        lineterminator=line_terminator,
        extrasaction="raise",
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def inject_player_attributes(
    *,
    players_csv: Path,
    team: PlayerAttributeTeam,
    dry_run: bool = False,
    expected_players_sha256: str | None = None,
    replace: Callable[[Path, Path], None] = os.replace,
) -> PlayerInjectionResult:
    """Apply one complete validated team artifact in a single CSV commit."""

    raw = validate_player_attribute_team(team.to_dict()).to_dict()
    profile_by_id = {str(item["Player ID"]): item for item in raw["Players"]}

    original, fieldnames, rows, line_terminator = _read_players_csv(players_csv)
    before_hash = hashlib.sha256(original).hexdigest()
    if expected_players_sha256 is not None:
        if (
            not isinstance(expected_players_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_players_sha256) is None
        ):
            raise ValueError(
                "expected_players_sha256 must be a lowercase SHA-256 hex digest"
            )
        if expected_players_sha256 != before_hash:
            raise RuntimeError(
                f"{players_csv}: source snapshot changed since "
                "player-attribute preflight; "
                "refusing to use stale generated profiles"
            )
    _index_target_rows(rows, set(profile_by_id), players_csv)

    modified_count = 0
    for row in rows:
        profile = profile_by_id.get(row["Id"])
        if profile is None:
            continue
        _apply_profile(row, profile)
        modified_count += 1
    if modified_count != len(profile_by_id):
        raise RuntimeError("internal target coverage mismatch before CSV publication")

    rendered_csv = _render_players_csv(fieldnames, rows, line_terminator)
    after_hash = hashlib.sha256(rendered_csv).hexdigest()
    if not dry_run:
        # The advisory lock serializes cooperating subsystem processes. The
        # snapshot comparison is best-effort detection for other writers
        # it does not make the replacement an OS-level compare-and-swap
        with _exclusive_commit_lock(players_csv):
            if players_csv.read_bytes() != original:
                raise RuntimeError(
                    f"{players_csv}: changed concurrently; refusing to overwrite newer data"
                )
            write_bytes_atomic(players_csv, rendered_csv, replace=replace)

    return PlayerInjectionResult(
        modified_count=modified_count,
        players_sha256_before=before_hash,
        players_sha256_after=after_hash,
        dry_run=dry_run,
    )


def read_player_attribute_team(path: Path) -> PlayerAttributeTeam:
    """Read one run's stored merged artifact and revalidate it."""

    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"{path}: expected a UTF-8 JSON artifact") from error
    try:
        payload = json.loads(text)
    except ValueError as error:
        raise ValueError(f"{path}: is not valid JSON") from error
    if not isinstance(payload, Mapping):
        raise ValueError(f"{path}: does not contain a JSON object")
    return validate_player_attribute_team(payload)


__all__ = [
    "PlayerInjectionResult",
    "inject_player_attributes",
    "preflight_player_injection",
    "read_player_attribute_team",
]
