本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Active

---

## 大任务名称

WS016 Runtime 全局注入解耦

---

## 大任务目标

1. 把 runtime 与 8 个 runtime_parts 之间的 __dict__ 双向合并收窄为显式 __acf_exports__ allowlist 合并，并对同名不同对象 fail-closed。
2. 用显式 RuntimeContext 取代 commands/workstream.py 的 28 处 per-call _bind，使命令模块与 runtime 之间只剩显式依赖。
3. 把 runtime.build_parser() 中内联的命令组分批下移为各模块自己的 register_*_parser，让 runtime.py 成为薄聚合层。
4. 移除 acf.py 对 runtime 私有全局的写入与手动 re-sync，改为显式 root 传递。
5. 全程保持对外 CLI 命令/参数/JSON 契约、退出码、help 文本与 usage log 隐私边界不变，并且不再用横向搬运满足 2000 行门禁。

---

## 成功标准

1. acf check template、acf check --strict、uv run python -m unittest（全量 680+ 项）、minimal_smoke、upgrade_matrix --mode full、release_check --mode package 全部通过。
2. ai_context_framework 包内所有模块 ≤2000 行、acf.py ≤100 行、包内模块不导入顶层 acf。
3. 新增导出名单快照回归与命令树形状快照回归：每个子命令的 dest/参数/默认值/help 文本被断言锁定；同名不同对象在合并期 fail-closed 且有专门回归。
4. 对外契约零变化：既有 JSON contract、smoke 场景与 upgrade matrix 无需修改即通过；仅“绑定实现细节”类断言可有意重写并单独记录。

---

## 规划依据

列出当前大任务必须对齐的 reference 设计、路线或差距文档；只放路径和一句话用途，不复制详细规划。

- [reference/Top_Level_Implementation_Gap.md](../reference/Top_Level_Implementation_Gap.md)：六域真实差距与 runtime 条目的当前状态。
- [reference/ACF_Top_Level_Design.md](../reference/ACF_Top_Level_Design.md)：模块边界与 CLI 分层上位约束。
- [reference/Architecture.md](../reference/Architecture.md)：当前模块依赖方向，重构后需同步。
- [reference/Product_Roadmap.md](../reference/Product_Roadmap.md)：阶段路线，确认本轮属内部重构而非新能力。
- [reference/System_Manual.md](../reference/System_Manual.md)：用户可见命令合同，重构不得改变。

---

## 当前焦点

