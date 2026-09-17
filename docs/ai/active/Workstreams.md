本文件记录显式启用的并行 Workstream 索引。

Workstream 是可选并行目标线协议。启用后采用强隔离协作约束：详情文件 front matter 是唯一事实源，索引由工具同步，AI 执行前先读取专属 context packet，完成、ready、done 或切换状态前优先用 guard 的显式文件集模式检查本次改动。

默认读取规则：只有存在 Active、Blocked、ReadyToMerge 或 Merging workstream，或当前任务需要整理并行协作时，才读取本文件。没有这些状态时，本文件不进入默认上下文。

---

## Workstream 状态

Inactive

说明：当前没有 Active、Blocked、ReadyToMerge 或 Merging workstream。

---

## Workstreams

| ID | 状态 | 标题 | Owner | 写入范围 | 依赖 | 输出物 | 详情 |
|---|---|---|---|---|---|---|---|
| WS012 | Cancelled | Project Observer Operational Dogfood & Maintenance | ChatGPT | 详情(75 项) |  | docs/ai/reference/ws012_project_observer_operational_dogfood/ | active/workstreams/WS012.md |

---

## 使用规则

1. 本索引只保留低噪音摘要，由 `acf workstream sync` 从详情 front matter 同步。
2. 写入范围超过 3 项时，索引只显示 `详情(N 项)`；完整 machine scope 始终从对应详情 front matter 读取。
3. 单个 Workstream 详情文件是该 Workstream 的唯一事实源。
4. Task / Merge / Maintenance 三类 Workstream 权限不同；Task 不直接写 authority 文件。
5. Active 类 Workstream 默认禁止重叠 `owned:` 写入；共享文件必须显式 `shared:` 并设置 merge_owner 或 serial coordination。
6. AI 执行前运行 `acf workstream context WSxxx`，完成、ready、done 或切换状态前优先运行 `acf workstream guard WSxxx --files <本次修改文件...> --json`；裸 guard / `--from-git` 只用于快速查看当前 git diff，旧式整工作区排他检查需显式使用 `--workspace --strict-workspace`。
7. ReadyToMerge 表示任务产物完成；Done 表示合并或处置完成。
8. Done / Cancelled workstream 只在当前计划仍需解释时保留在 active 区域。
9. 当前计划结束后，Done / Cancelled workstream 应归档到 archive/workstreams。
