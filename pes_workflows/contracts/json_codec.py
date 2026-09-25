"Strict JSON parsing and reusable artifact-schema primitives."

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .constants import SUPPORTED_SCHEMA_VERSIONS
from .errors import ArtifactSchemaError, ArtifactSyntaxError


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def parse_single_json_artifact(text: str, artifact: str = "Artifact") -> dict[str, Any]:
    "Parse exactly one bare JSON object and reject wrappers or non-JSON values."

    stripped = text.strip()
    if not stripped:
        raise ArtifactSyntaxError(artifact, "$", "response is empty")

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant {value!r}")

    try:
        value = json.loads(
            stripped,
            object_pairs_hook=_strict_object,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise ArtifactSyntaxError(
            artifact, "$", f"invalid single JSON object: {error}"
        ) from error
    if not isinstance(value, dict):
        raise ArtifactSchemaError(artifact, "$", "root value must be an object")
    return value


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _path(parent: str, child: Any) -> str:
    if isinstance(child, int):
        return f"{parent}[{child}]"
    return f"{parent}.{child}" if parent != "$" else f"$.{child}"


def _expect_object(value: Any, artifact: str, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ArtifactSchemaError(artifact, path, "must be an object")
    return value


def _expect_exact_keys(
    value: Mapping[str, Any], keys: Sequence[str], artifact: str, path: str
) -> None:
    expected = set(keys)
    actual = set(value)
    if actual == expected:
        return
    details = []
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        details.append("missing " + ", ".join(repr(key) for key in missing))
    if extra:
        details.append("unexpected " + ", ".join(repr(key) for key in extra))
    raise ArtifactSchemaError(artifact, path, "; ".join(details))


def _expect_ordered_keys(
    value: Mapping[str, Any], keys: Sequence[str], artifact: str, path: str
) -> None:
    """Exact keys *and* the emission order the match-plan output protocol fixes.

    ``parse_single_json_artifact`` preserves the model's key order, so the
    system prompt's "in this order" clause is checkable rather than advisory.
    """

    _expect_exact_keys(value, keys, artifact, path)
    if tuple(value) != tuple(keys):
        raise ArtifactSchemaError(
            artifact,
            path,
            "keys must be emitted in the order " + ", ".join(repr(key) for key in keys),
        )


def _expect_list(value: Any, artifact: str, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ArtifactSchemaError(artifact, path, "must be an array")
    return value


def _expect_string(value: Any, artifact: str, path: str) -> str:
    if not isinstance(value, str):
        raise ArtifactSchemaError(artifact, path, "must be a string")
    if value != value.strip():
        raise ArtifactSchemaError(
            artifact, path, "must not contain leading or trailing whitespace"
        )
    if not value:
        raise ArtifactSchemaError(artifact, path, "must not be empty")
    return value


def _expect_int(value: Any, artifact: str, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArtifactSchemaError(artifact, path, "must be an integer")
    return value


def _expect_enum(value: Any, legal: Sequence[str], artifact: str, path: str) -> str:
    string = _expect_string(value, artifact, path)
    if string not in legal:
        raise ArtifactSchemaError(
            artifact,
            path,
            f"must be one of {', '.join(repr(item) for item in legal)}",
        )
    return string


def _expect_string_list(
    value: Any,
    artifact: str,
    path: str,
    *,
    min_items: int = 0,
    unique: bool = False,
) -> tuple[str, ...]:
    items = _expect_list(value, artifact, path)
    if len(items) < min_items:
        raise ArtifactSchemaError(
            artifact, path, f"must contain at least {min_items} item(s)"
        )
    parsed = tuple(
        _expect_string(item, artifact, _path(path, index))
        for index, item in enumerate(items)
    )
    if unique and len(set(parsed)) != len(parsed):
        raise ArtifactSchemaError(artifact, path, "must not contain duplicates")
    return parsed


def _validate_common(
    raw: Mapping[str, Any], artifact_name: str, expected_keys: Sequence[str]
) -> str:
    _expect_ordered_keys(raw, expected_keys, artifact_name, "$")
    schema_version = _expect_string(
        raw["Schema Version"], artifact_name, "$.Schema Version"
    )
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ArtifactSchemaError(
            artifact_name,
            "$.Schema Version",
            "must be one of "
            + ", ".join(repr(version) for version in SUPPORTED_SCHEMA_VERSIONS),
        )
    if raw["Artifact"] != artifact_name:
        raise ArtifactSchemaError(
            artifact_name, "$.Artifact", f"must equal {artifact_name!r}"
        )
    return schema_version
