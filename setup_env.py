#!/usr/bin/env python3
"""Create the project's isolated Python environment; never install external CLIs."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path


def initialize(project: Path, *, dev: bool = False) -> Path:
    project = project.resolve()
    environment = project / ".venv"
    if environment.is_symlink() or (
        environment.exists() and not (environment / "pyvenv.cfg").is_file()
    ):
        raise RuntimeError(f"Refusing to overwrite a non-venv directory: {environment}")
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    clean_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PIP_") and key not in {"PYTHONHOME", "PYTHONPATH"}
    }
    subprocess.run(
        [
            str(python),
            "-I",
            "-c",
            "import sys; assert sys.prefix != sys.base_prefix, 'Virtual environment required'",
        ],
        check=True,
        env=clean_env,
    )
    subprocess.run(
        [
            str(python),
            "-I",
            "-m",
            "pip",
            "--isolated",
            "install",
            "--editable",
            str(project) + ("[dev]" if dev else ""),
        ],
        check=True,
        cwd=project,
        env=clean_env,
    )
    configuration = project / "pes-workflows.toml"
    if not configuration.exists():
        # Exclusive creation preserves settings if another setup finishes first.
        try:
            with configuration.open("x", encoding="utf-8") as stream:
                stream.write(
                    (project / "pes-workflows.example.toml").read_text(encoding="utf-8")
                )
        except FileExistsError:
            pass
    return environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dev", action="store_true", help="Also install development dependencies"
    )
    args = parser.parse_args()
    if sys.version_info < (3, 11):  # noqa: UP036 - bootstrap runs before installation
        parser.error("Python 3.11 or newer is required")
    try:
        environment = initialize(Path(__file__).resolve().parent, dev=args.dev)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Setup failed: {error}", file=sys.stderr)
        return 1
    print(f"Ready: {environment}")
    print(
        "Edit pes-workflows.toml to set the CSV paths and choose teams. "
        "In WSL, Windows files use paths such as /mnt/c/PES2021/Players.csv. "
        "Workflow output directories are enabled in the generated template."
    )
    print(f"Run: {environment / 'bin/pes-match-plans'} --check-only")
    print("Install and authenticate claude / codex separately for model generation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
