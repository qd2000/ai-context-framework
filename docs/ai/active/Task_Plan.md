本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P2 Workstream Archive Candidates

---

## 大任务目标

1. Implement the first read-only Workstream archive lifecycle helper from the top-level design gap audit.

---

## 成功标准

1. acf workstream archive-candidates reports safe candidates and blockers without writing files, with tests, docs, and version updated.

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Define archive-candidates contract | 无。 | Read-only command contract | acf.py; tests/test_cli.py; tests/test_context_matrix.py | T002 owns CLI regression coverage |
| T002 | Done | Implement archive-candidates CLI | T001 | Command, JSON output, tests | tests/test_cli.py; tests/test_context_matrix.py; scripts/minimal_smoke.py | T003 owns docs/version/final verification |
| T003 | Done | Sync docs version verification | T002 | Docs, version, verification, commit | unittest; minimal_smoke; check template; check docs/ai --strict; audit context; upgrade dry-run; diff --check | Commit and push P2-3 |

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
