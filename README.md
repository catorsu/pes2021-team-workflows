# PES 2021 Team Workflows

Standalone Python 3.11+ workflows for WSL and Linux. Copy this directory anywhere;
it contains its own compiler, validators, roster readers, CSV writers, CLI
adapters, prompts, and offline tests. Runtime dependencies are pandas and an
authenticated `claude` executable, or `codex` for match plans. No GUI or API SDK is
required.

## Install and run

After cloning, run from the repository directory:

```bash
python3 setup_env.py
```

This creates `.venv` with system packages excluded, installs this project in
editable mode and its Python dependencies, and copies
`pes-workflows.example.toml` to `pes-workflows.toml` if it does not exist.
Re-running setup preserves your settings. Python 3.11+ with `venv`/`ensurepip`
support and access to a Python package index are prerequisites. Setup never
installs or authenticates Claude Code (`claude`) or Codex (`codex`); install and
authenticate your chosen CLI separately. Offline preflight needs neither CLI.
Use `python3 setup_env.py --dev` to include the development tools.

Edit `pes-workflows.toml` to set the absolute CSV paths and your team selection, then run
`.venv/bin/pes-match-plans --check-only`. No activation is required. For the
short command names below, activate the environment first:

```bash
source .venv/bin/activate

# Independent input paths; each filename and directory may be customized.
csv_paths=(
    --players-csv /path/to/players/Players.csv
    --teams-players-csv /path/to/memberships/Teams-Players.csv
    --rosters-csv /path/to/squads/Rosters.csv
    --formations-csv /path/to/tactics/Formations.csv
)

# One team: validate and generate without changing Formations.csv.
pes-match-plan "${csv_paths[@]}" --team 'My Club' --preset-mode single --dry-run

# Generate and atomically inject a team’s match plan.
pes-match-plan "${csv_paths[@]}" --team 77 --preset-mode multi

# Preflight all teams, or select several clubs, national teams, or custom squads.
pes-match-plans "${csv_paths[@]}" --preset-mode single --check-only
pes-match-plans "${csv_paths[@]}" --preset-mode single --team 'My Club' --team 77

# Codex uses the same match-plan pipeline and contracts.
pes-match-plan "${csv_paths[@]}" --team 77 --preset-mode single --engine codex

# Model the roster at its existing Players.csv ages, then atomically inject it.
pes-player-attributes --players-csv /path/to/people.csv --teams-players-csv /path/to/members.csv --team 'My Club' --check-only
pes-player-attributes --players-csv /path/to/people.csv --teams-players-csv /path/to/members.csv --team 'My Club'
```

