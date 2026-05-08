本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P2-8 Context Attention Cleanup and P2-5 Readiness

---

## 大任务目标

1. Clean the active attention entry after P2-7 by syncing current facts, triaging feedback, and preparing the next P2-5 audit fixture slice.

---

## 成功标准

1. active/Context.md no longer triggers active_section_too_long.
2. Feedback items for progressive disclosure and timestamp precision are structured and planned or triaged.
3. Current version facts reflect v0.0.3.36 and the next P2-5 task is ready to start.

---

## 规划依据

列出当前大任务必须对齐的 reference 设计、路线或差距文档；只放路径和一句话用途，不复制详细规划。

- [reference/Product_Roadmap.md](../../reference/Product_Roadmap.md)：阶段路线和近期优先级。
- [reference/Top_Level_Implementation_Gap.md](../../reference/Top_Level_Implementation_Gap.md)：P2-5 推荐切片和实现缺口依据。
- [reference/Context_Curation_Prompt.md](../../reference/Context_Curation_Prompt.md)：Context 渐进式披露和注意力治理整理方式。
- [reference/System_Manual.md](../../reference/System_Manual.md)：维护命令、归档、检查和默认上下文规则。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Triage context governance feedback | 无。 | Feedback_Inbox structured entries and explicit follow-up destinations | F015-F018 structured in Feedback_Inbox; F016 planned for Context progressive disclosure and F018 records archive relative-link rewrite gap. | 无。 |
| T002 | Done | Compress Context active facts | T001 | Context uses progressive disclosure with concise facts and document index | Context current facts compressed into progressive-disclosure summary plus document index; v0.0.3.36 synced; check strict, audit context, and review stale all clean. | 无。 |
| T003 | Done | Prepare P2-5 audit fixture slice | T002 | P2-5 fixture expansion scope and current task are ready | P2-5 implemented: added audit_stale_stage and audit_terminal_merge context_matrix fixtures plus tests; full unittest, docs/ai strict check, template check, minimal smoke, and git diff --check passed. | 无。 |
| T004 | Done | Record archive link rewrite gap | T001 | Dogfooding-discovered archive/link gap is recorded for later CLI design | F018 records archive current-task/task-plan relative-link rewrite gap; current archived task/plan links were manually corrected and strict check passes. | 无。 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 当前大任务依赖 reference 规划时，必须在 `## 规划依据` 列出路径和一句话用途。
4. 已失效的大任务计划应归档到 `archive/plans/`。
5. 不要把历史过程、完整日志或详细推理写入本文件。
