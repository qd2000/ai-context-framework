本文件记录项目当前阶段的有效上下文。

- 长期目标请查看：[reference/Project_Brief.md](../reference/Project_Brief.md)
- 当前具体任务请查看：[active/Current_Task.md](Current_Task.md)
- 本文件只维护当前阶段目标和当前有效事实

---

## 审阅标记

- Last reviewed: 2026-09-22 17:24
- Review scope: 文件级；WS018「公开仓库与 MIT 许可发布闭合」阶段 B 完成后的当前事实——`v0.0.3.97` 发布与 installed-state 证据已回填，`v0.0.3.98` 以 PEP 639 许可元数据发布并完成 tag / PyPI / 全局安装三项验证。

---

## 当前阶段

WS017「Runtime 缺陷与欠账修复」进入收口：修复 `scripts/worktree_release_smoke.py` 的运行态隔离缺口并补 3 项无污染回归（一次性全链路证据证明真实 `<ACF_HOME>/projects` 命名空间 created / removed 均为 `[]`）；新增 `acf clock now` 分钟级时间原语（纯函数命令模块 + runtime 组合注册，命令树快照 210 -> 212 且差异仅为 `clock` / `clock now` 两条路径）；校准 [reference/Top_Level_Implementation_Gap.md](../reference/Top_Level_Implementation_Gap.md) 六域矩阵中与代码、CHANGELOG、workflow 事实矛盾的行，并把「smoke 隔离」「CI 固定 SHA」两处过期缺陷更正为已实现。WS018「公开仓库与 MIT 许可发布闭合」已完成：仓库转为 public，master 与 `v*` tag 受 rulesets 保护，`pypi` environment 与 Trusted Publisher 绑定就位，`v0.0.3.97` 的发布与 installed-state 证据回填，`v0.0.3.98` 落地 PEP 639 许可元数据并完成发布与全局安装闭合。发布状态：`v0.0.3.97` 已闭合（release workflow #39，attempt 2 / success，tag 仍指向 `33163fc8`）；`v0.0.3.98` 已完成 tag（`1b115ed`）/ PyPI（`latest=0.0.3.98`）/ 全局安装（`acf v0.0.3.98`）三项验证，是当前稳定版本，并首次让 wheel/sdist 确定地携带 MIT 许可（`License-Expression: MIT`、wheel 的 `dist-info/licenses/LICENSE`、sdist 顶层 `LICENSE`）。当前存在一个 Active Workstream（WS018），收口后回到 global-only。

---

## 当前阶段目标

1. 验证本框架可以作为本仓库自身的 AI 上下文系统使用。
2. 用 `acf` 将模板生成、简化、完整度检查和结构化维护自动化，降低人工维护成本。
3. 让默认注意力入口始终低噪声、高权威、与当前任务相关。
4. 将 `acf` 逐步演进为可安装、可在任意目录调用、主要面向 AI 使用的上下文维护 CLI。

---

## 当前阶段范围

### 当前阶段要做

- 维护 `template/` 作为可复制的产品模板。
- 维护 `docs/ai/` 作为本仓库真实 dogfooding 上下文。
- 保持 CLI 无第三方运行依赖。
- 用检查命令发现结构漂移、断链、状态不一致和索引遗漏。
- 隔离测试运行态，治理跨项目 issue 与 usage log 生命周期。

### 当前阶段不做

- 不做常驻 agent runtime 或 scheduler。
- 不引入向量库、数据库或私有上下文存储。
- 不把 `acf` 做成通用 Markdown 编辑器。
- 不让 subagent 静默修改权威上下文。
- 不把 `template/` 的占位内容当作当前项目事实。

---

## 当前有效事实

### 核心事实

1. 本仓库维护模型无关、Markdown-first 的 AI 上下文管理框架；核心产品源是 `template/`，真实 dogfooding 实例是 `docs/ai/`。
2. `acf` 是主要面向 AI 的上下文维护 CLI；它负责确定性检查、生成、结构化编辑、归档、草案和审计，不替代人的事实判断，也不扩展为通用 Markdown 编辑器或常驻 runtime。
3. 当前发布版本不在 Context 中复制固定数字；以仓库根 `README.md`、`ai_context_framework/version.py`、`pyproject.toml`、`uv.lock` 与正式发布元数据为版本权威，安装态用 `acf --version` 验证。
4. 本仓库使用 uv Python 环境，Python 版本约束为 `>=3.10`；运行项目 Python 或 CLI 时优先使用 `uv run python ...` 和 `uv run acf ...`。
5. `docs/ai/` 当前应保持 `uv run acf check --strict` 通过；CLI 或模板行为变更后还应运行 `uv run acf check template`、`uv run python -m unittest`，必要时运行 upgrade matrix。
6. Observer 产品能力已从 ACF 核心退役：`acf observer` 只保留无副作用 `observer_retired` 墓碑；升级不会自动删除用户级 Observer 数据，历史证据保留在 archive 与 Git 历史中。

### 已落地能力摘要

