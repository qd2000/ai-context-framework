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
- Workstreams 索引：全局并行目标线摘要。默认只读索引行，不读取任何 Workstream 详情；只有显式选择后才进入单一 WS。

使用规则：

1. 默认优先读取 `active/Context.md`。
2. 有 Open 条目或需要整理人工反馈时读取 `active/Feedback_Inbox.md`。
3. 默认读取 `active/Task_Plan.md`，但该文件必须保持轻量；如果 `## 规划依据` 列出 reference 设计、路线或差距文档，应按任务需要读取这些依据。
4. 如果 `active/Current_Task.md` 状态为 Active，则读取它；`## 输入材料` 必须列出当前任务所需 active 文件和相关 reference 规划依据。
5. Workstream 层存在时只读取 Workstreams 摘要。未显式选择 WS 时到此停止；用户或执行合同明确指定后，先运行 `acf status --workstream WSxxx` 获取 pointer-only 入口，再运行 `acf workstream context WSxxx` 读取对应详情和边界。
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

Global-first progressive disclosure：没有明确选择时，无论存在多少 Active / Blocked / ReadyToMerge / Merging Workstream，`acf status|next` 都保持 `GlobalOnly`，只披露全局文件指针和索引摘要；attention 只用于 dashboard 管理。显式 `--workstream`、Active Current_Task 唯一绑定或 verified worktree 可以选择单一 WS，但状态结果仍只给 pointer-only 入口，必须再调用 `acf workstream context WSxxx` 才披露专属 detail/read_scope。选择来源冲突或指向不存在、非活动 WS 时分别返回 `SelectionConflict` / `SelectionInvalid`，保持全局并 fail-closed。`reference/` 是中间材料层，Knowledge 高可信但不默认全量读取。

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

- 正式发布版本安装：Windows 已取得仓库/发布包脚本时优先 `pwsh -NoLogo -NoProfile -File scripts/install_acf.ps1`；macOS/Linux 使用 `uv tool install ai-context-framework`
- 正式发布版本更新：Windows 自动化/并行环境优先运行 `pwsh -NoLogo -NoProfile -File scripts/update_acf.ps1`；确认没有并发 ACF 进程的普通交互式环境也可使用 `uv tool upgrade ai-context-framework`
- 安装或更新后刷新 shell PATH：`uv tool update-shell`
- 仓库维护者安装当前源码快照：`uv tool install .`
- 调试 CLI 改动或安装链路时使用 editable 安装：`uv tool install -e .`
- 已取得源码时可运行 `pwsh -NoLogo -NoProfile -File scripts/install_acf.ps1`、`pwsh -NoLogo -NoProfile -File scripts/update_acf.ps1` 或对应的 `sh` 入口。Windows PowerShell 脚本会在 ACF tool 环境仍被进程占用时 fail-closed；安装/更新成功后原子生成 uv tool bin 下的 canonical `acf.cmd`，由该 uv tool environment 的 Python 执行 `-m acf`，并删除同目录 uv 自动生成的 `acf.exe`，避免 `.EXE` 的 `PATHEXT` 优先级绕过 CMD shim。若 tool bin 已在 PATH，脚本会机械验证 `Get-Command acf` 首先解析到 `acf.cmd`。更新脚本使用未固定版本的 `uv tool install --force --upgrade`，避免 pinned receipt 阻止发现新稳定版，并可在无占用进程时用 `-Reinstall` 修复中断安装。裸 `uv tool install/upgrade` 会重新生成 `acf.exe`，因此只作为 bootstrap/debug 路径，正式 Windows installed-state 应再次通过脚本 canonicalize；CMD shim 不复制业务逻辑，也不引入 signing/certificate 子系统。

验证命令：

- Windows CMD：`where.exe acf`
- PowerShell：`Get-Command acf`
- macOS/Linux：`which acf`
- 通用：`acf --help`
- 查看版本：`acf --version`

Windows canonical installed-state 中，`where.exe acf` / `Get-Command acf` 的首个 ACF application 应是 uv tool bin 下的 `acf.cmd`，同目录不应再保留 `acf.exe`。

请注意：能在任意目录运行 `acf`，不等于任意目录都有 AI 上下文。`acf status --json` 只有在当前目录位于某个包含 `docs/ai`、`docs-acf/ai` 或上下文根目录的项目中时才会成功。否则应先进入项目目录、显式传入上下文路径，或运行 `acf init docs/ai` 初始化。正式用户应从 PyPI 安装；Git URL 只适合临时测试，避免失去发布源升级能力。

### 15.2 常用命令

