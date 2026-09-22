本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Active

---

## 大任务名称

WS019 Ownerless dirty WIP agent-first takeover

---

## 大任务目标

1. 默认继续 fail-closed：ownerless 期间的未知 task-owned WIP 漂移仍阻塞 claim，新增 `workspace_handoff_review_required` 原因码。
2. 新增 `acf continuation workspace review-handoff`：只读生成按文件指纹绑定的审查包与决策草稿。
3. `claim --handoff-review-file` 在同一 state lock 内完成机械验证、应用决策、写 receipt、推进 generation 与建 lease。
4. 文档、版本与全量门禁同步闭合。

---

## 成功标准

1. check template、check docs/ai --strict、unittest、upgrade_matrix 与隔离安装门禁全部通过。
2. 审查包与原子接管的 observation digest 失配、runner 不一致、scope 冲突等 11 类 fail-closed 路径全部有稳定错误码与回归。
3. 接管全程不改工作区字节、不改 HEAD、不先建 lease。
4. 文档与版本四处一致为 v0.0.3.100。

---

## 规划依据

列出当前大任务必须对齐的 reference 设计、路线或差距文档；只放路径和一句话用途，不复制详细规划。

- [reference/Continuation_Control_Design.md](../../reference/Continuation_Control_Design.md)：continuation 命令面、handoff drift 与接管语义上位约束。
- [reference/ACF_Top_Level_Design.md](../../reference/ACF_Top_Level_Design.md)：模块边界与 CLI 分层上位约束。
- [reference/System_Manual.md](../../reference/System_Manual.md)：用户可见命令合同，新增命令需同步。
- [../workstreams/WS019.md](../workstreams/WS019.md)：本轮 Workstream 唯一事实源（已归档）。

---

## 当前焦点

T003

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | ownerless 接管模型层与命令实现 | 无 | ai_context_framework/continuation_handoff_review.py、commands/continuation_workspace.py、commands/continuation.py、commands/continuation_workspace_parsers.py、commands/continuation_group_parsers.py | 新增 continuation_handoff_review.py（build_handoff_review_bundle / paginate_review_bundle / validate_handoff_decisions / apply_handoff_review / build_takeover_receipt），drift 判定抽取 _drift_pairs 作为审查包与接管的单一真相源；doctor/_status 注入 handoff_reviewable 与审查摘要并追加 workspace_handoff_review_required；新增 review-handoff 命令（只读 + --draft-file 决策草稿 + 分组分页）；claim --handoff-review-file 在既有 state lock 内完成 13 项机械验证、应用决策、写 last_handoff_takeover.json、推进 generation 与建 lease，失败时不建 lease 且随事务回滚。为守住 agent-friendly 体积上限，命令层另拆出 continuation_handoff_review / continuation_journal / continuation_setup 三个适配器模块。 | 进入 T002 回归与 fail-closed 测试 |
| T002 | Done | 接管回归测试与命令树快照 | T001 | tests/test_continuation_handoff_takeover.py、tests/fixtures/cli_surface.json | 新增 tests/test_continuation_handoff_takeover.py 29 项：成功路径（20 文件批量分组审查 + 原子 claim + 字节/HEAD/status 不变 + 新 owner 可继续修改/revert/删除/checkpoint）、11 类 fail-closed（stale / runner 不一致 / scope 冲突 / conflict 未解释 / HEAD 未接受 / block / 决策不完整 / unresolved effect / 非 handoff lifecycle / lease 存在 / 无关 drift）与 4 项回归（unchanged dirty 直 claim、stale owner recovery、cleanup-only reconcile、legacy adoption），29 项全通过；命令树快照 --write 重建，新增 review-handoff 与 claim --handoff-review-file 参数且其余零漂移。continuation CLI 135 项、其余批次全绿。 | 进入 T003 文档同步与发布闭合 |
| T003 | Done | 文档同步、版本收敛与全量门禁 | T002 | WS019 详情与索引、Continuation_Control_Design.md、两份 System_Manual、docs/Automation.md、README、CHANGELOG、version.py | commit 3451cbe / tag v0.0.3.100 指向 99f49fd；release #42 全绿，PyPI latest=0.0.3.100，全局安装 acf v0.0.3.100 | 无。 |

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
- archived_at: 2026-09-23
- item_type: Plan
- item_id: WS019 Ownerless dirty WIP agent-first takeover
- source_path: active/Task_Plan.md
- archive_path: `archive/plans/2026-09-23-ws019-ownerless-dirty-wip-agent-first-takeover.md`
- status: Archived
- archive_reason: WS019 已 Done 并归档；T001-T003 全部 Done 且 v0.0.3.100 已发布到 PyPI，terminal plan 归档以移出 active 上下文
<!-- ACF:ARCHIVE:RECORD:END -->
