本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P2 Top-Level Design Implementation Audit

---

## 大任务目标

1. 将 ACF 顶层设计逐项映射到当前实现，形成 gap-driven 实施依据。
2. 按 content model、object model、CLI、check、audit、sync、upgrade、tests 分层识别已实现、部分实现、未实现、不应实现、需补测试、需补文档和需补 upgrade 兼容项。
3. 基于差距矩阵排定下一批受控实施切片，避免继续零散扩展 audit 或随意新增规则。

---

## 成功标准

1. 生成 docs/ai/reference/Top_Level_Implementation_Gap.md，并包含证据、缺口、优先级和下一步。
2. 当前任务板 T001-T005 已建立，T001 完成后能指向下一步优先级。
3. 验证 uv run acf check docs/ai --strict --json 和 uv run acf audit context docs/ai --json 通过。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Map top-level requirements to current implementation | ACF_Top_Level_Design.md and Product_Roadmap.md are active planning baseline | Top_Level_Implementation_Gap.md initial matrix with evidence | docs/ai/reference/Top_Level_Implementation_Gap.md; verification: uv run acf check docs/ai --strict --json, uv run acf audit context docs/ai --json | 无。 |
| T003 | Done | Prioritize next implementation slices | T002 | P1/P2 ordered implementation recommendation | docs/ai/reference/Top_Level_Implementation_Gap.md#prioritized-next-slices | 无。 |
| T002 | Done | Identify gaps by implementation layer | T001 | Layered gap summary for content model, object model, CLI, check, audit, sync, upgrade and tests | docs/ai/reference/Top_Level_Implementation_Gap.md#layer-summary | 无。 |
| T004 | Done | Create implementation backlog | T003 | Backlog entries with acceptance and verification notes | docs/ai/reference/Top_Level_Implementation_Gap.md#prioritized-next-slices | 无。 |
| T005 | Done | Decide first code PR | T004 | First code PR decision with why/why-not alternatives | docs/ai/reference/Top_Level_Implementation_Gap.md#first-code-pr-decision | 下一步首选 JSON contract consistency tests。 |

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
