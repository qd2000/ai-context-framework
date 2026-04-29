本文件告诉 AI 助手如何进入、理解和协助本项目。

本目录是本仓库 dogfooding 的标准版 AI 上下文根目录。默认只读取当前有效上下文和核心规则，其他资料按需读取。

---

## 默认读取顺序

1. `active/Context.md`
2. `rules/Always_Active.md`
3. `active/Feedback_Inbox.md`（仅当存在 Open 条目或需要整理人工反馈时）
4. `active/Task_Plan.md`
5. `active/Current_Task.md`（仅当任务状态为 Active 时）

如果用户在当前消息中已给出明确任务，以用户当前消息为准。

---

## CLI 辅助维护

如果项目可用 `acf` 命令，维护上下文时优先考虑使用它完成确定性操作。

- 开始维护前，可先运行 `acf status --json` 确认上下文位置和当前状态。
- 新增或更新当前计划、当前任务、资料索引、Knowledge 草案、归档、worklog、ADR、section 或 table 时，优先考虑 `acf plan`、`acf task`、`acf knowledge`、`acf archive`、`acf new`、`acf edit`、`acf writeback` 和 `acf check`。
- 需要参数细节时，先查看 `acf --help`；如果项目包含系统手册，再按需读取 System Manual。

`acf` 只负责结构化落盘、检查和草案生成，不替代人或 AI 对事实和语义的判断。

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

## 按需读取指引

| 场景 | 读取文件 |
|---|---|
| 需要理解长期背景 | `reference/Project_Brief.md` |
| 需要整理人工反馈、问题、需求和计划碎片 | `active/Feedback_Inbox.md` |
| 需要追溯重要决策 | `reference/Decisions_Index.md` -> `decisions/ADR-*.md` |
| 涉及架构设计 | `reference/Architecture.md` |
| 涉及技术实现、运行环境 | `reference/Tech_Context.md` |
| 涉及项目通用约束 | `rules/Project_Rules.md` |
| 涉及代码实现 | `rules/Coding_Rules.md` |
| 涉及写作输出 | `rules/Writing_Rules.md` |
| 涉及方案评审 | `rules/Review_Rules.md` |
| 需要了解近期进展 | `worklog/Worklog_Index.md` |
| 涉及外部资料来源 | `reference/Sources_Index.md` |
| 需要追溯可复用经验 | `reference/Knowledge_Index.md` -> `reference/knowledge/*.md` |

---

## 事实源优先级

1. 用户当前消息
2. `active/Current_Task.md`
3. `active/Task_Plan.md`
4. `active/Context.md`
5. `active/Feedback_Inbox.md`（只作为待整理信号，不作为已确认事实）
6. `reference/Decisions_Index.md`
7. ADR 文件
8. `reference/Knowledge_Index.md`
9. `worklog/`
10. `archive/`

Knowledge 是可复用经验层，不是当前事实源；worklog 是历史过程记录，不等于当前事实；archive 默认不读取。

---

## 会话结束回写建议

重要协作结束时，AI 不应默认重复打印完整回写建议清单。先判断是否存在可确定写入的内容；有则优先落盘或生成可审阅草案，最终报告只列出实际变更、草案路径、验证结果和仍需人工判断的风险。

处理规则：

1. 当前任务或计划状态变化：优先使用 `uv run acf task ...` 或 `uv run acf plan ...` 更新 `active/Current_Task.md`、`active/Task_Plan.md`；工具不能表达时，再用 `uv run acf edit ...` 精确更新相关 section 或表格。
2. 新的人工反馈、问题、需求碎片：优先写入或更新 `active/Feedback_Inbox.md`；如果无法确定归属，生成 `uv run acf writeback draft ...` 草案，不把反馈直接写成当前事实。
3. 已验证的当前事实：只在与当前阶段仍相关、且证据明确时更新 `active/Context.md`；一次性过程不写入 Context。
4. 今日工作记录：完成了可复述的工作或验证后，优先使用 `uv run acf new worklog ...` 记录整理后的摘要；不要写入原始日志或大段命令输出。
5. Knowledge 候选：优先使用 `uv run acf knowledge draft ...` 生成草案；只有经审阅或任务明确要求时，才 apply 到 `reference/Knowledge_Index.md`。
6. Archive 候选：旧当前任务或旧大任务计划优先使用 `uv run acf archive ...`；其他归档建议先生成 writeback 草案，等待人工确认归档位置。
7. ADR 或规则候选：已经形成稳定决策时使用 `uv run acf new adr ...` 或更新 rules；只是建议或待确认事项时生成 writeback 草案。

最终回复规则：

- 只报告本轮实际修改的文件、生成的草案、执行的检查和检查结果。
- 对没有变化的类别，不输出“无需更新”清单。
- 如果存在应回写但本轮不能安全落盘的内容，只报告草案路径或明确的人工待确认项。
- 不把 usage event log、原始测试输出、完整对话或 Feedback_Inbox 随想直接写入权威事实源。
