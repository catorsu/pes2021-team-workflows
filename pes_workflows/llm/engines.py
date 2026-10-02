"""Engine selection and defaults shared by all workflow entry points."""

from __future__ import annotations

import argparse
import logging

from pes_workflows.claude_cli import CodexSubprocessAdapter
from pes_workflows.config import CHOICES, Config


def add_engine_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--engine",
        choices=CHOICES["engine"],
        default="claude-code",
        help="Execution engine (default: claude-code)",
    )
    parser.add_argument(
        "--model",
        help=f"Model (Claude default: {Config.DEFAULT_MODEL}; Codex default: {CodexSubprocessAdapter.DEFAULT_MODEL}; "
        "override with --model claude-fable-5-1 or gpt-6-sol)",
    )
    parser.add_argument(
        "--effort",
        choices=Config.EFFORT_CHOICES,
        help=f"Reasoning effort (default: {Config.DEFAULT_EFFORT})",
    )


def resolve_engine_arguments(args: argparse.Namespace) -> None:
    """Fill only omitted values, preserving TOML and CLI model overrides."""
    if args.engine == "codex":
        default_model = CodexSubprocessAdapter.DEFAULT_MODEL
        default_effort = CodexSubprocessAdapter.DEFAULT_EFFORT
    else:
        default_model = Config.DEFAULT_MODEL
        default_effort = Config.DEFAULT_EFFORT
    args.model = args.model if args.model is not None else default_model
    args.effort = args.effort if args.effort is not None else default_effort
    if (
        args.engine == "claude-code"
        and args.fast
        and not args.model.startswith("claude-opus")
    ):
        logging.getLogger(__name__).warning(
            "Fast mode only supports Opus 5.5/5/4.8; the current model %s does not support this setting.",
            args.model,
        )
