本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P2 Workstream Lifecycle Archive Design

---

## 大任务目标

1. 根据顶层设计和 gap audit，收敛 Workstream Done/Cancelled 从 active 保留到 archive 的生命周期 helper 边界。
2. 先补设计和 synthetic fixture，证明第一版不误归档仍被当前计划需要解释的 Workstream。

---

## 成功标准

1. 新增 Workstream lifecycle/archive 设计文档并同步路线入口。
2. 新增 context_matrix fixture/test 覆盖 retained terminal Workstream 和 expired keep-active 边界。
3. strict check、audit context 和相关单元测试通过；本轮不改变 CLI 行为，不 bump 版本。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Define Workstream archive helper boundary | Top_Level_Implementation_Gap.md P2-2 | Workstream_Lifecycle_Archive_Design.md | reference/Workstream_Lifecycle_Archive_Design.md defines conservative archive helper boundary: candidates/draft before moving files. | 无。 |
| T002 | Done | Add lifecycle fixture coverage | T001 | workstream_lifecycle_archive context_matrix fixture and tests | tests/fixtures/context_matrix/workstream_lifecycle_archive and test_context_matrix lifecycle test cover retained terminal Workstream, current execution line rejection and expired keep-active. | 无。 |
| T003 | Done | Sync roadmap docs and verify | T002 | roadmap/gap/system manual updates and verification | P2 Workstream lifecycle/archive design and fixture complete; no CLI behavior change, no version bump. | 无。 |

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
