本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Active

---

## 大任务名称

跨项目 dogfooding 评测

---

## 大任务目标

1. 在临时或真实小项目中验证 acf init/status/check/new/edit/writeback/log 的完整使用路径。
2. 启用 usage event log，记录命令成功率、失败类型、dry-run 使用和 changed files 规模。
3. 根据评测结果形成后续功能排序建议。

---

## 成功标准

1. 至少完成一轮 init/status/check/new/edit/writeback/log 路径验证。
2. 记录成功命令、失败命令、失败原因和 AI 使用痛点。
3. 给出下一步优先级建议。

---

## 当前焦点

T004

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | 实现任务规划、归档、升级与 Knowledge 层增强 | 无。 | CLI、模板、文档和测试同步完成 | uv run acf check template; uv run acf check --strict; uv run python -m unittest | 无。 |
| T002 | Superseded | 执行跨项目 dogfooding 评测 | T001 | 评测记录和功能排序建议 | 已拆分为 T004/T006/T003/T005 | 按拆分后的评测子任务推进 |
| T003 | Pending | 验证 plan/task/archive/knowledge 路径 | T006 | 任务板、当前任务、归档和 Knowledge 草案评测记录 | 无。 | 使用新命令完成一轮维护流程 |
| T004 | Active | 准备临时评测项目和基线 | T001 | 临时项目路径和旧版/新版上下文基线 | 无。 | 创建隔离目录并准备命令清单 |
| T005 | Pending | 整理评测发现和优先级建议 | T003 | 问题清单、改进建议和后续功能排序 | 无。 | 汇总 usage log、worklog 和人工观察 |
| T006 | Pending | 验证 init/status/check/upgrade 路径 | T004 | 初始化、发现、检查和升级结果摘要 | 无。 | 运行 dry-run 与正式命令并记录 changed files |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
