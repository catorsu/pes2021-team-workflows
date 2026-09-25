"""Human-readable reporting for validated player-attribute team artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pes_workflows.player_attributes.constants import (
    POSITIONS,
    order_com_styles,
    order_player_skills,
)
from pes_workflows.player_attributes.contracts import PlayerAttributeTeam

_POSITION_ORDER = POSITIONS

_STAT_CATEGORIES = (
    (
        "Attack & Tech",
        (
            ("Off Awareness", "Offensive Awareness"),
            ("Ball Control", "Ball Control"),
            ("Dribbling", "Dribbling"),
            ("Tight Possession", "Tight Possession"),
            ("Finishing", "Finishing"),
        ),
    ),
    (
        "Pass & Set Piece",
        (
            ("Low Pass", "Low Pass"),
            ("Lofted Pass", "Lofted Pass"),
            ("Set Piece Taking", "Set Piece Taking"),
            ("Curl", "Curl"),
            ("Header", "Header"),
        ),
    ),
    (
        "Physical & Mvmt",
        (
            ("Speed", "Speed"),
            ("Acceleration", "Acceleration"),
            ("Kicking Power", "Kicking Power"),
            ("Jump", "Jump"),
            ("Physical Contact", "Physical Contact"),
            ("Balance", "Balance"),
            ("Stamina", "Stamina"),
        ),
    ),
    (
        "Defense & GK",
        (
            ("Def Awareness", "Defensive Awareness"),
            ("Ball Winning", "Ball Winning"),
            ("Aggression", "Aggression"),
            ("GK Awareness", "GK Awareness"),
            ("GK Catching", "GK Catching"),
            ("GK Parrying", "GK Parrying"),
            ("GK Reflexes", "GK Reflexes"),
            ("GK Reach", "GK Reach"),
        ),
    ),
    (
        "Form & Traits",
        (
            ("Weak Foot Usage", "Weak Foot Usage"),
            ("Weak Foot Accuracy", "Weak Foot Accuracy"),
            ("Conditioning", "Conditioning"),
            ("Injury Resistance", "Injury Resistance"),
        ),
    ),
)


_NO_VALUE = "—"


def _markdown_text(value: Any) -> str:
    """Flatten and escape untrusted dynamic text for inline Markdown."""

    text = " ".join(str(value).splitlines()).strip()
    replacements = (
        ("\\", "\\\\"),
        ("`", "\\`"),
        ("*", "\\*"),
        ("_", "\\_"),
        ("[", "\\["),
        ("]", "\\]"),
        ("<", "&lt;"),
        (">", "&gt;"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _render_familiarity(
    familiarity: Mapping[str, Any], registered_position: str
) -> str:
    order = {position: index for index, position in enumerate(_POSITION_ORDER)}
    positions = sorted(
        familiarity,
        key=lambda position: (
            position != registered_position,
            order.get(position, len(order)),
            position,
        ),
    )
    return ", ".join(
        f"{_markdown_text(position)}({familiarity[position]})" for position in positions
    )


def _render_playing_style(value: Any) -> str:
    """``Playing Style`` is nullable; a null renders as the absence marker."""

    return _NO_VALUE if value is None else _markdown_text(value)


def _render_terms(terms: Sequence[Any]) -> str:
    return ", ".join(_markdown_text(term) for term in terms) if terms else _NO_VALUE


def _render_stat_category(
    title: str,
    fields: Sequence[tuple[str, str]],
    stats: Mapping[str, Any],
    rationales: Mapping[str, Any],
) -> str:
    rendered_stats = ", ".join(
        f"{label} {stats[canonical_name]}" for label, canonical_name in fields
    )
    category_rationales = []
    for _label, canonical_name in fields:
        if canonical_name not in rationales:
            continue
        category_rationales.append(
            f"{canonical_name} {stats[canonical_name]}: "
            f"{_markdown_text(rationales[canonical_name])}"
        )
    rationale_suffix = (
        " [" + "; ".join(category_rationales) + "]" if category_rationales else ""
    )
    return f"- **{title}:** {rendered_stats}{rationale_suffix}"


def render_player_attribute_team_markdown(team: PlayerAttributeTeam) -> str:
    """Render one validated team artifact without reparsing model Markdown."""

    if not isinstance(team, PlayerAttributeTeam):
        raise TypeError("team must be a validated PlayerAttributeTeam")

    raw = team.to_dict()
    players = raw["Players"]
    lines = [
        f"# PES 2021 Player Information Report — {_markdown_text(raw['Team Name'])}",
        "",
        f"- **Team Kind:** {_markdown_text(raw['Team Kind'])}",
        f"- **Team ID:** {_markdown_text(raw['Team ID'])}",
        f"- **Players:** {len(players)}",
        f"- **Schema:** `{_markdown_text(raw['Schema Version'])}`",
        "",
        (
            "This report is a human-readable projection of a validated machine "
            "artifact. Injection uses the structured artifact, never this Markdown."
        ),
    ]

    for profile in players:
        player_name = _markdown_text(profile["Player Name"])
        registered_position = profile["Registered Position"]
        stats = {**profile["Abilities"], **profile["Form and Traits"]}
        rationales = profile["Elite Rationales"]
        skills = order_player_skills(profile["Player Skills"])
        com_styles = order_com_styles(profile["COM Playing Styles"])

        lines.extend(
            [
                "",
                "---",
                "",
                f"## {player_name} (Age: {profile['Age']})",
                "",
                f"- **Player ID:** {_markdown_text(profile['Player ID'])}",
                (f"- **Registered Position:** {_markdown_text(registered_position)}"),
                (
                    "- **Position Familiarity:** "
                    + _render_familiarity(
                        profile["Position Familiarity"], registered_position
                    )
                ),
                (
                    "- **Stronger Foot:** "
                    f"{_markdown_text(profile['Stronger Foot'])} "
                    f"(Weak Foot Usage: {stats['Weak Foot Usage']}, "
                    f"Weak Foot Accuracy: {stats['Weak Foot Accuracy']})"
                ),
                f"- **Playing Style:** {_render_playing_style(profile['Playing Style'])}",
                f"- **Player Skills [{len(skills)}]:** {_render_terms(skills)}",
                (
                    f"- **COM Playing Styles [{len(com_styles)}]:** "
                    f"{_render_terms(com_styles)}"
                ),
                "",
                (
                    f"**[{player_name} ({profile['Age']}) - "
                    f"{_markdown_text(registered_position)} - "
                    f"{_render_playing_style(profile['Playing Style'])}]**"
                ),
                "",
            ]
        )
        lines.extend(
            _render_stat_category(title, fields, stats, rationales)
            for title, fields in _STAT_CATEGORIES
        )

    return "\n".join(lines).rstrip() + "\n"


__all__ = ["render_player_attribute_team_markdown"]
