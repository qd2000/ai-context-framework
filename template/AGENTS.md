本文件告诉 AI 助手如何进入、理解和协助本项目。

**设计说明**：这是上下文目录内的完整入口文件，应该放在 docs/ai/AGENTS.md（项目初始化时自动复制）。
项目根目录应该有一个薄入口 `AGENTS.md` 文件，指向本文件的位置；`acf.py init` 会在缺失时生成该薄入口，且默认不覆盖已有根入口。
详见 README 中关于"两层 AGENTS.md 的设计"部分。

本项目采用分层上下文结构。不要默认扫描整个项目或读取所有文件。先读取当前有效上下文，再根据任务按需读取。

---

## 路径约定

本文件所在目录是 AI 上下文根目录。以下所有路径均相对于本文件所在目录。

---

## 核心原则

1. 不是所有保存的信息都应第一时间暴露给 AI。
2. AI 默认只读取当前有效、高信号、低噪音的上下文。
3. 历史记录、归档资料、原始日志默认不进入当前上下文。
4. 不同类型的信息有不同事实源，避免重复维护。
5. 如果不同文件之间出现冲突，应按事实源优先级判断。
6. 写入当前事实前先判断唯一权威位置，能更新旧表述时不要追加重复事实。
7. 核心行为规则请遵守 `rules/Always_Active.md`。

---

## 目录结构

```text
active/      当前有效上下文、人工反馈 inbox、任务计划和当前任务
rules/       规则系统，按 always / requested / manual 分层
reference/   支持性资料、索引、摘要，按需读取
decisions/   重要决策详情，通常通过 Decisions_Index.md 进入
worklog/     整理后的工作记录，不是原始运行日志
archive/     历史归档和 `archive/feedback/` 已处理反馈归档，默认不读取
```

---

## 默认读取顺序

进入本项目后，请默认只读取以下文件：

1. `active/Context.md`
2. `rules/Always_Active.md`
3. `active/Feedback_Inbox.md`（仅当存在 Open 条目或需要整理人工反馈时）
4. `active/Task_Plan.md`（读取后按 `## 规划依据` 追溯当前大任务需要对齐的 reference 规划文档）
5. `active/Current_Task.md`（仅当该文件存在且任务状态为 Active 时）
6. Workstreams 索引（仅当该可选文件存在，且存在 Active、Blocked 或 ReadyToMerge workstream，或需要整理并行协作时）

如果用户在当前消息中已给出明确任务，以用户当前消息为准，以上文件作为背景上下文。

---

## CLI 辅助维护

如果项目可用 `acf` 命令，维护上下文时优先考虑使用它完成确定性操作。

- 开始维护前，可先运行 `acf status --json` 确认上下文位置和当前状态。
- 新增或更新当前计划、规划依据、当前任务、资料索引、Knowledge 草案、归档、worklog、ADR、section 或 table 时，优先考虑 `acf plan`（包括 `acf plan reference`）、`acf task`、`acf knowledge`、`acf archive`、`acf new`、`acf edit`、`acf writeback` 和 `acf check`。
- 需要参数细节时，先查看 `acf --help`；需要系统级说明时，再读取 `reference/System_Manual.md`。

`acf` 只负责结构化落盘、检查和草案生成，不替代人或 AI 对事实和语义的判断。

---

## 按需读取指引

| 场景 | 读取文件 |
|------|----------|
| 需要理解项目长期背景 | `reference/Project_Brief.md` |
| 需要整理人工反馈、问题、需求和计划碎片 | `active/Feedback_Inbox.md` |
| 需要处理多个并行目标线 | Workstreams 索引 → 对应 Workstream 详情文件 |
| 需要追溯重要决策 | `reference/Decisions_Index.md` → `decisions/ADR-*.md` |
| 涉及架构设计 | `reference/Architecture.md` |
| 涉及技术实现、运行环境 | `reference/Tech_Context.md` |
| 涉及外部资料来源 | `reference/Sources_Index.md` |
| 需要追溯可复用经验 | `reference/Knowledge_Index.md` → `reference/knowledge/*.md` |
| 需要了解近期进展 | `worklog/Worklog_Index.md` → 最近 N 条 daily |
| 需要整理、归纳、精简上下文 | `reference/Context_Curation_Prompt.md` |
| 涉及项目通用约束 | `rules/Project_Rules.md` |
| 涉及代码实现 | `rules/Coding_Rules.md` |
| 涉及写作输出 | `rules/Writing_Rules.md` |
| 涉及方案评审 | `rules/Review_Rules.md` |
| 需要了解系统详细用法 | `reference/System_Manual.md` |

