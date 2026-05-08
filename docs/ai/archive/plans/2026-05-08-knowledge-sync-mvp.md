本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

Knowledge Sync MVP

---

## 大任务目标

1. Implement generated marker helper and Knowledge sync MVP based on Generated_Marker_Sync_Design.

---

## 成功标准

1. knowledge sync can dry-run and write a generated Knowledge_Index marker block without touching marker-outside content.
2. JSON contract and regression tests cover missing marker, init marker, and generated table replacement.
3. docs/ai strict check and unit tests pass.

---

## 规划依据

列出当前大任务必须对齐的 reference 设计、路线或差距文档；只放路径和一句话用途，不复制详细规划。

- [reference/Generated_Marker_Sync_Design.md](../../reference/Generated_Marker_Sync_Design.md)：Knowledge sync MVP 的 marker 契约和验收依据。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Implement generated marker helper | 无。 | Reusable marker parse/replace helper and tests | acf.py marker helper and tests/test_cli.py generated marker coverage | 无。 |
| T002 | Done | Implement knowledge sync MVP | T001 | knowledge sync --dry-run/--init-marker/write path | acf knowledge sync docs/ai --init-marker --json | 无。 |
| T003 | Done | Document and verify knowledge sync | T002 | Docs, version, and verification evidence | uv run python -m unittest; uv run acf check template --json; uv run acf check docs/ai --strict --json; uv run python scripts/minimal_smoke.py; uv run acf knowledge sync docs/ai --dry-run --json | 无。 |

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
