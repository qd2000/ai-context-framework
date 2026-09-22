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
4. 文档与版本四处一致为 v0.0.3.99。

---

## 规划依据

列出当前大任务必须对齐的 reference 设计、路线或差距文档；只放路径和一句话用途，不复制详细规划。

- [reference/Continuation_Control_Design.md](../reference/Continuation_Control_Design.md)：continuation 命令面、handoff drift 与接管语义上位约束。
- [reference/ACF_Top_Level_Design.md](../reference/ACF_Top_Level_Design.md)：模块边界与 CLI 分层上位约束。
- [reference/System_Manual.md](../reference/System_Manual.md)：用户可见命令合同，新增命令需同步。
- [../active/workstreams/WS019.md](../active/workstreams/WS019.md)：本轮 Workstream 唯一事实源。

---

## 当前焦点

T003

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | ownerless 接管模型层与命令实现 | 无 | ai_context_framework/continuation_handoff_review.py、commands/continuation_workspace.py、commands/continuation.py、commands/continuation_workspace_parsers.py、commands/continuation_group_parsers.py | 新增 continuation_handoff_review.py（build_handoff_review_bundle / paginate_review_bundle / validate_handoff_decisions / apply_handoff_review / build_takeover_receipt），drift 判定抽取 _drift_pairs 作为审查包与接管的单一真相源；doctor/_status 注入 handoff_reviewable 与审查摘要并追加 workspace_handoff_review_required；新增 review-handoff 命令（只读 + --draft-file 决策草稿 + 分组分页）；claim --handoff-review-file 在既有 state lock 内完成 13 项机械验证、应用决策、写 last_handoff_takeover.json、推进 generation 与建 lease，失败时不建 lease 且随事务回滚。为守住 agent-friendly 体积上限，命令层另拆出 continuation_handoff_review / continuation_journal / continuation_setup 三个适配器模块。 | 进入 T002 回归与 fail-closed 测试 |
| T002 | Done | 接管回归测试与命令树快照 | T001 | tests/test_continuation_handoff_takeover.py、tests/fixtures/cli_surface.json | 新增 tests/test_continuation_handoff_takeover.py 29 项：成功路径（20 文件批量分组审查 + 原子 claim + 字节/HEAD/status 不变 + 新 owner 可继续修改/revert/删除/checkpoint）、11 类 fail-closed（stale / runner 不一致 / scope 冲突 / conflict 未解释 / HEAD 未接受 / block / 决策不完整 / unresolved effect / 非 handoff lifecycle / lease 存在 / 无关 drift）与 4 项回归（unchanged dirty 直 claim、stale owner recovery、cleanup-only reconcile、legacy adoption），29 项全通过；命令树快照 --write 重建，新增 review-handoff 与 claim --handoff-review-file 参数且其余零漂移。continuation CLI 135 项、其余批次全绿。 | 进入 T003 文档同步与发布闭合 |
| T003 | Done | 文档同步、版本收敛与全量门禁 | T002 | WS019 详情与索引、Continuation_Control_Design.md、两份 System_Manual、docs/Automation.md、README、CHANGELOG、version.py | 创建 active/workstreams/WS019.md（含边界说明、目标、输出物、验证结果与证据）并用 `acf workstream sync` 同步 active/Workstreams.md（Active / 详情 26 项写入范围），Current_Task 绑定 WS019-T003，Task_Plan 切换为 WS019 子任务板；Continuation_Control_Design.md 命令面补 review-handoff 并在 handoff drift 段后写明"Agent 审查 + 原子接管 + 仍不可判断则 block"三条路径，两份 System Manual 与 docs/Automation.md、README 同步新命令、四种决策与 fail-closed 错误码语义；版本收敛 v0.0.3.99（version.py / pyproject.toml / uv.lock / PKG-INFO 四者一致，acf --version 输出 acf v0.0.3.99）+ CHANGELOG 条目；命令树快照重生成仅新增 review-handoff 与 claim --handoff-review-file。门禁：check template、check docs/ai --strict、minimal_smoke ok=true、unittest 分批全绿（接管 29 / continuation_cli 135 / 其余批次 166+323+70+36+14）、upgrade_matrix 与隔离安装通过、guard WS019 26 文件强验收 ok=true 零违规。追加：release_check 打包段构建 0.0.3.99 wheel/sdist 并在隔离环境安装 smoke 全绿（`acf v0.0.3.99`）；本地/远端 tag 与 PyPI 碰撞探测显示 0.0.3.99 未被占用；今日 worklog 与 Worklog_Index 经 scope-add 纳入写入边界后 guard 28 文件仍零违规。 | 取得发布授权后执行 commit、tag v0.0.3.99 与发布 |

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