1. 基础维护：`init`、`simplify`、`status`、`check`、`new ...`、`writeback draft`、`version show/set` 已形成可安装 CLI 主链路。
2. AI 友好契约：主要命令支持 `--json`、`--dry-run`、`--check-after`、稳定 `schema_version/ok/error_code/next_actions`、changed files 和分层退出码。
3. 安全编辑：`edit section get|replace|append` 与 `edit table upsert` 仅允许在 context root 内既有 Markdown 文件上做结构化修改。
4. 计划与历史：`plan`、`task`、`archive`、`decisions`、`knowledge`、`feedback`、`workstream` 系列已覆盖任务板、归档、Feedback 生命周期、index sync 和可选并行 Workstream 层。
5. 观测与评测：usage event log 默认开启并写入用户级目录；`acf log projects` 可只读盘点全局 usage log；`scripts/minimal_smoke.py` 与 `scripts/upgrade_matrix.py` 覆盖最小 smoke 与旧上下文升级兼容性。
6. 注意力治理：`review stale`、`audit context`、`curate draft`、`doctor` 提供机械 stale signal、active 污染候选、可审阅整理草案和跨文件健康诊断；CLI 不裁决事实真假。
7. 时间原语：`acf clock now` 以纯函数命令输出分钟级本地时间 `YYYY-MM-DD HH:MM`，供上下文「上次更新 / 上次修改」等字段引用；不依赖上下文目录、不读写文件，支持 `--json`。

### 当前进展与未完成项

1. WS014「Post-v0.0.3.92 Stabilization and Product Health」已完成实现、验收与归档（[archive/workstreams/WS014.md](../archive/workstreams/WS014.md)）。
2. WS015「发布链收口与 worktree 退役窄路径」已完成并归档（[archive/workstreams/WS015.md](../archive/workstreams/WS015.md)）：交付 `acf worktree retire` 窄路径与 `v0.0.3.95` 发布闭合，全局安装经 `scripts/update_acf.ps1` 更新并验证 `acf v0.0.3.95`。
3. 发布链失败的根因（WS014 引入的 `release.yml` verify 门禁在 Windows runner 上暴露的 3 处既有测试夹具缺陷：8.3 短路径别名让 overlap 竞态注入静默失效、install 脚本裸路径字符串比对、tearDown 临时目录被刚终止进程瞬时占用）已修复并随 `v0.0.3.95` 发布；`v0.0.3.93` 与 `v0.0.3.94` 保留为历史失败 tag，按不可变约定不改写。
4. 跨项目 issue：open 3 条——owner-context 真实链路复测、child effect 委派设计、历史 state-loss 事故复现确认；worktree curated handoff 退休已由 `v0.0.3.95` 收口为 resolved。
5. WS016「Runtime 全局注入解耦」已完成实现、验收与归档（[archive/workstreams/WS016.md](../archive/workstreams/WS016.md)）：导出 allowlist fail-closed、显式 RuntimeContext、parser composition、`acf.py` 收敛与 ADR-0007 全部落地，全套门禁 704 项全绿，版本收敛 `v0.0.3.96`。
6. owner-context 的 ACF 侧隔离验证已通过（`scripts/continuation_owner_fixture.py`）；真实网页工具链复测仍是待执行验收项，协议见 [reference/Continuation_Owner_Context_Verification.md](../reference/Continuation_Owner_Context_Verification.md)。
7. [active/Feedback_Inbox.md](Feedback_Inbox.md)：F015/F017 已转为 rules 条目并 Done，F019 已转为 Planned 并指向 ADR-0006 与后续 UX 计划。
8. WS017「Runtime 缺陷与欠账修复」已完成实现与门禁：运行态隔离修复与无污染回归、`acf clock now`、六域矩阵校准；`v0.0.3.97` 的 publish 作业曾因 GitHub 账户计费问题未启动，处置后 Re-run 成功（release workflow #39，attempt 2 / success），tag 未被移动，PyPI `0.0.3.97` 与全局安装均已验证。`.97` 的 wheel/sdist 不含 LICENSE、METADATA 无 License 字段（tag 早于 LICENSE 落地），因此不是许可完整版本。
9. WS018「公开仓库与 MIT 许可发布闭合」已完成：仓库 public、rulesets 与 `pypi` environment 就位；新增 PEP 639 `license = "MIT"` 与 `license-files = ["LICENSE"]`、setuptools 下限 `>=77.0.3`、`MANIFEST.in` 显式收录 LICENSE、`tests/test_release_license_metadata.py` 四项确定性回归；版本收敛 `v0.0.3.98` 并完成 tag / PyPI / 全局安装三项验证。
10. 后续独立候选：System Manual 共享区块同步机制、owner-context 真实网页链路复测、child effect 委派设计、历史 state-loss 事故复现确认、ADR-0006 的 ACF Core / Operations 分层落地。

### 默认索引

