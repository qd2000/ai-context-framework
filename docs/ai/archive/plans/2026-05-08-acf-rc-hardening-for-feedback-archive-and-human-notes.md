本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

ACF RC hardening for feedback, archive, and human notes

---

## 大任务目标

1. 一次性实现 Feedback 生命周期、Task/Plan archive record marker 和 human-note，并打磨到可上线测试。

---

## 成功标准

1. 新增命令完成并有回归测试。
2. README、template manual 和 dogfooding 文档同步。
3. 完整 RC 验证通过。

---

## 规划依据

列出当前大任务必须对齐的 reference 设计、路线或差距文档；只放路径和一句话用途，不复制详细规划。

- 无。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Implement feedback lifecycle commands | 无。 | acf feedback list/triage/done/reject/archive-candidates/archive | Implemented in acf.py and covered by tests/test_cli.py. | 无。 |
| T002 | Done | Implement Task/Plan archive record marker | 无。 | ACF:ARCHIVE:RECORD marker and archive sync recovery | Implemented ACF:ARCHIVE:RECORD and archive sync recovery tests. | 无。 |
| T003 | Done | Implement human-note creation | 无。 | acf new human-note | Implemented acf new human-note and standard/minimal tests. | 无。 |
| T004 | Done | RC documentation and verification | 无。 | docs/version/verification evidence | uv run python -m unittest; uv run acf check docs/ai --strict --json; uv run acf check template --json; uv run python scripts/minimal_smoke.py --acf uv run acf | 无。 |

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

---

<!-- ACF:ARCHIVE:RECORD:START -->
- archived_at: 2026-05-08
- item_type: Plan
- item_id: ACF RC hardening for feedback, archive, and human notes
- source_path: active/Task_Plan.md
- archive_path: `archive/plans/2026-05-08-acf-rc-hardening-for-feedback-archive-and-human-notes.md`
- status: Archived
- archive_reason: ACF RC hardening v0.0.3.43 completed and verified.
<!-- ACF:ARCHIVE:RECORD:END -->
