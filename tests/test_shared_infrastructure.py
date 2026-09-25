"""Offline regression coverage for extracted infrastructure and prompt assets."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest import mock

from pes_workflows import claude_cli, file_lock
from pes_workflows.attribute_audit import AuditedAdapter
from pes_workflows.llm.base import LLMResponseError
from pes_workflows.prompts.assets import read_prompt_text

ROOT = Path(__file__).resolve().parents[1] / "pes_workflows"


class PromptAssetsTests(unittest.TestCase):
    def test_required_prompt_assets_are_readable_and_nonempty(self) -> None:
        required_assets = (
            "match_plan/system_prompt.md",
            "match_plan/game_plan_rules.md",
            "match_plan/user_message_templates.md",
            "match_plan/player_records_example.md",
            "match_plan/bench_system_prompt.md",
            "match_plan/bench_user_message_template.md",
            "player_attributes/system_prompt.md",
            "player_attributes/user_message_template.md",
            "shared/player_glossary.md",
        )
        for name in required_assets:
            with self.subTest(asset=name):
                self.assertTrue(read_prompt_text(ROOT / "prompts" / name).strip())


class NativeClaudeTests(unittest.TestCase):
    def test_tool_overrides_and_tool_free_default_reach_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cases = [
                (claude_cli.ClaudeCodeSubprocessAdapter(delay=0), "", "1"),
                (
                    AuditedAdapter(
                        Path(directory), delay=0, allowed_tools=(), max_turns=1
                    ),
                    "",
                    "1",
                ),
                (
                    AuditedAdapter(
                        Path(directory),
                        delay=0,
                        allowed_tools=("WebFetch",),
                        max_turns=12,
                    ),
                    "WebFetch",
                    "12",
                ),
            ]
            for adapter, tools, turns in cases:
                process = mock.Mock(returncode=0)
                process.communicate.return_value = ("{}", "")
                with (
                    self.subTest(adapter=type(adapter).__name__, tools=tools),
                    mock.patch.object(
                        claude_cli.subprocess, "Popen", return_value=process
                    ) as popen,
                ):
                    adapter.generate(
                        [
                            {"role": "system", "content": "policy"},
                            {"role": "user", "content": "task"},
                        ],
                        1,
                        "A",
                    )
                cmd = popen.call_args.args[0]
                self.assertEqual(cmd[cmd.index("--model") + 1], "claude-opus-5-5")
                self.assertEqual(
                    popen.call_args.kwargs["env"]["CLAUDE_CODE_EFFORT_LEVEL"], "high"
                )
                self.assertEqual(cmd[cmd.index("--tools") + 1], tools)
                self.assertEqual(cmd[cmd.index("--max-turns") + 1], turns)
                self.assertEqual(cmd[cmd.index("--disallowedTools") + 1], "mcp__*")
                if tools:
                    self.assertEqual(cmd[cmd.index("--allowedTools") + 1], tools)
                else:
                    self.assertNotIn("--allowedTools", cmd)
                self.assertNotIn("--settings", cmd)

    def test_tool_enabled_retry_audits_each_attempt_without_changing_request(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit = Path(directory)
            adapter = AuditedAdapter(audit, delay=0, max_turns=29)
            adapter._sleep = mock.Mock()
            failed, succeeded = mock.Mock(returncode=1), mock.Mock(returncode=0)
            failed.communicate.return_value = ("partial", "503 overloaded")
            succeeded.communicate.return_value = ('  {"ok":true}  ', "")
            messages = [
                {"role": "system", "content": "policy"},
                {"role": "user", "content": "roster"},
            ]
            with (
                mock.patch.object(
                    claude_cli.subprocess, "Popen", side_effect=[failed, succeeded]
                ) as popen,
                self.assertLogs(claude_cli.logger, level="INFO") as logs,
            ):
                self.assertEqual(
                    adapter.generate(messages, 2, "A"), ('{"ok":true}', "")
                )
            self.assertEqual(popen.call_count, 2)
            self.assertEqual(
                popen.call_args_list[0].kwargs, popen.call_args_list[1].kwargs
            )
            cmd = popen.call_args.args[0]
            self.assertEqual(cmd[cmd.index("--tools") + 1], "WebSearch,WebFetch")
            self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "WebSearch,WebFetch")
            self.assertEqual(cmd[cmd.index("--max-turns") + 1], "29")
            self.assertEqual(
                sum(
                    "Tools=WebSearch,WebFetch, MaxTurns=29" in line
                    for line in logs.output
                ),
                2,
            )
            adapter._sleep.assert_called_once_with(adapter.initial_backoff)
            requests = sorted(audit.glob("*.request.json"))
            self.assertEqual(len(requests), 2)
            for request in requests:
                self.assertEqual(
                    json.loads(request.read_text()),
                    {
                        "messages": messages,
                        "turn": 2,
                        "team_name": "A",
                        "user_id": None,
                    },
                )
            error_path = requests[0].with_name(
                requests[0].name.replace(".request.json", ".error.json")
            )
            self.assertIn("503 overloaded", json.loads(error_path.read_text())["error"])
            response_path = requests[1].with_name(
                requests[1].name.replace(".request.json", ".response.txt")
            )
            self.assertEqual(response_path.read_text(), '{"ok":true}')
            self.assertEqual(len(list(audit.glob("*.error.json"))), 1)
            self.assertEqual(len(list(audit.glob("*.response.txt"))), 1)

    def test_all_entry_points_support_direct_execution_outside_checkout(self) -> None:
        scripts = (
            "generate_match_plan.py",
            "batch_generate_match_plans.py",
            "batch_design_player_attributes.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            for name in scripts:
                with self.subTest(script=name):
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pes_workflows." + name.removesuffix(".py"),
                            "--help",
                        ],
                        cwd=directory,
                        env={**os.environ, "PYTHONPATH": str(ROOT.parent)},
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("--model", result.stdout)

    def test_attribute_native_args_environment_and_verbatim_repairs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="claude policy ") as directory:
            audit = Path(directory)
            adapter = AuditedAdapter(audit, delay=0, fast_mode=True)
            process = mock.Mock(returncode=0)
            process.communicate.return_value = ("  ```json\n{}\n```  ", "")
            messages = [
                {"role": "system", "content": "not sent on stdin"},
                {"role": "user", "content": "original\n\n"},
                {"role": "assistant", "content": "bad\n"},
                {"role": "user", "content": "repair\n"},
            ]
            with (
                mock.patch.object(
                    claude_cli.subprocess, "Popen", return_value=process
                ) as popen,
                mock.patch.dict(
                    os.environ, {"ANTHROPIC_BASE_URL": "https://unused.invalid"}
                ),
            ):
                result = adapter._generate_once(
                    messages=messages, turn=2, team_name="A", user_id=None
                )
            cmd = popen.call_args.args[0]
            self.assertEqual(cmd[0], "claude")
            self.assertFalse(Path(cmd[cmd.index("--system-prompt-file") + 1]).exists())
            for flag, value in [
                ("--tools", "WebSearch,WebFetch"),
                ("--allowedTools", "WebSearch,WebFetch"),
                ("--max-turns", "80"),
                ("--disallowedTools", "mcp__*"),
            ]:
                self.assertEqual(cmd[cmd.index(flag) + 1], value)
            self.assertEqual(
                json.loads(cmd[cmd.index("--settings") + 1]), {"fastMode": True}
            )
            self.assertNotIn("ANTHROPIC_BASE_URL", popen.call_args.kwargs["env"])
            self.assertEqual(
                popen.call_args.kwargs["env"]["CLAUDE_CODE_EFFORT_LEVEL"], "high"
            )
            self.assertEqual(
                process.communicate.call_args.kwargs["input"],
                "original\n\n\n\n--- PREVIOUS ATTEMPT (CONTAINED ERRORS) ---\nbad\n\n\n"
                "--- CORRECTION REQUIRED ---\nrepair\n",
            )
            self.assertEqual(result, ("```json\n{}\n```", ""))
            self.assertEqual(len(list(audit.glob("*.request.json"))), 1)
            self.assertEqual(len(list(audit.glob("*.response.txt"))), 1)
            self.assertNotIn("timeout", process.communicate.call_args.kwargs)

    def test_process_interruption_reaps_child_and_preserves_error(self) -> None:
        for error in (KeyboardInterrupt(), OSError("pipe failed")):
            with self.subTest(error=type(error)):
                process = mock.Mock()
                process.communicate.side_effect = error
                with (
                    mock.patch.object(
                        claude_cli.subprocess, "Popen", return_value=process
                    ),
                    self.assertRaises(type(error)) as caught,
                ):
                    claude_cli.run_claude(["claude", "-p"], input="task")
                self.assertIs(caught.exception, error)
                process.kill.assert_called_once_with()
                process.wait.assert_called_once_with()

    def test_adapter_preserves_error_details_and_audits_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit = Path(directory)
            adapter = AuditedAdapter(audit, delay=0)
            for code, stdout, stderr, expected in [
                (7, "usage limit", "details", "Code 7"),
                (0, "  ", "", "returned no content"),
            ]:
                process = mock.Mock(returncode=code)
                process.communicate.return_value = (stdout, stderr)
                with (
                    mock.patch.object(
                        claude_cli.subprocess, "Popen", return_value=process
                    ),
                    self.assertRaisesRegex(LLMResponseError, expected),
                ):
                    adapter._generate_once(
                        messages=[
                            {"role": "system", "content": "rendered policy"},
                            {"role": "user", "content": "task"},
                        ],
                        turn=1,
                        team_name="A",
                        user_id=None,
                    )
            self.assertEqual(len(list(audit.glob("*.error.json"))), 2)
            self.assertFalse(list(audit.glob("*.response.txt")))


class NativeCodexTests(unittest.TestCase):
    def test_rendered_policy_validation_and_cleanup_for_both_transports(self) -> None:
        for cls in (
            claude_cli.ClaudeCodeSubprocessAdapter,
            claude_cli.CodexSubprocessAdapter,
        ):
            adapter = cls(delay=0)
            for policies in ([], [""], ["one", "two"]):
                messages = [{"role": "system", "content": text} for text in policies]
                messages.append({"role": "user", "content": "task"})
                with (
                    self.subTest(adapter=cls.__name__, policies=policies),
                    mock.patch.object(claude_cli, "run_claude") as run,
                    self.assertRaisesRegex(LLMResponseError, "exactly one nonempty"),
                ):
                    adapter._generate_once(
                        messages=messages, turn=1, team_name="A", user_id=None
                    )
                run.assert_not_called()
            for error in (OSError("spawn failed"), KeyboardInterrupt()):
                paths = []

                def run(
                    cmd: list[str], **kwargs: Any
                ) -> subprocess.CompletedProcess[str]:
                    if cmd[0] == "claude":
                        path = Path(cmd[cmd.index("--system-prompt-file") + 1])
                    else:
                        settings = dict(
                            cmd[i + 1].split("=", 1)
                            for i, arg in enumerate(cmd)
                            if arg == "-c"
                        )
                        path = Path(json.loads(settings["model_instructions_file"]))
                    self.assertEqual(
                        path.read_bytes(), "Tactics\npolicy — preserve UTF-8\n".encode()
                    )
                    paths.append(path)
                    raise error

                expected = (
                    KeyboardInterrupt
                    if isinstance(error, KeyboardInterrupt)
                    else LLMResponseError
                )
                with (
                    self.subTest(adapter=cls.__name__, error=error),
                    mock.patch.object(claude_cli, "run_claude", side_effect=run),
                    self.assertRaises(expected),
                ):
                    adapter._generate_once(
                        messages=[
                            {
                                "role": "system",
                                "content": "Tactics\npolicy — preserve UTF-8\n",
                            },
                            {"role": "user", "content": "task"},
                        ],
                        turn=1,
                        team_name="A",
                        user_id=None,
                    )
                self.assertEqual(len(paths), 1)
                self.assertFalse(paths[0].parent.exists())

    def test_default_model_and_high_effort_reach_subprocess(self) -> None:
        adapter = claude_cli.CodexSubprocessAdapter(delay=0)

        def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            self.assertEqual(cmd[cmd.index("--model") + 1], "gpt-6-astra")
            self.assertIn('model_reasoning_effort="high"', cmd)
            self.assertFalse(
                any(
                    arg.startswith(("service_tier=", "features.fast_mode="))
                    for arg in cmd
                )
            )
            Path(cmd[cmd.index("--output-last-message") + 1]).write_text('{"ok":true}')
            return mock.Mock(returncode=0)

        with mock.patch.object(claude_cli, "run_claude", side_effect=run):
            adapter._generate_once(
                messages=[
                    {"role": "system", "content": "rendered policy"},
                    {"role": "user", "content": "task"},
                ],
                turn=1,
                team_name="China*",
                user_id=None,
            )
        for effort in ("invalid", "", "ultra"):
            with self.subTest(effort=effort), self.assertRaises(ValueError):
                claude_cli.CodexSubprocessAdapter(effort=effort)

    def test_final_message_policy_repairs_and_cooldown(self) -> None:
        adapter = claude_cli.CodexSubprocessAdapter(
            model="gpt-6-sol", effort="high", delay=2
        )
        messages = [
            {"role": "system", "content": "policy comes from file"},
            {"role": "user", "content": "task\n"},
            {"role": "assistant", "content": "bad attempt\n"},
            {"role": "user", "content": "repair\n"},
        ]
        directories = []

        def popen(cmd: list[str], **kwargs: Any) -> mock.Mock:
            directories.append(Path(kwargs["cwd"]))
            self.assertEqual(cmd[:2], ["codex", "exec"])
            self.assertEqual(cmd[-1], "-")
            self.assertEqual(cmd[cmd.index("--model") + 1], "gpt-6-sol")
            self.assertEqual(cmd[cmd.index("--sandbox") + 1], "read-only")
            for flag in (
                "--ignore-user-config",
                "--ephemeral",
                "--skip-git-repo-check",
            ):
                self.assertIn(flag, cmd)
            settings = dict(
                cmd[i + 1].split("=", 1) for i, arg in enumerate(cmd) if arg == "-c"
            )
            policy_path = Path(json.loads(settings["model_instructions_file"]))
            self.assertEqual(policy_path.read_text(), "policy comes from file")
            self.assertEqual(json.loads(settings["model_reasoning_effort"]), "high")
            self.assertEqual(settings["project_doc_max_bytes"], "0")
            self.assertEqual(settings["features.shell_tool"], "false")
            self.assertEqual(json.loads(settings["web_search"]), "disabled")
            self.assertNotIn("shell", kwargs)
            self.assertNotIn("timeout", kwargs)
            Path(cmd[cmd.index("--output-last-message") + 1]).write_text(
                '```json\n{"ok":true}\n```'
            )
            process = mock.Mock(returncode=0)

            def communicate(*, input: str) -> tuple[str, str]:
                self.assertEqual(
                    input,
                    "task\n\n\n--- PREVIOUS ATTEMPT (CONTAINED ERRORS) ---\n"
                    "bad attempt\n\n\n--- CORRECTION REQUIRED ---\nrepair\n",
                )
                return 'progress {"wrong":true}', "diagnostics"

            process.communicate.side_effect = communicate
            return process

        with (
            mock.patch.object(
                claude_cli.subprocess, "Popen", side_effect=popen
            ) as spawn,
            mock.patch.object(claude_cli.time, "sleep") as sleep,
        ):
            for turn in (1, 2, 3):
                result = adapter._generate_once(
                    messages=messages, turn=turn, team_name="A", user_id=None
                )
                self.assertEqual(result, ('{"ok":true}', ""))
            self.assertEqual(spawn.call_count, 3)
            self.assertEqual(sleep.call_args_list, [mock.call(2)] * 3)
        self.assertEqual(len(set(directories)), 3)
        self.assertTrue(all(not path.exists() for path in directories))

    def test_fast_mode_settings_preserve_effort_on_every_turn(self) -> None:
        for effort in ("low", "medium", "high", "xhigh", "max"):
            adapter = claude_cli.CodexSubprocessAdapter(
                effort=effort, delay=0, fast_mode=True
            )

            def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                self.assertEqual(cmd[-1], "-")
                self.assertEqual(cmd[cmd.index("--model") + 1], "gpt-6-astra")
                settings = dict(
                    cmd[i + 1].split("=", 1) for i, arg in enumerate(cmd) if arg == "-c"
                )
                self.assertEqual(json.loads(settings["service_tier"]), "fast")
                self.assertEqual(settings["features.fast_mode"], "true")
                self.assertEqual(json.loads(settings["model_reasoning_effort"]), effort)
                self.assertEqual(settings["features.multi_agent"], "false")
                self.assertNotIn("--settings", cmd)
                self.assertIn("--ignore-user-config", cmd)
                Path(cmd[cmd.index("--output-last-message") + 1]).write_text(
                    '{"ok":true}'
                )
                return mock.Mock(returncode=0)

            with (
                self.subTest(effort=effort),
                mock.patch.object(claude_cli, "run_claude", side_effect=run) as spawn,
            ):
                for turn in (1, 2, 3):
                    result = adapter._generate_once(
                        messages=[
                            {"role": "system", "content": "rendered policy"},
                            {"role": "user", "content": "task"},
                        ],
                        turn=turn,
                        team_name="China*",
                        user_id=None,
                    )
                    self.assertEqual(result, ('{"ok":true}', ""))
                self.assertEqual(spawn.call_count, 3)

    def test_both_transports_report_errors_and_reap_interruptions(self) -> None:
        for cls in (
            claude_cli.ClaudeCodeSubprocessAdapter,
            claude_cli.CodexSubprocessAdapter,
        ):
            for failure in ("missing", "exit", "empty", "interrupt", "io"):
                with self.subTest(adapter=cls.__name__, failure=failure):
                    adapter = cls(delay=0)
                    process = mock.Mock(returncode=7 if failure == "exit" else 0)
                    process.communicate.return_value = (
                        "partial response" if failure == "exit" else "",
                        "error details",
                    )
                    if failure in ("interrupt", "io"):
                        process.communicate.side_effect = (
                            KeyboardInterrupt()
                            if failure == "interrupt"
                            else OSError("broken pipe")
                        )
                    expected = (
                        KeyboardInterrupt
                        if failure == "interrupt"
                        else LLMResponseError
                    )
                    with (
                        mock.patch.object(
                            claude_cli.subprocess,
                            "Popen",
                            return_value=process,
                            side_effect=FileNotFoundError("missing CLI")
                            if failure == "missing"
                            else None,
                        ),
                        self.assertRaises(expected) as caught,
                    ):
                        adapter._generate_once(
                            messages=[
                                {"role": "system", "content": "rendered policy"},
                                {"role": "user", "content": "task"},
                            ],
                            turn=1,
                            team_name="A",
                            user_id=None,
                        )
                    if failure == "exit":
                        self.assertIn("Code 7", str(caught.exception))
                        self.assertIn("partial response", str(caught.exception))
                        self.assertIn("error details", str(caught.exception))
                    if failure in ("interrupt", "io"):
                        process.kill.assert_called_once_with()
                        process.wait.assert_called_once_with()

    def test_both_transports_retry_transient_errors_only(self) -> None:
        for cls in (
            claude_cli.ClaudeCodeSubprocessAdapter,
            claude_cli.CodexSubprocessAdapter,
        ):
            with self.subTest(adapter=cls.__name__):
                adapter = cls(delay=0)
                adapter._sleep = mock.Mock()
                transient = LLMResponseError("503 overloaded")
                with mock.patch.object(
                    adapter, "_generate_once", side_effect=[transient, ("{}", "")]
                ) as call:
                    self.assertEqual(adapter.generate([], 1, "A"), ("{}", ""))
                    self.assertEqual(call.call_count, 2)
                    adapter._sleep.assert_called_once()
                with mock.patch.object(
                    adapter,
                    "_generate_once",
                    side_effect=LLMResponseError("bad credentials"),
                ) as call:
                    with self.assertRaisesRegex(LLMResponseError, "bad credentials"):
                        adapter.generate([], 1, "A")
                    call.assert_called_once()


class StorageTests(unittest.TestCase):
    def test_lock_contention_then_release_on_exception(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.lock"
            with self.assertRaisesRegex(RuntimeError, "stop"):
                with ExitStack() as owner:
                    file_lock.acquire_lock(owner, path)
                    with ExitStack() as contender, self.assertRaises(BlockingIOError):
                        file_lock.acquire_lock(contender, path)
                    raise RuntimeError("stop")
            with ExitStack() as next_owner:
                file_lock.acquire_lock(next_owner, path)
