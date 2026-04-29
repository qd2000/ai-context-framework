本文件记录人工临时反馈、问题、需求和计划碎片。

这里允许写得不规范。它的作用是先接住重要信号，再由人或 AI 后续整理到 `active/Task_Plan.md`、`active/Context.md`、ADR、worklog 或 Knowledge。

---

## 状态说明

- Open：尚未整理；AI 看到后应先判断归属，不直接视为当前事实。
- Triaged：已判断归属，但尚未完全落盘；后续处理必须说明目标文件、计划项或草案位置。
- Planned：已进入 `active/Task_Plan.md` 或当前任务，等待按计划完成。
- Done：已处理完成，后续处理列必须给出证据位置；只在近期或当前计划仍需引用时保留在 active 表中。
- Rejected：明确不采纳或不再适用，后续处理列必须说明拒绝原因或替代位置；只在近期仍有解释价值时保留。

---

## 反馈条目

| ID | 状态 | 类型 | 内容 | 来源 | 后续处理 |
|---|---|---|---|---|---|
| F001 | Done | 需求 | 需要一个人工可直接写入的地方，用于记录不规范但关键的问题、需求和计划碎片。 | 2026-04-29 用户反馈 | 已新增 active/Feedback_Inbox.md，并纳入模板与默认读取顺序；保留为当前反馈流程来源证据。 |
| F002 | Done | 需求 | 当前 dogfooding 上下文应从 minimal 补齐为 standard。 | 2026-04-29 用户反馈 | 已补齐 standard 文档；strict 检查策略已处理示例模板占位符。 |
| F003 | Done | 需求 | 每次改动需要判断是否更新 version number，并提供便捷工具一键更新。 | 2026-04-29 用户反馈 | 已增加版本规则和 acf version show/set；版本维护规则已进入项目规则。 |
| F004 | Done | 问题 | strict mode 不应因为标准模板中的 ADR/worklog 示例模板阻塞真实项目检查。 | 2026-04-29 用户反馈 | 已让真实项目 strict 忽略 ADR/worklog 示例模板占位符，模板源自身仍保留检查能力。 |
| F005 | Done | 需求 | 会话结束回写建议不应每轮只重复打印建议；应优先直接落盘或生成明确草案，并只报告实际写入或修改的内容，未变更部分不输出，减少 token 浪费。 | 2026-04-29 用户反馈 | 已进入 active/Task_Plan.md T002，并通过 docs/ai/AGENTS.md 的会话结束回写落盘协议处理。 |
| F006 | Done | 问题 | Feedback_Inbox 需要已解决条目的归档、删除或隐藏约束，避免长期污染上下文。 | 2026-04-29 用户反馈 | 已进入 active/Task_Plan.md T003，并通过本文件状态说明、使用规则和 archive/feedback/ 归档位置处理。 |
|  |  |  | 目前系统没有考虑到多个agents在同一个项目中并行处理不同目标的情况，没有针对这种并行场景设计任务和信息管理方案 |  |  |

---

## 使用规则

1. 人工可以直接追加粗糙描述，不要求一开始就结构化。
2. AI 看到 Open 条目时，应先判断是否需要转入任务计划、当前事实、ADR、worklog、rules、Knowledge 或 writeback 草案。
3. AI 不应把本文件中的随想直接当作已确认事实；只有转入对应事实源或计划后，才按目标文件的事实源级别使用。
4. 状态推进顺序通常是 Open -> Triaged -> Planned -> Done；不采纳时使用 Rejected，并在后续处理列说明原因。
5. Planned 条目必须引用 `active/Task_Plan.md` 的任务 ID、`active/Current_Task.md` 的任务名称，或明确说明等待哪一类落盘动作。
6. Done 或 Rejected 条目必须保留证据位置，例如计划任务、worklog、ADR、Context、Knowledge 草案或拒绝理由。
7. active 表只长期保留 Open、Triaged、Planned，以及当前大任务仍需解释的 Done/Rejected 条目。
8. 清理阈值：当 Done/Rejected 条目超过 10 条，或条目完成超过 30 天且不再支撑当前计划时，应整理到反馈归档。
9. 反馈归档位置使用 `archive/feedback/`，归档文件按月份命名为 YYYY-MM.md；归档摘要应记录 ID、状态、类型、内容摘要、处理结果和证据位置，不复制长过程。
10. AI 执行反馈清理时，应先确认条目已有证据位置，再移动或摘要归档；不能确定是否仍需保留时，生成 writeback 草案而不是删除。
