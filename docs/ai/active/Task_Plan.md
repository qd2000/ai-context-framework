本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P1 Upgrade Matrix Expansion

---

## 大任务目标

1. 根据 Top_Level_Implementation_Gap.md 的 P1-3 扩展 upgrade compatibility matrix。
2. 覆盖旧 Workstream optional/no-current-stage、旧 ADR 无 front matter、自定义 AGENTS 与缺失 reference 文件组合。
3. 只补测试 fixture 和 runner 断言，不改变 upgrade 语义。

---

## 成功标准

1. tests/fixtures/upgrade_matrix 覆盖新增旧形态。
2. scripts/upgrade_matrix.py 能验证 optional Workstream 不自动启用、Workstream sync no-op、custom docs marker 和缺失 reference 组合。
3. quick/full upgrade matrix 均通过。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T003 | Done | Verify quick and full upgrade matrix | T002 | upgrade_matrix quick/full verification | uv run python scripts/upgrade_matrix.py --mode quick; uv run python scripts/upgrade_matrix.py --mode full; tests/test_upgrade_matrix.py | 无。 |
| T002 | Done | Add new upgrade compatibility fixtures | T001 | upgrade_matrix fixtures for Workstream, ADR and custom AGENTS reference combo | tests/fixtures/upgrade_matrix/old_without_workstreams_optional; old_workstreams_without_current_stage; old_adr_without_front_matter; custom_agents_missing_reference_combo | 无。 |
| T001 | Done | Extend upgrade matrix runner assertions | Top_Level_Implementation_Gap.md P1-3 | scripts/upgrade_matrix.py supports expected_absent/features/sync checks | scripts/upgrade_matrix.py expected_absent/features/changed suffix/workstream sync assertions | 无。 |

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
