本文件记录项目当前阶段的有效上下文。

- 长期目标请查看：[reference/Project_Brief.md](../reference/Project_Brief.md)
- 当前具体任务请查看：[active/Current_Task.md](Current_Task.md)
- 本文件只维护当前阶段目标和当前有效事实

---

## 审阅标记

- Last reviewed: 2026-09-18 19:52
- Review scope: 文件级；WS015 启动后的当前事实。

---

## 当前阶段

WS015「发布链收口与 worktree 退役窄路径」正在执行：闭合 `v0.0.3.93` tag 已推送但 PyPI 未发布的发布链，并落地 `acf worktree retire` 窄路径。本轮不新增通用产品能力；runtime 全局注入解耦、child effect 委派、owner-context 真实链路复测仍属后续独立工作。

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

### 当前进展与未完成项

1. WS014「Post-v0.0.3.92 Stabilization and Product Health」已完成实现、验收与归档（[archive/workstreams/WS014.md](../archive/workstreams/WS014.md)）；其子任务板已移入 `archive/plans/` 保留追溯。
2. WS015「发布链收口与 worktree 退役窄路径」进行中：已实现 `acf worktree retire`——只移除 worktree 工作目录与 registry 记录、永不删除分支或 Git 引用、要求显式 `--disposition curated_handoff` 与非空 `--evidence-ref`，并保持 `acf worktree close` 的 merged-only 硬门不变；回归见 `tests/test_worktree_retire.py`。用户可见文档、六域 Gap Matrix、Roadmap 与 CHANGELOG 已同步，版本已收敛到 `v0.0.3.94`。
3. `v0.0.3.93` 的 tag 已推送到远端且指向 master HEAD，但 PyPI 上仍无该版本；本地制品复现（wheel + sdist 隔离安装）证明失败不在代码与制品层。`v0.0.3.94` 的 commit / tag / push（触发 PyPI 发布）与全局安装更新仍在等待明确授权后执行。
4. 跨项目 issue 首轮 triage 后 open 4 条：其中 `d33a11a387320d21a862`（worktree curated handoff 退休）已具备实现与回归证据，待发布后用 `v0.0.3.94` 证据正式 resolve；其余 3 条为 owner-context 真实链路复测、child effect 委派设计、历史 state-loss 事故复现确认。
5. owner-context 的 ACF 侧隔离验证已通过（`scripts/continuation_owner_fixture.py`）；真实网页工具链复测仍是待执行验收项，协议见 [reference/Continuation_Owner_Context_Verification.md](../reference/Continuation_Owner_Context_Verification.md)。
6. [active/Feedback_Inbox.md](Feedback_Inbox.md)：F015/F017 已转为 rules 条目并 Done，F019 已转为 Planned 并指向 ADR-0006 与后续 UX 计划。
7. 后续独立候选：runtime 全局注入解耦（export allowlist → 显式 RuntimeContext → parser composition）、System Manual 共享区块同步机制、分钟级时间字段的 CLI 自动生成能力。

### 默认索引

1. 产品目标和阶段路线：[reference/Project_Brief.md](../reference/Project_Brief.md)、[reference/Product_Roadmap.md](../reference/Product_Roadmap.md)。
2. 架构与边界：[reference/ACF_Top_Level_Design.md](../reference/ACF_Top_Level_Design.md)、[../Automation.md](../../Automation.md)、[reference/System_Manual.md](../reference/System_Manual.md)。
3. 实现差距与下一步：[reference/Top_Level_Implementation_Gap.md](../reference/Top_Level_Implementation_Gap.md)、[reference/Generated_Marker_Sync_Design.md](../reference/Generated_Marker_Sync_Design.md)、[reference/Doctor_Reconcile_Design.md](../reference/Doctor_Reconcile_Design.md)、[active/Task_Plan.md](Task_Plan.md)、[active/Feedback_Inbox.md](Feedback_Inbox.md)。
4. 决策与规则：[reference/Decisions_Index.md](../reference/Decisions_Index.md)、[rules/Project_Rules.md](../rules/Project_Rules.md)、[decisions/ADR-0003.md](../decisions/ADR-0003.md)、[decisions/ADR-0004.md](../decisions/ADR-0004.md)、[decisions/ADR-0005.md](../decisions/ADR-0005.md)、[decisions/ADR-0006.md](../decisions/ADR-0006.md)。
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
5. 是否为分钟级时间字段提供 CLI 自动生成能力（格式规则已落地，见 [rules/Project_Rules.md](../rules/Project_Rules.md)）。
6. ACF Core 与 Operations 控制面的边界如何在不拆包的前提下落地（ADR-0006 的设计结论）。

7. `v0.0.3.93` 的 GitHub Actions 发布 run 究竟是等待 `pypi` 环境审批还是失败，需在仓库侧确认；该结论决定是否需要修发布配置，且不影响既有 tag 的不可变性。
8. `v0.0.3.94` 的 PyPI 发布、全局安装更新与 issue `d33a11a387320d21a862` 的正式收口，都取决于同一项用户授权。

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

- 日期：2026-09-18 21:12
- 更新原因：WS015 实现与本地验收完成——落地 `acf worktree retire` 与回归测试、同步用户可见文档与六域差距记录、版本收敛到 `v0.0.3.94`；发布与全局安装等待明确授权。
