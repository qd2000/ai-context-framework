本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P1 Workstream Stage Flow Fixture

---

## 大任务目标

1. 根据 Top_Level_Implementation_Gap.md 的 P1-2 补充 Workstream stage flow synthetic fixture。
2. 覆盖 stage add/list/focus/done、focus 多 Active 拒绝、done evidence 和 clear-current。
3. 扩展 minimal_smoke，明确覆盖 workstream sync dry-run no-op 和 audit context clean。

---

## 成功标准

1. tests/fixtures/context_matrix/workstream_stage_flow 已建立。
2. tests/test_context_matrix.py 覆盖该 fixture 的 strict/sync/audit/stage flow 行为。
3. scripts/minimal_smoke.py 明确验证 stage flow、sync dry-run no-op 和 audit context clean。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Add workstream_stage_flow fixture | Top_Level_Implementation_Gap.md P1-2 | tests/fixtures/context_matrix/workstream_stage_flow | tests/fixtures/context_matrix/workstream_stage_flow/metadata.json | 无。 |
| T002 | Done | Cover fixture in context_matrix tests | T001 | tests/test_context_matrix.py stage flow coverage | tests/test_context_matrix.py#test_workstream_stage_flow_fixture_exercises_stage_commands | 无。 |
| T003 | Done | Extend minimal smoke sync and audit checks | T002 | scripts/minimal_smoke.py covers workstream sync no-op and audit clean | scripts/minimal_smoke.py workstream sync no-op and audit clean assertions | 无。 |

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
