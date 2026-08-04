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
- `active/Task_Plan.md`：当前大任务计划和轻量子任务板，记录子任务、规划依据、可选任务阶段、证据和下一步。
- `active/Current_Task.md`：当前具体任务说明，仅在任务状态为 Active 时作为当前任务事实源；`当前执行线` 只记录正在执行的 Workstream，不记录历史依赖。
- Workstreams 索引：可选并行目标线索引，仅在显式启用 Workstream 层且存在 Active、Blocked、ReadyToMerge 或 Merging workstream 时按需读取。

使用规则：

1. 默认优先读取 `active/Context.md`。
2. 有 Open 条目或需要整理人工反馈时读取 `active/Feedback_Inbox.md`。
3. 默认读取 `active/Task_Plan.md`，但该文件必须保持轻量；如果 `## 规划依据` 列出 reference 设计、路线或差距文档，应按任务需要读取这些依据。
4. 如果 `active/Current_Task.md` 状态为 Active，则读取它；`## 输入材料` 必须列出当前任务所需 active 文件和相关 reference 规划依据。
5. 如果存在 Active、Blocked、ReadyToMerge 或 Merging workstream，或当前任务需要整理并行协作，则读取 Workstreams 索引，再运行 `acf workstream context WSxxx` 读取对应详情文件和边界。
6. 如果用户当前消息提出了新的任务，并且与 `active/Current_Task.md` 冲突，以用户当前消息为准。
7. `active/` 中的信息应保持短、准、当前有效。
8. 不要把历史过程、旧方案、原始日志写入 `active/`。
9. 写入 `active/` 前先判断唯一权威位置；能更新旧表述时，不追加重复事实。

### 1.1 Context 审阅标记

`active/Context.md` 推荐保留文件级或 section 级审阅标记，用于 `acf review stale` 机械判断默认事实入口是否可能过期。

最小格式：

```markdown
## 审阅标记

- Last reviewed: YYYY-MM-DD
- Review scope: 文件级；确认当前目标、当前事实、约束和开放问题仍适合作为默认注意力入口。
```

也可以使用中文标签：

```markdown
- 上次审阅：YYYY-MM-DD
```

该标记只表示“已审阅过默认注意力入口”，不表示每条事实都已逐条重新验证；不要求为每条事实添加 ID 或 reviewed 字段。

### 1.2 Feedback_Inbox 生命周期

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

### 1.3 human/ 人工异步笔记层

标准模板包含 `human/`，用于保存人类给 AI 上下文系统留下的理解、规划、疑问、解释、整理、随笔、复盘和汇报材料。

使用规则：

1. `human/Human_Index.md` 是 human 层可发现索引，记录材料状态、路径和已整理去向。
2. `human/Human_Notes.md` 是人工随笔入口，不放入 `active/`，默认不读取；`acf new human-note` 会同步更新 `Human_Index.md`。
3. `human/weekly/` 保存周记录，`human/reports/` 保存复盘、解释、整理和汇报材料；这些文件只有在用户要求整理、追溯或生成汇报时按需读取。
4. `human/` 中的内容是未整理信号或面向人的材料，不是已确认当前事实；需要进入 AI 当前事实时，应整理到 `active/Context.md`、`active/Task_Plan.md`、`active/Current_Task.md`、ADR、Knowledge、reference 或 worklog 的权威位置。
5. 可以把项目 `docs/` 作为 Obsidian vault 根目录，用 `[[双链]]` 方便人工查看和导航。ACF 不解析、不校验、不依赖 Obsidian 双链；AI 和 CLI 仍以普通 Markdown 路径引用作为结构化依据。
6. `active/Feedback_Inbox.md` 仍用于待处理反馈和需求碎片；`human/` 用于更自由的人工记录、周报和汇报材料，二者不自动合并。

### 1.4 Markdown 链接与人工导航

ACF 的结构化引用优先使用普通 Markdown 链接，例如 `[reference/System_Manual.md](../reference/System_Manual.md)`；这类链接可被 Obsidian、GitHub 和常规 Markdown 工具识别。`[[双链]]` 可以作为人工导航补充，但不作为 ACF 机器校验或 AI 读取增强的依据。

