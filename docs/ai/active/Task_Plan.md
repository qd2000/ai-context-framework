本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Active

---

## 大任务名称

WS017 Runtime 缺陷与欠账修复

---

## 大任务目标

1. 修复 worktree_release_smoke 的 ACF_HOME 运行态污染缺口并补无污染回归。
2. 新增分钟级时间生成命令 acf clock now。
3. 校准六域 Gap Matrix 第 4/5 域过期行。
4. 闭合 v0.0.3.96 发布，并以 v0.0.3.97 发布本轮变更。

---

## 成功标准

1. check template、check docs/ai --strict、unittest、minimal_smoke、upgrade_matrix 全部通过。
2. 真实运行态命名空间集合在隔离脚本运行前后完全一致。
3. clock now 输出恰为分钟级本地时间且可在无上下文目录调用。
4. PyPI 可见版本与已安装入口版本一致。

---

## 规划依据

列出当前大任务必须对齐的 reference 设计、路线或差距文档；只放路径和一句话用途，不复制详细规划。

- [reference/Top_Level_Implementation_Gap.md](../reference/Top_Level_Implementation_Gap.md)：六域真实差距与下一批候选。
- [reference/ACF_Top_Level_Design.md](../reference/ACF_Top_Level_Design.md)：模块边界与 CLI 分层上位约束。
- [reference/System_Manual.md](../reference/System_Manual.md)：用户可见命令合同，新增命令需同步。

---

## 当前焦点

T005

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | 修复 worktree_release_smoke 运行态隔离并补无污染回归 | 无 | scripts/worktree_release_smoke.py 注入隔离 ACF_HOME、tests/test_smoke_isolation.py 增加隔离注入断言 | worktree_release_smoke.py 新增 isolated_acf_home_env 与 isolated_runtime_state context manager，run() 统一传入 env=_RUN_ENV，git 与 acf 子进程全部走隔离运行态，main() 用 with isolated_runtime_state(temp) 包裹生命周期；tests/test_smoke_isolation.py 新增 3 项确定性回归（隔离 env 指向运行根目录、AST 断言每个 subprocess.run 都传 env、子进程实际收到隔离 ACF_HOME），0.027s 通过；一次性全链路证据：脚本 exit=0、ok=true、worktree_closed=true，真实运行态 project namespace created=[] / removed=[]；guard WS017 显式文件集强验收 ok=true。 | 进入 T002 新增 acf clock now |
| T002 | Done | 新增 acf clock now 命令与组合注册 | T001 | ai_context_framework/commands/clock.py 与 runtime.build_parser 组合注册 | 新增 ai_context_framework/commands/clock.py（纯函数叶子模块：local_now / utc_offset_value / clock_now_payload / clock_now_command / register_clock_parser），runtime.build_parser 用 clock_commands.register_clock_parser(..., now_handler=clock_commands.clock_now_command) 显式注入注册，符合 ADR-0007 组合契约；未新增 runtime_parts 导出面（runtime_export_audit 仍 narrowing closed，无新增缺口）。tests/test_clock.py 7 项通过：已知时刻的分钟级输出、负半小时偏移 +05 -> -05:30、真实当前时刻格式与偏移、人读输出为裸时间戳、JSON 满足 AI-facing 契约、runtime 绑定 handler 身份、以及无上下文目录的子进程调用。实测人读 2026-09-20 18:06，JSON 含 datetime/date/time/utc_offset/iso_local/utc 与标准契约字段。 | 进入 T003 快照、契约与双份文档同步 |
| T003 | Done | 命令树快照、契约测试与双份文档同步 | T002 | tests/fixtures/cli_surface.json、tests/test_clock.py、tests/test_cli.py、两份 System_Manual、README、CHANGELOG | 命令树快照有意重生成（-write），210 -> 212 条路径，差异仅为新增 clock 与 clock now 两条；tests/test_cli.py 的 AI-facing 成功契约用例新增 clock now 并整体通过（16.7s OK）；双份 System Manual（docs/ai/reference 与 template/reference）、README 常用命令示例与说明、docs/Automation.md 均已同步；check template 与 check docs/ai --strict 全绿；WS017 写入边界用 scope-add 纳入 docs/Automation.md 后，guard 显式文件集强验收 ok=true、零违规。 | 进入 T004 六域 Gap Matrix 过期行校准 |
| T004 | Done | 六域 Gap Matrix 域 4/5 过期行校准 | T003 | reference/Top_Level_Implementation_Gap.md 的第 4/5 域与下一批候选清单 | 用 code-explorer 逐条取证后校准六域矩阵：第 4 域「test / smoke 运行态隔离」由 缺陷 改为 已实现（v0.0.3.93 落地，WS017 补齐 worktree_release_smoke 同类实例），并把 release_check 仓库门禁段作为观测项保留而非本轮修复；「跨项目 issue 生命周期」与第 6 域「跨项目 open issue 收口」的 open 计数由 4 更正为 3（curated handoff 以 git:17024d2 + pypi:0.0.3.95 resolve）；第 5 域 CI 由 部分 改为 已实现（checkout 固定 3d3c42e5aac5…、setup-uv 08807647e706…、tests/package 双 job os 矩阵含 windows-latest、release 以 verify: uses ci.yml + needs verify 为必需门禁）；「版本收敛与发布闭合」更新为 v0.0.3.96 事实并在发布闭合后改写为 缺口 无；「发布链」缺口同步；第 3 域命令树快照路径数 210 -> 212；头部状态与 Next Code PR Decision 候选清单同步到 WS017。check docs/ai --strict 与 guard 文件集强验收全绿。 | 进入 T005 版本收敛、全量门禁与收口 |
| T005 | Done | v0.0.3.97 版本收敛、全量门禁与收口 | T004 | 版本文件、CHANGELOG、发布与已安装验证、WS017 收口归档 | 版本收敛 v0.0.3.97（version.py / pyproject.toml / uv.lock / PKG-INFO 四者一致）+ CHANGELOG 条目 + README 推荐版本由 v0.0.3.92 收敛为 v0.0.3.97；不可变 tag v0.0.3.97 已推送并由 release workflow 复用 ci.yml 执行跨平台发布门禁（本机无法读取私有仓库 Actions 结论，发布证据以 PyPI 与已安装入口为准）。门禁：check template、check docs/ai --strict、minimal_smoke 8/8、unittest 345 项（53 相关批次 + 292 test_cli）、runtime export audit narrowing closed、guard 显式文件集零违规。收口：merge-request（Context / Task_Plan / Current_Task 三个 authority 目标）→ ready → done（merge_resolution=merged）→ archive，审批按指纹逐次重记；Current_Task 清空、Workstreams 索引同步为 Inactive、status 回到 global-only。 | 取得发布授权后执行 |

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
