"""Native Claude CLI execution and shared text-response adapter."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pes_workflows.config import Config, validate_agy_model
from pes_workflows.llm.base import (
    BaseLLMAdapter,
    LLMResponseError,
    Message,
    ModelResponse,
)
from pes_workflows.paths import (
    ensure_agy_on_path,
    ensure_claude_on_path,
    ensure_codex_on_path,
)

logger = logging.getLogger("Generate_National_Match_Plan")


def run_claude(
    cmd: Sequence[str], *, input: str, **kwargs: Any
) -> subprocess.CompletedProcess[str]:
    """Communicate without a timeout; reap the child on interruption or I/O failure."""
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **kwargs,
    )
    try:
        stdout, stderr = proc.communicate(input=input)
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


@contextmanager
def _isolated_directory(prefix: str) -> Iterator[str]:
    directory = tempfile.mkdtemp(prefix=prefix)
    try:
        yield directory
    finally:
        for attempt in range(10):
            try:
                shutil.rmtree(directory)
                break
            except PermissionError:
                if attempt == 9:
                    shutil.rmtree(directory, ignore_errors=True)
                else:
                    time.sleep(0.05)


class ClaudeCodeSubprocessAdapter(BaseLLMAdapter):
    """Invoke Claude with a supplied policy file or the rendered system message."""

    provider_name: str = "claude-code-cli"

    def __init__(
        self,
        *,
        model: str = Config.DEFAULT_MODEL,
        effort: str = Config.DEFAULT_EFFORT,
        delay: float = 5.0,
        fast_mode: bool = False,
        max_turns: int = 1,
        allowed_tools: tuple[str, ...] = (),
        system_prompt_file: Path | None = None,
    ) -> None:
        if effort not in Config.EFFORT_CHOICES:
            raise ValueError(f"Claude effort must be one of {Config.EFFORT_CHOICES}")
        if type(max_turns) is not int or max_turns < 1:
            raise ValueError("max_turns must be a positive integer")
        super().__init__(model=model, logger=logger)
        self.effort: str = effort
        self.delay: float = delay
        self.fast_mode: bool = fast_mode
        self.max_turns: int = max_turns
        self.allowed_tools: tuple[str, ...] = allowed_tools
        self.system_prompt_file: Path | None = system_prompt_file

    @contextmanager
    def _system_policy_file(self, messages: Sequence[Message]) -> Iterator[Path]:
        """Keep the exact audited system text alive until the CLI has exited."""
        if self.system_prompt_file is not None:
            yield self.system_prompt_file.resolve()
            return
        policies = [m["content"] for m in messages if m.get("role") == "system"]
        if len(policies) != 1 or not policies[0].strip():
            raise LLMResponseError(
                "Expected exactly one nonempty rendered system message"
            )
        with _isolated_directory(prefix="pes-system-policy-") as directory:
            policy_path = Path(directory) / "system_prompt.md"
            with policy_path.open("w", encoding="utf-8", newline="") as stream:
                stream.write(policies[0])
            yield policy_path

    def _generate_once(
        self,
        *,
        messages: Sequence[Message],
        turn: int,
        team_name: str,
        user_id: str | None,
    ) -> ModelResponse:
        user_prompt = self._build_user_prompt(messages)

        env = os.environ.copy()
        env.pop("ANTHROPIC_BASE_URL", None)
        env["CLAUDE_CODE_EFFORT_LEVEL"] = self.effort
        env["CI"] = "true"
        env.setdefault("PYTHONUTF8", "1")
        executable = ensure_claude_on_path(env)

        cmd = [
            executable,
            "--tools",
            ",".join(self.allowed_tools),
            "-p",
            "--model",
            self.model,
            "--no-session-persistence",
            "--disallowedTools",
            "mcp__*",
            "--max-turns",
            str(self.max_turns),
            "--output-format",
            "text",
        ]

        if self.allowed_tools:
            tools = ",".join(self.allowed_tools)
            cmd += ["--allowedTools", tools]

        # Headless (-p) mode ignores /fast and user settings; inject via --settings.
        if self.fast_mode:
            cmd += ["--settings", json.dumps({"fastMode": True})]

        logger.info(
            f"[{team_name}] Sending Turn {turn} request to Claude Code "
            f"(Model={self.model}, Effort={self.effort}, Fast={'on' if self.fast_mode else 'off'}, "
            f"Tools={','.join(self.allowed_tools) or 'none'}, MaxTurns={self.max_turns})..."
        )

        try:
            with self._system_policy_file(messages) as policy_path:
                cmd[1:1] = ["--system-prompt-file", str(policy_path)]
                proc = run_claude(cmd, input=user_prompt, env=env, encoding="utf-8")
            stdout, stderr = proc.stdout, proc.stderr
        except Exception as e:
            raise LLMResponseError(f"Unable to start Claude Code process: {e}") from e

        if proc.returncode != 0:
            err_details = f"STDOUT:\n{stdout.strip()}\n\nSTDERR:\n{stderr.strip()}"
            raise LLMResponseError(
                f"Claude Code exited abnormally (Code {proc.returncode}):\n{err_details}"
            )

        raw = stdout.strip()
        if not raw:
            raise LLMResponseError(
                "Claude Code returned no content; check CLI output or debug logs."
            )

        clean_json = self._extract_clean_json(raw)

        if self.delay > 0:
            logger.info(
                f"[{team_name}] Turn {turn} response received; waiting {self.delay} seconds for cooldown before continuing..."
            )
            time.sleep(self.delay)

        return clean_json, ""

    @staticmethod
    def _build_user_prompt(messages: Sequence[Message]) -> str:
        # The CLI loads the explicit policy file; stdin retains task and repair context.
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) == 1:
            user_prompt = non_system[0]["content"]
        elif len(non_system) >= 3:
            user_prompt = (
                f"{non_system[0]['content']}\n\n"
                f"--- PREVIOUS ATTEMPT (CONTAINED ERRORS) ---\n{non_system[1]['content']}\n\n"
                f"--- CORRECTION REQUIRED ---\n{non_system[2]['content']}"
            )
        else:
            user_prompt = "\n\n".join(
                f"[{m.get('role', 'user').upper()}]:\n{m.get('content', '')}"
                for m in non_system
            )

        return user_prompt

    @staticmethod
    def _extract_clean_json(text: str) -> str:
        fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text.strip())
        if fence_match:
            return fence_match.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1].strip()
        return text.strip()

    def is_retryable_error(self, error: BaseException) -> bool:
        s = str(error).lower()
        return any(
            k in s
            for k in (
                "timeout",
                "connection",
                "502",
                "503",
                "504",
                "rate limit",
                "overloaded",
            )
        )


class CodexSubprocessAdapter(ClaudeCodeSubprocessAdapter):
    """Headless transport with optional hosted web research and final-file output."""

    provider_name: str = "codex-cli"
    DEFAULT_MODEL: str = "gpt-6-astra"
    DEFAULT_EFFORT: str = Config.DEFAULT_EFFORT
    EFFORT_CHOICES: tuple[str, ...] = Config.EFFORT_CHOICES

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
        delay: float = 5.0,
        system_prompt_file: Path | None = None,
        fast_mode: bool = False,
        web_search: bool = False,
    ) -> None:
        if effort not in self.EFFORT_CHOICES:
            raise ValueError(f"Codex effort must be one of {self.EFFORT_CHOICES}")
        super().__init__(
            model=model,
            effort=effort,
            delay=delay,
            system_prompt_file=system_prompt_file,
            fast_mode=fast_mode,
        )
        self.web_search: bool = web_search

    def _generate_once(
        self,
        *,
        messages: Sequence[Message],
        turn: int,
        team_name: str,
        user_id: str | None,
    ) -> ModelResponse:
        user_prompt = self._build_user_prompt(messages)
        logger.info(
            "[%s] Sending Turn %s request to Codex (Model=%s, Effort=%s, Fast=%s, Web=%s)...",
            team_name,
            turn,
            self.model,
            self.effort,
            "on" if self.fast_mode else "off",
            "live" if self.web_search else "disabled",
        )
        try:
            # A fresh directory and final-message file prevent workspace context
            # and CLI progress output from entering the artifact contract.
            with (
                _isolated_directory(prefix="pes-codex-") as directory,
                self._system_policy_file(messages) as policy_path,
            ):
                env = os.environ.copy()
                env.setdefault("PYTHONUTF8", "1")
                executable = ensure_codex_on_path(env)
                response_path = Path(directory) / "response.txt"
                cmd = [
                    executable,
                    "exec",
                    "--ignore-user-config",
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "--sandbox",
                    "read-only",
                    "--color",
                    "never",
                    "--model",
                    self.model,
                    "--output-last-message",
                    str(response_path),
                    "-c",
                    'approval_policy="never"',
                    "-c",
                    "model_instructions_file="
                    + json.dumps(str(policy_path), ensure_ascii=False),
                    "-c",
                    "model_reasoning_effort=" + json.dumps(self.effort),
                    "-c",
                    "project_doc_max_bytes=0",
                    "-c",
                    'web_search="live"' if self.web_search else 'web_search="disabled"',
                    "-c",
                    "features.shell_tool=false",
                    "-c",
                    "features.apps=false",
                    "-c",
                    "features.multi_agent=false",
                    "-c",
                    "features.plugins=false",
                    "-c",
                    "features.hooks=false",
                ]
                if self.fast_mode:
                    cmd += [
                        "-c",
                        'service_tier="fast"',
                        "-c",
                        "features.fast_mode=true",
                    ]
                cmd.append("-")
                proc = run_claude(
                    cmd,
                    input=user_prompt,
                    cwd=directory,
                    env=env,
                    encoding="utf-8",
                )
                if proc.returncode != 0:
                    raise LLMResponseError(
                        f"Codex exited abnormally (Code {proc.returncode}):\n"
                        f"STDOUT:\n{proc.stdout.strip()}\n\nSTDERR:\n{proc.stderr.strip()}"
                    )
                raw = (
                    response_path.read_text(encoding="utf-8").strip()
                    if response_path.exists()
                    else ""
                )
                if not raw:
                    raise LLMResponseError(
                        "Codex returned no content; check CLI output or debug logs."
                    )
        except LLMResponseError:
            raise
        except Exception as e:
            raise LLMResponseError(
                f"Unable to execute Codex process or read its response: {e}"
            ) from e

        if self.delay > 0:
            time.sleep(self.delay)
        return self._extract_clean_json(raw), ""


class AgySubprocessAdapter(ClaudeCodeSubprocessAdapter):
    """Headless Antigravity CLI transport with single-model lock and isolated agent policy."""

    provider_name: str = "agy-cli"
    SUPPORTED_MODELS: tuple[str, ...] = Config.AGY_MODELS
    MODEL_SLUGS: dict[str, str] = dict(Config.AGY_MODEL_SLUGS)
    MODEL_DEFAULT_EFFORTS: dict[str, str] = dict(Config.AGY_MODEL_DEFAULT_EFFORTS)
    DEFAULT_MODEL: str = Config.AGY_DEFAULT_MODEL
    DEFAULT_EFFORT: str = Config.AGY_DEFAULT_EFFORT
    EFFORT_CHOICES: tuple[str, ...] = Config.EFFORT_CHOICES

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        effort: str | None = None,
        delay: float = 5.0,
        system_prompt_file: Path | None = None,
        fast_mode: bool = False,
        web_search: bool = False,
    ) -> None:
        canonical_model = validate_agy_model(model)
        resolved_effort = (
            self.MODEL_DEFAULT_EFFORTS[canonical_model] if effort is None else effort
        )
        if resolved_effort not in self.EFFORT_CHOICES:
            raise ValueError(f"Antigravity effort must be one of {self.EFFORT_CHOICES}")
        super().__init__(
            model=canonical_model,
            effort=resolved_effort,
            delay=delay,
            system_prompt_file=system_prompt_file,
            fast_mode=fast_mode,
        )
        self.cli_model: str = self.MODEL_SLUGS[canonical_model]
        self.web_search: bool = web_search

    def _generate_once(
        self,
        *,
        messages: Sequence[Message],
        turn: int,
        team_name: str,
        user_id: str | None,
    ) -> ModelResponse:
        user_prompt = self._build_user_prompt(messages)
        logger.info(
            "[%s] Sending Turn %s request to Antigravity CLI (Model=%s, Effort=%s, Fast=%s, Web=%s)...",
            team_name,
            turn,
            self.model,
            self.effort,
            "on" if self.fast_mode else "off",
            "live" if self.web_search else "disabled",
        )
        try:
            with (
                _isolated_directory(prefix="pes-agy-") as directory,
                self._system_policy_file(messages) as policy_path,
            ):
                policy_bytes = policy_path.read_bytes()
                policy_text = policy_bytes.decode("utf-8")
                (Path(directory) / "GEMINI.md").write_bytes(policy_bytes)
                agent_dir = Path(directory) / ".agents" / "agents"
                agent_dir.mkdir(parents=True, exist_ok=True)
                tools_yaml = (
                    '["search_web", "read_url_content"]' if self.web_search else "[]"
                )
                body = (
                    policy_text
                    if policy_text.lstrip().startswith("# ")
                    else f"# System Prompt\n\n{policy_text}"
                )
                (agent_dir / "pes.md").write_text(
                    "---\n"
                    "name: pes\n"
                    "description: PES 2021 headless workflow agent\n"
                    "excludeDefaultComponents: true\n"
                    "inheritCustomizations: false\n"
                    "subagent: false\n"
                    f"tools: {tools_yaml}\n"
                    "---\n\n"
                    f"{body}",
                    encoding="utf-8",
                    newline="",
                )
                env = os.environ.copy()
                env["CI"] = "true"
                env.setdefault("PYTHONUTF8", "1")
                executable = ensure_agy_on_path(env)
                settings: dict[str, Any] = {
                    "allowNonWorkspaceAccess": False,
                    "artifactReviewPolicy": "always-proceed",
                    "model": (
                        f"{self.cli_model}-{self.effort}"
                        if self.effort in ("low", "medium", "high")
                        else self.cli_model
                    ),
                }
                cmd = [
                    executable,
                    "--agent",
                    "pes",
                    "--model",
                    self.cli_model,
                    "--effort",
                    self.effort,
                    "--disable-slash-commands",
                    "--sandbox",
                    "--input-format",
                    "text",
                    "--output-format",
                    "text",
                    "--settings",
                    json.dumps(settings, ensure_ascii=False),
                ]
                if self.web_search:
                    cmd.append("--dangerously-skip-permissions")
                proc = run_claude(
                    cmd,
                    input=user_prompt,
                    cwd=directory,
                    env=env,
                    encoding="utf-8",
                )
                if proc.returncode != 0:
                    raise LLMResponseError(
                        f"Antigravity CLI exited abnormally (Code {proc.returncode}):\n"
                        f"STDOUT:\n{proc.stdout.strip()}\n\nSTDERR:\n{proc.stderr.strip()}"
                    )
                raw = proc.stdout.strip()
                if not raw:
                    raise LLMResponseError(
                        "Antigravity CLI returned no content; check CLI output or debug logs."
                    )
        except LLMResponseError:
            raise
        except Exception as e:
            raise LLMResponseError(
                f"Unable to execute Antigravity CLI process or read its response: {e}"
            ) from e

        if self.delay > 0:
            time.sleep(self.delay)
        return self._extract_clean_json(raw), ""
