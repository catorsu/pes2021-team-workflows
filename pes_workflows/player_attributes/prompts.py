"Prompt loading for the two-call, team-level player-attribute workflow."

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pes_workflows.prompts.assets import read_prompt_text

from ..config import Config

_SYSTEM_PROMPT_FILENAME = "system_prompt.md"
_USER_PROMPT_FILENAME = "user_message_template.md"
_GLOSSARY_FILENAME = "player_glossary.md"

_GLOSSARY_PLACEHOLDER = "[PASTE PLAYER_GLOSSARY HERE]"
_PLAYER_INPUT_PLACEHOLDER = "[PASTE PLAYER_INPUT HERE]"
_FROZEN_PROFILES_PLACEHOLDER = "[PASTE FROZEN_PLAYER_PROFILES HERE]"
_SYSTEM_PLACEHOLDERS = frozenset({_GLOSSARY_PLACEHOLDER})
_PROFILES_PLACEHOLDERS = frozenset({_PLAYER_INPUT_PLACEHOLDER})
_ABILITIES_PLACEHOLDERS = frozenset(
    {_FROZEN_PROFILES_PLACEHOLDER, _PLAYER_INPUT_PLACEHOLDER}
)
_PLACEHOLDER_PATTERN = re.compile(r"\[PASTE [A-Z0-9_ -]+ HERE\]")

# The roster table's columns, in the order the contract calls normative
_ROSTER_COLUMNS = (
    "Player ID",
    "Player Name",
    "Designated Age",
    "Height",
    "Weight",
    "Country 1",
    "Country 2",
    "National Affiliations",
    "Club Affiliations",
)
_TEAM_HEADER_COLUMNS = ("Team Name", "Team ID")


def _read_prompt_asset(path: Path, *, description: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Required {description} not found: {path}")
    content = read_prompt_text(path).strip()
    if not content:
        raise ValueError(f"{description.capitalize()} must not be empty: {path}")
    return content


def _validate_placeholders(
    template: str,
    required: frozenset[str],
    *,
    description: str,
) -> None:
    for placeholder in sorted(required):
        count = template.count(placeholder)
        if count != 1:
            raise ValueError(
                f"{description} must contain {placeholder!r} exactly once; "
                f"found {count}"
            )
    unexpected = sorted(set(_PLACEHOLDER_PATTERN.findall(template)) - required)
    if unexpected:
        raise ValueError(
            f"{description} contains unsupported placeholders: " + ", ".join(unexpected)
        )


def _parse_user_templates(content: str) -> tuple[str, str]:
    """Split the two stage messages out of the single-mode user template."""

    pattern = r"## Call\s+(\d+)\b.*?```(?:text)?\s*\n(.*?)\n```"
    matches = re.findall(pattern, content, re.DOTALL)
    if len(matches) != 2:
        raise ValueError(
            "user_message_template.md must contain exactly two Call templates; "
            f"found {len(matches)}"
        )

    prompts: list[str] = []
    for expected, (call_number, prompt) in enumerate(matches, start=1):
        rendered = prompt.strip()
        # The task text closes the message, behind that call's data blocks
        stage_match = re.search(r"^STAGE (\d+) OF 2.*", rendered, re.MULTILINE)
        if (
            int(call_number) != expected
            or stage_match is None
            or int(stage_match.group(1)) != expected
        ):
            stage_line = "" if stage_match is None else stage_match.group(0)
            raise ValueError(
                "user_message_template.md call numbering is inconsistent: "
                f"expected Call/STAGE {expected}, found Call {call_number} with "
                f"stage line {stage_line!r}"
            )
        prompts.append(rendered)

    # Call 1 receives the roster alone; Call 2 receives the frozen Stage 1
    # artifact beside it. Any other placeholder would reach the model unfilled
    for description, template, required in (
        ("Call 1", prompts[0], _PROFILES_PLACEHOLDERS),
        ("Call 2", prompts[1], _ABILITIES_PLACEHOLDERS),
    ):
        _validate_placeholders(
            template, required, description=f"{description} template"
        )
    return prompts[0], prompts[1]


def _value_from(
    value: Any,
    *,
    attributes: Sequence[str],
    keys: Sequence[str],
    label: str,
) -> Any:
    if isinstance(value, Mapping):
        for key in keys:
            if key in value:
                return value[key]
    else:
        for attribute in attributes:
            if hasattr(value, attribute):
                return getattr(value, attribute)
    raise TypeError(f"{label} is missing from {type(value).__name__}")


def _single_line(value: Any, *, label: str) -> str:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{label} must be a non-empty scalar value")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} must not be empty")
    if len(text.splitlines()) != 1:
        raise ValueError(f"{label} must not contain line breaks")
    return text


