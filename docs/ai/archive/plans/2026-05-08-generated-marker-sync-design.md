本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

Generated Marker Sync Design

---

## 大任务目标

1. Define the generated marker contract that must precede Knowledge, ADR, and Archive sync commands.

---

## 成功标准

1. Generated marker sync design exists as a reference document.
2. Roadmap and gap documents identify the next code slice after the design.
3. docs/ai strict check and audit remain clean.

---

## 规划依据

列出当前大任务必须对齐的 reference 设计、路线或差距文档；只放路径和一句话用途，不复制详细规划。

- [reference/Product_Roadmap.md](../../reference/Product_Roadmap.md)：阶段路线和剩余功能优先级。
- [reference/Top_Level_Implementation_Gap.md](../../reference/Top_Level_Implementation_Gap.md)：剩余实现缺口和下一代码切片依据。
- [reference/System_Manual.md](../../reference/System_Manual.md)：命令分层、marker 规范和 sync 边界。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Write generated marker sync design | 无。 | Generated marker design reference document | Added reference/Generated_Marker_Sync_Design.md defining marker contract, sync boundaries, deletion policy, JSON contract, tests, and next code slice. | 无。 |
| T002 | Done | Update roadmap and current facts | T001 | Roadmap, gap, System Manual, and Context point to the next code slice | Roadmap, gap, System Manual, Sources_Index, and Context now point from generated marker design to marker helper + Knowledge sync MVP; check/audit/review clean. | 无。 |

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
