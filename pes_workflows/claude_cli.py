"""Native Claude CLI execution and shared text-response adapter."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pes_workflows.config import Config
from pes_workflows.llm.base import (
    BaseLLMAdapter,
    LLMResponseError,
    Message,
    ModelResponse,
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
        with tempfile.TemporaryDirectory(prefix="pes-system-policy-") as directory:
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

        cmd = [
            "claude",
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

        env = os.environ.copy()
        env.pop("ANTHROPIC_BASE_URL", None)
        env["CLAUDE_CODE_EFFORT_LEVEL"] = self.effort
        env["CI"] = "true"
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
    """Match-plan transport using the same policy, text and retry contracts."""

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
            "[%s] Sending Turn %s request to Codex (Model=%s, Effort=%s, Fast=%s)...",
            team_name,
            turn,
            self.model,
            self.effort,
            "on" if self.fast_mode else "off",
        )
        try:
            # A fresh directory and final-message file prevent workspace context
            # and CLI progress output from entering the artifact contract.
            with (
                tempfile.TemporaryDirectory(prefix="pes-match-plan-") as directory,
                self._system_policy_file(messages) as policy_path,
            ):
                response_path = Path(directory) / "response.txt"
                cmd = [
                    "codex",
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
                    'web_search="disabled"',
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
                    env=os.environ.copy(),
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