使用规则：

1. 文档中引用上下文内其他文件时，优先使用相对 Markdown 链接，链接目标按当前文件所在目录计算。
2. 需要链接到标题时使用 `path.md#heading-anchor`；`acf check` 会校验本地 Markdown 链接目标是否存在，并校验 `.md#anchor` 是否能匹配目标文件标题。
3. `acf linkify [target] --format markdown` 可把安全识别到的本地路径引用转换为 Markdown 链接；默认只处理 active、reference、rules、decisions、Worklog_Index 和 Archive_Index，不修改 archive 详情或 daily worklog。
4. `acf archive current-task|task-plan` 归档移动当前任务或计划时，会按归档文件的新位置重写已有本地 Markdown 相对链接；URL、URI、缺失目标和代码块内链接保持原样。
4. `acf link add [target] <file> --heading "## 输入材料" --target reference/X.md` 可向指定小节追加一个确定性链接 bullet；它不做语义判断、不自动猜 section、不批量替换。
5. `http://`、`https://` 和其他 URI scheme 不做本地存在性校验；本地图片链接 `![alt](path)` 会按文件存在性校验。

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
| 需要整理、归纳、精简上下文 | `reference/Context_Curation_Prompt.md` |

不要默认读取所有 reference 文件。

如果需要资料详情，请先查看 `Sources_Index.md`，再读取 `reference/sources/` 下对应的资料笔记。

`Context_Curation_Prompt.md` 是按需读取的 AI 整理提示词模板。它用于帮助 AI 归纳、精简、去重并提出上下文整理建议；默认产物是整理建议，不是文件修改。除非用户明确要求落盘，否则不要根据该 prompt 自动修改上下文文件。

---

## 5. reference/ 文件含义

- **Project_Brief.md**：项目长期背景、目标、愿景、边界和非目标。不记录当前阶段目标。
- **Decisions_Index.md**：重要决策索引，只记录摘要和 ADR 路径。
- **Knowledge_Index.md**：可复用经验索引，只记录从历史材料中提炼出的模式、反例和判断方法。
- **Context_Curation_Prompt.md**：上下文整理提示词模板，仅在需要整理、归纳、精简上下文时按需读取；不进入默认读取路径。
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

注意力治理规则：

1. 默认上下文只保留当前目标、当前事实、当前任务和下一步。
2. 当前仍成立的信息写入或替换 `active/` 中的权威位置。
3. 已发生但不一定长期成立的信息写入 worklog。
4. 需要人确认的信息写入 `active/Feedback_Inbox.md` 或 writeback draft。
5. 已被替代的信息应标记失效、归档或从 active 删除。
6. 低优先级文件不得复制高优先级文件的完整事实；能引用权威位置时，不复制原文。

上下文预算规则：

1. 整理事实时优先读取 changed files、`active/`、相关索引和最近 worklog。
2. 不为 curation 默认读取 archive 或全部历史日志。
3. curation draft 不进入默认读取路径。
4. 若只处理当前任务，不读取历史日志。

Workstream-first when active：存在 Active / Blocked / ReadyToMerge / Merging Workstream 时，agent 入口优先使用 Workstreams 索引和 `acf workstream context WSxxx`。`reference/ 是中间材料层`，Knowledge 高可信但不默认全量读取。

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

- 稳定安装当前源码快照（在仓库根目录执行）：`uv tool install .`
- 调试 CLI 改动或安装链路时使用 editable 安装：`uv tool install -e .`
- 安装后更新 shell PATH：`uv tool update-shell`
- 已安装旧快照时覆盖重装（在仓库根目录执行）：`uv tool install --reinstall .`
- 发布后按包名安装：`uv tool install ai-context-framework`
- 从 Git 地址安装：`uv tool install git+<repo-url>`

验证命令：

- Windows CMD：`where.exe acf`
- PowerShell：`Get-Command acf`
- macOS/Linux：`which acf`
- 通用：`acf --help`
- 查看版本：`acf --version`

