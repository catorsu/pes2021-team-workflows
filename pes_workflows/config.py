"""Defaults and TOML configuration shared by the headless workflows."""

import argparse
import math
import sys
import tomllib
from pathlib import Path
from typing import Any, TypedDict

from pes_workflows.paths import normalize_path

PROMPTS_DIR: Path = Path(__file__).resolve().parent / "prompts"


class Config:
    DEFAULT_MODEL: str = "claude-opus-5-5"
    DEFAULT_EFFORT: str = "high"
    EFFORT_CHOICES: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")
    DEFAULT_PLAYER_ATTRIBUTE_MAX_TURNS: int = 80
    DEFAULT_PRESET_MODE: str = "multi"
    SUPPORTED_PRESET_MODES: tuple[str, ...] = ("multi", "single")
    DEFAULT_PLAYER_ATTRIBUTE_PROMPTS_DIR: Path = PROMPTS_DIR / "player_attributes"
    MAX_RETRIES: int = 3
    RETRY_INITIAL_BACKOFF: int = 5
    MAX_FORMAT_REPAIRS: int = 1
    DEFAULT_AUTO_SUBSTITUTIONS: int = 2
    DEFAULT_AUTO_CHANGE_ATT_DEF: int = 0


GLOBAL_AUTO_CHOICES = {
    "auto_substitutions": (0, 1, 2, 3),
    "auto_change_att_def": (0, 1),
    "auto_switch_preset_tactics": (0, 1),
}


class GlobalAutoOptions(TypedDict):
    auto_substitutions: int
    auto_change_att_def: int
    auto_switch_preset_tactics: int


def resolve_global_auto_options(
    *,
    preset_mode: str,
    auto_substitutions: int = Config.DEFAULT_AUTO_SUBSTITUTIONS,
    auto_change_att_def: int = Config.DEFAULT_AUTO_CHANGE_ATT_DEF,
    auto_switch_preset_tactics: int | None = None,
) -> GlobalAutoOptions:
    """Validate integer options and apply the legacy auto-switch fallback if omitted."""
    values: GlobalAutoOptions = {
        "auto_substitutions": auto_substitutions,
        "auto_change_att_def": auto_change_att_def,
        "auto_switch_preset_tactics": (
            int(preset_mode == "multi")
            if auto_switch_preset_tactics is None
            else auto_switch_preset_tactics
        ),
    }
    for key, value in values.items():
        if type(value) is not int or value not in GLOBAL_AUTO_CHOICES[key]:
            raise ValueError(
                f"{key} must be an integer in {GLOBAL_AUTO_CHOICES[key]}; got {value!r}"
            )
    return values


def add_global_auto_arguments(parser: argparse.ArgumentParser) -> None:
    help_text = {
        "auto_substitutions": "Auto Substitutions: 0=Off, 1=Very Late, 2=Flexible, 3=Very Early (default: 2)",
        "auto_change_att_def": "Auto-Adjust Att/Def: 0=Off, 1=On (default: 0)",
        "auto_switch_preset_tactics": "Auto Switch Preset Tactics: 0=Off, 1=On (omitted: 0 for single, 1 for multi)",
    }
    defaults = {
        "auto_substitutions": Config.DEFAULT_AUTO_SUBSTITUTIONS,
        "auto_change_att_def": Config.DEFAULT_AUTO_CHANGE_ATT_DEF,
        "auto_switch_preset_tactics": None,
    }
    for key, choices in GLOBAL_AUTO_CHOICES.items():
        parser.add_argument(
            "--" + key.replace("_", "-"),
            type=int,
            choices=choices,
            default=defaults[key],
            help=help_text[key],
        )


