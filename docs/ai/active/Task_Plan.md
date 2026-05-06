本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、状态、证据入口和下一步，不记录长过程、完整日志或详细推理

---

## 大任务状态

Active

---

## 大任务名称

P0 governance hardening: task-stage registry, workstream stage focus, authority write gate, merge resolution, active retention gate

---

## 大任务目标

1. 把 FCC dogfooding 暴露的阶段编号、Workstream 内部阶段焦点、Workstream 权威写入、合并结果和 active 滞留问题转成 `acf check --strict` 的确定性门禁。
2. 保持 ACF Markdown-first、模型无关、人工可审阅，不引入 agent runtime、数据库、向量库或自动事实裁决。
3. 第一阶段只做 P0 hardening；generated index 只在 Workstream 上先检测后 sync；content audit 独立后置，不进入默认 strict。

---

## 成功标准

1. `T001.4` 这类阶段编号必须在 `Task_Plan.md` 的 `## 任务阶段` 表注册；未注册引用在普通 check 和 strict check 中都失败。
2. `WS004.2` 这类 Workstream 内部阶段编号必须在对应 Workstream 详情文件的 `## 阶段` 表注册；`current_stage` 必须可机械校验。
3. Workstream 的 `owned` / `assigned` 写入范围不得直接命中 authority path；需要影响 authority 文件时必须使用 `merge_targets` 和合并请求。
4. Done / Cancelled workstream 留在 active 区域时有 `keep_active_reason`、`keep_active_until`；Done 有 evidence 和 `merge_resolution`。
5. Workstream index 与详情文件一致性先由 check 检测，再引入 `acf workstream sync --dry-run --json`。
6. 每个 PR 均通过基线验证命令。

---

## 当前焦点

T007

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Task Stage registry | 现有 Task_Plan / Current_Task 结构 | `## 任务阶段` 表、stage ID 检查、Current_Task 引用检查 | PR 1 implemented and verified: acf check docs/ai --strict, acf check template, upgrade dry-run, unittest, minimal smoke, quick upgrade matrix, py_compile | 无。 |
| T002 | Done | PR 1b: Workstream Stage Focus | T001 | `current_stage`、Workstream `## 阶段` 表、内部阶段注册和状态检查 | acf.py; tests/test_cli.py; README.md; template/reference/System_Manual.md; docs/ai/reference/Workstream_Design.md; worklog/daily/2026-05-06.md; verification: unittest, check template, strict docs check, upgrade dry-run, minimal smoke, quick upgrade matrix, py_compile | 无。 |
| T003 | Done | Workstream authority write gate + `merge_targets` | T002 | authority path 门禁、`merge_targets` metadata、错误码 | acf.py; tests/test_cli.py; README.md; template/reference/System_Manual.md; docs/ai/reference/Workstream_Design.md; docs/ai/reference/System_Manual.md; worklog/daily/2026-05-06.md; verification: unittest, check template, strict docs check, upgrade dry-run, minimal smoke, quick upgrade matrix, py_compile | 无。 |
| T004 | Done | Merge resolution + active retention gate | T003 | `merge_resolution`、`keep_active_reason`、`keep_active_until` 检查 | acf.py; tests/test_cli.py; README.md; template/reference/System_Manual.md; docs/ai/reference/Workstream_Design.md; docs/ai/reference/System_Manual.md; docs/ai/active/workstreams/WS001.md; worklog/daily/2026-05-06.md; verification: targeted PR3 tests, py_compile, unittest, check template, strict docs check, upgrade dry-run, minimal smoke, quick upgrade matrix | 无。 |
| T005 | Done | Workstream index consistency check, then sync | T004 | Workstreams 索引一致性检查；后续 sync dry-run | PR 4a/4b complete: acf.py; tests/test_cli.py; README.md; template/reference/System_Manual.md; docs/ai/reference/Workstream_Design.md; docs/ai/reference/System_Manual.md; docs/Automation.md; docs/ai/active/Workstreams.md; worklog/daily/2026-05-06.md; verification: sync targeted tests, unittest, check template, strict docs check, upgrade dry-run, minimal smoke, quick upgrade matrix, py_compile, workstream sync dry-run no-op after formal sync | 无。 |
| T006 | Done | Cross-project P0 hardening dogfooding on fcc_workspace | T001-T005 | fcc_workspace P0 hardening regression findings | worklog/daily/2026-05-06.md | 无。 |
| T007 | Pending | Authority path 前缀归一化补强 | T006 | Workstream assigned/owned claim docs/ai 前缀 authority path 时被 strict check 拒绝 | 无。 | 补 docs/ai/active/Context.md 与 docs/ai/active/Current_Task.md claim 的回归测试，再归一化 authority path 匹配。 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 非目标

本阶段不做：

1. 不新增 task object 单文件。
2. 不引入可配置 authority map。
3. 不让 generated index 覆盖 Knowledge / ADR / Archive。
4. 不把 content audit 接入默认 strict。
5. 不做自动事实裁决、自动语义去重或自动合并权威上下文。
6. PR 1b 不实现完整 `acf workstream stage` / `focus` 命令，只做注册和 check。

---

## 基线验证

每个 PR 至少运行：

```bash
uv run acf check template
uv run acf check docs/ai --strict --json
uv run acf upgrade docs/ai --dry-run --json
uv run python -m unittest
uv run python scripts/minimal_smoke.py --acf uv run acf
uv run python scripts/upgrade_matrix.py --mode quick
```

修改 `upgrade`、模板结构或默认检查语义时，再运行 full matrix。

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