请注意：能在任意目录运行 `acf`，不等于任意目录都有 AI 上下文。`acf status --json` 只有在当前目录位于某个包含 `docs/ai`、`docs-acf/ai` 或上下文根目录的项目中时才会成功。否则应先进入项目目录、显式传入上下文路径，或运行 `acf init docs/ai` 初始化。

### 15.2 常用命令

- `acf status`：自动发现当前上下文，输出项目根、上下文目录、profile、当前任务状态和检查结果。
- `acf init <target>`：生成标准上下文模板，并在项目根目录生成缺失的薄入口 AGENTS.md。
- `acf init <target> --profile minimal`：生成简化模板，并在项目根目录生成缺失的薄入口 AGENTS.md。
- `acf init <target> --force-root-agent`：根入口已存在时重写薄入口；默认不会覆盖已有根入口。
- `acf simplify <source> <target>`：从已有上下文导出简化版本，并保留真实 ADR 与 daily worklog，排除占位模板文件。
- `acf upgrade [target]`：非破坏式补齐当前版本需要的 Feedback_Inbox、Task_Plan、标准 profile 的 human 层（含 `Human_Index.md`）、archive、archive/feedback、Knowledge 结构和 active -> reference 规划依据追溯入口；自定义旧文档无法识别时会追加 marker 包围的升级说明块。
- `acf plan init|add-task|set-task|focus|complete|status [target]` / `acf plan reference list|add|remove [target]` / `acf plan stage list|add|set|done [target]`：维护当前大任务计划、子任务板、`## 规划依据` 和 `## 任务阶段` 表，并在完成后标记计划 Done；`plan reference add --path reference/X.md --purpose "用途"` 只写 reference 路径和一句话用途，默认要求目标文件存在，可用 `--allow-missing` 显式允许缺失，用 `--force` 更新同一路径，用 `--sync-current-task` 显式同步到 Active `active/Current_Task.md`；Task Stage CLI 只维护 `active/Task_Plan.md` 中的阶段表，要求 `T001.1` 这类阶段 ID 归属于已存在父任务，不创建 task object 单文件，不自动修改 `active/Current_Task.md`，也不自动联动 Workstream。
- `acf linkify [target] --format markdown --dry-run --json`：把默认范围内安全识别到的本地路径引用转换为可点击 Markdown 链接；默认跳过 archive 详情和 daily worklog，可用 `--include-archive` / `--include-worklog-daily` 显式扩大范围，缺失目标默认跳过并报告，可用 `--allow-missing` 显式允许。
- `acf link add [target] <file> --heading "## 输入材料" --target reference/X.md --json`：向上下文内指定 Markdown 文件的小节追加链接 bullet；`--target-heading` 会生成并校验 Markdown heading anchor，重复链接默认拒绝，`--force` 才允许重复。
- `acf task start|done|block|clear [target]`：从任务板启动、完成、阻塞或清空当前小任务；`task start` 默认拒绝启动依赖未完成的子任务，除非传入 `--force`。
- `acf archive current-task|task-plan|list|sync [target]`：归档旧当前任务或旧大任务计划，并维护归档索引；归档 current task / task plan 时会按归档文件的新位置重写本地 Markdown 相对链接，并追加 `ACF:ARCHIVE:RECORD` marker；`sync` 从 `archive/tasks`、`archive/plans` 和 `archive/workstreams` 重算 `ACF:ARCHIVE:INDEX-GENERATED` marker block，优先使用归档 record marker 恢复 Task/Plan 归档原因，旧索引首次接入时需显式 `--init-marker`。
- `acf decisions sync [target]`：从 `decisions/ADR-*.md` 重算 `reference/Decisions_Index.md` 的 `ACF:DECISIONS:INDEX-GENERATED` marker block；旧索引首次接入时需显式 `--init-marker`，命令只替换 marker 内内容，不修改 ADR 正文。
- `acf knowledge draft|apply|list|show|mark|sync [target]`：生成 Knowledge 草案、审阅后写入可复用经验索引，并维护状态；`sync` 从 `reference/knowledge/K*.md` 重算 `reference/Knowledge_Index.md` 的 `ACF:KNOWLEDGE:INDEX-GENERATED` marker block，旧索引首次接入时需显式 `--init-marker`；`apply` 默认拒绝疑似重复条目，可用 `--allow-similar` 显式覆盖。
- `acf feedback list|triage|done|reject|archive-candidates|archive [target]`：维护 `active/Feedback_Inbox.md` 的确定性生命周期；`triage/done/reject` 只更新状态和处理结果，不自动转写 Context、Task、ADR 或 Knowledge；`archive-candidates` 只读列出 Done/Rejected 候选，`archive` 只显式移动单条反馈到 archive/feedback/YYYY-MM dot md。
- `acf human index sync|list|mark [target]`：维护 `human/Human_Index.md`；`index sync` 扫描 `Human_Notes.md`、`human/weekly/*.md` 和 `human/reports/*.md` 并补齐缺失索引行，不删除旧行、不覆盖人工状态；`list` 按状态或类型查看 human 材料；`mark` 按 ID 或路径更新处理状态和整理去向。
- `acf review stale [target]`：只读检查默认注意力入口是否可能过期，报告 stale candidates，不判断内容真假、不写文件；支持 `--json`、`--days` 和 `--today`。
- `acf audit context [target]`：只读检查 active 层上下文污染候选，不判断事实真假、不写文件、不生成 patch、不接入 `check --strict`；MVP 只报告长 active section、陈旧当前任务 / Workstream 阶段和 ReadyToMerge 待合并或 Done 缺合并结果候选；支持 `--json`。
- `acf curate draft [target]`：复用 `review stale` 的 stale candidates 生成 curation-drafts 目录下的日期命名注意力治理草案；空信号时不创建草案，同名草案已存在时安全拒绝；支持 `--json`、`--dry-run`、`--days`、`--today` 和 `--name`。
- `acf doctor [target]`：跨文件诊断上下文状态漂移、generated index 漂移、Workstream 生命周期、数据证据和注意力治理信号；默认只读，`--fix safe` 只应用确定性机械修复，`--fix evidence` 只规划 evidence 修复且不改写语义权威文件，`--report` 生成 doctor report，`--draft-semantic` 生成可审阅语义回写草案；支持 `--json`、`--strict`、`--check-after`、`--today`、`--projects`、`--dry-run` 和 `--force`。
- `acf workstream init|status|list|dashboard|archive-candidates|archive-draft|sync|add|reserve [target]` / `acf workstream archive WS001 [target] --reason "..."` / `acf workstream show|context|set|block|cancel|merge-request|merge-start|ready|done|claim|scope-add|guard|note WS001 [target]` / `acf workstream stage add|list|done WS001 [target]` / `acf workstream focus WS001 WS001.1 [target]`：显式启用可选 Workstream 层，读取并行目标线索引与详情 metadata，并维护强隔离状态转换、合并请求、完成证据、scope claim/扩权、详情备注、内部阶段焦点和显式归档；`reserve` 只在 primary branch 预约并提交唯一编号，不创建 branch/worktree；原 `add` 行为不变；`context` 输出 AI 专属任务入口，`guard` 检查变更文件是否符合当前 Workstream 写入边界，完成或切换状态前优先用 `--files` 显式传入本次修改文件做强验收；`scope-add` 以工具化方式扩展 scope 并写入 Activity Log，`dashboard` 显示冲突、陈旧任务、缺 evidence 和待合并目标；Workstream 类型为 Task / Merge / Maintenance，Task 不直接写 authority 文件，Active 类 Workstream 默认禁止重叠 `owned:` 写入，`shared:` 必须指定 merge_owner 或 serial coordination；`archive-candidates` 只读报告 Done / Cancelled Workstream 的归档候选和 `blocked_by`；`archive-draft` 写入 `worklog/archive-drafts/` 供人工或 AI 审阅；`archive` 只在显式指定单个终态 Workstream 和 `--reason` 时移动详情、清理 active 索引并写入 `archive/Archive_Index.md`；`sync` 只根据 Workstream 详情 front matter 更新 Workstreams 索引，不会删除缺详情的旧索引行；Workstream 详情可用 optional `current_stage` 和 `## 阶段` 表记录内部阶段焦点，`stage add/list` 只维护详情文件，`focus` 不更新全局 Current_Task，`stage done` 要求 evidence 且完成当前阶段时需要 `--clear-current`；`merge_targets` 记录候选合并目标，ReadyToMerge 表示任务产物完成，`ready` 需要人工确认参数 `--human-approved`，Merging 表示 Merge/Maintenance 正在合并，Done 需要 `--merge-resolution` 写入合并或处置结果；`add --goal` 可在创建时写入详情目标，`set --goal` 可替换已有详情目标，`--write-scope` 必须使用 `TYPE: PATH` 格式，例如 owned: src/foo.py；`upgrade` 和旧项目默认不启用 Workstream。