DEFAULT_CONFIG_NAME = "pes-workflows.toml"
CSV_PATH_OPTIONS = {
    "players_csv",
    "teams_players_csv",
    "rosters_csv",
    "formations_csv",
}
SHARED_OPTIONS = CSV_PATH_OPTIONS | {"model", "effort", "delay", "fast"}
MATCH_OPTIONS = (
    SHARED_OPTIONS
    | GLOBAL_AUTO_CHOICES.keys()
    | {
        "output_dir",
        "engine",
        "preset_mode",
        "dry_run",
        "force",
        "attributes_completed_teams",
        "scope",
        "teams",
    }
)
WORKFLOW_OPTIONS = {
    "match_plan": MATCH_OPTIONS,
    "match_plans": MATCH_OPTIONS | {"check_only"},
    "player_attributes": SHARED_OPTIONS
    | {
        "output_dir",
        "check_only",
        "max_teams",
        "max_turns",
        "scope",
        "teams",
    },
}
PATH_OPTIONS = CSV_PATH_OPTIONS | {"output_dir", "attributes_completed_teams"}
BOOL_OPTIONS = {"fast", "dry_run", "force", "check_only"}
CHOICES = {
    "effort": Config.EFFORT_CHOICES,
    "engine": ("claude-code", "codex"),
    "preset_mode": Config.SUPPORTED_PRESET_MODES,
    "scope": ("single", "multiple", "all"),
}


def load_configuration(path: Path) -> dict[str, dict[str, Any]]:
    """Validate absolute CSV paths and resolve other paths beside the TOML file."""
    with path.open("rb") as stream:
        document = tomllib.load(stream)
    sections = {
        "defaults": SHARED_OPTIONS | GLOBAL_AUTO_CHOICES.keys(),
        **WORKFLOW_OPTIONS,
    }
    for section, values in document.items():
        if section not in sections or not isinstance(values, dict):
            raise ValueError(f"Unknown configuration section: {section}")
        for key, value in values.items():
            label = f"{section}.{key}"
            if key not in sections[section]:
                raise ValueError(f"Unknown configuration option: {label}")
            if key in GLOBAL_AUTO_CHOICES:
                valid = type(value) is int and value in GLOBAL_AUTO_CHOICES[key]
            elif key in BOOL_OPTIONS:
                valid = type(value) is bool
            elif key == "delay":
                valid = (
                    type(value) in (int, float) and math.isfinite(value) and value >= 0
                )
            elif key in {"max_teams", "max_turns"}:
                valid = type(value) is int and value > 0
            elif key == "teams":
                valid = isinstance(value, list) and all(
                    isinstance(item, str) and item.strip() for item in value
                )
            else:
                valid = isinstance(value, str) and bool(value.strip())
            if not valid:
                raise ValueError(f"Invalid value for {label}: {value!r}")
            if key in CHOICES and value not in CHOICES[key]:
                raise ValueError(f"{label} must be one of {CHOICES[key]}")
            if key in PATH_OPTIONS:
                expanded = normalize_path(value)
                if key in CSV_PATH_OPTIONS and not expanded.is_absolute():
                    raise ValueError(f"{label} must be an absolute file path")
                values[key] = (path.parent / expanded).resolve()
    return document


def add_scope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scope", choices=CHOICES["scope"], help="single, multiple, or all teams"
    )


