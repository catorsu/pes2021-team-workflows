"""CSV parsing and exact attribute replay comparisons."""

from __future__ import annotations

import csv
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path


def validate_csv_file(path: Path, *, writable: bool = False) -> None:
    if not path.is_file():
        hint = (
            "; check that the Windows drive is mounted in WSL and the export path is correct"
            if path.as_posix().startswith("/mnt/")
            else ""
        )
        raise FileNotFoundError(
            f"CSV file not found or not a regular file: {path}{hint}"
        )
    if not os.access(path, os.R_OK):
        raise PermissionError(f"CSV file is not readable: {path}")
    with path.open("rb") as stream:
        stream.read(1)
    if writable:
        if not os.access(path, os.W_OK):
            raise PermissionError(f"CSV file is not writable: {path}")
        with path.open("r+b"):
            pass


def validate_csv_target(path: Path) -> None:
    validate_csv_file(path, writable=True)
    with tempfile.TemporaryFile(dir=path.parent):
        pass


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def attribute_mismatches(
    original: Sequence[Mapping[str, str]],
    current: Sequence[Mapping[str, str]],
    expected: Mapping[str, Mapping[str, str]],
) -> list[str]:
    if [r["Id"] for r in original] != [r["Id"] for r in current]:
        raise RuntimeError("CSV row count or ordering changed")
    return [r["Id"] for r in current if r != expected[r["Id"]]]