### 可选 Git Worktree 生命周期

创建 Workstream 不会隐式创建 worktree。任务需要长期、并行或独立合并环境时，AI 可单独调用：

```powershell
acf worktree create --workstream WS001 --apply --json
```

非 WS 任务使用 `--kind bugfix|docs|experiment|investigation|maintenance|refactor|release --slug ...`。`worktree list|audit|verify|attach|sync|merge-plan|merge|close|resume` 提供发现、恢复、同步、无冲突 no-ff 合并和安全关闭；写操作默认 plan-only，`--apply` 后执行。项目可在 `.acf/project.toml` 配置 primary checkout/branch、worktree root 和命名模板；不配置或不调用 worktree 时，原上下文与 Workstream 命令不受影响。ACF 不自动 stash、reset、clean、rebase、force、push、覆盖目录或解决冲突。

### Workstream guard 模式

`acf workstream guard` 检查的是“变更文件是否符合当前 Workstream 的写入范围”，不是默认独占整个工作区。多个 agent 或多个 Workstream 在同一仓库并行时，完成、ready、done 或切换状态前，优先显式传入本次要验收的文件集：

```bash
acf workstream guard WS001 --files src/foo.py docs/ai/active/workstreams/WS001.md --json
```

| 场景 | 推荐命令 | 语义 |
|---|---|---|
| 本次变更文件明确 | `acf workstream guard WS001 --files path1 path2 --json` | 权威文件集强验收；失败表示这些文件越过当前 Workstream scope。 |
| 单个文件验收 | `acf workstream guard WS001 --file path --json` | `--files` 的单文件形式，可重复传入。 |
| 快速查看当前 git diff | `acf workstream guard WS001 --from-git --json` 或裸 `guard` | 读取 git diff；若存在其他 Workstream 或未归属 dirty files，结果不能直接作为完成证据。 |
| 旧式整工作区排他检查 | `acf workstream guard WS001 --workspace --strict-workspace --json` | 要求整个工作区没有无关改动；只适合单线或需要强制清空工作区的场景。 |
| 禁止 shared 写入 | `acf workstream guard WS001 --files path --owned-only --json` | shared scope 也会失败，用于严格 ownership 验收。 |

