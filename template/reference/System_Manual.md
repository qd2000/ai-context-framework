本文件是上下文管理系统的详细使用手册。

通常不需要默认读取本文件。只有在以下情况才需要读取：

- 需要理解本系统如何运作
- 需要指导 AI 如何正确使用某个目录或文件
- 用户要求查看或修改系统规则

入口文件请查看：`AGENTS.md`

---

## 1. active/ 使用规则

`active/` 是 AI 默认优先读取的当前上下文层。

其中：

- `active/Context.md`：当前阶段事实源，记录当前阶段目标、范围、约束、有效事实和开放问题。
- `active/Feedback_Inbox.md`：人工临时反馈、问题、需求和计划碎片的入口，允许不规范描述，但不直接作为已确认事实。
- `active/Task_Plan.md`：当前大任务计划和轻量子任务板，记录子任务状态、证据和下一步。
- `active/Current_Task.md`：当前具体任务说明，仅在任务状态为 Active 时作为当前任务事实源。
- Workstreams 索引：可选并行目标线索引，仅在显式启用 Workstream 层且存在 Active、Blocked 或 ReadyToMerge workstream 时按需读取。

使用规则：

1. 默认优先读取 `active/Context.md`。
2. 有 Open 条目或需要整理人工反馈时读取 `active/Feedback_Inbox.md`。
3. 默认读取 `active/Task_Plan.md`，但该文件必须保持轻量。
4. 如果 `active/Current_Task.md` 状态为 Active，则读取它。
5. 如果存在 Active、Blocked 或 ReadyToMerge workstream，或当前任务需要整理并行协作，则读取 Workstreams 索引，再按需读取对应详情文件。
6. 如果用户当前消息提出了新的任务，并且与 `active/Current_Task.md` 冲突，以用户当前消息为准。
7. `active/` 中的信息应保持短、准、当前有效。
8. 不要把历史过程、旧方案、原始日志写入 `active/`。

### 1.1 Feedback_Inbox 生命周期

`active/Feedback_Inbox.md` 用于接住尚未整理的人工反馈，不是最终事实源。

状态含义：

- Open：尚未整理。
- Triaged：已判断归属，但尚未完全落盘。
- Planned：已进入 `active/Task_Plan.md` 或当前任务。
- Done：已处理完成，并已有证据位置。
- Rejected：明确不采纳或不再适用，并已有原因说明。

处理规则：

1. Open 条目先判断归属，不直接写成当前事实。
2. Planned 条目必须引用任务计划、当前任务或明确的落盘动作。
3. Done / Rejected 条目必须保留证据位置或拒绝原因。
4. active 表长期只保留 Open、Triaged、Planned，以及当前大任务仍需解释的 Done / Rejected 条目。
5. 当 Done / Rejected 条目超过 10 条，或完成超过 30 天且不再支撑当前计划时，应整理到 `archive/feedback/`。
6. 反馈归档文件按月份命名为 YYYY-MM.md，摘要记录 ID、状态、类型、内容摘要、处理结果和证据位置，不复制长过程。

---

## 2. rules/ 读取策略

规则不是一次性全部读取的。

默认读取：

- `rules/Always_Active.md`

根据任务类型按需读取：

| 场景 | 读取文件 |
|------|----------|
| 需要了解规则体系 | `rules/Rules_Index.md` |
| 涉及项目通用约束 | `rules/Project_Rules.md` |
| 涉及代码实现、调试、重构 | `rules/Coding_Rules.md` |
| 涉及写作、文档、内容输出 | `rules/Writing_Rules.md` |
| 涉及方案评审、风险审查 | `rules/Review_Rules.md` |
| AI 判断可能需要额外规则 | `rules/Agent_Requested.md` |
| 用户明确要求特殊模式 | `rules/Manual_Only.md` |

请不要默认读取整个 `rules/` 目录。

---

## 3. rules/ 文件含义