def _escape_cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|")


def _table_cell(value: Any, *, label: str) -> str:
    return _escape_cell(_single_line(value, label=label))


def _optional_cell(value: Any) -> str:
    """A context column, blank when the editor database recorded no value."""

    if value is None:
        return ""
    return _escape_cell(" ".join(str(value).split()))


def _positive_age(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    if isinstance(value, int):
        age = value
    elif isinstance(value, str) and value.strip().isascii() and value.strip().isdigit():
        age = int(value.strip())
    else:
        raise ValueError(f"{label} must be a positive integer")
    if age <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return age


def _markdown_table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    return [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
        *("| " + " | ".join(row) + " |" for row in rows),
    ]


def _render_player_input(team: Any, targets: Sequence[Any]) -> str:
    """Render ``PLAYER_INPUT``: the team header table, then the roster table.

    The order of the two tables is normative in the contract, as is the roster
    column order.
    """

    target_rows = tuple(targets)
    if not target_rows:
        raise ValueError("targets must contain at least one player")

    team_name = _table_cell(
        _value_from(
            team,
            attributes=("name",),
            keys=("Team Name",),
            label="Team Name",
        ),
        label="Team Name",
    )
    team_id = _table_cell(
        _value_from(
            team,
            attributes=("team_id",),
            keys=("Team ID",),
            label="Team ID",
        ),
        label="Team ID",
    )

    rows: list[Sequence[str]] = []
    seen_ids: set[str] = set()
    for index, target in enumerate(target_rows):
        player_id = _single_line(
            _value_from(
                target,
                attributes=("player_id",),
                keys=("Player ID",),
                label=f"targets[{index}] Player ID",
            ),
            label=f"targets[{index}] Player ID",
        )
        if player_id in seen_ids:
            raise ValueError(f"targets contains duplicate Player ID {player_id!r}")
        seen_ids.add(player_id)
        player_name = _table_cell(
            _value_from(
                target,
                attributes=("name",),
                keys=("Player Name",),
                label=f"targets[{index}] Player Name",
            ),
            label=f"targets[{index}] Player Name",
        )
        age = _positive_age(
            _value_from(
                target,
                attributes=("designated_age",),
                keys=("Designated Age",),
                label=f"targets[{index}] Designated Age",
            ),
            label=f"targets[{index}] Designated Age",
        )
        rows.append(
            (
                _escape_cell(player_id),
                player_name,
                str(age),
                _optional_cell(getattr(target, "height", "")),
                _optional_cell(getattr(target, "weight", "")),
                _optional_cell(getattr(target, "country_1", "")),
                _optional_cell(getattr(target, "country_2", "")),
                _optional_cell(getattr(target, "national_affiliations", "")),
                _optional_cell(getattr(target, "club_affiliations", "")),
            )
        )

    lines = _markdown_table(_TEAM_HEADER_COLUMNS, ((team_name, team_id),))
    lines.append("")
    lines.extend(_markdown_table(_ROSTER_COLUMNS, rows))
    return "\n".join(lines)


def _artifact_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if not callable(to_dict):
        raise TypeError("validated_profiles must be a mapping or expose to_dict()")
    rendered = to_dict()
    if not isinstance(rendered, Mapping):
        raise TypeError("validated_profiles.to_dict() must return a mapping")
    return rendered


def _render_user_prompt(template: str, blocks: Mapping[str, str]) -> str:
    """Fill one call's data blocks, keeping the template's own block order.

    One pass over the template, so a bracketed phrase inside the frozen
    artifact cannot swallow the roster block that follows it.
    """

    return _PLACEHOLDER_PATTERN.sub(lambda match: blocks[match.group(0)], template)


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "validated_profiles must contain only finite JSON-compatible values"
        ) from error