只有显式文件集模式可作为完成或切换状态的强验收证据；裸 guard 和 `--from-git` 适合发现当前工作区风险，不应在存在并行 dirty files 时替代 `--files`。
- `acf new task [target] --title "..." --goal "..."`：生成或重置当前任务文件；如果现有任务是 Active，需传入 `--force` 才能覆盖。
- `acf new source [target] --title "..." --type "..." --location "..." --relation "..."`：添加或更新资料索引行；重复资料标题需传入 `--force` 才能覆盖。
- `acf new reference [target] --title "..." --summary "..."`：在 `reference/` 下创建长期按需读取的 Markdown 文档；可用 `--file reference/X.md` 指定文件，拒绝写到 context 外或 `reference/knowledge/` 托管目录。
- `acf new rule [target] --title "..." --condition "..." --purpose "..." --rule "..."`：在 `rules/` 下创建按需规则文件，并更新 `rules/Rules_Index.md`；minimal context 首次使用时会补 Rules_Index，但不要求补齐 standard profile 规则文件。
- `acf new feedback [target] --type "..." --content "..."`：向 `active/Feedback_Inbox.md` 添加反馈行，自动分配下一个 `Fxxx`，默认 Open，重复 ID 需 `--force`。
- `acf new human-note [target] --type "..." --content "..."`：向标准 profile 的 `human/Human_Notes.md` Inbox 添加人工异步笔记行，自动分配下一个 `Hxxx`，并同步更新 `human/Human_Index.md`；minimal context 没有 human 层时会拒绝，建议使用 `new feedback` 或先升级为 standard。
- `acf new worklog [target] --summary "..."`：生成 daily worklog 并更新工作记录索引；同日已有记录且需要补记时使用 `--append`，需要重建时使用 `--force`，二者不能混用。
- `acf new adr [target] --title "..." --summary "..." --decision "..."`：生成 ADR 并更新决策索引。
- `acf writeback draft [target] --text "..."`：生成注意力治理式会话回写草案，供人工审阅后再决定是否写入权威上下文。
- `acf version show --json`：查看 CLI、包配置和锁文件中的版本号。
- `acf version set vX.Y.Z --dry-run --json`：预览一键更新版本号；正式执行时同步 CLI 常量、包配置和本地元数据。
- `acf edit section get <file> --heading "## 标题"`：读取上下文根目录内某个 Markdown section 的正文。
- `acf edit section replace <file> --heading "## 标题" --text "..."`：替换指定 section 的正文。
- `acf edit section append <file> --heading "## 标题" --text "..."`：向指定 section 追加正文。
- `acf edit table upsert <file> --key-column "列名" --key "键值" --cell "列名=内容"`：按 key column 更新或追加表格行。
- `acf check [target]`：检查结构完整度、乱码、空文件、内部路径引用、状态枚举、任务阶段注册和索引一致性；Workstream 检查仅在存在 Workstreams 索引时启用，并包含 optional `current_stage` 与 `## 阶段` 表一致性、strict 下 Done 阶段 evidence、Workstreams 索引与详情 front matter 一致性、Task authority 写入门禁、Active 类 Workstream 写入冲突、`shared:` merge owner/serial coordination 要求和 `merge_targets` 合并请求要求。
- `acf check [target] --strict`：把占位符残留作为错误，适合正式项目上下文。
- `acf log enable [target]`：显式启用用户级全局使用状态日志；当前默认已启用，并按项目子目录隔离。
- `acf log disable [target]`：关闭该项目的用户级全局使用状态日志，不删除已有日志。
- `acf log status [target] --json`：查看日志启用状态、路径、事件数量和最近事件时间。
- `acf log tail [target] --limit 20 --json`：读取最近 usage event。
- `acf log summarize [target] --json`：统计命令次数、成功率、错误类型、dry-run 次数和 changed files 数量。
- `acf log summarize [target] --days 7 --errors-only --json`：按时间窗口和失败状态筛选统计。
- `acf log projects --scan-root <path> --json`：只读汇总全局 usage log 项目，并尝试把日志 project id 映射到磁盘上的真实 context root；`--log-root` 可读取测试或备份日志目录，`--min-events` 和 `--include-unresolved` 用于过滤展示。
- `acf log feedback [target] --text "..." --type Problem --source manual --json`：显式记录实际使用反馈正文，写入用户级 usage log；普通命令不会自动记录正文。
- `acf log prune [target] --days 30`：删除旧 usage event。

