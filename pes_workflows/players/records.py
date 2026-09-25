"""Parse authoritative PLAYER_RECORDS documents and project dossier scopes."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from pes_workflows.domain.vocabulary import POSITION_CODES


def parse_familiarity_positions(raw: str, where: str) -> set[str]:
    value = raw.replace("`", "").replace("**", "").strip()
    if value.casefold() in {"none", "-", "–", "—", "n/a", "na"}:
        return set()
    tokens = [
        token.strip().upper()
        for token in re.split(r"\s*[,;/]\s*", value)
        if token.strip()
    ]
    invalid = [token for token in tokens if token not in POSITION_CODES]
    if invalid:
        raise ValueError(
            f"{where}: unknown position code(s) {', '.join(invalid)}; "
            f"valid values are {', '.join(POSITION_CODES)}."
        )
    if len(tokens) != len(set(tokens)):
        raise ValueError(f"{where}: the Familiarity position list repeats a value.")
    return set(tokens)


def _parse_dossier_attributes_and_skills(body: str) -> dict[str, Any]:
    """Extract role-relevant abilities, skills, and physical profile fields."""
    foot_match = re.search(r"Preferred Foot:\s*(Left|Right)\b", body, re.IGNORECASE)
    foot = foot_match.group(1).capitalize() if foot_match else "Right"

    height_match = re.search(r"Height:\s*([0-9]+)\s*cm", body, re.IGNORECASE)
    height = int(height_match.group(1)) if height_match else 180

    skills: set[str] = set()
    skills_match = re.search(r"-\s*\*\*Player Skills\*\*:\s*(.*?)$", body, re.MULTILINE)
    if skills_match:
        raw_skills = skills_match.group(1).strip()
        if raw_skills.casefold() not in {"none", "-", "–", "—", "n/a"}:
            skills = {
                token.strip()
                for token in re.split(r"\s*[,;/]\s*", raw_skills)
                if token.strip()
            }

    abilities: dict[str, int] = {}
    for name, value in re.findall(r"([A-Za-z\s&/-]+?):\s*([0-9]+)\b", body):
        abilities[name.strip()] = int(value)

    return {
        "foot": foot,
        "height": height,
        "skills": skills,
        "abilities": abilities,
    }


def parse_player_records_identity(content: str, source_label: str) -> dict[str, Any]:
    header = re.search(
        r"^Team:\s*.*?\(ID:\s*([0-9]+)\)\s*\|\s*Total Players:\s*([0-9]+)\s*$",
        content,
        re.MULTILINE,
    )
    if not header:
        raise ValueError(
            f"{source_label}: missing the standard Team header "
            "(Team: ... (ID: n) | Total Players: N)."
        )
    team_id, total_text = header.groups()
    if int(team_id) <= 0:
        raise ValueError(
            f"{source_label}: Team ID must be a positive integer; found {team_id!r}."
        )
    total_players = int(total_text)
    if total_players < 11:
        raise ValueError(
            f"{source_label}: squad size {total_players} is below the minimum of 11."
        )

    matrix_section = re.search(
        r"^##[ \t]+PRE-CALCULATED POSITIONAL SQUAD MATRIX[ \t]*$"
        r"([\s\S]*?)"
        r"^##[ \t]+DETAILED PLAYER DOSSIERS[ \t]*$",
        content,
        re.MULTILINE | re.IGNORECASE,
    )
    if not matrix_section:
        raise ValueError(
            f"{source_label}: missing a complete PRE-CALCULATED POSITIONAL "
            "SQUAD MATRIX section."
        )
    matrix_positions = []
    matrix_header_seen = False
    for line in matrix_section.group(1).splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        position = re.sub(r"[`*_]", "", cells[0]).strip().upper()
        if position == "POSITION":
            normalized_header = [
                re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    re.sub(r"[`*_]", "", cell).strip().casefold(),
                ).strip()
                for cell in cells
            ]
            matrix_header_seen = normalized_header == [
                "position",
                "level 2 players id",
                "level 1 players id",
                "squad available playing styles derived",
            ]
            continue
        if position in POSITION_CODES:
            if len(cells) != 4 or any(not cell.strip() for cell in cells):
                raise ValueError(
                    f"{source_label}: position matrix row {position} must have "
                    "four non-empty columns."
                )
            if any(
                re.search(r"\.\.\.|…|\bplaceholder\b", cell, re.IGNORECASE)
                for cell in cells[1:]
            ):
                raise ValueError(
                    f"{source_label}: position matrix row {position} "
                    "contains a placeholder."
                )
            matrix_positions.append(position)
    if not matrix_header_seen:
        raise ValueError(
            f"{source_label}: the position matrix is missing its standard "
            "four-column header."
        )
    if len(matrix_positions) != len(set(matrix_positions)):
        raise ValueError(f"{source_label}: the position matrix repeats a Position row.")
    missing_positions = [
        position for position in POSITION_CODES if position not in matrix_positions
    ]
    if missing_positions or len(matrix_positions) != len(POSITION_CODES):
        raise ValueError(
            f"{source_label}: the position matrix must cover exactly the 13 "
            "standard Positions; missing: "
            + (", ".join(missing_positions) or "none")
            + f"; valid rows found: {len(matrix_positions)}."
        )

    dossier_matches = list(
        re.finditer(
            r"^### Player:\s*(.*?)\s*\(ID:\s*([0-9]+)\)\s*$",
            content,
            re.MULTILINE,
        )
    )
    players: dict[str, str] = {}
    registered_positions: dict[str, str] = {}
    familiarity: dict[str, dict[str, set[str]]] = {}
    player_stats: dict[str, dict[str, Any]] = {}

    for index, dossier in enumerate(dossier_matches):
        name, player_id = dossier.groups()
        name = name.strip()
        if not name:
            raise ValueError(
                f"{source_label}: Player ID {player_id} has no player name."
            )
        if int(player_id) <= 0:
            raise ValueError(
                f"{source_label}: player {name!r} must have a positive integer ID."
            )
        if player_id in players:
            raise ValueError(f"{source_label}: duplicate player ID {player_id}.")
        next_start = (
            dossier_matches[index + 1].start()
            if index + 1 < len(dossier_matches)
            else len(content)
        )
        body = content[dossier.end() : next_start]
        registered = re.search(r"Registered Position:\s*([A-Z]+)\b", body)
        if not registered:
            raise ValueError(
                f"{source_label}: {name} [ID {player_id}] has no Registered Position."
            )
        registered_position = registered.group(1).upper()
        if registered_position not in POSITION_CODES:
            raise ValueError(
                f"{source_label}: {name} [ID {player_id}] has an unknown "
                f"Registered Position {registered_position!r}."
            )

        searchable_body = body.replace("**", "")

        def extract_familiarity_line(label: str) -> str:
            matches = re.findall(
                rf"^\s*-\s*{re.escape(label)}\s*:\s*(.*?)\s*$",
                searchable_body,
                re.MULTILINE | re.IGNORECASE,
            )
            if len(matches) != 1:
                raise ValueError(
                    f"{source_label}: {name} [ID {player_id}] must contain "
                    f"exactly one `{label}: ...` line; found {len(matches)}."
                )
            return matches[0]

        level_2 = parse_familiarity_positions(
            extract_familiarity_line("Fully Familiar (Level 2)"),
            f"{source_label}: {name} [ID {player_id}] Level 2",
        )
        level_1 = parse_familiarity_positions(
            extract_familiarity_line("Partially Familiar (Level 1)"),
            f"{source_label}: {name} [ID {player_id}] Level 1",
        )
        overlap = level_2 & level_1
        if overlap:
            raise ValueError(
                f"{source_label}: {name} [ID {player_id}] repeats position(s) "
                f"across Level 2 and Level 1: {', '.join(sorted(overlap))}."
            )

        players[player_id] = name
        registered_positions[player_id] = registered_position
        familiarity[player_id] = {"L2": level_2, "L1": level_1}
        player_stats[player_id] = _parse_dossier_attributes_and_skills(body)

    if len(players) != total_players:
        raise ValueError(
            f"{source_label}: the Team header declares {total_players} players, "
            f"but only {len(players)} complete dossier headings were parsed."
        )
    return {
        "team_id": team_id,
        "total_players": total_players,
        "players": players,
        "registered_positions": registered_positions,
        "familiarity": familiarity,
        "player_stats": player_stats,
    }


def scope_player_records(
    player_records: str, player_ids: Iterable[str], scope_label: str
) -> str:
    """One call-scoped PLAYER_RECORDS extract, in the order ``player_ids`` gives.

    ``player_records_example.md`` fixes the shape: the header line is copied
    unchanged so ``Total Players`` keeps naming the full squad size ``P``, the
    matrix section is dropped entirely, and the dossier heading always survives.
    """

    dossier_matches = list(
        re.finditer(
            r"^### Player:\s*(.*?)\s*\(ID:\s*([0-9]+)\)\s*$",
            player_records,
            re.MULTILINE,
        )
    )
    blocks: dict[str, str] = {}
    for index, match in enumerate(dossier_matches):
        player_id = match.group(2)
        end = (
            dossier_matches[index + 1].start()
            if index + 1 < len(dossier_matches)
            else len(player_records)
        )
        blocks[player_id] = player_records[match.start() : end].strip()

    selected = list(dict.fromkeys(player_ids))
    missing = [player_id for player_id in selected if player_id not in blocks]
    if missing:
        raise ValueError(
            f"Cannot build {scope_label} PLAYER_RECORDS; missing dossier ID(s): "
            + ", ".join(sorted(set(missing), key=int))
        )
    header = re.search(
        r"^Team:[ \t]*.*?\(ID:[ \t]*[0-9]+\)[ \t]*\|[ \t]*Total Players:[ \t]*[0-9]+"
        r"[ \t]*$",
        player_records,
        re.MULTILINE,
    )
    if not header:
        raise ValueError("Cannot build scoped PLAYER_RECORDS without the Team header.")
    dossiers = "\n\n".join(blocks[player_id] for player_id in selected)
    return f"{header.group(0)}\n\n## DETAILED PLAYER DOSSIERS\n\n{dossiers}"