- `acf status`：自动发现当前上下文，默认输出 `GlobalOnly`、全局文件指针、Workstream 摘要、项目根、profile 和检查结果。
- `acf status --workstream WS001`：显式选择一个活动 Workstream，只返回 pointer-only 入口；随后调用 `acf workstream context WS001` 才读取专属内容。
- `acf next --workstream WS001`：显式选择后的低风险下一入口；省略参数时保持 global-only。
- `acf init <target>`：生成标准上下文模板，并在项目根目录生成缺失的薄入口 AGENTS.md。
- `acf init <target> --profile minimal`：生成简化模板，并在项目根目录生成缺失的薄入口 AGENTS.md。
- `acf init <target> --force-root-agent`：根入口已存在时重写薄入口；默认不会覆盖已有根入口。
- `acf simplify <source> <target>`：从已有上下文导出简化版本，并保留真实 ADR 与 daily worklog，排除占位模板文件。
- `acf init` / `acf simplify --force`：在 destructive replacement 既有 target 前保护当前 `ACF_HOME`（默认 `~/.acf`）；target 若等于、位于或包含当前 `ACF_HOME`，会以 `acf_home_target_protected` fail-closed，避免删除 continuation、closeout authorization 或 usage-log state。普通非破坏性 target 行为保持原语义；destructive dogfood/测试应显式使用隔离的临时 `ACF_HOME`。
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
- `acf review stale [target]`：只读检查默认注意力入口是否可能过期，报告 stale candidates，不判断内容真假、不写文件；除日期型 stale signal 外，也会机械报告 Done 的非空 Current_Task / Task_Plan 仍保留在 active 时的 terminal-retention signals；支持 `--json`、`--days` 和 `--today`。
- `acf audit context [target]`：只读检查 active 层上下文污染候选，不判断事实真假、不写文件、不生成 patch、不接入 `check --strict`；MVP 只报告长 active section、陈旧当前任务 / Workstream 阶段和 ReadyToMerge 待合并或 Done 缺合并结果候选；支持 `--json`。
- `acf curate draft [target]`：复用 `review stale` 的 stale candidates 生成 curation-drafts 目录下的日期命名注意力治理草案；空信号时不创建草案，同名草案已存在时安全拒绝；支持 `--json`、`--dry-run`、`--days`、`--today` 和 `--name`。
- `acf doctor [target]`：跨文件诊断上下文状态漂移、generated index 漂移、Workstream 生命周期、数据证据和注意力治理信号；attention hygiene 直接复用 `review stale` 的 terminal Current_Task/Task_Plan retention 与 Context review marker/stale signals，这些 findings 保持 warning / draft-only，不接入 `check --strict`。默认只读，`--fix safe` 只应用确定性机械修复，`--fix evidence` 只规划 evidence 修复且不改写语义权威文件，`--report` 生成 doctor report，`--draft-semantic` 生成可审阅语义回写草案；支持 `--json`、`--strict`、`--check-after`、`--today`、`--projects`、`--dry-run` 和 `--force`。
- `acf workstream init|status|list|dashboard|archive-candidates|archive-draft|sync|add|reserve [target]` / `acf workstream archive WS001 [target] --reason "..."` / `acf workstream show|context|set|block|cancel|merge-request|merge-start|ready|done|claim|scope-add|guard|note WS001 [target]` / `acf workstream authorization status|list|policy-set|approve|revoke ...` / `acf workstream stage add|list|done WS001 [target]` / `acf workstream focus WS001 WS001.1 [target]`：显式启用可选 Workstream 层，读取并行目标线索引与详情 metadata，并维护强隔离状态转换、合并请求、完成证据、scope claim/扩权、详情备注、内部阶段焦点和显式归档；`reserve` 只在 primary branch 预约并提交唯一编号，不创建 branch/worktree；原 `add` 行为不变；`context` 输出 AI 专属任务入口，`guard` 检查变更文件是否符合当前 Workstream 写入边界，完成或切换状态前优先用 `--files` 显式传入本次修改文件做强验收；`scope-add` 以工具化方式扩展 scope 并写入 Activity Log，`dashboard` 显示冲突、陈旧任务、缺 evidence 和待合并目标；Workstream 类型为 Task / Merge / Maintenance，Task 不直接写 authority 文件，Active 类 Workstream 默认禁止重叠 `owned:` 写入，`shared:` 必须指定 merge_owner 或 serial coordination；`archive-candidates` 只读报告 Done / Cancelled Workstream 的归档候选和 `blocked_by`；`archive-draft` 写入 `worklog/archive-drafts/` 供人工或 AI 审阅；`archive` 只在显式指定单个终态 Workstream 和 `--reason` 时移动详情、清理 active 索引并写入 `archive/Archive_Index.md`；`sync` 只根据 Workstream 详情 front matter 更新 Workstreams 索引，不会删除缺详情的旧索引行；Workstream 详情可用 optional `current_stage` 和 `## 阶段` 表记录内部阶段焦点，`stage add/list` 只维护详情文件，`focus` 不更新全局 Current_Task，`stage done` 要求 evidence 且完成当前阶段时需要 `--clear-current`；`merge_targets` 记录候选合并目标。`ready / merge / done / archive` 统一经过用户级 closeout authorization resolver：`authorization policy-set` 记录可按 Workstream id/type/class/action 限定的 durable `auto|manual|deny` policy，`authorization approve` 只对一个 Workstream、一个 action 和当前 material authority fingerprint 生效，`authorization revoke` 显式撤销记录；更窄、更新的 policy 优先，WS-specific manual/deny 可覆盖项目默认 auto。material authority 变化使旧 approval stale，Activity Log 追加不使其失效；`merge` 的 deterministic `ReadyToMerge -> Merging` transition 自身不 stale 同一次 merge approval，因此 `merge-start` 与后续 worktree merge 可以复用同一批准；其他 material authority 变化仍 fail-closed。缺少匹配 authority 时返回 `approval_required`，显式 deny 返回 `denied`。裸 `--human-approved` 仅为兼容参数，不创建 approval evidence，也不能绕过 resolver。authorization ledger 位于用户级 ACF_HOME、不写项目 Git，未知 schema 或语义损坏均 fail-closed。Merging 表示 Merge/Maintenance 正在合并，Done 需要 `--merge-resolution` 写入合并或处置结果；`add --goal` 可在创建时写入详情目标，`set --goal` 可替换已有详情目标，`--write-scope` 必须使用 `TYPE: PATH` 格式，例如 owned: src/foo.py；`upgrade` 和旧项目默认不启用 Workstream。

