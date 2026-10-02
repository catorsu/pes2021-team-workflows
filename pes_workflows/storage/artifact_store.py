"""Publish accepted match-plan artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pes_workflows.contracts.json_codec import canonical_json
from pes_workflows.storage.atomic import write_text_atomic
from pes_workflows.storage.filenames import slugify


def write_artifact_files(*, team_output_dir: Path, record: Mapping[str, Any]) -> None:
    stem = f"Turn_{record['turn']:02d}_{slugify(record['title'])}"
    write_text_atomic(
        team_output_dir / f"{stem}.json", canonical_json(record["raw"]) + "\n"
    )
