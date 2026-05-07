本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P2 Task Stage CLI

---

## 大任务目标

1. 根据顶层设计和 gap audit，将已有 Task Stage registry 从手写表推进到受控 CLI 薄切片。
2. 实现 plan stage add/set/done 的确定性表格维护，不改变 Current_Task 或 Workstream 语义边界。

---

## 成功标准

1. 新增 Task Stage CLI 有 JSON/dry-run/error recovery 测试和文档。
2. strict check、audit、smoke、upgrade matrix 回归通过。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Define Task Stage CLI contract | Top_Level_Implementation_Gap.md P2-1 | add/set/done command boundary and tests shape | Task Stage CLI contract fixed: table-only command family, no Current_Task/Workstream automation. | 无。 |
| T002 | Done | Implement plan stage commands | T001 | acf plan stage add/set/done | acf.py implements plan stage list/add/set/done; tests cover command flow, invalid parent, duplicate id and Workstream owner validation. | 无。 |
| T003 | Done | Add tests, docs and version bump | T002 | unit tests, smoke/gap docs, README/System Manual and v0.0.3.29 | P2 Task Stage CLI complete: acf plan stage list/add/set/done, task_stage_registry fixture, minimal smoke Task Stage path, docs and v0.0.3.29 version metadata. | 无。 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| T003.1 | Done | T003 | release verification | 无。 | 无。 | verification evidence and version bump | unittest; check template; docs/ai strict check; audit context; upgrade dry-run; version show; minimal_smoke; upgrade_matrix quick/full; py_compile; git diff --check | 无。 |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
