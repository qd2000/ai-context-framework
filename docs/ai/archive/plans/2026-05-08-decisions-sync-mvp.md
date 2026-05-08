本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

Decisions Sync MVP

---

## 大任务目标

1. Implement decisions sync by reusing generated marker helper without expanding archive sync.

---

## 成功标准

1. decisions sync dry-run/write handles generated marker block and preserves marker-outside content.
2. Regression tests cover missing marker, init marker, generated replacement, and JSON contract.
3. docs/ai checks and unit tests pass.

---

## 规划依据

列出当前大任务必须对齐的 reference 设计、路线或差距文档；只放路径和一句话用途，不复制详细规划。

- [reference/Generated_Marker_Sync_Design.md](../../reference/Generated_Marker_Sync_Design.md)：Decisions sync marker contract and first-version behavior。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Implement decisions sync MVP | 无。 | decisions sync command and marker integration | uv run python -m unittest; uv run acf check template --json; uv run acf check docs/ai --strict --json; uv run python scripts/minimal_smoke.py; uv run acf decisions sync docs/ai --dry-run --json | 无。 |

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