1. 产品目标和阶段路线：[reference/Project_Brief.md](../reference/Project_Brief.md)、[reference/Product_Roadmap.md](../reference/Product_Roadmap.md)。
2. 架构与边界：[reference/ACF_Top_Level_Design.md](../reference/ACF_Top_Level_Design.md)、[../Automation.md](../../Automation.md)、[reference/System_Manual.md](../reference/System_Manual.md)。
3. 实现差距与下一步：[reference/Top_Level_Implementation_Gap.md](../reference/Top_Level_Implementation_Gap.md)、[reference/Generated_Marker_Sync_Design.md](../reference/Generated_Marker_Sync_Design.md)、[reference/Doctor_Reconcile_Design.md](../reference/Doctor_Reconcile_Design.md)、[active/Task_Plan.md](Task_Plan.md)、[active/Feedback_Inbox.md](Feedback_Inbox.md)。
4. 决策与规则：[reference/Decisions_Index.md](../reference/Decisions_Index.md)、[rules/Project_Rules.md](../rules/Project_Rules.md)、[decisions/ADR-0003.md](../decisions/ADR-0003.md)、[decisions/ADR-0004.md](../decisions/ADR-0004.md)、[decisions/ADR-0005.md](../decisions/ADR-0005.md)、[decisions/ADR-0006.md](../decisions/ADR-0006.md)、[decisions/ADR-0007.md](../decisions/ADR-0007.md)。
5. 可复用经验与历史证据：[reference/Knowledge_Index.md](../reference/Knowledge_Index.md)、[worklog/Worklog_Index.md](../worklog/Worklog_Index.md)、[archive/Archive_Index.md](../archive/Archive_Index.md)；archive 默认不读，只有追溯历史时按需进入。

---

## 当前关键约束

1. 框架必须保持模型无关；权威上下文必须是普通 Markdown，并且可人工审阅。
2. CLI 不应引入第三方运行依赖；Python 命令应优先使用项目 uv 环境运行。
3. 自动化应优先做确定性检查和草案生成，不替代人的事实判断。
4. 涉及模板结构变更时，需要同时验证模板和 dogfooding 实例。
5. 新增或重置当前任务优先使用 `acf new task`；资料索引优先 `acf new source`；重要决策优先 `acf new adr`；当天记录优先 `acf new worklog`；回写建议优先 `acf writeback draft`。
6. 维护 `docs/ai/` 内已有 section 或 table 时优先使用 `acf edit` 的结构化写入；不为 dogfooding 临时放宽 `acf edit` 的 context-root 限制。
7. usage event log 是用户级运行态观测数据，不是权威上下文；日志写入失败不应影响原命令退出码。
8. Task_Plan 只保存当前大任务拆分、子任务状态、证据和下一步；详细过程进入 worklog，失效计划进入 archive；Knowledge 只能通过草案流程沉淀可迁移判断。

---

## 当前开放问题

1. 根薄入口生成是否需要支持少量用户自定义仓库规则字段。
2. 是否需要 writeback-curator subagent 生成更高质量的回写分类草案。
3. 是否需要为 `docs/ai/` 外的仓库级维护文档设计安全的 project-root scoped edit 能力，还是继续保持常规补丁维护。
4. 是否需要继续新增 weekly/report 创建命令，或保持 human layer 只通过 `new human-note` 写 Inbox。
5. 已落地：分钟级时间字段由 `acf clock now` 生成（输出本地 `YYYY-MM-DD HH:MM`，不依赖上下文目录、不写文件），格式规则仍见 [rules/Project_Rules.md](../rules/Project_Rules.md)。
6. ACF Core 与 Operations 控制面的边界如何在不拆包的前提下落地（ADR-0006 的设计结论）。
7. 下一阶段优先级：WS018 收口后，在 System Manual 共享区块同步机制、owner-context 真实网页链路复测、child effect 委派设计、历史 state-loss 事故复现确认之间选择（均由 Gap Matrix 记为需独立 Workstream 的候选）。

---

## 重要决策

重要决策请查看：[reference/Decisions_Index.md](../reference/Decisions_Index.md)。

---

## 当前相关路径

- 上下文目录：`docs/ai/`
- 产品模板目录：`template/`
- CLI 入口：`acf.py`（兼容 shim）；包实现：`ai_context_framework/`
- 当前大任务计划：[active/Task_Plan.md](Task_Plan.md)
- 自动化路线：[../Automation.md](../../Automation.md)

---

## 容易误解的地方

1. `template/` 是产品模板，不是本仓库当前事实源。
2. `docs/ai/` 是真实 dogfooding 实例，优先级高于模板占位内容。
3. worklog 是历史过程记录，不等于当前事实。
4. subagent 适合产出草案和审阅意见，不应默认静默落盘到权威上下文。

---

## 上次更新

- 日期：2026-09-22 17:24
- 更新原因：WS018「公开仓库与 MIT 许可发布闭合」阶段 B 完成——回填 `v0.0.3.97` 发布与 installed-state 证据，落地 PEP 639 `license = "MIT"` / `license-files = ["LICENSE"]` 与 setuptools 下限 `>=77.0.3`，新增 wheel/sdist 的 LICENSE 与 METADATA 确定性回归，版本收敛 `v0.0.3.98` 并完成 tag / PyPI / 全局安装三项验证。