`reserve` 不要求 primary checkout 完全 clean；与 reservation detail/index 无关的 staged、unstaged、untracked 修改会被保留，reservation 路径自身或父子路径发生冲突时 fail-closed。

### 可选 Git Worktree 生命周期

创建 Workstream 不会隐式创建 worktree。任务需要长期、并行或独立合并环境时，AI 可单独调用：

```powershell
acf worktree create --workstream WS001 --apply --json
```

非 WS 任务使用 `--kind bugfix|docs|experiment|investigation|maintenance|refactor|release --slug ...`。`worktree list|audit|verify|attach|sync|merge-plan|merge|artifact-plan|artifact-migrate|close|retire|resume` 提供发现、恢复、同步、临时候选合并、结果迁移、安全关闭和 curated handoff 退役。来源 worktree 必须 semantic-clean；正式 merge 总是在临时 integration worktree 中执行并运行 post-check，primary checkout 只进行碰撞保护后的 fast-forward promotion，因此可以保留无关 staged/unstaged/untracked 修改。短时锁、Git 状态和 HEAD 推进会有限等待或自动重规划；稳定冲突保留在 integration worktree，解决并提交后使用 operation ID resume。ignored/untracked 结果默认 unknown，必须明确分类并完成 handoff 后才能 promotion/close。close 对真实 dirty 继续 fail-closed；仅在 canonical semantic-clean 已证明无内容变化且存在 `stat_only_paths` 时，内部可用 `git worktree remove --force` 绕过 raw Git 的 stat-only 假 dirty，branch 仍禁止 `-D`。`retire` 只服务「必要提交已由 reviewed cherry-pick 等保存在别处、但分支因无关历史而刻意不可合并」的已登记 worktree：它只移除 worktree 与 registry、永不删除分支，要求 `--disposition curated_handoff` 与非空 `--evidence-ref`，分支已是 primary ancestor 时拒绝并提示改用 `close`。写操作默认 plan-only，`--apply` 后执行；项目可在 `.acf/project.toml` 配置 primary checkout/branch、worktree root 和命名模板。ACF 不自动 stash、reset、clean、rebase、force、push、覆盖不一致内容或静默解决冲突。

### 外部 AI 续跑控制

需要被外部 Scheduled Task、其他 scheduler 或人工多轮 agent 持续推进时，可使用安装态 ACF 的 `continuation` 命令组：

