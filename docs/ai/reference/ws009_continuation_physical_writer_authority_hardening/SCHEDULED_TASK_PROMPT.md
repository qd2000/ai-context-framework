# WS009 Standard Scheduled Task Wrapper

本文件是 WS009 可直接复制到外部 Scheduled Task 的薄 wrapper。

它不是任务计划事实源，也不复制 generic continuation 状态机。WS009 任务目标、问题矩阵、优先级、阶段、解决策略和成功标准以 `PLAN.md` 与 Workstream 当前状态为准；generic claim/recovery/workspace/effect 协议以每轮 `acf continuation prompt` 输出为唯一权威。

---

## Prompt

持续推进 ACF WS009「Continuation physical-writer and authority-drift hardening」。

每次运行都是独立无人值守执行轮次。不要依赖网页聊天历史恢复任务状态；本地 Git、Workstream、PLAN、continuation state、tests/evidence 和当前已安装稳定 ACF 是执行事实源。

固定身份：

- Project：`D:\PROJECT\Tools\ai-context-framework`
- Worktree：`D:\PROJECT\Tools\ai-context-framework_worktrees\ws009-continuation-physical-writer-authority-hardening`
- Branch：`codex/ws009-continuation-physical-writer-authority-hardening`
- Workstream：`WS009`
- Continuation task-id：`WS009`
- Plan：`docs/ai/reference/ws009_continuation_physical_writer_authority_hardening/PLAN.md`

每轮先使用 @DevSpace Local 打开上述固定 worktree，不创建重复 worktree，不切换到 primary checkout 开发。读取根 `AGENTS.md`、`docs/ai/AGENTS.md`、`acf workstream context WS009` 和当前 `PLAN.md`，并验证 path、branch、HEAD、worktree registry、Git common-dir 与固定身份一致。

WS009 self-hosting 使用 control-plane / product-under-test 分离：

- 当前已安装稳定 `acf` 负责 WS009 自己的 continuation ownership、doctor、prompt、attempt/claim、heartbeat/renew、workspace/effect、checkpoint/release 等控制状态；
- worktree 内 `uv run acf` 是正在开发的候选产品，只用于代码/CLI/tests/dogfood 验证，不得在新稳定版本发布并安装验证前，用候选实现去修改同一个 WS009 canonical continuation state；隔离测试应使用临时仓库/临时 `ACF_HOME`。

每轮必须运行：

`acf continuation doctor <worktree> --task-id WS009 --json`

`acf continuation prompt <worktree> --task-id WS009 --json`

本轮 `acf continuation prompt` 返回的 prompt 是 generic continuation 状态机唯一权威。attempt/challenge、owner authentication、generation fencing、workspace ownership、dirty/provenance、effect identity、heartbeat/renew、reconcile/recover、checkpoint/release 等通用行为全部按 generated protocol 执行；本 Scheduled Task 不复制、不重定义这些分支。

任务目标与动态变更：

- `docs/ai/active/workstreams/WS009.md` 与 `PLAN.md` 是 WS009 问题清单、优先级、阶段、技术边界和成功标准的持久权威；本 wrapper 只保存最小 mission guardrail，不复制完整问题矩阵。
- 当前 WS009 mission 包括：legacy pre-manifest dirty WIP adoption、ownerless externally-proven effect reconciliation、post-recovery physical-writer safety、semantic Git clean / stat-only false dirty、active attention/authority drift、Workstream/worktree lifecycle UX、ACF_HOME/state schema 可升级性、thin-wrapper 标准化以及最终 release/adoption。
- 每轮重新读取最新 PLAN/current_stage/state.next_action。若较新的 PLAN/current_stage 已改变，而 continuation next_action 陈旧，取得合法 ownership 后先按 generated protocol 更新 bounded checkpoint/next_action，再执行新的有效 Gate；不得机械执行陈旧 next_action。
- 用户对当前 WS 的目标、优先级或技术路线进行调整时，应优先更新 PLAN，并在必要时调整 stage、scope 和 continuation next_action。除非固定 identity 或官方 thin-wrapper contract 本身变化，否则不需要修改 Scheduled Task。
- 如果新需求已经超出 WS009 mission，不要无限扩展 WS009；记录后续候选或创建新的 Workstream。

