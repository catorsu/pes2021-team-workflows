"""Isolated run directories and their atomic manifests."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pes_workflows.contracts.json_codec import canonical_json
from pes_workflows.storage.atomic import write_text_atomic

logger = logging.getLogger(__name__)

RUN_ID_PREFIX = "run_"
BATCH_ID_PREFIX = "batch_"
RUN_MANIFEST_NAME = "run_manifest.json"
MANIFEST_SCHEMA_VERSION = 2

SYSTEM_PROMPT_NAME = "00_Final_System_Prompt.md"
CONVERSATION_HISTORY_NAME = "conversation_history.json"

RUN_STATUS_PREPARED = "prepared"
RUN_STATUS_GENERATED = "generated"
RUN_STATUS_INJECTED = "injected"
RUN_STATUS_INJECTION_FAILED = "injection_failed"
RUN_STATUS_FAILED = "failed"


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def new_run_id() -> str:
    """Return ``run_<UTC>_<uuid12>``."""

    return f"{RUN_ID_PREFIX}{_utc_stamp()}_{uuid.uuid4().hex[:12]}"


def new_batch_id() -> str:
    """Return ``batch_<UTC>_<uuid12>`` — one id shared by every team of a batch."""

    return f"{BATCH_ID_PREFIX}{_utc_stamp()}_{uuid.uuid4().hex[:12]}"


def utc_timestamp() -> str:
    """An ISO-8601 UTC instant with a literal ``Z``."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def create_run_dir(team_root: Path, run_id: str | None = None) -> Path:
    """Create one fresh run directory under ``team_root``."""

    run_dir = team_root / (run_id or new_run_id())
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def run_manifest_path(run_dir: Path) -> Path:
    return run_dir / RUN_MANIFEST_NAME


def write_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    """Publish one complete manifest atomically, never a truncated target."""

    write_text_atomic(path, canonical_json(payload) + "\n")


def _deep_update(target: dict[str, Any], fields: Mapping[str, Any]) -> None:
    """One-level-deep merge, so ``update(source={...})`` does not drop siblings."""

    for key, value in fields.items():
        existing = target.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            existing.update(value)
        else:
            target[key] = value


class RunRecorder:
    """Owns one run directory's manifest; created per ``run_team`` call."""

    __slots__ = (
        "run_dir",
        "manifest_path",
        "run_id",
        "started_at",
        "_started_monotonic",
        "_payload",
        "_final",
        "_lock",
    )

    def __init__(self, run_dir: Path, *, manifest_path: Path | None = None) -> None:
        self.run_dir: Path = run_dir
        self.manifest_path: Path = manifest_path or run_manifest_path(run_dir)
        self.run_id: str = run_dir.name
        self.started_at: str = utc_timestamp()
        self._started_monotonic: float = time.monotonic()
        self._payload: dict[str, Any] = {}
        self._final: bool = False
        self._lock: threading.Lock = threading.Lock()

    def start(self, payload: Mapping[str, Any]) -> None:
        """Seed and publish the ``prepared`` manifest."""

        with self._lock:
            self._payload = dict(payload)
            self._payload["status"] = RUN_STATUS_PREPARED
            self._payload["started_at"] = self.started_at
            self._payload.setdefault("finished_at", None)
            self._payload.setdefault("elapsed_s", None)
            self._payload.setdefault("error", None)
        self._publish()

    def update(self, status: str | None = None, **fields: Any) -> None:
        """Record a non-terminal transition; a later ``finish`` may override it."""

        with self._lock:
            if self._final:
                return
            if status is not None:
                self._payload["status"] = status
            _deep_update(self._payload, fields)
        self._publish()

    def finish(self, status: str, **fields: Any) -> None:
        """Record the terminal transition. First writer wins."""

        with self._lock:
            if self._final:
                return
            self._final = True
            self._payload["status"] = status
            self._payload["finished_at"] = utc_timestamp()
            self._payload["elapsed_s"] = round(
                time.monotonic() - self._started_monotonic, 3
            )
            _deep_update(self._payload, fields)
        self._publish()

    def _publish(self) -> None:
        # A manifest write must never turn a successful build into a failure
        # the same rule the player-attribute finalize handler follows
        try:
            with self._lock:
                snapshot = dict(self._payload)
            write_manifest(self.manifest_path, snapshot)
        except (OSError, TypeError, ValueError):
            # OSError covers a full or read-only disk; TypeError/ValueError
            # cover a caller that put a non-JSON value (a Path, a datetime)
            # into the payload. None of them may reach run_team's blanket
            # handler, which would turn a successful build into a failure
            logger.warning(
                "could not write run manifest %s", self.manifest_path, exc_info=True
            )
