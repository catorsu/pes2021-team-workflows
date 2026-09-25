"Load and validate mode-scoped model-call prompt templates."

from __future__ import annotations

import re
from pathlib import Path

from pes_workflows.config import Config
from pes_workflows.prompts.assets import read_prompt_text


class TemplateLoader:
    _VALID_PRESET_MODES = Config.SUPPORTED_PRESET_MODES
    _MODE_TAG_PATTERN: re.Pattern[str] = re.compile(
        r"<!-- \[(?:IF_MODE:(?P<mode>multi|single)|(?P<end>ENDIF_MODE))\] -->"
    )
    _MODE_DIRECTIVE_PATTERN: re.Pattern[str] = re.compile(
        r"\[(?:IF_MODE(?::[^\]]*)?|ENDIF_MODE)\]"
    )
    _PLAYER_RECORDS_PLACEHOLDER: str = "[PASTE PLAYER_RECORDS HERE]"
    _FROZEN_ARTIFACTS_PLACEHOLDER: str = "[PASTE FROZEN_ARTIFACTS HERE]"
    _PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(r"\[PASTE [^\]]*HERE\]")
    # Every user message leads with its call-scoped data blocks, so the STEP
    # line that titles the turn is matched per line rather than at the start
    _STEP_LINE_PATTERN: re.Pattern[str] = re.compile(
        r"^STEP (\d+)[A-C]? OF (\d+)[^\n]*", re.MULTILINE
    )

    def __init__(self, prompts_dir: Path, *, preset_mode: str = "multi") -> None:
        if preset_mode not in self._VALID_PRESET_MODES:
            allowed = ", ".join(self._VALID_PRESET_MODES)
            raise ValueError(
                f"preset_mode must be one of {allowed}; received {preset_mode!r}"
            )
        self.preset_mode: str = preset_mode
        self.prompts_dir: Path = prompts_dir
        self.system_prompt_raw: str = self._preprocess(
            self._read_file(prompts_dir / "system_prompt.md"),
            preset_mode,
        )
        self.system_prompt_raw = self._render_bench(
            self.system_prompt_raw, "BENCH_SYSTEM", "bench_system_prompt.md"
        )
        self.game_plan_rules: str = self._preprocess(
            self._read_file(prompts_dir / "game_plan_rules.md"),
            preset_mode,
        )
        self.player_glossary: str = self._read_file(
            prompts_dir.parent / "shared" / "player_glossary.md"
        )
        parsed = self._parse_user_templates(prompts_dir / "user_message_templates.md")
        # Titles come from the raw templates, so injected PLAYER_RECORDS can
        # never supply one
        self.user_templates: tuple[str, ...] = tuple(template for template, _ in parsed)
        self.user_template_titles: tuple[str, ...] = tuple(title for _, title in parsed)

    def _render_bench(self, content: str, placeholder: str, filename: str) -> str:
        template = self._read_file(self.prompts_dir / filename)
        values = {
            "{bench_turn}": "3" if self.preset_mode == "single" else "5",
            "{preset_names}": "Main"
            if self.preset_mode == "single"
            else "Main, Defensive, and Custom",
            "{duty_label}": "MAIN-DUTY"
            if self.preset_mode == "single"
            else "ALL-PRESET-DUTY",
        }
        for key, value in values.items():
            template = template.replace(key, value)
        marker = f"[PASTE {placeholder} HERE]"
        if content.count(marker) != 1:
            raise ValueError(f"Expected exactly one {marker}")
        return content.replace(marker, template)

    @staticmethod
    def _read_file(file_path: Path) -> str:
        if not file_path.exists():
            raise FileNotFoundError(f"Required prompt file not found: {file_path}")
        return read_prompt_text(file_path).strip()

    @classmethod
    def _preprocess(cls, content: str, preset_mode: str) -> str:
        "Retain only the selected mode's non-nested conditional blocks."
        if preset_mode not in cls._VALID_PRESET_MODES:
            allowed = ", ".join(cls._VALID_PRESET_MODES)
            raise ValueError(
                f"preset_mode must be one of {allowed}; received {preset_mode!r}"
            )

        unrecognized = cls._MODE_DIRECTIVE_PATTERN.search(
            cls._MODE_TAG_PATTERN.sub("", content)
        )
        if unrecognized:
            raise ValueError(
                "Malformed mode directive: expected exactly "
                "'<!-- [IF_MODE:multi] -->', '<!-- [IF_MODE:single] -->', "
                "or '<!-- [ENDIF_MODE] -->'."
            )

        rendered = []
        cursor = 0
        open_mode = None
        for match in cls._MODE_TAG_PATTERN.finditer(content):
            token_start = match.start()
            token_end = match.end()
            line_start = content.rfind("\n", 0, match.start()) + 1
            line_end = content.find("\n", match.end())
            if line_end < 0:
                line_end = len(content)
            if (
                not content[line_start : match.start()].strip()
                and not content[match.end() : line_end].strip()
            ):
                token_start = line_start
                token_end = min(line_end + 1, len(content))

            if open_mode is None or open_mode == preset_mode:
                rendered.append(content[cursor:token_start])

            block_mode = match.group("mode")
            if block_mode is not None:
                if open_mode is not None:
                    raise ValueError(
                        "Nested or overlapping IF_MODE blocks are not allowed."
                    )
                open_mode = block_mode
            else:
                if open_mode is None:
                    raise ValueError("ENDIF_MODE has no matching IF_MODE block.")
                open_mode = None
            cursor = token_end

        if open_mode is not None:
            raise ValueError(f"IF_MODE:{open_mode} has no matching ENDIF_MODE block.")

        rendered.append(content[cursor:])
        return re.sub(r"\n{3,}", "\n\n", "".join(rendered)).strip()

    def _parse_user_templates(self, template_path: Path) -> list[tuple[str, str]]:
        """Every raw template paired with the STEP line that titles its turn."""

        content = self._preprocess(self._read_file(template_path), self.preset_mode)
        content = self._render_bench(
            content, "BENCH_USER", "bench_user_message_template.md"
        )
        pattern = r"## Call\s+(\d+)\b.*?\s*```(?:text)?\s*\n(.*?)\n```"
        matches = re.findall(pattern, content, re.DOTALL)

        expected_total = 5 if self.preset_mode == "multi" else 3
        if len(matches) != expected_total:
            raise ValueError(
                "Failed to parse user_message_templates.md: "
                f"{self.preset_mode} mode expects exactly {expected_total} "
                f"API turns, but {len(matches)} were extracted."
            )

        parsed = []
        for expected, (call_number, prompt) in enumerate(matches, start=1):
            prompt = prompt.strip()
            step_match = self._STEP_LINE_PATTERN.search(prompt)
            if step_match is None:
                step_line = prompt.splitlines()[0] if prompt else ""
            else:
                step_line = step_match.group(0)
            if (
                int(call_number) != expected
                or step_match is None
                or int(step_match.group(1)) != expected
                or int(step_match.group(2)) != expected_total
            ):
                raise ValueError(
                    "user_message_templates.md turn numbering does not line up: "
                    f"template {expected} is labeled Call {call_number!s} "
                    f"and starts with {step_line!r}."
                )

            declared = sorted(self._PLACEHOLDER_PATTERN.findall(prompt))
            required = [self._PLAYER_RECORDS_PLACEHOLDER]
            if expected > 1:
                required.append(self._FROZEN_ARTIFACTS_PLACEHOLDER)
            if declared != sorted(required):
                raise ValueError(
                    "user_message_templates.md declares the wrong data "
                    f"placeholders: template {expected} must declare exactly "
                    f"{sorted(required)}, but it declares {declared}."
                )
            parsed.append((prompt, step_line))
        return parsed

    def build_system_prompt(self) -> str:
        """Fill the static reference documents the system prompt declares.

        `PLAYER_RECORDS` and `FROZEN_ARTIFACTS` are call-scoped and travel in
        the user message, so one system prompt serves every call in a run.
        """

        replacements = {
            "[PASTE GAME_PLAN_RULES HERE]": (
                f"```markdown\n{self.game_plan_rules}\n```"
            ),
            "[PASTE PLAYER_GLOSSARY HERE]": (
                f"```markdown\n{self.player_glossary}\n```"
            ),
        }

        def fill(match: re.Match[str]) -> str:
            placeholder = match.group(0)
            if placeholder not in replacements:
                raise ValueError(
                    f"system_prompt.md declares {placeholder}, which the "
                    "system prompt does not carry; the call-scoped "
                    "documents travel in the user message."
                )
            return replacements[placeholder]

        # One pass, so a bracketed phrase inside an embedded document is never
        # mistaken for a placeholder of the prompt's own
        return self._PLACEHOLDER_PATTERN.sub(fill, self.system_prompt_raw)

    def get_turn_user_prompt(
        self,
        turn_idx: int,
        *,
        player_records_content: str,
        frozen_artifacts_json: str | None = None,
    ) -> tuple[str, str]:
        """Render one turn's user message and return it with its STEP title.

        `frozen_artifacts_json` is the JSON the pipeline table assigns to this
        call; turn 1 designs from personnel alone and takes none.
        """

        total = len(self.user_templates)
        if not 1 <= turn_idx <= total:
            raise IndexError(
                f"API turn index must be in 1-{total}; received {turn_idx}"
            )
        if turn_idx == 1 and frozen_artifacts_json is not None:
            raise ValueError(
                "API turn 1 precedes every frozen artifact; "
                "frozen_artifacts_json must be omitted."
            )
        if turn_idx > 1 and frozen_artifacts_json is None:
            raise ValueError(
                f"API turn {turn_idx} designs against frozen artifacts; "
                "frozen_artifacts_json is required."
            )

        blocks = {
            self._PLAYER_RECORDS_PLACEHOLDER: (
                f"```markdown\n{player_records_content}\n```"
            ),
        }
        if frozen_artifacts_json is not None:
            blocks[self._FROZEN_ARTIFACTS_PLACEHOLDER] = (
                f"```json\n{frozen_artifacts_json}\n```"
            )
        # One pass over the template, so a bracketed phrase inside the records
        # cannot swallow the frozen-artifact block
        prompt = self._PLACEHOLDER_PATTERN.sub(
            lambda match: blocks[match.group(0)],
            self.user_templates[turn_idx - 1],
        )
        return prompt, self.user_template_titles[turn_idx - 1]