`target` 省略时，CLI 会从当前目录向上查找 `docs/ai`、`docs-acf/ai` 或上下文根目录；显式传入 `target` 时，以显式路径为准。CLI 的检查结果不能替代人工判断，但可以自动发现维护成本高、容易遗忘的结构性问题。

### 15.3 旧版本上下文升级

旧项目升级到当前模板结构时，推荐流程：

1. `acf status --json`：确认当前目录能发现目标上下文。
2. `acf upgrade --plan --json`：只读生成升级评估，区分结构补齐、语义债务和 Workstream 债务。
3. `acf upgrade --dry-run --json`：预览将补齐的文件和目录。
4. 审阅 `detected_features`、`planned_changes`、`skipped_changes` 和 `changed_files`。
5. `acf upgrade --check-after --json`：正式补齐结构并检查。
6. `acf check --strict --json`：在正式项目中确认占位符和结构问题。

`upgrade --plan --json` 不写项目文件、不写 usage log、不获取写锁；JSON 输出包含 `readiness`、`risk_summary`、`findings`、`structural_changes`、`manual_actions` 和 `recommended_commands`。`upgrade` 是非破坏式命令，只补齐当前 schema 缺失的 `active/Task_Plan.md`、标准 profile 的 human 层（含 `human/Human_Index.md`）、archive、archive/feedback 和 Knowledge 文件/目录，并为旧 `active/Task_Plan.md` 补 `## 规划依据` 结构、为 Active `active/Current_Task.md` 的 `## 输入材料` 保守追加规划依据提示；它不移动旧内容、不自动归档任务、不覆盖 Active `active/Current_Task.md`，也不自动判断哪些 reference 是正确依据。`--json` 输出包含 `detected_features`、`planned_changes`、`skipped_changes` 和 `changed_files`，用于审查升级原因、预期写入和已跳过项。对高度自定义的旧入口文档，`upgrade` 会追加 `ACF:UPGRADE:NOTES` marker 块而不是强行重排原文；旧 `ACF:UPGRADE-NOTES` marker 会被兼容识别并在可管理文档中迁移。