- **Rules_Index.md**：规则索引，说明各规则文件用途和读取条件。
- **Always_Active.md**：每次 AI 协作都必须遵守的核心规则，保持短小。
- **Project_Rules.md**：项目级通用规则，适用于大多数任务。
- **Agent_Requested.md**：AI 按需请求的规则说明。
- **Manual_Only.md**：只有用户明确要求时才启用的特殊规则。
- **Coding_Rules.md**：代码相关任务规则。
- **Writing_Rules.md**：写作相关任务规则。
- **Review_Rules.md**：评审相关任务规则。

---

## 4. reference/ 使用规则

`reference/` 是支持性资料区，不是默认上下文区。

根据任务需要读取：

| 场景 | 读取文件 |
|------|----------|
| 需要理解项目长期背景 | `reference/Project_Brief.md` |
| 需要追溯重要决策 | `reference/Decisions_Index.md` |
| 涉及架构设计 | `reference/Architecture.md` |
| 涉及技术实现、运行环境 | `reference/Tech_Context.md` |
| 涉及外部资料来源 | `reference/Sources_Index.md` |
| 需要追溯可复用经验 | `reference/Knowledge_Index.md` |

不要默认读取所有 reference 文件。

如果需要资料详情，请先查看 `Sources_Index.md`，再读取 `reference/sources/` 下对应的资料笔记。

---

## 5. reference/ 文件含义

- **Project_Brief.md**：项目长期背景、目标、愿景、边界和非目标。不记录当前阶段目标。
- **Decisions_Index.md**：重要决策索引，只记录摘要和 ADR 路径。
- **Knowledge_Index.md**：可复用经验索引，只记录从历史材料中提炼出的模式、反例和判断方法。
- **Architecture.md**：项目架构说明，仅在涉及系统设计时读取。
- **Tech_Context.md**：技术环境和约束，仅在涉及技术栈、兼容性时读取。
- **Sources_Index.md**：外部资料索引，只保存摘要和路径，不保存大段原文。
- **System_Manual.md**：本文件，系统详细使用手册。

---

## 6. decisions/ 使用规则

`decisions/` 中保存重要决策详情，采用 ADR（Architecture Decision Record）形式。

使用规则：

1. 先读取 `reference/Decisions_Index.md`。
2. 只有需要理解决策原因、替代方案、代价或重新评估条件时，才读取具体 ADR 文件。
3. 不要默认读取所有 ADR。
4. 不要重复推进已标记为 Rejected、Superseded 或 Deprecated 的方案。
5. 如果 worklog 中的结论已成为重要决策，应同步到 `Decisions_Index.md` 或新增 ADR。

---

## 7. worklog/ 使用规则

`worklog/` 保存整理后的工作记录，不是原始代码日志。

使用规则：

1. 默认不要读取每日 worklog。
2. 需要近期历史时，先浏览 `worklog/Worklog_Index.md` 的"关键结论"列。
3. 需要追溯某一天的过程时，通过 Worklog_Index 定位，再读取对应日期文件。
4. daily worklog 是历史过程记录，不等于当前事实。
5. 如果 daily worklog 中的内容已成为当前事实，应同步到 `active/Context.md`。
6. 如果 daily worklog 中的内容已成为重要决策，应同步到 `reference/Decisions_Index.md` 或 `decisions/`。

原始运行日志不应写入 `worklog/`，应放在项目的 `logs/` 或用户指定的日志目录中。

---

## 8. archive/ 使用规则

`archive/` 保存历史归档内容。

使用规则：

1. 默认不要读取 `archive/`。
2. archive 中的内容不能直接视为当前事实。
3. 只有在用户要求追溯历史、比较旧版本时，才读取 archive。
4. 如果 archive 中的内容重新变得重要，应先经过确认，再同步到 `active/` 或 `reference/`。
5. 已处理反馈的长期归档放在 `archive/feedback/`，默认不读取。

---

## 9. knowledge/ 使用规则

`reference/knowledge/` 保存可复用经验、模式、反例和判断方法。

使用规则：

