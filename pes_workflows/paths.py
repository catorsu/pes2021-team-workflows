"""Translate external Windows paths when workflows run inside WSL."""

import os
import platform
import subprocess
from pathlib import Path, PureWindowsPath


def is_wsl() -> bool:
    return os.name == "posix" and (
        bool(os.environ.get("WSL_DISTRO_NAME"))
        or "microsoft" in platform.release().lower()
    )


def normalize_path(value: str | Path) -> Path:
    """Expand home paths and translate absolute Windows paths using WSL's mounts."""
    raw = str(value)
    windows = PureWindowsPath(raw)
    if os.name != "nt" and windows.drive:
        if not windows.is_absolute():
            raise ValueError(f"Windows path must include a drive root: {raw}")
        if not is_wsl():
            raise ValueError(
                f"Windows path requires WSL translation: {raw}; use an absolute Linux path"
            )
        try:
            result = subprocess.run(
                ["wslpath", "-u", raw],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise ValueError(
                f"Cannot translate Windows path {raw!r}; supply its mounted WSL path "
                "(for example /mnt/c/PES2021/Players.csv)"
            ) from error
        raw = result.stdout.rstrip("\r\n")
        if not raw or not Path(raw).is_absolute():
            raise ValueError(
                f"wslpath did not return an absolute Linux path for {value!r}"
            )
    return Path(raw).expanduser()