维护本框架时，如果修改 `template/`、默认上下文结构、打包清单或 `acf upgrade` 行为，必须同时评估旧版本上下文的升级路径。新增结构应同步到 init 文件清单、upgrade 补齐清单、`pyproject.toml` data-files、文档、init/upgrade 单元测试和 upgrade compatibility runner；入口或手册变更不能安全重排旧文档时，应通过 marker notes 非破坏式提示。ACF 维护块统一使用 `<!-- ACF:<DOMAIN>:<PURPOSE>:START -->` 与对应 `END` marker，例如 `ACF:UPGRADE:NOTES`、`ACF:ARCHIVE:RECORD`、`ACF:WORKSTREAM:ARCHIVE-RECORD`、`ACF:KNOWLEDGE:INDEX-GENERATED`、`ACF:DECISIONS:INDEX-GENERATED` 和 `ACF:ARCHIVE:INDEX-GENERATED`；旧 marker 保持兼容，但 `check` 会给出 future warning。

模板占位符统一使用 `【ACF:KEY|提示】`，便于代码快速匹配和替换。Markdown 表格单元格内如需占位符，应使用无提示形式 `【ACF:KEY】`，避免 `|` 破坏表格。`acf check template` 会对旧式中文括号占位符给出 warning；正式项目 strict 下仍只把残留占位符视为项目内容问题，不额外要求格式迁移。

如果旧任务或旧计划需要归档，升级后再显式运行：

- `acf archive current-task --reason "..."`
- `acf archive task-plan --reason "..."`

如果全局 `acf` 未安装，可以从本框架源码环境运行：

```bash
uv run --project <ai-context-framework 路径> acf upgrade --plan --json
uv run --project <ai-context-framework 路径> acf upgrade --dry-run --json
```

面向 AI 的稳定调用建议：

- `acf status --json`：获取机器可读的上下文位置、profile、当前任务状态和检查结果。
- `acf check --json --strict`：获取机器可读的检查结果。
- `acf workstream status|list|show|context|dashboard --json` 和 `acf workstream guard WS001 --files <本次修改文件...> --json`：获取机器可读的 Workstream 初始化状态、索引行、详情 metadata、执行上下文入口、并行安全仪表盘和文件集写入边界检查结果。
- `acf review stale --json`：获取机器可读的 stale candidates；这些候选只表示默认注意力入口可能过期，不代表事实真假。JSON 顶层包含 `summary.total`、`summary.by_kind` 和 `summary.by_path`；每个候选包含 `kind`、`signal`、`path`、`reason`、`age_days`、`status` 和 `suggested_action`；`next_actions` 会在 clean 状态或按 stale `kind` 给出机械下一步建议。
- `acf audit context --json`：获取机器可读的 context audit candidates；这些候选只表示上下文可能需要治理，不代表事实真假。JSON 顶层包含 `candidates`、`summary.total`、`summary.by_kind`、`summary.by_path`、`summary.by_severity` 和 `next_actions`；每个候选包含 `kind`、`severity`、`path`、`section`、`reason` 和 `suggested_action`。
- `acf curate draft --json`：把 `review stale` 的机器信号转换成可审阅治理草案；JSON 输出包含 `draft_path`、`created`、`stale_summary`、`stale_items`、`changed_files` 和 `next_actions`。该命令不读取 archive、不裁决语义、不修改权威上下文；无 stale candidate 时不创建空草案。
- `acf doctor --json`：获取机器可读的跨文件健康诊断；JSON 顶层包含 `summary`、`findings`、`check`、`changed_files`、`error_code` 和 `next_actions`。`summary.planned_repairs` 表示计划的 repair 动作数量，`summary.applied_repairs` 表示实际落盘的 repair 动作数量，`summary.changed_repair_files` 表示 repair 涉及的去重文件数；check 失败时先修复 `check.errors`。
- `acf edit section get ... --json`：获取机器可读的 section 正文和行号信息。
- 写命令可追加 `--dry-run --json`：只预览 changed files，不实际落盘。
- 写命令可追加 `--check-after`：落盘后自动运行 context check。