1. 默认不要读取完整 knowledge 条目。
2. 先读取 `reference/Knowledge_Index.md`，再按需读取具体条目。
3. Knowledge 不是当前事实源，不保存当前状态、一次性过程或完整决策。
4. 每条 Knowledge 必须有来源、适用场景、不适用场景、与现有事实源的关系和去重判断。
5. 如果 Knowledge 已升级为 rules、ADR 或手册内容，应标记为 Promoted。

---

## 10. Sources 和原始资料的处理

`reference/Sources_Index.md` 只是资料索引。

推荐存放方式：

- 资料索引：`reference/Sources_Index.md`
- 整理后的资料笔记：`reference/sources/`
- PDF、截图、原始文件：`materials/` 或用户指定的资料目录
- 外部网页或 GitHub 项目：只在 `Sources_Index.md` 中记录链接和摘要

使用资料时：

1. 索引摘要不等于完整证据。
2. 需要准确引用时，应查看原始资料。
3. 不要把未经验证的资料摘要写成项目事实。

---

## 11. 原始日志的处理

原始运行日志、错误堆栈、构建输出、测试输出等，不应写入 `worklog/`。

AI 使用日志时：

1. 不要默认读取完整日志。
2. 优先读取用户提供的日志片段。
3. 如果需要日志文件，请说明需要哪一个、哪一段。
4. 分析后请提炼摘要，不要把大量日志写入 `active/`。

---

## 12. 处理不确定信息

如果信息不足：

1. 明确说明缺少哪些信息。
2. 给出基于当前上下文的临时判断。
3. 标注该判断的不确定性。
4. 说明需要读取或补充哪些文件。
5. 不要把临时判断写成确定事实。

---

## 13. 更新项目上下文的规则

AI 可以提出项目文件更新建议，但不要擅自把内容写入长期上下文。

重要协作结束后，AI 不应默认重复打印完整回写建议清单。应先判断哪些内容可以确定落盘，优先使用 `acf plan`、`acf task`、`acf edit`、`acf new worklog`、`acf knowledge draft`、`acf archive` 或 `acf writeback draft` 写入对应文件或草案。

最终回复只报告实际修改的文件、生成的草案、执行的检查和仍需人工判断的风险。没有变化的类别不需要输出“无需更新”。

---

## 14. 根目录其他文件

项目根目录可能存在模板、笔记、概念卡等其他文件。

使用规则：

1. 不要默认读取这些文件。
2. 只有当用户明确要求时，才读取对应文件。
3. 不要把这些文件中的内容自动视为项目事实。

---

## 15. CLI 辅助工具

如果项目可用 `acf` 命令，可以用它降低维护成本。未安装 `acf` 时，可按项目实际运行方式使用 `python acf.py ...` 作为兼容入口。

### 15.1 安装和可用性判断

`acf` 能在任意目录直接运行的前提是：命令已经安装到当前 shell 的 PATH 中。

常见安装方式：

- 从本框架源码目录开发安装：`uv tool install -e .`
- 安装后更新 shell PATH：`uv tool update-shell`
- 发布后按包名安装：`uv tool install ai-context-framework`
- 从 Git 地址安装：`uv tool install git+<repo-url>`

验证命令：

- Windows CMD：`where.exe acf`
- PowerShell：`Get-Command acf`
- macOS/Linux：`which acf`
- 通用：`acf --help`
- 查看版本：`acf --version`

请注意：能在任意目录运行 `acf`，不等于任意目录都有 AI 上下文。`acf status --json` 只有在当前目录位于某个包含 `docs/ai` 或上下文根目录的项目中时才会成功。否则应先进入项目目录、显式传入上下文路径，或运行 `acf init docs/ai` 初始化。

### 15.2 常用命令

