# PES 2021 球队工作流

[English](README.md)

适用于 WSL 和 Linux 的独立 Python 3.11+ 工作流。可以将整个项目目录复制到任意位置运行；项目自带编译器、校验器、名单读取器、CSV 写入器、CLI 适配器、提示词和离线测试。运行依赖 pandas，以及已完成身份验证的 `claude` 命令；比赛计划也可以使用 `codex`。无需图形界面或 API SDK。

## 安装与运行

克隆后，在项目根目录运行：

```bash
python3 setup_env.py
```

安装脚本会创建不继承系统包的 `.venv`，以可编辑模式安装本项目及 Python 依赖，并在 `pes-workflows.toml` 不存在时从 `pes-workflows.example.toml` 复制配置。重复运行会保留已有设置。需要 Python 3.11+、`venv`/`ensurepip` 支持和可访问的 Python 包索引。脚本不会安装或登录 Claude Code（`claude`）或 Codex（`codex`）；请另行安装并登录所选 CLI。离线预检不需要这两个 CLI。使用 `python3 setup_env.py --dev` 可同时安装开发工具。

编辑 `pes-workflows.toml`，配置 CSV 的绝对路径和目标球队，然后运行 `.venv/bin/pes-match-plans --check-only`，无需激活环境。若使用下面的简短命令，先激活虚拟环境：

```bash
source .venv/bin/activate

# 四个输入路径独立配置，文件名和目录均可自定义。
csv_paths=(
    --players-csv /path/to/players/Players.csv
    --teams-players-csv /path/to/memberships/Teams-Players.csv
    --rosters-csv /path/to/squads/Rosters.csv
    --formations-csv /path/to/tactics/Formations.csv
)

# 单支球队：生成、校验并原子注入单预设计划。
pes-match-plan "${csv_paths[@]}" --team 'My Club' --preset-mode single

# 生成比赛计划并原子写入 CSV。
pes-match-plan "${csv_paths[@]}" --team 77 --preset-mode multi

# 预检所有球队，或选择多个俱乐部、国家队、自定义球队。
pes-match-plans "${csv_paths[@]}" --preset-mode single --check-only
pes-match-plans "${csv_paths[@]}" --preset-mode single --team 'My Club' --team 77

# Codex 使用相同的比赛计划流程和数据契约。
pes-match-plan "${csv_paths[@]}" --team 77 --preset-mode single --engine codex

# 按 Players.csv 中的现有年龄建模球员属性，然后原子写入。
pes-player-attributes --players-csv /path/to/people.csv --teams-players-csv /path/to/members.csv --team 'My Club' --check-only
pes-player-attributes --players-csv /path/to/people.csv --teams-players-csv /path/to/members.csv --team 'My Club'
```

也可以不安装项目，在项目目录中使用 `python3 -m pes_workflows.generate_match_plan`、`python3 -m pes_workflows.batch_generate_match_plans` 或 `python3 -m pes_workflows.batch_design_player_attributes`，参数相同。安装后的命令可以在任意工作目录运行。