```powershell
acf continuation init <worktree> --task-id WS001 --workstream WS001 --title "WS001" --objective "目标" --profile long-running --json
acf continuation configure <worktree> --task-id WS001 --profile long-running --json
acf continuation doctor <worktree> --task-id WS001 --json
acf continuation coordination attempt <worktree> --task-id WS001 --runner-id scheduled-agent --objective-summary "继续当前权威计划" --json
acf continuation coordination wait <worktree> --task-id WS001 --challenge-id <challenge_id> --attempt-id <attempt_id> --json
acf continuation claim <worktree> --task-id WS001 --runner-id scheduled-agent --json
acf continuation assert-owner <worktree> --task-id WS001 --owner-file <owner_context_handle> --json
# 仅用于 pre-.90 active owner 的本地 token-file 迁移；不改变 lease/generation/runner
acf continuation owner migrate-legacy-token-file <worktree> --task-id WS001 --legacy-token-file <local_legacy_token_file> --json
acf continuation workspace status <worktree> --task-id WS001 --json
acf continuation workspace intent <worktree> --task-id WS001 --owner-file <owner_context_handle> --path src/example.py --json
acf continuation workspace reclassify <worktree> --task-id WS001 --owner-file <owner_context_handle> --task-owned build/generated.txt --evidence-ref effect:release-job:terminal --reason "Reviewed durable-writer output." --json
acf continuation workspace reconcile-handoff <worktree> --task-id WS001 --cleanup build/generated.txt --accept-head <current-head-if-closeout-advanced-head> --evidence-ref git:<reviewed-closeout-commit> --reason "Reviewed closeout made the recorded handoff WIP semantic-clean." --json
acf continuation workspace adopt <worktree> --task-id WS001 --task-owned src/reviewed.py --baseline-external notes/local.txt --evidence-ref review:handoff --reason "Reviewed legacy no-manifest WIP." --json
acf continuation workspace refresh <worktree> --task-id WS001 --owner-file <owner_context_handle> --json
acf continuation heartbeat <worktree> --task-id WS001 --owner-file <owner_context_handle> --json
acf continuation execution run <worktree> --task-id WS001 --owner-file <owner_context_handle> --key validation:full-unit --json -- uv run python -m unittest
acf continuation progress <worktree> --task-id WS001 --owner-file <owner_context_handle> --phase executing --milestone gate-started --json
acf continuation effect prepare <worktree> --task-id WS001 --owner-file <owner_context_handle> --key campaign:wave-01 --kind external-job --json
acf continuation effect update <worktree> --task-id WS001 --owner-file <owner_context_handle> --key campaign:wave-01 --status completed --evidence-ref artifact:wave-01-result --json
acf continuation directive add <worktree> --task-id WS001 --kind requirement --lifetime durable --priority 80 --text "新增持久需求" --json
acf continuation directive list <worktree> --task-id WS001 --status pending --json
acf continuation directive show <worktree> --task-id WS001 --directive-id <directive_id> --json
acf continuation directive adopt <worktree> --task-id WS001 --directive-id <directive_id> --evidence-ref docs/ai/active/Task_Plan.md --json
acf continuation directive resolve <worktree> --task-id WS001 --directive-id <directive_id> --evidence-ref git:<commit> --json
acf continuation directive supersede <worktree> --task-id WS001 --directive-id <directive_id> --kind priority_change --priority 95 --text "新的优先级要求" --json
acf continuation directive withdraw <worktree> --task-id WS001 --directive-id <directive_id> --evidence-ref user:cancelled --note "用户明确取消该要求" --json
acf continuation reconcile <worktree> --task-id WS001 --owner-ended --evidence-ref scheduler:old-run-ended --reason "verified prior owner ended" --record --json
acf continuation recover <worktree> --task-id WS001 --reconcile-id <receipt_id> --runner-id recovery-agent --json
acf continuation renew <worktree> --task-id WS001 --owner-file <owner_context_handle> --json
acf continuation checkpoint <worktree> --task-id WS001 --owner-file <owner_context_handle> --stage validated --verification "gates passed" --json
acf continuation release <worktree> --task-id WS001 --owner-file <owner_context_handle> --final-status ready --json
```

Continuation owner credential 不通过普通命令文本或 JSON 交付。`claim` / `recover` 在提交 fresh owner 之前创建本地 `owner_context.handle`，该 ephemeral owner context 绑定 workspace、task、lease、generation 与 possession credential；后续 owner-protected 命令只传 `--owner-file <owner_context_handle>`，公共 parser 不再接收 `--fence-token`、`--lease-id` 或 `--generation`。pre-.90 active owner 若仍持有正确的本地 token file，可用显式本地 migration 命令转成同一 lease/generation/runner 的 owner context；旧环境变量不再作为认证输入，迁移失败或旧文件无法安全退休时 fail-closed。UUID、Git SHA、deterministic digest、generation 与普通 external job id 继续作为合法非秘密 metadata。校验采用 binding-first：先验证 handle 文件系统边界、schema 与 workspace/task/runner 绑定，再验证 active lease identity、generation 和 credential possession；已提供 handle 的 schema、绑定、lease identity 或 credential possession 校验失败统一返回 `owner_context_binding_mismatch`，不暴露 `owner_context_invalid`、`lease_mismatch` 或 `fence_token_*` 深层错误码；generation fencing 的状态错误仍按独立 fencing 合同返回。handle 缺失或不可用仍保留 `owner_context_required` / `owner_context_unavailable`。

可能跨 stale window 的确定性本地命令使用 `continuation execution run`。supervisor 在既有 effect journal 中占用不可 replay 的 deterministic key，记录 generation-bound PID + process-start identity，并在精确进程仍 live 时自动 heartbeat/按需 renew；进程退出后 effect terminalize。普通 heartbeat 已 stale 时，只有 active lease + 同 generation 的 active physical-execution effect + 精确 PID/start identity 才能以 `liveness_source=physical_execution` 保持 verified-live。裸 PID、PID reuse、zombie/dead process、unverifiable probe 或 stale effect label 都不算 live；physical evidence 不复活 expired lease。公共结果不回显完整 child argv，只保留非敏感命令摘要与 process/effect 审计身份；明确 credential-bearing argv fail-closed，bounded stdout/stderr 返回前做 credential-like redaction。普通 parent environment 仍为业务兼容继承，但 ACF owner capability/credential transport 不委托给 child；这只是 credential containment，不是通用 sandbox。DevSpace 返回 running session 时仍必须 poll 同一个 session 到 terminal，不能遗弃或重复启动。该能力不引入 daemon/数据库/第二套 scheduler。

