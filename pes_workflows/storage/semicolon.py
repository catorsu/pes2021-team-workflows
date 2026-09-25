"""Structural validation for editor CSV exports, preserving original cells."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from pathlib import Path


def read_semicolon_csv(
    path: Path, required_columns: Iterable[str]
) -> tuple[bytes, list[str], list[dict[str, str]]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"{path}: expected a UTF-8/UTF-8-BOM CSV file.") from error
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=";")
        fields = reader.fieldnames
        if not fields:
            raise ValueError(f"{path}: CSV file is empty or has no header row.")
        if any(not name.strip() for name in fields):
            raise ValueError(f"{path}: CSV header contains an empty column name.")
        if len(fields) != len(set(fields)):
            raise ValueError(f"{path}: CSV contains duplicate column names.")
        missing = [name for name in required_columns if name not in fields]
        if missing:
            raise ValueError(
                f"{path}: missing required CSV column(s): {', '.join(missing)}."
            )
        rows = []
        for number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(
                    f"{path}: row {number} has more fields than the header."
                )
            if any(value is None for value in row.values()):
                raise ValueError(
                    f"{path}: row {number} has fewer fields than the header."
                )
            rows.append(row)
    except csv.Error as error:
        raise ValueError(f"Could not parse semicolon CSV {path}: {error}") from error
    return raw, list(fields), rows