def parse_workflow_args(
    parser: argparse.ArgumentParser, workflow: str, argv: list[str] | None = None
) -> argparse.Namespace:
    """Merge built-ins < defaults < workflow < explicit CLI options."""
    required_csv_paths = (
        {"players_csv", "teams_players_csv"}
        if workflow == "player_attributes"
        else CSV_PATH_OPTIONS
    )
    for option in sorted(CSV_PATH_OPTIONS):
        parser.add_argument(
            "--" + option.replace("_", "-"),
            type=normalize_path,
            required=option in required_csv_paths,
            help="Absolute path to the " + option.replace("_", " ") + " file",
        )
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        "--config",
        type=normalize_path,
        help=f"TOML settings (default: ./{DEFAULT_CONFIG_NAME})",
    )
    config_group.add_argument(
        "--no-config", action="store_true", help="Ignore automatic configuration"
    )
    argv = list(sys.argv[1:] if argv is None else argv)
    probe = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    probe.add_argument("--config", type=normalize_path)
    probe.add_argument("--no-config", action="store_true")
    known, _ = probe.parse_known_args(argv)
    settings: dict[str, Any] = {}
    path = known.config or Path.cwd() / DEFAULT_CONFIG_NAME
    if not known.no_config and "--help" not in argv and "-h" not in argv:
        if known.config is not None or path.exists():
            try:
                document = load_configuration(path.resolve())
            except (OSError, ValueError) as exc:
                parser.error(f"Cannot load configuration {path}: {exc}")
            settings = {
                key: value
                for key, value in {
                    **document.get("defaults", {}),
                    **document.get(workflow, {}),
                }.items()
                if key in WORKFLOW_OPTIONS[workflow]
            }

    # A CLI selection replaces the entire configured selection, never appends.
    cli_selection = any(
        arg.split("=", 1)[0] in {"--team", "--team-id", "--scope"} for arg in argv
    )
    teams = settings.pop("teams", [])
    scope = settings.pop("scope", None)
    if cli_selection:
        teams, scope = [], None
    if scope is None:
        scope = ("single" if len(teams) == 1 else "multiple") if teams else None
    if scope == "all" and teams:
        parser.error("scope=all cannot include teams")
    if scope == "single" and len(teams) != 1:
        parser.error("scope=single requires exactly one configured team")
    if scope == "multiple" and len(teams) < 2:
        parser.error("scope=multiple requires at least two configured teams")
    if workflow == "player_attributes" and "output_dir" in settings:
        settings["output"] = settings.pop("output_dir")
    for action in parser._actions:
        if action.dest in settings:
            value = settings[action.dest]
            if action.choices is not None and value not in action.choices:
                parser.error(
                    f"Invalid configuration {action.dest}: {value!r}; choose from {action.choices}"
                )
            action.required = False
    parser.set_defaults(**settings)
    args = parser.parse_args(argv)
    if workflow in {"match_plan", "match_plans"}:
        try:
            resolved = resolve_global_auto_options(
                preset_mode=args.preset_mode,
                **{key: getattr(args, key) for key in GLOBAL_AUTO_CHOICES},
            )
        except ValueError as exc:
            parser.error(str(exc))
        for key, value in resolved.items():
            setattr(args, key, value)
    for option in PATH_OPTIONS | {"output"}:
        value = getattr(args, option, None)
        if value is not None:
            try:
                value = normalize_path(value)
            except ValueError as exc:
                parser.error(str(exc))
            if option in CSV_PATH_OPTIONS and not value.is_absolute():
                parser.error(
                    f"--{option.replace('_', '-')} must be an absolute file path"
                )
            setattr(
                args, option, value.resolve() if option in CSV_PATH_OPTIONS else value
            )
    if not math.isfinite(args.delay) or args.delay < 0:
        parser.error("--delay must be finite and nonnegative")
    if getattr(args, "max_teams", None) is not None and args.max_teams < 1:
        parser.error("--max-teams must be positive")
    if getattr(args, "max_turns", None) is not None and args.max_turns < 1:
        parser.error("--max-turns must be positive")
    if cli_selection:
        teams = args.team or []
        if isinstance(teams, str):
            teams = [teams]
        if getattr(args, "team_id", None) is not None:
            teams = [args.team_id]
        scope = args.scope
    scope = scope or (("single" if len(teams) == 1 else "multiple") if teams else "all")
    if (
        (scope == "all" and teams)
        or (scope == "single" and len(teams) != 1)
        or (scope == "multiple" and len(teams) < 2)
    ):
        parser.error(
            "Team selection does not match scope (single: one, multiple: two or more, all: no selectors)"
        )
    if workflow == "match_plan" and (scope != "single" or len(teams) != 1):
        parser.error(
            "Single match plans require exactly one team; use pes-match-plans for multiple/all"
        )
    args.scope = scope
    args.teams = teams
    if workflow == "match_plan":
        args.team = teams[0]
    elif workflow == "match_plans":
        args.team = teams or None
    return args