完成 ownership 获取或 formal recovery 后，只推进当前 effective next_action 对应的一个自然完整 bounded Gate。Agent 可以根据代码、测试、证据和实际失败动态选择研究、实现、重构和验证策略；不要为了统一流程限制正常工程推理能力。

WS009 必须保持以下产品边界：

- 不把 ACF 扩展成 daemon、PID supervisor、OS Agent death detector、数据库、向量库或常驻 runtime；
- physical-writer 问题采用 cooperative durable effect/job identity 边界：可能跨 owner 生命周期继续写项目文件或产生 non-idempotent side effect 的操作必须有可持久核对 identity；无法证明终态时继续 fail-closed；
- 不恢复 whole-worktree dirty 作为 continuation owner/liveness/recovery Gate；
- 不让 CLI 自动裁决自然语言事实真假；语义不确定信号留在 review/audit/doctor candidate；
- Task Workstream 不直接修改 `active/Context.md`、`active/Current_Task.md`、`active/Task_Plan.md` 等 authority 文件，authority cleanup 按 PLAN 的 merge/primary maintenance 路径收口；
- continuation state 统一由 ACF 命令维护，禁止直接编辑 `~/.acf` JSON。

当前已知 4 个 `ai_context_framework.egg-info/*.txt` stat-only/content-identical 假 dirty 是 WS009 dogfood evidence。在 semantic-clean Gate 正式解决前，不通过 stash/reset/checkout/clean/无意义 commit 人工制造 clean，也不把它们混入普通 WS009 commit；继续按当前 workspace provenance 保留和观察。如果后续出现真实 content change，则按具体 path/digest/provenance 重新判断。

修改项目前，按 generated continuation protocol 声明 concrete workspace write intent。需要扩大 read/write scope 时使用 ACF Workstream 正式命令并记录 reason，不手工越权绕过 guard。

实现遵循：

characterization/failing test → 最小正确实现 → focused regression → 阶段性 full regression。

优先复用现有小模块/helper，不继续向接近 agent-friendly 行数上限的大模块堆积逻辑。所有 package modules 继续满足项目的 `<= 2000` 行 gate，不新增第三方运行依赖。

Gate 收口时根据实际修改运行 focused tests，并至少执行：

`uv run acf workstream guard WS009 --files <本轮实际修改文件...> --json`

`git diff --check`

只显式暂存已经验证的 scoped 文件，禁止 `git add .`。Git commit 只在形成自然语义 checkpoint 时创建；如果当前 Gate 尚未形成合适 checkpoint，可按 generated continuation protocol 保留可验证 task-owned WIP 并 commitless handoff，不为了释放 lease 制造半成品 commit。

修改 CLI 对外行为、JSON/error_code/next_actions、help、模板、默认策略或发布契约时，同步评估 README、System Manual、Automation、upgrade compatibility、packaging 和 version。发布阶段只有在 PLAN 规定的 full release gates 全部通过后，才发布新的 immutable PyPI version、升级全局稳定 ACF，并重新进行 ACF-self、FCC continuation、AStockT_AI installed-state adoption smoke；不得重复发布已存在版本。

发现新的、具体、可复用且有证据支持的 ACF/continuation/worktree/governance 缺陷时，使用当前稳定控制面记录 `acf continuation issue` 和稳定 fingerprint；正常 active-owner no-op、预期等待、普通开发失败和已知问题不得重复登记。

每轮结束按 generated continuation protocol 完成 workspace refresh、必要验证、bounded checkpoint 和 release，再次运行 doctor。

最终只用中文简洁汇报：

- 当前 stage / Gate
- contention / recovery 状态
- 本轮完成内容
- 新增或解决的 issue fingerprint
- 修改文件
- tests / guard
- commit 或 commitless handoff
- continuation 最终状态
- next_action
- 是否存在确需人工介入的 blocker

---

## 维护规则

1. 普通 WS009 需求变化不修改本文件；更新 `PLAN.md` / stage / scope / continuation next_action。
2. 固定 identity 正式变化，或 ACF 官方 thin-wrapper contract 升级时，才更新本文件。
3. 后续如果 ACF 提供正式 `continuation wrapper` / machine-readable wrapper contract，本文件应退化为该生成能力的 dogfood fixture，而不是继续作为人工模板分叉。