class PlayerAttributePromptBuilder:
    "Build the two team-scoped calls for one immutable roster."

    def __init__(
        self,
        system_prompt: str | None = None,
        *,
        prompts_dir: Path | str | None = None,
        glossary_path: Path | str | None = None,
    ) -> None:
        selected_dir = (
            Path(Config.DEFAULT_PLAYER_ATTRIBUTE_PROMPTS_DIR)
            if prompts_dir is None
            else Path(prompts_dir)
        )
        selected_glossary = (
            selected_dir.parent / "shared" / _GLOSSARY_FILENAME
            if glossary_path is None
            else Path(glossary_path)
        )

        system_template = (
            _read_prompt_asset(
                selected_dir / _SYSTEM_PROMPT_FILENAME,
                description="player-attribute system prompt",
            )
            if system_prompt is None
            else system_prompt
        )
        if not isinstance(system_template, str):
            raise TypeError("system_prompt must be a string or None")
        system_template = system_template.strip()
        if not system_template:
            raise ValueError("system_prompt must not be empty")
        _validate_placeholders(
            system_template,
            _SYSTEM_PLACEHOLDERS,
            description=_SYSTEM_PROMPT_FILENAME,
        )
        glossary = _read_prompt_asset(
            selected_glossary,
            description="player-attribute glossary",
        )

        user_template = _read_prompt_asset(
            selected_dir / _USER_PROMPT_FILENAME,
            description="player-attribute user prompt template",
        )
        profiles_template, abilities_template = _parse_user_templates(user_template)

        self.prompts_dir: Path = selected_dir
        self.glossary_path: Path = selected_glossary
        self._system_prompt: str = system_template.replace(
            _GLOSSARY_PLACEHOLDER,
            f"```markdown\n{glossary}\n```",
        )
        self._profiles_template: str = profiles_template
        self._abilities_template: str = abilities_template

    def build_profiles_call(self, team: Any, targets: Sequence[Any]) -> tuple[str, str]:
        "Build Call 1 as ``(system_prompt, user_prompt)``."

        if isinstance(targets, (str, bytes)) or not isinstance(targets, Sequence):
            raise TypeError("targets must be a sequence of player targets")
        player_input = _render_player_input(team, targets)
        user_prompt = _render_user_prompt(
            self._profiles_template,
            {_PLAYER_INPUT_PLACEHOLDER: f"```markdown\n{player_input}\n```"},
        )
        return self._system_prompt, user_prompt

    def build_abilities_call(
        self, team: Any, targets: Sequence[Any], validated_profiles: Any
    ) -> tuple[str, str]:
        "Build Call 2 with the accepted Call-1 artifact frozen as JSON."

        if isinstance(targets, (str, bytes)) or not isinstance(targets, Sequence):
            raise TypeError("targets must be a sequence of player targets")
        profiles = _artifact_mapping(validated_profiles)
        if profiles.get("Artifact") != "PlayerProfiles":
            raise ValueError(
                "validated_profiles must be a PlayerProfiles artifact mapping"
            )
        # PLAYER_INPUT is identical in both calls: Stage 2 reads physique and
        # context from it while the frozen artifact governs every Stage 1 field
        player_input = _render_player_input(team, targets)
        user_prompt = _render_user_prompt(
            self._abilities_template,
            {
                _FROZEN_PROFILES_PLACEHOLDER: (
                    f"```json\n{_canonical_json(profiles)}\n```"
                ),
                _PLAYER_INPUT_PLACEHOLDER: f"```markdown\n{player_input}\n```",
            },
        )
        return self._system_prompt, user_prompt


__all__ = ["PlayerAttributePromptBuilder"]