`pause` 在 physical execution 尚未开始时继续阻止新执行；若 pause 在 supervised child 已启动并取得精确 process identity 后到达，supervisor 不强制终止该 child，而是继续维持 owner liveness直到同一个 child terminal。terminal JSON 返回 `pause_pending=true`，随后由当前 owner 正常 `continuation release`，让既有 release path 根据仍存在的 pause marker 把 continuation 转为 `paused`。这既防止 orphan/强杀，也不允许 pause 后继续启动新 work。

`init` 会把当时已有的 changed paths 作为受保护的 external baseline，而不是要求为了自动化先清空整个 worktree。`standard` timing 为 scheduler/TTL/renew/heartbeat/stale=`60/120/30/10/30` 分钟；`long-running` 为 `60/180/45/10/25` 分钟。已有 task 用 `configure` 原位调整，不需要 `init --force`；active lease 存在时 configure 会拒绝执行。`continuation directive` 是用户级 live-steering inbox，不是第二套 Task Plan：kind 仅为 `requirement / priority_change / constraint / plan_change`，lifetime 为 `transient / durable / unspecified`，状态为 `pending / adopted / resolved / superseded / withdrawn`。resolve=完成、withdraw=明确取消、supersede=同一 active requirement 被新版本替换；resolved 历史不重新打开。transient one-shot 可直接 `pending -> resolved`，需要跨轮的 transient 与 durable adopt 都要求 durable evidence；durable 语义还必须先由 Agent authority refresh 同步到正确 Markdown PLAN/Workstream/Rules/Task authority，不能因为“读到了文本”就 adopt。非 Writer owner 可 add/supersede 用户 authority，但不会取得 writer lease/generation/fence/workspace write authority。pending directive 在 generated prompt 中优先于 stale persisted `next_action`，实际 consumed directive 在 safe control point 必须显式 disposition。claim 保存已观察的 directive revision/digest；heartbeat/renew 返回 change signal、pending/adopted/active count 和 pressure 摘要，因此长 session 可在下一次 scheduler wake 前发现 steering。`continuation doctor` 只机械报告 stale adopted/high-priority pending、adoption evidence 与容量/rollover pressure，不自动判断自然语言任务完成。current directive journal 到软 event/byte pressure 时，只归档完整 terminal prefix 到 `directives.archive.NNNNNN.json`；pending/adopted 永不归档。archive-first/current-second 允许 crash 后 exact duplicate 去重，不一致 duplicate/revision gap fail-closed；archive history 仍可 list/show、digest 审计并参与 migration-preservation。active authority 自身耗尽容量时继续 fail-closed。每个新 runner 用 `coordination attempt` 登记 compact current-goal intent；没有 owner 时只是 claim candidate，遇到 **fresh** owner 时返回 live-owner observation 且不自动 challenge，只有 stale / legacy-unverified owner 才自动 open/join generation-bound challenge。challenge 形成后，`coordination wait`（alias `await`）以单次 blocking tool call 读取持久化 `deadline_at`，等待 `owner_active | owner_released | timeout`；它不依赖模型纯 idle、永不授予 ownership。`owner_active` 让行，`owner_released` 刷新 doctor 后走正常 claim，`timeout` 仍必须刷新 physical execution / HEAD / workspace / effect / provenance 并 formal reconcile/recover；只要当前 activation 仍存在，pending challenge 不是 session-end signal，成功 recover 后应在同一 activation 继续项目工作。显式 `coordination challenge` 仍可用于独立证据要求重新确认 owner 的场景，但本身不授予写权限。普通可定位项目的 ACF 命令只在 stderr opportunistic 提示 pending challenge，不是 ACK；只有 owner-protected continuation 命令通过本地 owner-context handle 完成 lease identity、generation fencing 与 credential-possession 校验后才 authenticated touch。既有 effect replay protection、terminal archive rollover、workspace manifest v3、legacy adoption、task-owned handoff、semantic-clean 和 generation fencing 规则保持不变。heartbeat 只证明 liveness，不延长 TTL；Scheduled Task 小时触发只是恢复唤醒。`acf continuation prompt --runner-id <runner>` 是唯一 generic Scheduled Task protocol 权威，并按当前 owner/workspace/effect 状态 progressive disclosure，同时返回 `directive_context`；Scheduled Task wrapper 每次 wake 重新读取它，但 wrapper 本身必须是 sufficient high-salience bootstrap，而不是只保留最少字段：应完整携带 exact existing workspace / connector mode、stable ACF upgrade-adaptation、authority refresh、execute generated plan、owner disclosure 与项目专用约束。运行态保存在用户级 `~/.acf`，不会写入项目 Git；ACF 不是通用文件编辑器或源码备份系统。

