本文件记录显式启用的并行 Workstream 索引。

Workstream 是可选并行目标线协议，不是 agent runtime、调度器或权限系统。

默认读取规则：只有存在 Active、Blocked 或 ReadyToMerge workstream，或当前任务需要整理并行协作时，才读取本文件。没有这些状态时，本文件不进入默认上下文。

---

## Workstream 状态

Inactive

说明：当前没有 Active、Blocked 或 ReadyToMerge workstream。

---

## Workstreams

| ID | 状态 | 标题 | Owner | 写入范围 | 依赖 | 输出物 | 详情 |
|---|---|---|---|---|---|---|---|
| WS001 | Done | Workstream dogfooding gate | 主 agent | owned: [active/workstreams/WS001.md](workstreams/WS001.md), authority: [active/Workstreams.md](Workstreams.md), authority: [active/Task_Plan.md](Task_Plan.md), authority: docs/ai/AGENTS.md, authority: [template/AGENTS.md](../../../template/AGENTS.md), authority: docs/ai/reference/System_Manual.md, authority: [template/reference/System_Manual.md](../../../template/reference/System_Manual.md) | T002,T003,T005,T006 | docs/ai 最小 Workstream 试运行记录与验收结论 | [active/workstreams/WS001.md](workstreams/WS001.md) |

---

## 使用规则

1. 本索引只保留低噪音摘要。
2. 单个 Workstream 详情文件是该 Workstream 的事实源。
3. Done / Cancelled workstream 只在当前计划仍需解释时保留在 active 区域。
4. 当前计划结束后，Done / Cancelled workstream 应归档到 archive/workstreams。