- `acf status`：自动发现当前上下文，输出项目根、上下文目录、profile、当前任务状态和检查结果。
- `acf init <target>`：生成标准上下文模板，并在项目根目录生成缺失的薄入口 AGENTS.md。
- `acf init <target> --profile minimal`：生成简化模板，并在项目根目录生成缺失的薄入口 AGENTS.md。
- `acf init <target> --force-root-agent`：根入口已存在时重写薄入口；默认不会覆盖已有根入口。
- `acf simplify <source> <target>`：从已有上下文导出简化版本，并保留真实 ADR 与 daily worklog，排除占位模板文件。
- `acf upgrade [target]`：非破坏式补齐当前版本需要的 Feedback_Inbox、Task_Plan、archive、archive/feedback 和 Knowledge 结构；自定义旧文档无法识别时会追加 marker 包围的升级说明块。
- `acf plan init|add-task|set-task|focus|complete|status [target]`：维护当前大任务计划和子任务板，并在完成后标记计划 Done。
- `acf task start|done|block|clear [target]`：从任务板启动、完成、阻塞或清空当前小任务；`task start` 默认拒绝启动依赖未完成的子任务，除非传入 `--force`。
- `acf archive current-task|task-plan|list [target]`：归档旧当前任务或旧大任务计划，并维护归档索引。
- `acf knowledge draft|apply|list|show|mark [target]`：生成 Knowledge 草案、审阅后写入可复用经验索引，并维护状态；`apply` 默认拒绝疑似重复条目，可用 `--allow-similar` 显式覆盖。
- `acf workstream init|status|list|add [target]` / `acf workstream show|set|block|cancel|merge-request|ready|done|claim|note WS001 [target]`：显式启用可选 Workstream 层，读取并行目标线索引与详情 metadata，并维护基础状态转换、合并请求、完成证据、scope claim 和详情备注；`upgrade` 和旧项目默认不启用 Workstream。
- `acf new task [target] --title "..." --goal "..."`：生成或重置当前任务文件；如果现有任务是 Active，需传入 `--force` 才能覆盖。
- `acf new source [target] --title "..." --type "..." --location "..." --relation "..."`：添加或更新资料索引行；重复资料标题需传入 `--force` 才能覆盖。
- `acf new worklog [target] --summary "..."`：生成 daily worklog 并更新工作记录索引。
- `acf new adr [target] --title "..." --summary "..." --decision "..."`：生成 ADR 并更新决策索引。
- `acf writeback draft [target] --text "..."`：生成会话回写草案，供人工审阅后再决定是否写入权威上下文。
- `acf version show --json`：查看 CLI、包配置和锁文件中的版本号。
- `acf version set v0.0.3.14 --dry-run --json`：预览一键更新版本号；正式执行时同步 CLI 常量、包配置和本地元数据。
- `acf edit section get <file> --heading "## 标题"`：读取上下文根目录内某个 Markdown section 的正文。
- `acf edit section replace <file> --heading "## 标题" --text "..."`：替换指定 section 的正文。
- `acf edit section append <file> --heading "## 标题" --text "..."`：向指定 section 追加正文。
- `acf edit table upsert <file> --key-column "列名" --key "键值" --cell "列名=内容"`：按 key column 更新或追加表格行。
- `acf check [target]`：检查结构完整度、乱码、空文件、内部路径引用、状态枚举和索引一致性；Workstream 检查仅在存在 Workstreams 索引时启用。
- `acf check [target] --strict`：把占位符残留作为错误，适合正式项目上下文。
- `acf log enable [target]`：显式启用用户级全局使用状态日志；当前默认已启用，并按项目子目录隔离。
- `acf log disable [target]`：关闭该项目的用户级全局使用状态日志，不删除已有日志。
- `acf log status [target] --json`：查看日志启用状态、路径、事件数量和最近事件时间。
- `acf log tail [target] --limit 20 --json`：读取最近 usage event。
- `acf log summarize [target] --json`：统计命令次数、成功率、错误类型、dry-run 次数和 changed files 数量。
- `acf log summarize [target] --days 7 --errors-only --json`：按时间窗口和失败状态筛选统计。
- `acf log prune [target] --days 30`：删除旧 usage event。

`target` 省略时，CLI 会从当前目录向上查找 `docs/ai` 或上下文根目录；显式传入 `target` 时，以显式路径为准。CLI 的检查结果不能替代人工判断，但可以自动发现维护成本高、容易遗忘的结构性问题。