在 WSL 中，可通过挂载路径直接访问 Windows 上的 CSV，例如 `C:\PES2021\Players.csv` 对应 `/mnt/c/PES2021/Players.csv`。配置模板采用这种布局，请按实际导出位置修改盘符和目录。WSL 也接受原生 Windows 路径（`C:/PES2021/Players.csv` 或反斜杠形式），并通过 `wslpath` 按系统挂载配置转换。参见 [Microsoft 的 WSL 路径说明](https://learn.microsoft.com/en-us/windows/dev-environment/wsl-interop)。

含反斜杠的 TOML 路径应使用字面量字符串，例如 `players_csv = 'C:\PES2021\Players.csv'`；CLI 路径含空格时应加引号。Linux 绝对路径和 `~` 路径同样可用。`C:Players.csv` 这类盘符相对路径会被拒绝。非 WSL 的 Linux 环境请使用 Linux 路径。对应磁盘或共享目录必须已挂载，文件必须可读写；预检会在调用模型之前检查解析后的文件，并验证每个 CSV 写入目标的父目录能否创建临时文件。

## 配置

所有命令默认读取当前工作目录中的 `pes-workflows.toml`（如果存在）。使用 `--config /path/to/settings.toml` 指定其他配置文件，或使用 `--no-config` 禁用自动加载。显式指定的文件不存在、TOML 语法错误、未知键或无效值都会在执行前触发参数错误。[配置示例](pes-workflows.example.toml) 列出了全部支持的设置。

优先级为：**内置默认值 → `[defaults]` → 工作流专属配置节 → CLI 参数**。TOML 和 CLI 中的 CSV 路径均须为绝对路径（允许先展开 `~`），没有默认 CSV 路径，也不会推断文件名。其他配置路径相对于配置文件解析，其他 CLI 路径相对于工作目录解析。可以完全通过 CLI 配置。比赛计划必须提供四个 CSV 路径和 `preset_mode`；球员属性只要求球员与归属关系两个文件路径。

| 配置节 | 支持的设置 |
| --- | --- |
| `[defaults]` | `players_csv`、`teams_players_csv`、`rosters_csv`、`formations_csv`、`model`、`effort`、`delay`、`fast`；比赛计划还继承下文的全局自动选项 |
| `[match_plan]` | 共享设置，以及 `output_dir`、`engine`、`preset_mode`、`auto_substitutions`、`auto_change_att_def`、`auto_switch_preset_tactics`、`force`、`attributes_completed_teams`、`scope`、`teams` |
| `[match_plans]` | 单队比赛计划的全部设置，以及 `check_only` |
| `[player_attributes]` | 共享设置，以及 `output_dir`、`check_only`、`max_teams`、`max_turns`、`scope`、`teams` |

配置键使用下划线，对应 CLI 参数使用连字符。球员属性的 `output_dir` 对应 `--output`，也接受 `--output-dir`。球员属性始终使用 Claude Code；`engine`、`preset_mode` 和 `force` 只适用于比赛计划。属性工作流的离线校验使用 `check_only`。

布尔选项支持显式反向覆盖：在支持相应选项的命令中，`--no-fast`、`--no-force` 和 `--no-check-only` 会覆盖配置中的 `true`。省略 `model` 和 `effort` 时使用引擎默认值；只覆盖 `--engine` 不会清除已配置的模型和推理强度。

两个引擎均默认使用 `effort="high"`；工作流接受 `low`、`medium`、`high`、`xhigh` 和 `max`，具体取决于模型是否支持。项目中 Claude 的默认模型是 `claude-opus-5-5`，备选示例为 `claude-fable-5-1`；Codex 默认模型是 `gpt-6-astra`，备选示例为 `gpt-6-sol`。模型 ID 不限于这些示例。模型信息可参考 [Claude 模型目录](https://platform.claude.com/docs/en/models/overview) 和 [OpenAI 模型指南](https://developers.openai.com/api/docs/guides/latest-model)。混用引擎时，建议在各工作流配置节中覆盖模型。配置模板说明了每个选项的含义、有效值和省略时的行为；安装脚本保留已有配置，需要手动合并模板更新。

球员属性仅在 `[player_attributes]` 中接受 `max_turns`，CLI 对应 `--max-turns N`。它必须为正整数，默认为 `80`。限制针对每次 Claude CLI 请求，包括联网工具交互，并分别用于各阶段、格式修复和重试。CLI 优先于 TOML。它不限制球队数量（该限制由 `max_teams` 控制），也不改变比赛计划的轮次上限。`max_teams`/`--max-teams N` 也是正整数，省略时不限制本次执行尝试的待处理球队数量。`delay`/`--delay` 为每次成功请求后的冷却秒数，必须是非负有限数，默认 `5.0`；`fast` 默认为 `false`，请求 CLI 的快速模式，不改变推理强度。比赛计划的 `engine` 可选 `claude-code`（默认）或 `codex`。

全局自动选项（Global Auto Options）可以配置在 `[defaults]`、`[match_plan]` 或 `[match_plans]` 中。这些设置直接应用于球队的全局阵型行，与模型输出无关。球员属性会忽略继承的全局自动选项，不接受在 `[player_attributes]` 或属性 CLI 中配置它们。

| TOML 设置 / CLI 参数 | CSV 列 | 整数取值及含义 | 省略时的值 |
| --- | --- | --- | --- |
| `auto_substitutions` / `--auto-substitutions` | `AutoSubstitutions` | 自动换人时机：`0` 关闭，`1` 很晚，`2` 灵活，`3` 很早 | `2` |
| `auto_change_att_def` / `--auto-change-att-def` | `AutoChangeAttDef` | 自动调整攻防等级：`0` 关闭（手动），`1` 开启（自动） | `0` |
| `auto_switch_preset_tactics` / `--auto-switch-preset-tactics` | `SwitchTactics` | 自动切换预设战术：`0` 关闭，`1` 开启 | `single` 为 `0`，`multi` 为 `1` |

显式设置自动切换值时，两种预设模式均可使用 `0` 或 `1`。单预设模式仍会将 Main 复制到三个预设槽位。只有所有配置层均省略自动切换选项时，才使用基于模式的默认值。CLI 覆盖 TOML，例如 `pes-match-plan --auto-substitutions 3 --auto-change-att-def 1 --auto-switch-preset-tactics 1` 会覆盖已配置球队的这三个选项。

TOML 值必须为整数，不能是布尔值、浮点数或带引号的数字。无效类型或超出范围的数值会在启动阶段终止，即使使用 check-only，也不会调用模型或修改 CSV。

**注意：** PES2021Editor-ejogc327 中的 **Switch Preset Tactics** 标签有误；它实际控制游戏中的 **Auto Switch Preset Tactics**。请按期望的游戏内自动切换状态设置。

每个工作流都可独立覆盖 `[defaults]` 的任意 CSV 路径，每个 CLI 参数也只覆盖对应路径：

| TOML 设置 | CLI 参数 | 常见导出文件名 |
| --- | --- | --- |
| `players_csv` | `--players-csv` | `Players.csv` |
| `teams_players_csv` | `--teams-players-csv` | `Teams-Players.csv` |
| `rosters_csv` | `--rosters-csv` | `Rosters.csv` |
| `formations_csv` | `--formations-csv` | `Formations.csv` |

例如 `pes-match-plans --formations-csv /other/location/custom-tactics.csv --check-only` 会保留其他三个已配置路径。属性命令接受全部四个设置，但不会读取名单或阵型文件。

球队选择在各自的工作流配置节中设置：

```toml
[match_plans]
preset_mode = "single"
scope = "multiple"
teams = ["77", "My Club"]
```

`scope = "single"` 要求恰好一个球队选择器；`"multiple"` 要求至少两个；`"all"` 要求 `teams` 为空或省略。选择器必须为包含 ID 或名称的字符串。省略 `scope` 时根据球队数量推断范围；两者均省略时，批量命令处理全部球队。单队命令必须选择一支球队。重复选择只执行一次。比赛计划批量执行保留选择顺序，属性批量执行按球队 ID 的数值升序排列。

CLI 中任意 `--team`、`--team-id` 或 `--scope` 都会替换配置中的整个选择范围。多次传入 `--team` 可指定列表，`--scope all` 可清空配置中的目标。CLI 使用 `--scope single`/`multiple` 时，必须同时在 CLI 中提供球队选择器。

```bash
pes-match-plan                         # 使用已配置的球队和选项
pes-match-plans --team 77 --team 'My Club'
pes-match-plans --scope all --check-only
pes-player-attributes --config ./settings.toml --team 77 --team 'My Club'
```

全队范围仍遵循资格检查、已完成检查点和可选的属性完成登记筛选条件。

## 输入与选择规则

输入为编辑器导出的分号分隔 CSV。比赛计划需要球员、球队名单、阵型和球队归属关系四类文件；球员属性需要球员与归属关系文件。`Players.csv`、`Rosters.csv`、`Formations.csv` 和 `Teams-Players.csv` 只是常见文件名，各文件可使用任意名称并存放在不同目录。Linux 路径区分大小写。

调用模型前会逐一检查必需文件是否存在、是否为普通文件、是否可读写；离线 `--check-only` 也执行这些检查。原子写入目标的父目录必须允许创建临时文件，不会推断共享目录。归属关系表头为 `Id;Name;Id Club;Club;Id National;National`。ID 必须为正数，并在同类实体中全局唯一。自定义球队使用俱乐部归属列编码；生成比赛计划时还须在 `Rosters.csv` 和 `Formations.csv` 中提供相应球队 ID。一名球员可同时归属俱乐部与国家队。

不会按国籍或名称标记过滤。比赛计划优先匹配精确球队名和 ID，再匹配去除标记的名称别名；存在歧义时会报错。比赛计划至少需要十一名球员及一名符合条件的门将。属性建模接受任意非空的已选名单，使用现有年龄和身份数据，不估算年龄。

单队比赛计划必须通过配置或 `--team` 指定球队。批量命令使用配置中的选择范围，默认选择全部球队。两个批量命令都接受重复的 `--team` 名称或 ID；属性命令还接受 `--team-id` 指定一个精确 ID，数字选择器按 ID 处理。

属性批次中若球队名单重叠，按球队 ID 数值升序执行。每支球队都生成完整报告，共享球员的当前 CSV 属性以最后一次提交的球队设计为准；每份报告记录其所属运行保存的设计。

`--preset-mode single` 的流程为：锁定首发 XI → Main → 精简替补决策。`--preset-mode multi` 的流程为：锁定首发 XI → Main/Defensive/Custom → 精简替补决策；首发锁定后，三个预设请求独立并行执行。编译器在本地解析坐标、角色和编辑器枚举。模型产物被拒绝时会收到限定范围的修正请求，无效计划不会进入 CSV 写入器。比赛计划执行成功后会原子注入已校验的计划并记录球队完成状态。

`--model`、`--effort`、`--fast` 配置所选 CLI，`--delay` 控制请求冷却。属性请求允许通过网页搜索和抓取开展建模研究。进程直接执行，通过标准输入接收数据并使用显式系统策略，不经过 shell，也不设置进程超时。身份验证由所选 CLI 管理。测试不需要模型 CLI 或登录凭据。

## 输出与续跑

生成的配置为每个工作流设置了 `output_dir`：

| 工作流 | 输出目录 | 完成登记文件 |
| --- | --- | --- |
| 单队比赛计划 | `./outputs/match_plan` | `completed_teams_match_plan_<preset_mode>.txt` |
| 批量比赛计划 | `./outputs/match_plans` | `completed_teams_match_plans_<preset_mode>.txt` |
| 球员属性建模 | `./outputs/player_attributes` | `completed_teams_player_attributes.txt` |

完成登记文件直接保存在各工作流解析后的 `output_dir` 中。覆盖输出目录会同时改变该工作流完成状态的读写位置。在一个工作流中完成的球队不会自动标记为其他工作流已完成。

可选的 `attributes_completed_teams` 是只读资格筛选器，指向所选属性输出目录中的属性完成登记文件，不接收比赛计划的完成记录。`<preset_mode>` 为 `single` 或 `multi`；即使共享输出目录，登记文件也按命令和预设模式区分。

配置中的输出路径相对于 TOML 文件解析；不加载配置时，相同默认目录名相对于工作目录解析。比赛计划在输出目录保存日志、逐轮 JSON、策略快照、运行清单、历史记录以及最终可注入的语义 JSON。使用 `--output-dir PATH` 更改产物和运行状态位置。续跑时保持相同输出目录；不同数据集应使用不同输出目录。

两个比赛计划命令还会发布完整的 **比赛计划报告（Match Plan Report）**：

```text
<output_dir>/<team>/run_<id>/
├── match_plan.md
├── run_manifest.json
├── conversation_history.json
├── 00_Final_System_Prompt.md
├── Turn_<nn>_<title>.json
└── semantic_game_plan_<team>.json
```

`match_plan.md` 记录锁定的首发 XI、每个有效预设在各流动阵型状态下的位置和战术职责、基础与高级指令、留守防守安排、参与进攻球员、越位陷阱设置、战术机制与约束、队长与定位球主罚者、全局自动选项，以及按优先级排列的替补名单。单预设模式说明 Main 被完全复制到 Defensive 和 Custom。多预设模式由 Main 提供全局越位陷阱和参与进攻 CSV 字段；报告标明 Defensive/Custom 中需要在游戏内调整的覆盖设置。角色分配使用与 CSV 注入相同的确定性选择器和球员属性。

报告以 UTF-8 编码，在计划组装完成后、CSV 注入前原子发布。`run_manifest.json` 的 `artifacts.match_plan_report` 记录报告路径，路径相对于本次运行目录。报告写入失败会阻止注入和完成登记；后续注入失败仍会保留报告供检查，最终结果以清单中的状态为准。离线 `--check-only` 不生成战术或比赛计划报告。已完成球队仍按原规则跳过；使用 `--force` 可生成包含报告的新运行。

迁移已有比赛计划运行时，请显式选择之前的输出目录；若要保留完成跳过行为，将旧文件 `completed_teams_<preset_mode>_match_plan.txt` 复制为相应的新工作流登记文件名。旧名称不区分命令，因此不会自动导入。属性续跑会根据 `batch_state.json` 重建新登记文件。请同步更新 `attributes_completed_teams` 筛选器中的路径。

比赛计划写锁为阵型文件旁的 `.<配置文件名>.match_plans.lock`，改变输出目录无法绕过该锁。批量备份使用目标文件配置的主文件名和后缀。`--force` 可重新生成已完成球队，`--attributes-completed-teams PATH` 可将任一比赛计划命令限制在属性登记文件列出的球队 ID 内。登记文件采用 UTF-8 编码，每条记录为 `Team ID<TAB>Team Name`，名称可省略。

球员属性默认输出到工作目录下的 `./outputs/player_attributes/`；`--output PATH` 可指定其他检查点与输出目录。不同球队选择应使用不同目录。输出包括初始 CSV 备份、已校验的档案与能力 JSON、合并属性 JSON、策略快照、请求审计、执行日志和检查点。每次球队运行还保留：

```text
teams/<team>__<kind>_<id>/run_<id>/player_attributes.md
```

该 **球员信息报告（Player Information Report）** 是必需产物，包含每位建模球员的身份、年龄、位置、风格、技能、能力和特征。报告在 CSV 提交前原子发布，写入失败会阻止完成。`batch_state.json` 保存报告绝对路径及 SHA-256；续跑时会校验报告，若缺失则从保存的、已校验的 `player_attributes.json` 重建，无需模型调用。报告被修改会阻止续跑。恢复批次时应保持输出目录原有的绝对路径。

重复执行相同属性命令即可续跑；`--max-teams N` 限制本次调用尝试的球队数。属性检查点保留模型和推理强度。续跑使用旧默认值创建的批次时，须显式指定其记录的模型和推理强度；若要使用新默认值重新开始，请使用新输出目录。`max_turns` 可在两次执行间调整，并用于后续请求。

仅有完成登记文件不能证明报告存在；检查点是权威依据，并会修复中断的登记更新。续跑检查源 CSV 的绝对路径、CSV 哈希和提示词哈希，并拒绝未跟踪的修改。任一源路径变化，即使文件内容相同，也需要新输出目录；不包含源路径的旧检查点同样需要新目录。

属性批次锁绑定球员文件所在目录中的配置文件名，提交锁保护同一文件。CSV 已提交但检查点尚未更新时若发生中断，需要检查该次运行的清单与备份；续跑会拒绝在已更改的 CSV 上静默重放。

POSIX 锁会串行化共享数据库的写入。属性验证会对照备份重放已提交产物，检查全部 CSV 行，包括未建模的单元格。比赛计划每次运行提供一份汇总 Markdown 报告，不生成逐轮 Markdown 页面、独立阵型显示文件或运行脚本副本。

## 提示词与开发

打包的提示词目录结构如下：

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

比赛计划模板直接引用两个替补提示词片段。`player_records_example.md` 说明输入语法。两个流程都加载自包含的 `shared/player_glossary.md`，其中内嵌全部球员技能和电脑比赛风格。自定义或迁移提示词时，应复制整个层级。

属性续跑哈希涵盖共享术语表及属性提示词，因此共享规则变更也会被检测到。哈希在运行时自动计算；直接编辑提示词源文件即可，无需更新校验和清单。离线测试检查必需提示词是否可读且非空，并覆盖提示词加载和渲染。

激活虚拟环境后，在项目根目录运行：

```bash
python3 run_tests.py
python3 -m pip install '.[dev]'
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy pes_workflows
```

测试使用临时合成数据库。覆盖 CLI 传输和重试、两种比赛计划模式、契约修复、编译器几何、位置资格、CSV 原子注入、锁、球队选择、检查点续跑、报告恢复和发布失败，以及复制到仓库外的项目执行。

比赛计划注入在 CSV 事务前只编译一次。两个工作流使用 `Config.MAX_FORMAT_REPAIRS` 控制契约修正次数，使用 `Config.DEFAULT_MODEL` 作为 Claude 模型默认值。

本包支持上述三个 CLI 工作流。未使用的协作取消、注入会话、名单筛选、年龄覆盖、名单展示摘要和已弃用编译报告等集成 API 已移除。
