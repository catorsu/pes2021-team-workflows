"""Publish accepted match-plan artifacts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pes_workflows.contracts.json_codec import canonical_json
from pes_workflows.storage.atomic import write_text_atomic


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s\u4e00-\u9fff-]", "", text)
    return re.sub(r"[\s-]+", "_", text).strip("_")[:40]


def write_artifact_files(*, team_output_dir: Path, record: Mapping[str, Any]) -> None:
    stem = f"Turn_{record['turn']:02d}_{slugify(record['title'])}"
    write_text_atomic(
        team_output_dir / f"{stem}.json", canonical_json(record["raw"]) + "\n"
    )