`acf continuation prompt` 采用 goal-directed continuous execution：scheduler wake 只是持续任务的恢复入口，不定义独立工作回合、汇报周期、工作配额或预期停止点；bounded 只约束 ownership、写入、副作用和恢复风险，不限制当前 execution session 的有效工作量。`.72+` 中 `state.next_action` 在 authority refresh 后仍有效时是默认执行计划，不是只供查看的 hint，也不是 work quota；newer Git/PLAN/Runtime/effect authority 可以覆盖它，否则应执行，完成后继续围绕总体目标推进。若默认计划明确等待下一次真实外部/项目状态变化，则 scheduler wake、`coordination attempt` 与 `claim` 本身都不算满足等待条件的项目进展；没有其他当前可执行的安全、有价值工作时，可以不 claim、不改变 task 状态地结束本次 wake，避免通过 claim 人为制造 lifecycle change。generated prompt 只展开当前状态相关的 claim/duplicate/recovery/workspace/effect 分支。final response、timing、测试/commit/checkpoint/Gate 的既有非停止语义保持不变；任务级 hard stop 仍只有总体目标完成、用户明确暂停、需要新的人工授权/凭据/不可替代决策，或项目访问工具经合理重连仍不可用。

“没有其他当前可执行工作”不是默认假设。mission 仍 open 时应先主动审计 blocker/root-cause diagnosis、adjacent gap implementation、validation/evidence、reusable contract hardening、accessible-target dogfood、release preparation 与 low-side-effect diagnostics；某一 lane blocked 应切换安全替代项。anti-busywork 只禁止输入/环境/证据/策略均未变化的同一失败动作；新的诊断、changed strategy 或低副作用实验只要能减少不确定性仍可执行。默认以 overall mission / 当前 PLAN stage 为 work unit，不为单个 bug、实验、test、checkpoint 或 release Gate 拆新 Workstream；自然 checkpoint 后 refresh authority 并继续。只有 alternative audit 证明当前安全增量项均无价值，或命中 hard stop，才允许结束 execution session。

`workspace reclassify` 只处理当前 fenced owner 已审阅的 `unexpected_nonoverlap`：durable writer 已结束后，启动前漏报的真实产出只有在提供 durable evidence 与 reason 时才能用 `--task-owned` 纳入任务，或用 `--baseline-external` 明确保留为外部修改。task-owned 仍必须命中 Workstream direct write scope；已有 conflict、非 unexpected 路径、路径重叠、scope 越界或 provenance 不确定继续 fail-closed。若绑定 Workstream 已由正式 `workstream archive` 移到 archive 且 active detail 已不存在，恢复流程可以校验 archived detail 并继续使用原 direct scope；只允许本次归档所需的 active index/detail 与 archive index/detail 四个精确 lifecycle authority 路径额外参与证据驱动 reclassify，不会重新激活 Workstream 或扩大普通 Task authority。

`workspace reconcile-handoff` 是 ownerless graceful-running-handoff 的窄恢复通道，不是对 provenance drift 的自动宽容。只有 lease 完全 absent、latest round 明确为 `released_to_running_handoff`、无 unresolved effects、workspace generation 与 handoff generation 一致时才可使用；每个 `--cleanup` path 必须原本是 task-owned、仍受保留 write intent 覆盖、当前 semantic Git snapshot 已 clean，并且这些 path 必须精确解释当前全部 `task_owned_handoff_drift` conflict。若 Git HEAD 自 handoff baseline 后推进，还必须显式传入与当前 HEAD 精确相等的 `--accept-head`；不能借 cleanup 顺带接受未知 commit。仍 dirty 的改写、普通 release、active/expired owner、未知 conflict、未接受的 HEAD drift 或 effect ambiguity 都 fail-closed。成功只更新 workspace provenance baseline，并把最新审计 receipt 写入 `last_workspace_reconcile.json`；它不授予 ownership、不执行 recover，随后仍需重新 doctor 并正常 claim。

`coordination wait|await` 是 stale-owner challenge 的阻塞观察面，不是新的 scheduler 或自动 takeover runtime。等待边界只来自 challenge 自身持久化 `deadline_at`；`--poll-seconds` 只控制本地观察频率。返回 `owner_active` 时让行，`owner_released` 时重新 doctor/claim，`timeout` 时仍需 formal reconcile/recover；所有结果都保持 `ownership_granted=false`。这样同一 Scheduled Task activation 可以用工具调用跨过 challenge window，而不要求模型“什么都不做地等十分钟”，同时也不把 challenge timeout 偷换成 owner 死亡或外部 effect 终态证明。

普通 `baseline_external` 必须继续保护，禁止 stash/reset/clean/stage/commit。唯一窄例外是当前 authenticated runner 刚通过 `acf workstream scope-add|merge-request|ready|merge-start|done` 为**当前绑定 Workstream**生成的 Workstreams 索引与当前 Workstream detail 文件：在 lifecycle/merge 边界可以审阅 exact diff 与 durable ACF command evidence，并把**仅这两个确定性 control-plane 文件**形成独立 checkpoint。该动作不扩展普通 Task authority write_scope，也不能把其他 baseline/external path 带入提交；来源不明或人工编辑的 authority dirty 仍 fail-closed。