Without installation, run from this directory using
`python3 -m pes_workflows.generate_match_plan`,
`python3 -m pes_workflows.batch_generate_match_plans`, or
`python3 -m pes_workflows.batch_design_player_attributes` with the same arguments.
Installed commands work from any working directory. In WSL, Windows-hosted CSVs
can be accessed directly using mounted paths such as `/mnt/c/PES2021/Players.csv`
for `C:\PES2021\Players.csv`. The template uses this layout; change the drive and
directories to match your exports. Native Windows paths (`C:/PES2021/Players.csv`
or backslash paths) are also accepted in WSL and translated by `wslpath`, which
respects the configured drive mounts. See [Microsoft's WSL path guidance](https://learn.microsoft.com/en-us/windows/dev-environment/wsl-interop).
Use TOML literal strings for backslashes, for example
`players_csv = 'C:\PES2021\Players.csv'`, and quote CLI arguments containing spaces.
Linux absolute paths and `~` paths continue to work. Windows drive-relative paths
such as `C:Players.csv` are rejected. On Linux outside WSL, use Linux paths.
The referenced drive/share must be mounted and the files readable/writable;
preflight checks the resolved files and verifies temporary-file creation beside
each CSV write target before any model calls.

## Configuration

All commands automatically load `pes-workflows.toml` from the current working
directory when present. `--config /path/to/settings.toml` selects a different
file; `--no-config` disables automatic loading. Explicitly requested missing
files, invalid TOML, unknown keys, and invalid values produce an argument error
before execution. The tracked example lists all supported settings.

Precedence is **built-in defaults → `[defaults]` → workflow section → CLI**.
All CSV paths must be absolute (after expanding `~`), in both TOML and CLI.
There are no default CSV paths or inferred filenames. Other configuration paths
are relative to the configuration file; other CLI paths are relative to the
working directory. CLI-only usage still works. Match plans require all four CSV
paths and `preset_mode`; attributes require only the players and membership paths.

| Section | Supported settings |
| --- | --- |
| `[defaults]` | `players_csv`, `teams_players_csv`, `rosters_csv`, `formations_csv`, `model`, `effort`, `delay`, `fast`; match plans also inherit the Global Auto Options below |
| `[match_plan]` | Shared settings plus `output_dir`, `engine`, `preset_mode`, `auto_substitutions`, `auto_change_att_def`, `auto_switch_preset_tactics`, `dry_run`, `force`, `attributes_completed_teams`, `scope`, `teams` |
| `[match_plans]` | All single-match settings plus `check_only` |
| `[player_attributes]` | Shared settings plus `output_dir`, `check_only`, `max_teams`, `max_turns`, `scope`, `teams` |

Keys use underscores; equivalent CLI flags use hyphens. Attribute `output_dir`
maps to `--output` (also accepted as `--output-dir`). Attributes retain their
Claude Code transport; `engine`, `preset_mode`, `dry_run`, and `force` apply to
match plans. For offline attribute validation, use `check_only`.
Booleans accept explicit CLI reversal: `--no-fast`, `--no-dry-run`,
`--no-force`, and `--no-check-only` override configured `true` values wherever
the corresponding flag is supported. Omit `model` and `effort` to use engine
defaults; configured values remain in effect when overriding only `--engine`.

Both engines default to `effort="high"`; supported workflow values are `low`,
`medium`, `high`, `xhigh`, and `max` (subject to the chosen model's support).
Claude defaults to `claude-opus-5-5`, with `claude-fable-5-1` as an alternative.
Codex defaults to `gpt-6-astra`, with `gpt-6-sol` as an alternative. Model IDs are
not restricted to these examples. Current IDs are documented in the
[Claude model catalog](https://platform.claude.com/docs/en/models/overview) and
[OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model).
Put model overrides in workflow sections when mixing engines. The template
documents each setting's meaning, valid values, and behavior when omitted;
setup preserves existing configuration files, so merge updates manually.

Player attributes accept `max_turns` only in `[player_attributes]`, or
`--max-turns N` on the CLI. It must be a positive integer and defaults to `80`.
The limit applies to each Claude CLI request, including web tool interactions,
and is reused for each stage, repair, and retry. CLI values override TOML.
It does not limit team count (`max_teams`) or change the match-plan turn limit.

Global Auto Options can be set in `[defaults]`, `[match_plan]`, or `[match_plans]`.
They apply to the team's global formation row and are independent of model output.
Player attribute workflows ignore inherited Global Auto Options and do not accept
them in `[player_attributes]` or as CLI flags.

| TOML setting / CLI flag | CSV column | Accepted integer values and meaning | Omitted fallback |
| --- | --- | --- | --- |
| `auto_substitutions` / `--auto-substitutions` | `AutoSubstitutions` | Automatic substitution timing: `0` = Off, `1` = Very Late, `2` = Flexible, `3` = Very Early | `2` |
| `auto_change_att_def` / `--auto-change-att-def` | `AutoChangeAttDef` | Automatic attack/defence level adjustment: `0` = Off (manual), `1` = On (automatic) | `0` |
| `auto_switch_preset_tactics` / `--auto-switch-preset-tactics` | `SwitchTactics` | Automatic switching between preset tactics: `0` = Off, `1` = On | `0` for `single`, `1` for `multi` |

Explicit auto-switch values work in either preset mode. Single mode still copies
Main to all three preset slots. The mode-dependent fallback applies only when
auto-switch is omitted at every configuration level. CLI flags override TOML;
for example, `pes-match-plan --auto-substitutions 3 --auto-change-att-def 1
--auto-switch-preset-tactics 1` overrides the configured team's three options.
TOML values must be integers, not booleans, floats, or quoted numbers. Invalid
types or values outside the listed ranges abort startup before model calls or
CSV changes, including dry-run and check-only runs.

**Note:** In PES2021Editor-ejogc327, **Switch Preset Tactics** is mislabeled; it controls the in-game **Auto Switch Preset Tactics** setting. Set it to match the desired in-game auto-switch state.

Each workflow can independently override any CSV path from `[defaults]`, and
each CLI flag replaces only its corresponding configured path:

| TOML Setting | CLI Flag | Conventional Export Name |
| --- | --- | --- |
| `players_csv` | `--players-csv` | `Players.csv` |
| `teams_players_csv` | `--teams-players-csv` | `Teams-Players.csv` |
| `rosters_csv` | `--rosters-csv` | `Rosters.csv` |
| `formations_csv` | `--formations-csv` | `Formations.csv` |

For example, `pes-match-plans --formations-csv /other/location/custom-tactics.csv
--check-only` uses the other three configured paths unchanged. Attribute commands
accept all four settings but do not read the roster or formations files.

Team selection belongs to each workflow section:

```toml
[match_plans]
preset_mode = "single"
scope = "multiple"
teams = ["77", "My Club"]
```

Use `scope = "single"` with exactly one team, `"multiple"` with at least two
selectors, or `"all"` with an empty/omitted `teams` list. Selectors are strings
containing IDs or names. Without `scope`, the team count determines the scope;
without either setting, batch commands process all teams. The single-match
command requires one team. Duplicate selections run once. Match-plan batches
preserve selection order; attribute batches run in numeric ID order.

Any CLI `--team`, `--team-id`, or `--scope` replaces the entire configured
selection. Repeat `--team` for a list, or use `--scope all` to clear configured
targets. A CLI `--scope single`/`multiple` must include its CLI team selectors.

```bash
pes-match-plan                         # configured team and options
pes-match-plans --team 77 --team 'My Club' --no-dry-run
pes-match-plans --scope all --check-only
pes-player-attributes --config ./settings.toml --team 77 --team 'My Club'
```

All-team scope still respects eligibility, completed checkpoints, and the
optional match-plan attribute completion registry filter.

## Input and selection

Supply the editor’s semicolon-delimited exports. Match plans require
players, squad rosters, formations, and team-player memberships.
Attributes require players and memberships. `Players.csv`, `Rosters.csv`,
`Formations.csv`, and `Teams-Players.csv` are conventional names only: each file
may have any name and live in a different directory. Paths are case-sensitive
on Linux. Every required file is checked individually for existence, regular-file
type, readability, and write access before model calls, including offline
`--check-only` and match-plan `--dry-run`. Atomic write targets also require their
own parent directory to allow temporary files. No shared directory is inferred.
The membership header is
`Id;Name;Id Club;Club;Id National;National`. IDs are positive and globally unique
within each entity type. Encode custom squads using the club membership columns
and a corresponding `Rosters.csv` / `Formations.csv` team ID for match plans.
Membership rows may associate a player with both a club and a national team.

There is no nationality or name-marker filter. Exact team names and IDs take
precedence over marker-stripped aliases in match plans. Ambiguous selectors fail.
A match plan needs at least eleven players and an eligible goalkeeper. Attribute
modeling accepts any nonempty selected roster and uses its existing age and
identity data; it does not estimate ages.

Single-team match plans require a team in configuration or `--team`. Batch
commands process their configured selection, or all teams by default. Both
batch commands accept repeated `--team` names or IDs; attributes also accept
`--team-id` for one exact ID. Numeric selectors are treated as IDs by attributes.
When rosters overlap in an
attribute batch, teams run in ascending numeric ID order; each team gets a full
report, and the latest committed team’s design supplies shared players’ current
CSV attributes. Reports describe the saved design for their own run.

`--preset-mode single` generates Starting XI → Main → compact bench decision.
`--preset-mode multi` generates Starting XI → Main/Defensive/Custom → compact
bench decision; the three preset requests run independently after the XI freezes.
The compiler resolves coordinates, roles, and editor enums locally. Rejected
model artifacts receive a scoped correction; invalid plans never reach the CSV
writer. Match-plan `--dry-run` generates and validates without committing.

`--model`, `--effort`, and `--fast` configure the selected CLI transport.
`--delay` controls request cooldown. Attribute calls allow web search
and fetch for modeling research. Processes run directly with stdin and explicit
system policies, without a shell or process timeout. Authentication is managed
by the selected CLI. Tests never require either executable or credentials.

## Outputs and resume

The generated configuration enables an `output_dir` for every workflow:

| Workflow | Output directory | Completion registry |
| --- | --- | --- |
| Single-team match plan | `./outputs/match_plan` | `completed_teams_match_plan_<preset_mode>.txt` |
| Batch match plans | `./outputs/match_plans` | `completed_teams_match_plans_<preset_mode>.txt` |
| Player attribute modeling | `./outputs/player_attributes` | `completed_teams_player_attributes.txt` |

Each completion registry lives directly inside its workflow's resolved `output_dir`.
An output-directory override also changes where that workflow reads and writes
completion state. A completed team in one workflow does not mark it complete in
another. The optional `attributes_completed_teams` setting is a read-only
eligibility filter: it points to the attribute registry under the selected
attribute output directory, and never receives match-plan completion records.

`<preset_mode>` is `single` or `multi`; registries distinguish both the command
and the preset mode, even when output directories are shared. Configured output
paths resolve beside the TOML file; without configuration, the same directory
names resolve from the working directory. Match plans store logs, per-turn JSON,
policy snapshots, run manifests, history, and the final injectable semantic JSON
there. Use `--output-dir PATH` to relocate artifacts and run state. Keep the same
output directory to resume; use separate output directories for different datasets.

For existing match-plan runs, explicitly select the previous output directory
and copy the old `completed_teams_<preset_mode>_match_plan.txt` to the corresponding
new workflow registry if you want to preserve completion skips. Old registry names
did not distinguish commands, so they are not imported automatically. Attribute
runs rebuild the new registry from `batch_state.json` on resume. Update any
`attributes_completed_teams` filter paths to the new attribute registry name.
The write lock is `.<configured-filename>.match_plans.lock` beside the configured
formations file, so changing output directories cannot bypass it. Batch backups
use the configured target's stem and suffix. Use `--force` to regenerate a completed
team. `--attributes-completed-teams PATH` optionally restricts either match-plan
command to IDs in an attribute completion registry. Registries use UTF-8
`Team ID<TAB>Team Name` records, with names optional.

Attributes default to `./outputs/player_attributes/` in the working directory; `--output PATH` chooses
a different checkpoint/output directory. Use separate directories for different
team selections. Outputs include the initial CSV backup, validated profile and
ability JSON, merged attribute JSON, policy snapshots, request audits, execution
logs, and the checkpoint. Each team run also retains:

```text
teams/<team>__<kind>_<id>/run_<id>/player_attributes.md
```

This **Player Information Report** is a required deliverable. It contains every
modeled player’s identity, age, positions, style, skills, abilities, and traits.
The report is published atomically before the CSV commit. A failed report write
prevents completion. `batch_state.json` stores its absolute path and SHA-256;
resume verifies it and recreates a missing report from the saved, validated
`player_attributes.json`, without model calls. Modified reports stop resume.
Keep the output directory at its original absolute path when resuming a batch.

Re-run the same attribute command to resume; `--max-teams N` bounds one invocation.
Attribute checkpoints retain their model and effort. To resume a batch created
with older defaults, explicitly select its recorded model and effort; use a new
output directory to start with the updated defaults. `max_turns` may be adjusted
between invocations and applies to subsequent requests.
A completion registry alone does not prove that reports exist: the checkpoint is
authoritative and repairs an interrupted registry update. Resume checks source
absolute CSV paths as well as CSV and prompt hashes and rejects untracked edits.
Changing either source path requires a new output directory, even if its bytes
are identical. Older checkpoints without source paths also require a new output
directory. Attribute batch locks are tied to the configured players filename in
its own directory; commit locks protect that same file. An interruption between a CSV
commit and its checkpoint requires inspection of that run’s manifest and backup;
resume refuses to silently replay over the changed CSV.

POSIX locks serialize writers sharing a database. Attribute verification replays
committed artifacts against the backup and checks all CSV rows, including
unmodeled cells. Per-turn Markdown pages, combined tactical presentations,
formation display files, and copied runtime scripts are not generated.

## Prompts and development

The packaged prompt hierarchy is:

```text
pes_workflows/prompts/
├── match_plan/
│   ├── system_prompt.md
│   ├── game_plan_rules.md
│   ├── user_message_templates.md
│   ├── player_records_example.md
│   ├── bench_system_prompt.md
│   └── bench_user_message_template.md
├── player_attributes/
│   ├── system_prompt.md
│   └── user_message_template.md
└── shared/
    └── player_glossary.md
```

The two bench fragments are referenced directly by the match-plan templates.
`player_records_example.md` documents the input grammar. Both pipelines load the
self-contained `shared/player_glossary.md`, which includes all Player Skills and
COM Playing Styles inline. Copy the whole prompt hierarchy when customizing or
relocating it. Attribute resume hashes cover the shared glossary as well as the
attribute prompts, so changes to shared rules are detected too. These hashes are
computed automatically at runtime. Edit prompt sources directly; no checksum
inventory needs updating. The offline suite checks that required prompt assets
are readable and nonempty and exercises prompt loading and rendering.

```bash
python3 run_tests.py
python3 -m pip install '.[dev]'
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy pes_workflows
```

Tests use temporary synthetic databases. Coverage includes native CLI transport
and retry behavior, both match-plan modes, contract repairs, compiler geometry,
position eligibility, atomic CSV injection, locking, team selection, checkpoint
resume, report recovery and publication failure, and execution from a copied
project outside this repository.

Match-plan injection compiles once before the CSV transaction. Both workflows
use `Config.MAX_FORMAT_REPAIRS` for contract corrections and
`Config.DEFAULT_MODEL` for the Claude model default.

The package supports the three CLI workflows. Unused integration APIs for
cooperative cancellation, injection sessions, roster filtering, age overrides,
roster display summaries, and discarded compiler reports have been removed.
