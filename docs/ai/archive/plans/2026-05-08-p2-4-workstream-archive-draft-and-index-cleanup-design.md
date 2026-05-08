本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P2-4 Workstream Archive Draft and Index Cleanup Design

---

## 大任务目标

1. Define the next controlled Workstream archive slice after read-only archive-candidates, without moving files before index cleanup rules are designed.

---

## 成功标准

1. active planning identifies archive draft/index cleanup boundaries, implementation prerequisites, verification scope, and the first safe code slice.

---

## 规划依据

列出当前大任务必须对齐的 reference 设计、路线或差距文档；只放路径和一句话用途，不复制详细规划。

- `reference/ACF_Top_Level_Design.md`：上位架构和边界。
- `reference/Product_Roadmap.md`：阶段路线和近期优先级。
- `reference/Top_Level_Implementation_Gap.md`：实现差距矩阵和当前 P2 backlog。
- `reference/Workstream_Lifecycle_Archive_Design.md`：Workstream archive/draft/index cleanup 设计边界。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Define archive draft and cleanup contract | 无。 | Updated lifecycle/gap design boundaries | Updated Workstream_Lifecycle_Archive_Design.md, Top_Level_Implementation_Gap.md, System_Manual.md, README.md and automation docs; docs/ai strict check passed. | 无。 |
| T002 | Done | Add archive draft and archive fixtures | T001 | Synthetic fixture expectations for archive-draft and explicit archive command | Added context_matrix archive fixture coverage plus CLI tests for archive-draft, explicit archive, blockers, missing index rows, duplicate index rows, and target conflicts. | 无。 |
| T003 | Done | Implement archive draft and explicit archive | T002 | archive-draft CLI, explicit workstream archive CLI, JSON contract, tests, docs | Implemented workstream archive-draft and explicit archive CLI with JSON contract, Archive_Index 7-column compatibility, index cleanup, marker block, and no new dependencies. | 无。 |
| T004 | Done | Verify version commit push | T003 | v0.0.3.33, full verification, commit and push | v0.0.3.33 set; unittest 199 passed; template check ok; docs/ai strict check ok; audit reviewed; minimal_smoke ok; upgrade_matrix quick ok; git diff --check ok. | 无。 |
| T005 | Done | Stabilize active-reference traceability | 无。 | Upgrade matrix, CLI boundary tests, and external dry-run validation summary | unittest 194 passed; template check ok; docs/ai strict check ok; audit context reviewed; upgrade_matrix quick ok; EcSOS/FCC dry-run summary recorded | 无。 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