Worktree lifecycle 与 continuation workspace 共用 read-only semantic-clean：普通 tracked unstaged `M` 若 `GIT_OPTIONAL_LOCKS=0` 的 Git diff 为空，则只报告在 `stat_only_paths`，不作为 blocker；staged/untracked/真实 diff/rename/delete/type/mode/unmerged/submodule 继续严格。verify/list 不调用会改 index 的 refresh。Workstream `## Workspace` 只保存 slug 和 local registry/verify/list authority，不保存机器相关 mode/path/branch；Open reserve/create next_actions 明确提示执行前显式设置 Active。

`continuation prompt --json` 返回可机器读取的 `identity` 与 `scheduler_wrapper_contract`；`bootstrap_policy=sufficient_high_salience` 要求 wrapper 完整提供 exact existing workspace / tool mode / stable ACF upgrade / authority refresh / execute generated plan / owner disclosure / project constraints / final-response contract，同时 `copy_generic_state_machine=false` 禁止复制 generic 状态机。对 DevSpace 已经存在的固定 worktree，应明确使用 existing checkout 语义（`mode="checkout"`），不得再次用 `mode="worktree"` 创建 `.devspace/worktrees` detached/重复副本。任何可能在 owner/tool-call 结束后继续写项目文件或产生非幂等副作用的 Runtime/external writer 仍必须在启动前建立 durable deterministic effect/job identity。

P1.5 `automation_prompt_execution_contract` v2 保持 Writer `acf.continuation.scheduler_wrapper.v1` 兼容键：Writer static wrapper 只承载 sufficient bootstrap、project/task extension 与 volatile-fields-not-static；owner/generation/stage/next_action/directive/release/acceptance 等动态状态仍只由每轮 `acf continuation prompt + execution_policy` 提供。`v0.0.3.92` 起该 contract 不再包含 Production Observer wrapper、observer semantic review、observer execution evidence 或 presentation maintenance 子树；已退役的 Observer 状态机不得被重新嵌入 Writer runtime prompt。

Agent-owned 文本稳定入口在晋升前必须能够 strict UTF-8 回读，且不得包含 Unicode replacement character（U+FFFD）；但 successful UTF-8 decode / U+FFFD=0 本身不足以证明可见文本未发生 mojibake。Agent 还必须从当前 authority/source 选取预期可见文本 marker（例如项目原生非 ASCII 标签或等价 sentinel）并在晋升前回读验证；当实际命令/PTY 通道的 Unicode 保真未经证明时，必须改用 byte-preserving 写入或 ASCII-safe payload transport。任一检查失败按更新失败处理并保留 last-good。这不是新的 renderer/schema，只是 Agent 直写页面的最小文本完整性保护，也不硬编码具体语言。

旧 P2 target semantic-review / one-shot / durable-rule runtime 已随 Project Observer 退役一并移除，不再是可调用的 legacy compatibility surface。`presentation-status`、`review-request-add`、`semantic-review-apply`、`presentation-rule-*` 等命令不再发布；对它们的旧调用只会得到未知命令错误，而 `acf observer` 稳定返回无副作用的 `observer_retired` 提示。因此新页面与续跑流程都不需要先创建或消费这些状态，也不存在每轮强制 Map Review 的要求。

`continuation prompt --json` 除 `identity` 与 `scheduler_wrapper_contract` 外，还返回 `current`、`owner_context`、`directive_context`、`resume_context`、`execution_policy`、`project_context` 和当前 `next_actions`。`owner_context` 在传入 `--runner-id` 后区分 current owner / verified live other owner / stale-or-unverified / expired / no-owner；未传 runner id 时 fresh lease 保持 caller-unknown。`directive_context` 给出 global revision、pending-set digest、pending/adopted/active count、current pressure、archive count/history digest 和 pending 摘要；pending 时 `authority_refresh_required=true`。`execution_policy` 包含 `pending_user_directive_supersedes_persisted_next_action=true`、`consumed_user_directive_requires_disposition=true`、`next_action_is_default_execution_plan=true`、`next_action_requires_authority_refresh=true`、`active_lease_requires_liveness_verification=true`、`verified_duplicate_owner_may_end_duplicate_wake=true`、`duplicate_wake_exit_is_task_stop=false`、`stale_owner_requires_recovery=true`、`contender_must_create_busywork=false`，并继续保留 `next_action_is_work_quota=false`、`final_response_is_terminal=true` 等既有语义；条件等待计划还显式暴露 `claim_requires_present_safe_useful_work=true`、`control_plane_activity_satisfies_wait_condition=false` 与 `no_useful_work_may_end_wake_without_claim=true`。

