本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P1 JSON Contract Consistency Tests

---

## 大任务目标

1. 根据 Top_Level_Implementation_Gap.md 的 P1-1 建立 AI-facing JSON 输出契约测试。
2. 覆盖代表性查询、检查、审计、升级、草案、Workstream 和 edit 命令的成功与失败 JSON 最小字段。
3. 只记录并守护当前兼容输出，不重排现有 JSON payload，不改变 CLI 行为。

---

## 成功标准

1. tests/test_cli.py 新增 JSON contract consistency helper 和代表性命令覆盖。
2. 验证 uv run python -m unittest、uv run acf check docs/ai --strict --json、uv run acf audit context docs/ai --json 通过。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T003 | Done | Cover representative failure payloads | T001 | check_failed/input_error/safety_refused/workstream_stage_active_conflict/curation_draft_exists contract tests | tests/test_cli.py#test_ai_facing_failure_json_contracts; acf.py check/status failure message payload | 无。 |
| T001 | Done | Add JSON contract test helper | Top_Level_Implementation_Gap.md P1-1 | Reusable helper asserting schema_version, ok, command/error_code/next_actions minimum contract | tests/test_cli.py; verification: targeted JSON contract tests, full unittest, check template, docs strict check, upgrade dry-run, minimal_smoke, upgrade_matrix quick, version show | 无。 |
| T002 | Done | Cover representative success payloads | T001 | Status/check/upgrade/audit/review/curate/workstream/edit success JSON contract tests | tests/test_cli.py#test_ai_facing_success_json_contracts | 无。 |

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
