"""Normalize workflow paths and locate headless CLI executables on Windows."""

import os
import platform
import shutil
import subprocess
from pathlib import Path, PurePosixPath, PureWindowsPath


def is_wsl() -> bool:
    return os.name == "posix" and (
        bool(os.environ.get("WSL_DISTRO_NAME"))
        or "microsoft" in platform.release().lower()
    )


def is_absolute_path(path: Path) -> bool:
    """Return whether path is absolute natively or uses a POSIX root on Windows."""
    return path.is_absolute() or (
        os.name == "nt" and not path.drive and bool(path.root)
    )


def _translate_wsl_mount_for_windows(raw: str) -> str:
    posix = PurePosixPath(raw)
    parts = posix.parts
    if (
        len(parts) >= 3
        and parts[0] == "/"
        and parts[1] == "mnt"
        and len(parts[2]) == 1
        and parts[2].isalpha()
    ):
        drive = parts[2].upper()
        tail = "/".join(parts[3:])
        return f"{drive}:/{tail}" if tail else f"{drive}:/"
    return raw


def normalize_path(value: str | Path) -> Path:
    """Expand home paths and translate cross-environment Windows/WSL paths."""
    raw = str(value)
    windows = PureWindowsPath(raw)
    if windows.drive and not windows.is_absolute():
        raise ValueError(f"Windows path must include a drive root: {raw}")
    if os.name == "nt" and not windows.drive and raw.startswith("/mnt/"):
        raw = _translate_wsl_mount_for_windows(raw)
    elif os.name != "nt" and windows.drive:
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


def _prepend_to_path(bin_dir: str, env: dict[str, str] | None = None) -> None:
    for target in (os.environ, env):
        if target is not None:
            current = target.get("PATH", "")
            entries = [e for e in current.split(os.pathsep) if e and e != bin_dir]
            target["PATH"] = os.pathsep.join([bin_dir, *entries])


def _resolve_env_override(
    var_name: str, env: dict[str, str] | None = None
) -> Path | None:
    raw = (env.get(var_name) if env is not None else None) or os.environ.get(var_name)
    if not raw or not raw.strip():
        return None
    try:
        candidate = normalize_path(raw.strip())
    except ValueError:
        return None
    try:
        if candidate.is_file():
            return candidate
    except OSError:
        return None
    return None


def _ensure_executable_on_path(
    default_cmd: str,
    resolved: Path | None,
    env: dict[str, str] | None = None,
) -> str:
    if resolved is not None:
        _prepend_to_path(str(resolved.parent), env)
        if (
            resolved.suffix.lower() in {".cmd", ".bat"}
            or resolved.stem.lower() != default_cmd
        ):
            return str(resolved)
    return default_cmd


def resolve_claude_executable(env: dict[str, str] | None = None) -> Path | None:
    """Locate the Claude Code CLI via PES_CLAUDE_BIN, PATH, or Windows install locations."""
    override = _resolve_env_override("PES_CLAUDE_BIN", env)
    if override is not None:
        return override
    found = shutil.which("claude", path=env.get("PATH") if env is not None else None)
    if found:
        return Path(found)
    if os.name == "nt":
        candidates: list[Path] = []
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            home = Path(user_profile)
            candidates.extend(
                (
                    home / ".local" / "bin" / "claude.exe",
                    home / ".claude" / "local" / "claude.exe",
                )
            )
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base = Path(local_app_data)
            candidates.extend(
                (
                    base / "Programs" / "claude-code" / "claude.exe",
                    base / "Programs" / "ClaudeCode" / "claude.exe",
                    base / "AnthropicClaudeCode" / "claude.exe",
                )
            )
            winget = base / "Microsoft" / "WinGet" / "Packages"
            if winget.is_dir():
                candidates.extend(
                    sorted(winget.glob("Anthropic.ClaudeCode*/**/claude.exe"))
                )
        app_data = os.environ.get("APPDATA")
        if app_data:
            npm_dir = Path(app_data) / "npm"
            candidates.extend((npm_dir / "claude.exe", npm_dir / "claude.cmd"))
        for candidate in candidates:
            if candidate.is_file():
                return candidate
    return None


def ensure_claude_on_path(env: dict[str, str] | None = None) -> str:
    """Ensure the discovered Claude Code CLI directory is on PATH and return the command."""
    return _ensure_executable_on_path("claude", resolve_claude_executable(env), env)


def resolve_codex_executable(env: dict[str, str] | None = None) -> Path | None:
    """Locate the OpenAI Codex CLI via PES_CODEX_BIN, PATH, or Windows install locations."""
    override = _resolve_env_override("PES_CODEX_BIN", env)
    if override is not None:
        return override
    found = shutil.which("codex", path=env.get("PATH") if env is not None else None)
    if found:
        return Path(found)
    if os.name == "nt":
        candidates: list[Path] = []
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base = Path(local_app_data)
            codex_bins = base / "OpenAI" / "Codex" / "bin"
            if codex_bins.is_dir():
                candidates.extend(sorted(codex_bins.glob("*/codex.exe")))
            candidates.append(base / "Programs" / "codex" / "codex.exe")
            packages = base / "Packages"
            if packages.is_dir():
                candidates.extend(
                    sorted(packages.glob("OpenAI.Codex_*/LocalCache/**/codex.exe"))
                )
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            home = Path(user_profile)
            candidates.extend(
                (
                    home / ".local" / "bin" / "codex.exe",
                    home / ".codex" / "bin" / "codex.exe",
                )
            )
        app_data = os.environ.get("APPDATA")
        if app_data:
            npm_dir = Path(app_data) / "npm"
            candidates.extend((npm_dir / "codex.exe", npm_dir / "codex.cmd"))
        program_files = os.environ.get("ProgramFiles") or r"C:\Program Files"
        windows_apps = Path(program_files) / "WindowsApps"
        try:
            if windows_apps.is_dir():
                candidates.extend(
                    sorted(
                        windows_apps.glob("OpenAI.Codex_*/app/resources/codex.exe"),
                        reverse=True,
                    )
                )
        except OSError:
            pass
        for candidate in candidates:
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
    return None


def ensure_codex_on_path(env: dict[str, str] | None = None) -> str:
    """Ensure the discovered Codex CLI directory is on PATH and return the command."""
    return _ensure_executable_on_path("codex", resolve_codex_executable(env), env)


def resolve_agy_executable(env: dict[str, str] | None = None) -> Path | None:
    """Locate the Antigravity CLI via PES_AGY_BIN, PATH, or Windows LocalAppData."""
    override = _resolve_env_override("PES_AGY_BIN", env)
    if override is not None:
        return override
    found = shutil.which("agy", path=env.get("PATH") if env is not None else None)
    if found:
        return Path(found)
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base = Path(local_app_data)
            candidates = [base / "agy" / "bin" / "agy.exe"]
            packages = base / "Packages"
            if packages.is_dir():
                candidates.extend(
                    sorted(packages.glob("*/LocalCache/Local/agy/bin/agy.exe"))
                )
            for candidate in candidates:
                if candidate.is_file():
                    return candidate
    return None


def ensure_agy_on_path(env: dict[str, str] | None = None) -> str:
    """Ensure the discovered Antigravity CLI directory is on PATH and return the command."""
    return _ensure_executable_on_path("agy", resolve_agy_executable(env), env)