长期自治字段还包括 `mission_open_requires_active_alternative_search=true`、`blocked_lane_should_switch_to_safe_alternative=true`、`anti_busywork_scope=unchanged_failed_action_only`、`no_useful_work_end_requires_alternative_audit=true`、`prefer_mission_stage_over_microtask_fragmentation=true`、`checkpoint_requires_authority_refresh_and_continue=true`。控制面检查要与 evidence-backed risk 成比例并优先最便宜的确定性安全 continuation；active lease、历史 abnormal generation、task-owned dirty、scheduler wake、checkpoint/test/commit/Gate 或单 lane blocked 本身都不是 stop signal。wall-clock/liveness timing 只作诊断和可配置 mechanics，不得成为固定 execution budget。genuine safe session end 应先持久化 progress/next_action/evidence，再以 `acf continuation release --handoff` 释放 owner/round 且保持 long-lived state=`running`；verified-live physical execution 必须 yield 且禁止 duplicate。`continuation prompt --json` 的 `execution_observability` 将 bootstrap/control-plane、project work、physical execution、graceful handoff、abnormal/incomplete termination、recovery overhead 分离为机器可读诊断，telemetry 不形成 timing policy。P1.5 `automation_prompt_execution_contract` 的 `writer_continuous_execution` 以及 Writer wrapper/runtime contract 应保持同一语义；这些规则只约束 work selection 与 session-end/handoff，不复制 generic continuation 状态机，也不放宽安全边界。

同一 stale generation 若同时存在多个已有 durable external id、且由外部 authority 明确证明 terminal 的 unresolved effects，可在一次 `reconcile` 中按相同顺序重复 `--effect-key`、`--effect-terminal-status`、`--effect-external-id`，以一个 receipt 原子绑定全部 assertions；它们共享本次 `--effect-evidence-ref` 集合，数量、identity 或 digest 不一致继续 fail-closed。write-ahead `effect prepare` 后若尚未真正 submit，仍允许一条单 effect 的显式 no-start 恢复路径：只有 effect 仍为 `prepared`、`external_id=null`，并有外部 authority 证明 submit 从未启动时，owner 结束/forfeiture 后才可用 `reconcile --effect-not-started --effect-terminal-status failed --effect-evidence-ref <ref>` 生成 receipt，并由 `recover` 标记 failed。对于已经实际执行、但没有 external id 而停在 `prepared|active + external_id=null` 的**本地确定性 effect**，可在 owner-ended/forfeiture 且 durable local authority evidence 明确证明 terminal 结果时使用 `--effect-local-terminal`；它可一次收口多个 local effects，但与 external-id / not-started 模式互斥，`unknown` 或证据不足仍严格拒绝。

continuation state 固定存放于 `ACF_HOME/projects/<root-slug>-<path-hash>/continuation/<task-id>/`；默认根目录是 `~/.acf`，`ACF_HOME` override 只替换这个根。`directives.json` 与 `directives.archive.NNNNNN.json`、control/state/round/effect 同属该用户级 namespace，不进入项目 Git。compact `state.json` 的 `completed / evidence_refs / verification` 是最多 64 项的 rolling history summary；旧版本遗留的 current-schema history overflow 会在读取时惰性压缩，并在下一次合法 state write 持久化。`constraints / open_questions / plan_refs` 继续严格限 64 项，超限 fail-closed，不会为了容量静默丢掉仍有效的安全/计划语义；其中 `constraints / open_questions` 属于当前 compact authority hint，newer authority 明确 supersede/resolve 后只能由 authenticated checkpoint exact-match `--supersede-constraint` / `--resolve-open-question` 并带 durable `--evidence-ref` 退休，不能靠模糊匹配或容量裁剪静默删除；裁剪前仍检查 forbidden raw-history 和单项大小。`acf continuation list <worktree> --json` 与 `--all-projects` 只读报告 task/workstream identity、timing、control generation、各 state schema 及 compatibility。支持的 legacy workspace schema 使用 `acf continuation migrate ... --dry-run` 预览，并只在没有 lease record 时显式 `--apply --reason ...`；migration receipt 记录 schema/digest 变化和其余 history 文件（包含 directive current/archive journals）的 byte digest，未知/future schema 继续 fail-closed。不要直接编辑 ACF_HOME JSON。


### Project Observer（已退役）

Observer 产品能力已在 `v0.0.3.92` 从 ACF 核心退役。`acf observer` 只保留一个无副作用的退役入口：它不导入旧实现、不读取或写入 Observer runtime、不创建目录，并稳定返回 `observer_retired` 与替代命令提示。原 Observer runtime、Dashboard、Target Registry、semantic-review / presentation lifecycle 与 narrative 能力均不再发布；`acf continuation prompt --json` 也不再携带 Observer 合同子树。旧机器上的用户级 Observer 数据不会被升级流程自动删除。

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
- `acf log gc --json`：只读报告可清理的孤儿 usage-log namespace（记录的项目根已不存在、无 continuation / closeout 状态、命名像 synthetic / smoke / temp，且超过保留期）。默认干跑，`--apply` 才实际删除并写出不含凭据的 receipt；仍能解析到真实项目的 namespace 永不删除。
- `acf log issue list|show|resolve|supersede|reject|reopen ...`：独立于 continuation 的产品 issue 生命周期。occurrence 仍来自各项目 usage log，处置写入用户级 append-only 台账 `<ACF_HOME>/issues/ledger.jsonl`；`resolve` / `supersede` / `reject` / `reopen` 都要求 `--reason`，可重复 `--evidence-ref` 并支持 `--dry-run`。

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