T006

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | 建立 WS016 与任务结构 | 无。 | WS016 详情、范围声明、Task_Plan 与 Current_Task | reservation commit 2c441e0；WS016 detail + scope-add（37 read / 30 write）+ Task_Plan T001-T008 + 5 条规划依据；Current_Task 与 Context 已同步到 WS016 阶段。 | 进入 T002 allowlist 合并 |
| T002 | Done | __acf_exports__ allowlist 合并与同名冲突 fail-closed | T001 | runtime.py 合并逻辑收窄、8 个 runtime_parts 的显式导出声明 | runtime.py 的 _install_runtime_parts 改为委托 ai_context_framework/runtime_exports.py：只合并 RUNTIME_PART_EXPORTS 显式声明的 202 个名字；未声明 part 模块、声明名在模块中不存在、RUNTIME_PART_EXPORTS 声明了未接入模块、以及同名不同对象四种情况均 fail-closed（RuntimeExportError）。实测 runtime 公开名 769 -> 531、runtime.py 1988 -> 1979 行；PEP 562 的 archive_workstream.__getattr__ 惰性兼容转发按显式契约保留（acf.parse_workstream_archive_date 仍可解析）。 | 进入 T003 契约回归 |
| T003 | Done | 导出名单审计脚本与契约回归 | T002 | scripts/runtime_export_audit.py、tests/test_runtime_contracts.py 导出名单快照 | 新增 scripts/runtime_export_audit.py（ast 计算各 part 自有名与自由名、跨模块同名冲突、最小必需导出集、part 闭包与消费注入闭包、tests/scripts 对 runtime/acf 的动态属性访问）与 tests/test_runtime_contracts.py 9 项。实测：8 个 part 自有名 447，同名冲突 2（annotations/re，均为同对象），消费名 82 + 13，最小必需导出 202，收窄后注入 534（< 332 + 447），part 闭包/消费注入闭包/动态访问缺口全部为空。 | 进入 T004 RuntimeContext |
| T004 | Done | RuntimeContext 与移除 per-call _bind | T003 | ai_context_framework/runtime_context.py、workstream.py 与 workstream_reserve.py 去 per-call 绑定 | 新增 ai_context_framework/runtime_context.py：RuntimeContext（有界冻结上下文）+ WORKSTREAM_CONSUMER_NAMES(82) / WORKSTREAM_RESERVE_CONSUMER_NAMES(13) + build_runtime_context fail-closed。archive_workstream.workstream_deps 不再传 globals()（531 名）而是构建一次并缓存的有界 context；reserve 路径改用 13 名 + vars(workstream_commands) overlay。commands/workstream.py 的 28 处 per-call _bind 改为 _ensure_bound（首次绑定后冻结），_bind 的刷新语义与 _MODULE_OWNED_NAMES 遮蔽规则逐字保留。LSP 在本仓库无 Python documentSymbol provider，按 lsp-code-analysis 技能的回退规则改用既定 ast 静态分析作为等价证据（已核验所有对 workstream.py helper 的外部调用都先显式绑定，故冻结安全）。证据：unittest 692 项（292 CLI + 129 杂项 + 162 continuation + 109 worktree）、check template/strict 通过、minimal_smoke 8/8、upgrade_matrix full 28 fixtures 通过。 | 进入 T005 parser composition |
| T005 | Done | 分批 parser composition | T004 | 各命令模块 register_*_parser、runtime.build_parser 瘦身、命令树形状快照回归 | parser composition 全部完成：runtime.build_parser 内已无任何内联 subparsers.add_parser，改为 31 处 register_*_parser 组合调用；新增 ai_context_framework/cli_arguments.py（共享 add_json_argument/add_write_arguments）、commands/workstream_parsers.py（29 个 handler 显式映射 + 缺失校验）、commands/continuation_group_parsers.py。下移的命令组：review/audit/curate/doctor、linkify/link/edit、decisions、draft、feedback、human、writeback、task、archive、knowledge、plan、new、status/check/next/init/simplify/upgrade/links/log/version、workstream、worktree、continuation。常量迁到 constants.py 并由消费方直接导入：DEFAULT_STALE_DAYS、VALID_FEEDBACK_STATUSES、VALID_HUMAN_INDEX_STATUSES、VALID_KNOWLEDGE_STATUSES、VALID_MERGE_RESOLUTIONS、VALID_WORKSTREAM_{ATTENTION,STATUSES,TYPES}、VALID_SUBTASK_STATUSES、VALID_TASK_STATUSES、VALID_SOURCE_STATUSES、VALID_HUMAN_NOTE_STATUSES；runtime_parts/{check,doctor,knowledge_review,archive_workstream}.py 改为直接导入。关键语义：CLI 绑定的是 runtime_parts 的 deps 适配器而不是命令模块同名函数，因此 register_*_parser 必须显式注入 handler（命令树快照护栏首次运行即抓到 4 处漂移）。runtime.py 1988 -> 838 行（-57%）。顺带修复既有失败：README.md 缺失 ws003_acceptance 要求的 GlobalOnly 术语（自 c425410 起缺失）。证据：命令树快照 210 条路径零漂移，unittest 292(test_cli)+292(continuation/杂项)+100(worktree)+10(ws003)+8(package/契约) 全绿，check template、check --strict、minimal_smoke 8/8 通过。 | 进入 T006 收敛 acf.py shim：移除对 runtime 私有全局的写入与 re-sync。 |
| T006 | Done | 收敛 acf.py shim | T005 | acf.py 移除私有全局写入与 re-sync、显式 root 传递、相关 shim 测试重写 | acf.py 收敛完成：新增 runtime.set_root(root) 作为唯一公开的 ROOT 重绑定入口（设 ROOT 并同步各 runtime part），acf.py 不再写 runtime.ROOT、不再调用私有 _sync_runtime_part_globals，且只在 acf.ROOT 与 runtime.ROOT 实际不同时才同步（去掉了每次属性访问都无条件 re-sync 的行为）；runtime.main() 中冗余的 _sync_runtime_part_globals 调用移除（import 时安装已完成同步）。test_package_skeleton 断言按有意契约更新：新增 test_top_level_shim_does_not_write_runtime_internals 直接断言 shim 源码含 set_root、不含私有同步调用与私有全局写入，并改用 runtime.set_root 恢复 ROOT；配套修正审计脚本的误报：dynamic_access_gaps 排除 dunder 协议属性（__file__ 由模块系统提供，不是注入面缺口）。证据：test_runtime_contracts 12 项、test_package_skeleton 9 项、test_entrypoint_smoke、test_cli_surface_snapshot 与 test_cli 的两个 shim ROOT 用例全绿；uv run python acf.py version show --json 正常。 | 进入 T007 全量门禁、证据矩阵与文档同步。 |
| T007 | Pending | 全量门禁、证据矩阵与文档同步 | T006 | 六域 Gap Matrix 第 3 域、Architecture、Context 与 worklog | 无。 | 跑全量门禁并归档证据 |
| T008 | Pending | 授权收口与归档 | T007 | WS016 done、归档与 Context 收敛回 global-only | 无。 | 取得用户 closeout 授权后执行 |

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