除上述场景外，不要默认读取 archive、完整 worklog、原始日志或所有 reference 文件。

---

## 事实源优先级

如果不同文件之间存在冲突，按以下优先级判断：

1. 用户当前消息
2. `active/Current_Task.md`
3. `active/Task_Plan.md`
4. `active/Context.md`
5. `active/Feedback_Inbox.md`（只作为待整理信号，不作为已确认事实）
6. `reference/Decisions_Index.md`
7. `decisions/` 中的 ADR 文件
8. `reference/Knowledge_Index.md`
9. `worklog/`
10. `archive/`

Knowledge 是可复用经验层，不是当前事实源；worklog 是历史过程记录，archive 是归档材料，均不等于当前事实。

---

## 注意力治理与上下文预算

- 默认上下文只保留当前目标、当前事实、当前任务和下一步。
- 整理事实时优先读取 changed files、`active/`、相关索引和最近 worklog。
- 不为 curation 默认读取 archive 或全部历史日志；curation draft 不进入默认读取路径。
- 低优先级文件不得重复完整表述高优先级事实；能引用权威位置时，不复制原文。

---

## 目标信息来源

不同层级的目标由不同文件维护：

- 长期目标 / 项目愿景：`reference/Project_Brief.md`
- 当前阶段目标：`active/Context.md`
- 人工反馈 / 问题 / 需求碎片：`active/Feedback_Inbox.md`
- 当前大任务计划：`active/Task_Plan.md`；其中 `## 规划依据` 只列 reference 路径和一句话用途，详细规划事实源仍在 reference 文件
- 当前具体任务：`active/Current_Task.md`
- 当前用户临时需求：用户当前消息

---

## 输出格式要求

给出重要建议时，优先使用以下结构：

1. 结论
2. 理由
3. 风险
4. 可选方案
5. 建议下一步
6. 需要用户确认的事项

评审任务额外指出：最可能失败的地方、需验证的假设、信息不足之处。
设计任务额外区分：当前 MVP、后续扩展、不建议现在做的部分。

---

## 会话结束回写建议

重要协作结束时，AI 不应默认重复打印完整回写建议清单。先判断是否存在可确定写入的内容；有则优先落盘或生成可审阅草案，最终报告只列出实际变更、草案路径、验证结果和仍需人工判断的风险。

处理规则：

1. 当前任务或计划状态变化：优先使用 `acf task ...` 或 `acf plan ...` 更新 `active/Current_Task.md`、`active/Task_Plan.md`；工具不能表达时，再用 `acf edit ...` 精确更新相关 section 或表格。
2. 新的人工反馈、问题、需求碎片：优先写入或更新 `active/Feedback_Inbox.md`；如果无法确定归属，生成 `acf writeback draft ...` 草案，不把反馈直接写成当前事实。
3. 已验证的当前事实：只在与当前阶段仍相关、且证据明确时更新 `active/Context.md`；写入前先查旧表述，能 replace 时不 append；一次性过程不写入 Context。
4. 今日工作记录：完成了可复述的工作或验证后，优先使用 `acf new worklog ...` 记录整理后的摘要；同日已有记录且需要补记时使用 `--append --json`，需要重建时才使用 `--force`；不要写入原始日志或大段命令输出。
5. Knowledge 候选：优先使用 `acf knowledge draft ...` 生成草案；只有经审阅或任务明确要求时，才 apply 到 `reference/Knowledge_Index.md`。
6. Archive 候选：旧当前任务或旧大任务计划优先使用 `acf archive ...`；其他归档建议先生成 writeback 草案，等待人工确认归档位置。
7. ADR 或规则候选：已经形成稳定决策时使用 `acf new adr ...` 或更新 rules；只是建议或待确认事项时生成 writeback 草案。
8. 注意力治理候选：发现重复、过期或权威位置不清的信息时，生成 `acf writeback draft ...` 草案，列出当前事实变更、唯一权威位置、仅保留为历史的信息和待确认信号。

最终回复规则：

- 只报告本轮实际修改的文件、生成的草案、执行的检查和检查结果。
- 对没有变化的类别，不输出“无需更新”清单。
- 如果存在应回写但本轮不能安全落盘的内容，只报告草案路径或明确的人工待确认项。
- 不把 usage event log、原始测试输出、完整对话或 Feedback_Inbox 随想直接写入权威事实源。
- 不把 writeback draft 或 curation draft 加入默认读取路径。

---

## 详细使用手册

各目录的详细使用规则、资料处理、日志处理、不确定信息处理等，请参阅：

→ `reference/System_Manual.md`