### 15.3 旧版本上下文升级

旧项目升级到当前模板结构时，推荐流程：

1. `acf status --json`：确认当前目录能发现目标上下文。
2. `acf upgrade --dry-run --json`：预览将补齐的文件和目录。
3. 审阅 `detected_features`、`planned_changes`、`skipped_changes` 和 `changed_files`。
4. `acf upgrade --check-after --json`：正式补齐结构并检查。
5. `acf check --strict --json`：在正式项目中确认占位符和结构问题。

`upgrade` 是非破坏式命令，只补齐当前 schema 缺失的 `active/Task_Plan.md`、archive、archive/feedback 和 Knowledge 文件/目录；它不移动旧内容、不自动归档任务、不覆盖 Active `active/Current_Task.md`。`--json` 输出包含 `detected_features`、`planned_changes`、`skipped_changes` 和 `changed_files`，用于审查升级原因、预期写入和已跳过项。对高度自定义的旧入口文档，`upgrade` 会追加 `ACF:UPGRADE-NOTES` marker 块而不是强行重排原文。

维护本框架时，如果修改 `template/`、默认上下文结构、打包清单或 `acf upgrade` 行为，必须同时评估旧版本上下文的升级路径。新增结构应同步到 init 文件清单、upgrade 补齐清单、`pyproject.toml` data-files、文档和 init/upgrade 单元测试；入口或手册变更不能安全重排旧文档时，应通过 marker notes 非破坏式提示。

如果旧任务或旧计划需要归档，升级后再显式运行：

- `acf archive current-task --reason "..."`
- `acf archive task-plan --reason "..."`

如果全局 `acf` 未安装，可以从本框架源码环境运行：

```bash
uv run --project <ai-context-framework 路径> acf upgrade --dry-run --json
```

面向 AI 的稳定调用建议：

- `acf status --json`：获取机器可读的上下文位置、profile、当前任务状态和检查结果。
- `acf check --json --strict`：获取机器可读的检查结果。
- `acf workstream status|list|show --json`：获取机器可读的 Workstream 初始化状态、索引行和详情 metadata。
- `acf edit section get ... --json`：获取机器可读的 section 正文和行号信息。
- 写命令可追加 `--dry-run --json`：只预览 changed files，不实际落盘。
- 写命令可追加 `--check-after`：落盘后自动运行 context check。

JSON 输出包含稳定字段：`schema_version`、`ok`、`error_code`、`next_actions`。当检查失败时，`error_code` 为 `check_failed`，`next_actions` 给出后续处理建议。

`edit` 命令只操作上下文根目录内已有的 `.md` 文件，拒绝路径穿越和非 Markdown 目标。它只提供 section/table 级确定性编辑，不做事实判断，也不是通用 Markdown 编辑器。

PowerShell 中反引号是转义字符。写入包含 Markdown 反引号或多行正文时，优先使用 `--input <file>`，避免 shell 改写正文。

`log` 命令默认开启，写入用户级全局目录：Windows 为 `%USERPROFILE%\.acf\projects\<project-id>\`，macOS/Linux 为 `~/.acf/projects/<project-id>/`；也可通过 `ACF_HOME` 指定根目录。它只记录命令形态、结果、错误分类、耗时、dry-run 状态和 changed files 等元数据，不记录 `--text` 正文、stdin 内容、Markdown diff、模型对话或完整 stdout/stderr。usage event log 是评测和排障资料，不是权威上下文，也不应直接写入 `worklog/`。日志写入带用户级锁，配置和 prune 重写使用原子替换；如需关闭某项目日志，运行 `acf log disable [target]`。

退出码约定：

- `0`：成功。
- `1`：检查失败，`error_code=check_failed`。
- `2`：输入错误，`error_code=input_error`。
- `3`：安全拒绝，例如重复写入或需要 `--force`，`error_code=safety_refused`。
- `70`：非预期运行时错误，`error_code=runtime_error`。