AI 调用 `new worklog` 的推荐模式：

| 目标状态 | 推荐命令 | 结果 |
|---|---|---|
| 不确定是否已有今日 worklog | `acf new worklog --summary "..." --dry-run --json` | 根据 `error_code` 判断下一步 |
| 今日 worklog 不存在 | `acf new worklog --summary "..." --json` | 创建 |
| 今日 worklog 已存在，想补记 | `acf new worklog --summary "..." --append --json` | 追加到稳定 anchor |
| 今日 worklog 已存在，想重建 | `acf new worklog --summary "..." --force --json` | 替换 |
| anchor 缺失 | 不自动修复 | 返回 `ANCHOR_NOT_FOUND` |

`new worklog --append` 的 JSON 面向 AI 稳定解析：`target` 和 `changed_files` 使用 repo-relative POSIX slash 路径；成功输出包含结构化 `warnings` 数组；`insert_after_line` 是 1-based 行号；`--dry-run --json` 不写文件；append 不是幂等操作，每运行一次都会新增一段内容。目标已存在但未传 `--append` 或 `--force` 时，`error_code=TARGET_EXISTS_APPEND_REQUIRED`；`--append --force` 返回 `APPEND_FORCE_CONFLICT`；anchor 缺失返回 `ANCHOR_NOT_FOUND`。

JSON 输出包含稳定字段：`schema_version`、`ok`、`error_code`、`next_actions`。当检查失败时，`error_code` 为 `check_failed`，`next_actions` 给出后续处理建议。

`edit` 命令只操作上下文根目录内已有的 `.md` 文件，拒绝路径穿越和非 Markdown 目标。它只提供 section/table 级确定性编辑，不做事实判断，也不是通用 Markdown 编辑器。

PowerShell 中反引号是转义字符。写入包含 Markdown 反引号或多行正文时，优先使用 `--input <file>`，避免 shell 改写正文。

`log` 命令默认开启，写入用户级全局目录：Windows 为 `%USERPROFILE%\.acf\projects\<project-id>\`，macOS/Linux 为 `~/.acf/projects/<project-id>/`；也可通过 `ACF_HOME` 指定根目录。自动 usage event 只记录命令形态、结果、错误分类、耗时、dry-run 状态、changed files、项目根和上下文根等元数据，不记录 `--text` 正文、stdin 内容、Markdown diff、模型对话或完整 stdout/stderr。需要保存实际使用反馈时，显式运行 `acf log feedback --text ...` 或 `--input <file>`，该命令会把反馈正文作为 `event_kind=feedback` 事件写入同一日志。usage event log 是评测和排障资料，不是权威上下文，也不应直接写入 `worklog/`。日志写入带用户级锁，配置和 prune 重写使用原子替换；如需关闭某项目日志，运行 `acf log disable [target]`。

退出码约定：

- `0`：成功。
- `1`：检查失败，`error_code=check_failed`。
- `2`：输入错误，`error_code=input_error`。
- `3`：安全拒绝，例如重复写入或需要 `--force`，`error_code=safety_refused`。
- `70`：非预期运行时错误，`error_code=runtime_error`。
