# WS012 — Project Observer Operational Dogfood & Maintenance

## 1. Mission

WS012 承接已经完成并归档的 WS011 之后的 **production operational dogfood**，不是重新开发 Project Observer。

目标：

- 让正式 `ACF Project Observer` Scheduled Task 长期以稳定安装态 ACF 运行；
- 让独立 Maintenance Writer 持续监督 watchdog 是否真的按期刷新，而不是自己替 watchdog 刷新；
- 验证 Dashboard freshness、北京时间展示、跨 worktree authority/source consistency、Writer 并行、异常检测和版本升级后的稳定性；
- 让 Observer 从“最近状态页”演进为可持续阅读的项目地图：展示总体目标、架构关系、逻辑 milestone 链、当前位置和关键历史证据，而不是只展示最近完成内容；
- 为 continuation 增加正式的动态用户需求注入渠道，使运行中的 Scheduled Task 能安全接收 requirement / priority / constraint / plan change，并在 authority refresh 后调整计划；
- 让 WS012 消费跨项目 `continuation issue` 聚合池，完成 current-stable triage、严重问题立即修复和普通问题的计划化批处理；
- 发现具体、可复用的 Observer/ACF 缺陷时，用正式 issue → fix → tests → release → installed-state dogfood 闭环处理；
- 不复活 WS011，不把 WS012 变成常驻 agent runtime、数据库或私有 scheduler。

WS011 保持历史事实：核心 Project Observer 产品已经完成、发布并归档。

---


## Current authority — Observer V2 / control-plane safety

本节由当前 durable user directives 同步而来；**与后续历史章节冲突时，以本节为准**。历史版本号、旧 acceptance 计数、旧页面模板与旧 scheduler minute 只保留 provenance，不再作为永久执行约束。

### Release terminal fact

`v0.0.3.84` 的 merge、`origin/master` 与 annotated tag 已形成历史 identity，但 exact GitHub Actions run `32984611066` 已取得终态 `completed/cancelled`，且 PyPI `ai-context-framework==0.0.3.84` 未发布。因此 `.84` publishing effect 只允许按同一 external identity reconcile 为 failed/cancelled；禁止 re-merge、re-push、再次 retrigger 或把新代码塞入 `.84`。`.84` 不是可 global-install 的 stable baseline，后续能力进入新的稳定候选，版本号由当时 release authority 决定。

### P0 — control-plane reliability first

P0 必须先形成独立 checkpoint，不与大型 Observer UI 重构混在一起。

1. **Fenced credential transport**：支持 `ACF_CONTINUATION_FENCE_TOKEN_FILE=<caller-controlled-temp-file>`。claim/recover 必须在提交 generation/lease 前完成 token delivery；启用 file transport 后 JSON 不回显 raw token；后续 assert-owner/heartbeat/renew/workspace/progress/effect/checkpoint/release 省略 `--fence-token` 时从同一 handle 读取；raw 参数保持兼容；非法/缺失/不可读写/空/异常尺寸 fail-closed；canonical state 只保存 hash；临时明文不进项目 Git/`~/.acf` canonical state；installed-state dogfood 必须证明 recover 后跨 execution-context 仍可继续 authenticated control-plane writes。
2. **Canonical Windows `acf.cmd`**：Windows 正式入口改为 CMD shim，通过 uv-tool environment 的 Python/module 进入 ACF，不复制业务逻辑。install/update scripts 必须创建/刷新/验证 `acf.cmd`，并机械保证同目录 `acf.exe` 不因 PATHEXT 优先级赢过 CMD；`Get-Command acf` installed-state regression 必须解析为 `acf.cmd`，并通过 CMD 验证 version/status/continuation/observer。不要新增 binary signing/certificate subsystem；文档只声明避免直接执行 ACF 自身 unsigned launcher，不声称绕过所有企业脚本/Python policy。
3. **Closeout authorization resolver**：durable scoped auto-close policy 与 explicit per-Workstream approval evidence 必须分离。记录至少可表达 project、WS id/type/class、action、authority/evidence source、revision/fingerprint、validity、supersession/revocation、optional expiry。narrower/newer explicit authority 优先；WS-specific manual gate 可覆盖项目默认；approval 不跨 WS/action 转移；material authority change 后 stale approval 必须重新评估；agent 不能靠裸 `--human-approved` 自行满足 Gate。Ready/merge/done/archive 及低层等价 closeout path 必须消费同一 resolver，AI-facing JSON 稳定给出 `auto_authorized | human_approved | approval_required | denied` 及 evidence/next-actions。必须覆盖 long-lived auto policy、manual override、non-transfer、revoked/superseded policy、stale approval、migration 与旁路回归。

### Observer V2 product authority

Observer V2 的目标是：**只展示用户实际注册并由外部自动化推进的目标，以中文 human-first 方式解释最终目标、完整路线、当前位置、问题、最近 Agent 执行、证据和下一步。**

#### Target Registry / display scope

新增显式 user-level Observer Target Registry，概念位置 `~/.acf/projects/<project-id>/observer/targets.json`（允许等价可审阅 runtime 文件）。它不写项目 Git、不成为事实源、不依赖数据库/ChatGPT 私有格式，也不要求 ACF 猜 Web Scheduled Task。Worktree/Workstream 存在不等于应该显示；只有显式注册的 scheduled-automation target 进入 Dashboard 主展示。第一阶段至少支持 fixed Workstream target 与 project-level dynamic automation target。每个 target 有独立 tab/page、timeline、problems、run chain、narrative/map。

Project Overview 是条件能力：只有认真读取当前 authority 后确实存在可解释统一目标/路线/架构时才 enable；异构项目可 evidence-backed disable，只显示 target pages；不得以偷懒为理由关闭。

#### Target Narrative / adaptive map / mandatory Map Review Gate

新增独立于 Project Narrative 的 target/workstream narrative，拥有 target-local sources、fingerprint/staleness、当前位置、problems/evidence；单个 target 变化不能让所有 target 一起 stale。derived semantic state 永不替代 Markdown authority。

可视化必须保持 single-file/self-contained/file:// safe HTML/CSS/inline SVG，不引入 React/Mermaid runtime/Graphviz runtime/CDN/daemon。Agent 根据真实语义选择 linear/branching/architecture/dependency/roadmap/state-machine/timeline/multi-lane/tree/text/hybrid，不固定模板。

每次 scheduled semantic refresh 强制执行 auditable **Map Review Gate**，至少记录 `decision=unchanged|patch|rebuild|presentation_change|project_overview_enable|project_overview_disable`、reason、evidence、authority_fingerprint。Review 必须检查 PLAN/Task Plan/Workstream/Current Task/planning references/ADR/user directives/current stage/key evidence、执行偏离、新问题、失效节点、新并行路径及当前图形是否仍真实。Fingerprint 只做 cheap triage；任何 map-relevant signal 变化都要重读必要 authority 并显式决定。重复 unchanged 也需审计，防止浅层复用；历史 map/route version 保留 provenance。

#### Problems / run observability

问题是 route/map 一等元素，并尽量绑定受影响 node/route。至少按正交维度表达：
`expectedness=expected|unexpected|unknown`；
`handler=agent_self|human_approval|human_action|external_system|other_project`；
`scope_relation=in_scope|cross_cutting|out_of_scope|tooling_dependency|external_dependency`；
`blocking_impact=non_blocking|degrading|blocks_current_step|blocks_task`；
`plan_impact=none|local_adjustment|route_change|major_replan`；
以及 detected/investigating/working/waiting/transferred/deferred/resolved 等 lifecycle。
route-impacting problem 必须触发真实 map review/update；跨项目问题只展示 dependency/impact/transfer linkage，不越权修改 foreign project。

每个 scheduled activation 尽量展示 start/end/duration/result/major outcome/route link。优先 continuation round 时间；无 continuation 时使用窄范围 user-level Observer start/finish marker。异常或不完整 run 禁止伪造 end time，只展示 last activity 与 lower-bound/approximate duration。主 timeline 只保留 Agent start/end、milestone/stage、plan/strategy change、problem、human action、route change、release、key validation；heartbeat/generation/fence/fingerprint 等噪声折叠技术详情。

#### Chinese human-first Dashboard V2

主视图必须直接给出足够细节：最终目标、完整计划/路线、当前位置/focus、为什么做当前步骤、最近证明/排除/改变了什么、当前问题及其 plan impact、下一步及理由、执行健康、是否需要人工介入、最近 Agent run 时间/时长/结果/主要产出。HEAD/generation/lease/fence/effects/schema/fingerprint/raw provenance 折叠技术详情，但有意义的 reasoning/progress 不得全部藏起来。人类可见时间按当前 authority（目前 UTC+08:00）展示，structured state 保持 canonical time semantics。

### P1 / P1.5 / P2–P4 implementation / dogfood

- **P1**：Target Registry、target-local scope/tabs、run timing/history、conditional Project Overview decision state。已在 `200c75f989319ae708acdf3ce8e4f8b4dfe1c1bc` 形成独立 checkpoint；验证包括 58 个 focused Observer tests、615 个 full unit tests、file-scoped WS012 guard、`git diff --check`、strict docs 与 template check。
- **P1.5 — Automation / Prompt Execution Contract**：在 P1 之后、P2 之前建立可审阅的自动化提示词执行合同。正确模型固定为“两类 Scheduled Task wrapper + 一个 Writer runtime-generated continuation prompt”，但不引入第二套 generic state machine：
  - **Writer Scheduled Task wrapper common core** 必须是 sufficient high-salience first-read bootstrap，而不是为了省 token 人为削薄。固定包含稳定 project/task/worktree/branch/Workstream identity、existing-worktree 的精确 project-access/DevSpace 打开语义、stable ACF upgrade/adaptation、authority refresh、每轮强制消费 `acf continuation prompt + execution_policy`、live-vs-stale owner 用户可见处理、安全/write-scope/exit 边界、checkpoint/commit/Gate 不等于 stop，以及缺失后会显著增加误执行风险的首读规则。volatile owner/generation/stage/next_action 不写死；项目/任务专属 scientific/Runtime/resource/permission/security/validation/issue-reporting 通过显式 extension slot/overlay 保留。
  - **Production Observer Scheduled Task wrapper common core** 同样是完整首读合同，至少固定 `read broad / write narrow / control none`、existing-checkout、Target Registry display scope、anti-masking、semantic review、Map Review Gate、human-first-but-detailed information policy、truthful run history、cross-project non-interference 与 local authority/source rules；项目/target 专属规则进入命名 extension slot。Observer wrapper 不复制 Writer ownership/recovery/fencing state machine。
  - **Writer runtime-generated prompt** 继续由 stable `acf continuation prompt + execution_policy` 唯一动态提供 owner/claim/recover/fencing/directive/current-plan/progress/checkpoint/release/exit generic authority；不得重复静态项目约束，也不得承载 Observer semantic state machine。
  - separation 必须成为 reviewable machine/docs/template/tests contract，而不只停留在 CLI help。已有 `scheduler_wrapper_contract` 的 sufficient-bootstrap 语义作为兼容基础，P1.5 在此基础上补齐 wrapper-family/role/static-vs-runtime/extension/evidence contracts，不回退到历史 thin-wrapper 设计。
  - **Observer anti-laziness 是硬 prompt contract**：每次 scheduled semantic refresh 必须显式审查 narrative/map/presentation/Project Overview 是否仍真实，并审计记录 `unchanged|patch|rebuild|presentation_change|project_overview_enable|project_overview_disable`、reason、evidence、authority fingerprint。fingerprint 只做 cheap triage；PLAN/Task Plan/Workstream/current task/planning refs/ADR/user directives/current stage/key evidence、执行偏离、架构、问题、依赖、并行路径或策略发生 map-relevant 变化时，必须重读必要 authority 后再决策。`unchanged` 也必须有 reason/evidence，连续 unchanged 仍可审计。
  - presentation type 必须从真实语义选择 flow/branch/architecture/dependency/roadmap/state-machine/timeline/multi-lane/tree/text/hybrid；Project Overview 只有 evidence-backed 证明不存在可信统一路线时才可 disable，并随 authority 变化重新评估。human-first 只折叠 control-plane 噪声，不得隐藏最终目标、路线、当前位置/why-now、已证明/排除/改变、问题及 plan impact、下一步及理由、health/人工介入与最新 run outcome。
  - Writer execution evidence 要能被 Observer 使用：stage/milestone、major outcome、proven/excluded result、blocker/problem + plan/route impact、next logic；heartbeat/generation/fence 噪声不足以替代语义 evidence。run observability 必须保持 start/end/duration/result 真值与顺序；无 continuation 的 target 使用 user-level marker；crash/incomplete run 禁止伪造 end time。
  - **Interactive presentation-maintenance contract** 分三种生命周期：① immediate transient presentation-only patch；② 下一次 Production Map Review 消费的 transient one-shot semantic/presentation review request；③ 明确 durable 的 presentation rule。Agent 必须先理解当前 derived semantic/presentation state，把用户意图转换为 reviewed intent/scope/rationale/evidence，ACF 只做确定性记录/并发校验，不自动解释自然语言。任何 immediate patch 只能通过窄范围 user-level derived presentation interface + deterministic re-render，禁止直接编辑 `dashboard.html`；可能改变/误导 route order、node relationship、dependency、stage/completion、architecture、mainline/branch 等语义时必须升级为 Map Review + authority reread。
  - interactive presentation write 不取得 Writer ownership，仍遵守 `read broad / write narrow / control none` 与 foreign-project non-interference；以 current presentation revision/fingerprint 做轻量 optimistic concurrency，冲突 fail-closed 并要求 reread/re-evaluate，不新增 lease/fence state machine。one-shot 成功应用/复核后必须退出 active context，仅保留审计历史；durable rule 仅在明确长期有效时进入 active contract，并支持 supersede/withdraw，防止 resolved transient guidance 被后续 Production Observer 复活。
  - P1.5 的**结构/进入 P2 Gate**必须同步 PLAN/Workstream、README/Automation/System Manual/template、相关 CLI/machine contracts 与 regression tests，并对 ACF、FCC WS079/WS080/WS086、AStockT_AI 的 Writer/Observer Scheduled Task families 完成真实 prompt-level audit、per-family migration delta 与可执行的 acceptance matrix：证明 shared common core、各项目唯一 extension、existing-wrapper migration safety 与 stable generated continuation authority 的职责边界已经冻结。若当前 scheduled execution context 对 sibling task 只有 inventory/read-back、没有 mutation authority，则该真实 platform boundary 必须 fail-visible 保留，但**不得把一个当前上下文无法执行的外部 mutation Gate 串行阻塞 P2/P3 内部产品实现**。
  - P1.5 三种 interactive presentation-maintenance lifecycle 的**完整 runtime acceptance 是跨阶段 Gate，不是 P2 的前置自相矛盾条件**：P2 实现 semantic review、one-shot review request、durable rule state/consume/supersede/withdraw 与 Map Review 语义；P3 实现 immediate transient derived-presentation patch、optimistic concurrency 与 deterministic re-render。`transient_patch / one_shot_semantic_review / durable_rule` 的 integrated acceptance（包括 cleanup、anti-resurrection、独立 Production render 交互）必须在进入 P4 / release Gate 前全部通过。未实现 runtime 前只能验证 contract/readiness，禁止伪造 runtime acceptance pass。
- **P2**：target narrative、independent fingerprint/staleness、Map Review Gate、adaptive map、problem model、route binding、cross-project transfer，并实现 P1.5 已冻结的 semantic review / presentation-maintenance runtime 语义。
- **P3**：基于 P1/P1.5/P2 重建 Chinese human-first self-contained Dashboard V2，并实现 narrow derived presentation maintenance surface。
- **P4**：真实项目 dogfood：ACF 只显示注册的 WS012 target；FCC 注册的 WS079/WS080/WS086 各自独立 tab，并认真判断是否应有 Project Overview；AStockT_AI 注册自动推进 target，若 authority 支持统一 project route 才启用 overview。必须真实覆盖 plan/strategy change、unexpected blocker、route-impacting issue、external/tooling transfer、abnormal run、map presentation change、overview enable/disable、Windows CMD、fenced credential installed-state 与 anti-masking。

最终 Production acceptance 只能从包含 P0 + P1 + P1.5 + P2–P4、正式 release + global install 的稳定安装态开始；旧 `.83`/过渡 activation 只作历史 evidence，不拼接。具体连续次数与 reset 条件读取当时最新 acceptance authority。Maintenance snapshot/narrative refresh 永远不冒充 Production activation；acceptance pass 也不结束 WS012 long-lived mission。

### Directive lifecycle / execution order

本节 durable authority 同步完成后，相关 current directives 应以本 PLAN/Workstream evidence `adopt`；对应能力真正完成后再 `resolve`。当前顺序：P0 credential → P0 Windows CMD → P0 closeout authorization → P1 → **P1.5 Automation / Prompt Execution + interactive presentation-maintenance contract** → P2 → P3 → P4 → full release/global install/installed-state dogfood → latest-authority Production acceptance → ongoing maintenance。

---

## 2. Historical scheduler topology（已被 Current authority 动态 cadence 规则 supersede）

当前 ACF dogfood 固定采用两个职责完全不同的 Scheduled Task：

### Production Observer

- 名称：`ACF Project Observer`
- cadence：每小时 `:34`
- project：`D:\PROJECT\Tools\ai-context-framework`
- workspace：primary checkout / existing-checkout
- control boundary：`read broad / write narrow / control none`
- 只允许稳定安装态 `acf observer` 写 `~/.acf/projects/<project-id>/observer/`
- 不 claim/challenge/recover/release Writer，不修改 Git/Workstream/project files，不升级 ACF
- v0.0.3.77 起，Dashboard 所有人类可见时间统一显示北京时间 `UTC+08:00`；canonical state/history 继续保存 UTC

### Maintenance Writer

- Workstream：WS012
- 标准 worktree：由 `acf worktree verify/list` 与 local registry 决定，不在共享 Markdown 固化机器绝对路径
- scheduler cadence：每小时 `:04`
- continuation task-id：`WS012`
- 负责诊断、修复、测试、release 和 installed-state verification
- 普通 wake **不得代替 Production Observer 例行执行 `observer snapshot` / render**

`:04 → :34` 保持约 30 分钟间隔，使 Writer 的真实变化先发生，Observer 再独立观察。

---

## 3. Anti-masking contract

这是 WS012 最重要的 dogfood 规则。

正式 Observer 已上线后，Maintenance Writer 每轮首先读取：

- `observer_status.json`
- `state/runs.jsonl`
- `state/current.json`
- `semantic/interpretations.jsonl`
- `dashboard.html` mtime / 可见 freshness

并判断最近一次 **Production Observer** 是否按期成功。

普通 Maintenance wake 禁止为了“让 Dashboard 看起来新鲜”而例行运行：

```text
acf observer snapshot
acf observer interpret
```

否则会掩盖：

- scheduler 没触发；
- watchdog 自身失败；
- lock/overlap 问题；
- data age stale；
- semantic 长期 stale。

只有以下场景允许 Maintenance 主动运行 Observer 写操作：

1. 修复后 focused verification；
2. 明确诊断实验，且已先保存故障前的 durable evidence；
3. release smoke / installed-state dogfood；
4. migration 或用户明确要求的人工刷新。

这类主动运行必须在 continuation effect/evidence 中注明用途，不能被当成 Production Observer 的 scheduler 成功证据。

---

## 4. Initial operational defect（历史已解决）

首个已确认问题：

- issue fingerprint：`e469e99755604428cd08`
- evidence：Observer revision 88
- 现象：primary master 已将 WS011 归档为 Done，但另一个仍注册的旧 worktree 保留历史 `WS011=Active` detail；Observer 将该旧副本重新投影成当前 Active Workstream，并产生 `registry-lifecycle-mismatch` warning 与 stale semantic。

这说明 Project Observer 当前的 Workstream source authority 仍可能把“同项目其他 worktree 中的历史副本”误当作当前 project authority。

### 期望 authority 规则

优先验证并实现以下原则，而不是简单忽略 warning：

1. primary checkout 的 active/archive lifecycle 是 project-level Workstream 当前/终态 authority；
2. 某 Workstream 自己的 bound worktree 只有在 registry/lifecycle 允许时，才能作为该 Workstream 的当前专属 source；
3. 任意其他 registered worktree 中顺带存在的旧 Active Workstream detail，不能单独复活一个在 primary 已归档/终态的 Workstream；
4. 这类历史副本可以作为 provenance / divergence / stale-source evidence 被观察，但不能覆盖 canonical current lifecycle；
5. 若 primary 与该 Workstream 自己的 active bound worktree 真正冲突，应 fail-visible（warning/critical + source consistency），不能静默选一个版本。

### Required regression

至少覆盖：

- primary archived Done + unrelated registered worktree stale Active → canonical 不复活；
- primary Active + bound worktree Active → 正常聚合；
- primary Active + bound worktree lifecycle divergence → 明确 Alert；
- unrelated worktree 的历史 WS detail 不参与 canonical current selection；
- history/provenance 仍可保留旧 source，不丢证据。

该问题已在 v0.0.3.78 完成修复、发布和 installed-state dogfood；后续 WS012 不再把本节视为当前默认执行计划。本节保留为最初 operational dogfood 的历史设计证据。

---

## 5. Operational dogfood gates

### WS012.1 — Bootstrap and separation

完成条件：

- 正式 `ACF Project Observer` task 启用且 cadence=`:34`；
- WS012 Writer cadence=`:04`；
- Dashboard shortcut 唯一维护在 `C:\Users\lenovo\Documents\ACF Project Observer.lnk`，只更新原快捷方式 target，不创建版本/时间戳副本；
- production / maintenance 权限边界和 anti-masking 文档化；
- WS012 continuation 初始化并使用稳定 ACF control plane。

### WS012.2 — Source authority hardening

完成条件：

- issue `e469e99755604428cd08` 有 deterministic regression；
- 修复后 focused Observer tests、strict/template checks、file-scoped guard 和 `git diff --check` 通过；
- 真正的 installed-state Observer 不再把已归档 WS011 ghost-resurrect 为 Active；
- 修复不删除历史 evidence，不把 arbitrary worktree 变成新的 authority。

**Implementation evidence（2026-08-24）**：已新增 primary archive authority 与 active-registry source gate。两个新回归先在旧实现上分别失败：primary 归档后 WS123 被 stale worktree 复活；registry 已 merged 时 stale bound Active 覆盖 primary Done。修复后这两个回归与既有 registry-scoped source 测试均通过，完整 `tests.test_observer_cli` 37/37 通过。真实 ACF candidate `observer snapshot --dry-run` 保留 production runtime 不写入，结果 `snapshot_consistency=stable`、current workstreams 仅 `WS012:Active`、alerts 为空、7 个 worktree diagnostics 仍保留；issue `e469e99755604428cd08` 的 ghost WS011 现场被产品层 source-authority 修复而不是靠清理旧 worktree 绕过。

### WS012.3 — Dynamic user directives / live steering

这是 2026-08-25 用户需求变化直接暴露出的 continuation 产品缺口：一个 Scheduled Task 即使已经进入 `waiting_external` 或已有 persisted `next_action`，用户仍可能在运行过程中新增需求、调整优先级、增加约束或改变计划；当前没有一等、可审计、低摩擦的输入渠道。

目标不是新增第二套 Task Plan，而是新增一个 **user-authority inbox**。第一版设计：

```text
acf continuation directive add
acf continuation directive list
acf continuation directive show
acf continuation directive adopt
acf continuation directive resolve
acf continuation directive supersede
```

要求：

- durable event 存在用户级 continuation namespace，不写项目私有数据库；
- CLI 只做确定性记录、状态迁移、边界校验、排序和 prompt 暴露，不自动判断自然语言需求真伪；
- 第一版 directive kind 固定为 `requirement | priority_change | constraint | plan_change`；
- directive 保留 `id / created_at / kind / priority / text / status / supersedes / evidence_refs` 等可审计字段，正文和集合继续受 bounded/secret-safe 约束；
- pending directive 是**新的用户 authority signal**，其优先级高于旧 persisted `next_action`，但不会静默成为项目事实；
- Agent 必须 authority refresh 后判断：临时运行要求可直接执行；持久需求/计划/约束应同步进入正确 Markdown authority（PLAN / Workstream / Rules 等），然后把 directive 标记 adopted；
- `continuation prompt --json` 稳定暴露 `directive_context`，至少包含 pending count、latest directive、digest/revision 和是否需要 authority refresh；
- generated prompt 在存在 pending directive 时高显著展示，并明确 old `next_action` 可被新用户 authority supersede；
- heartbeat / renew 至少返回 pending directive count 与 digest/revision 变化，使长 session 不必等下一个 scheduler wake 才发现用户 steering；
- directive lifecycle 保留 append-only/auditable 事件历史；resolve/supersede 不篡改原始用户输入；
- 不把普通产品 issue、自动推断、聊天 transcript 或模型内部想法写成 directive。

第一轮 dogfood 必须用该能力本身录入并消费至少两个真实 directive：

1. Observer Project Narrative / Project Map；
2. Global continuation issue intake / triage / batch maintenance。

#### WS012.3A — Directive lifecycle hardening（2026-08-26 final authority）

在继续 passive Production Observer acceptance 之前，先完成 continuation directive lifecycle 的正式加固。目标是让长时、多 Agent 项目中的 user live steering 可审计、可恢复、可长期运行，同时保持 directive 只是 **user-authority inbox**，不演化成第二套 Task Plan。

本阶段以 directive `dir-30af839cd72e4feca7de` 为最新用户 authority；它已正式 supersede 早先 provisional lifecycle directive `dir-302f383282b34c8185ff`。实现和 dogfood 必须遵守以下顺序：**P0 lifecycle semantics → P1 hygiene → P2 rollover/archive → release/global install → installed-state dogfood → restart Production Observer acceptance**。

##### P0 — Lifecycle semantics / owner separation

Directive schema/CLI 至少支持：

- lifetime：`transient | durable | unspecified`（或语义完全等价、可确定验证的 metadata）；
- projected status：`pending | adopted | resolved | superseded | withdrawn`；
- `resolve` = 工作/要求已完成；
- `withdraw` = 用户或更高 authority 明确取消，不等价于完成；
- `supersede` = 同一 active requirement 的新版本替换旧版本，并保留完整 lineage；
- 独立新增需求继续使用 `add`；已 resolved 的历史 directive 不允许被“重新打开”。

状态约束：

- transient one-shot 可 `pending -> resolved`，不要求为了形式先 adopt；
- 需要跨 round 执行的 transient directive 只有在 durable execution state 已建立后才允许 adopt；
- durable requirement / constraint / priority_change / plan_change 在 adopt 前必须完成 authority refresh，并把持久语义同步到正确 Markdown authority（PLAN / Workstream / Rules / Task 等），同时清理或 supersede 与新 authority 冲突的旧表述；
- durable adopt 必须携带可审计 evidence；**禁止仅因为 Agent“读到了文本”就 adopt**；
- 当前 session 实际消费过的 directive 在控制点必须有明确 disposition：`resolve / adopt / supersede / withdraw / keep pending with reason`，不得静默遗留；
- pending user authority 持续高于 stale persisted `next_action`。

Owner separation 是硬边界：

- 非当前 Writer owner 的 Agent 可以代表新的用户 authority 执行 `directive add/supersede`，不需要获取 Writer lease / generation / fence / workspace write authority；
- 当前 Writer 通过 `continuation prompt`、`heartbeat` 或 `renew` 暴露的 revision/digest 变化，在下一 safe control point 发现并处理；
- 外部 directive 注入本身不得偷偷获得项目文件写权限或 continuation owner 权限。

安全边界继续保留：credential-like value refusal、bounded text/evidence refs、schema migration compatibility，以及 CLI 只做机械校验/状态迁移、不自动判定自然语言事实真伪或任务是否语义完成。

##### P1 — Directive hygiene / doctor observability

`acf continuation doctor --json` 增加机械、非语义裁决式 hygiene findings，至少覆盖：

- stale adopted directive；
- stale high-priority pending directive；
- durable adopt 缺少 adoption evidence；
- active directive count pressure；
- journal event/byte rollover pressure；
- active directives 自身接近/达到 capacity 的 fail-closed 风险。

Doctor 只能报告机械事实和风险，不允许：

- 按年龄自动 resolve；
- 推断某条自然语言 requirement 已完成；
- 自动 withdraw/supersede；
- 把 hygiene warning 当作写 authority。

Generated continuation guidance 必须在有 consumed/pending directive 时高显著提示 disposition 义务，并且 heartbeat/renew 至少稳定暴露 pending/active 摘要、revision/digest 变化和 hygiene pressure，使长 session 不需要等下一个 scheduler wake。

##### P2 — Crash-safe terminal rollover / archive

当前 directive journal 不能依赖“达到 hard event/byte limit 后直接失败”作为长期运行策略。新增 terminal rollover/archive：

- 只允许归档 **完整 event chain 已终态** 的 directive：`resolved / superseded / withdrawn`；
- `pending / adopted` 及其链条绝不能归档；
- rollover 必须在 hard event/byte limits 之前由 deterministic pressure threshold 触发；
- active directives 自身已经占满 capacity 时继续 fail-closed，不通过丢 active authority 腾空间；
- current history 维持 bounded，archive history 继续可通过 CLI 查询；
- current + archive 必须保留 digest/audit 可验证性，能够证明 event chain 未丢失、未重排、未篡改；
- rollover 写入必须 crash-safe：新 archive 与 current journal 的切换不能产生半归档、双计数或丢链；
- schema migration / upgrade 必须保留 archived lineage 与 current projection compatibility。

CLI 需提供足够的 list/show/history 或等价查询能力，使 archived terminal directive 仍可被按 id/lineage 审计，而不是“归档后不可见”。

##### Required dogfood acceptance before next stable release

必须在真实 WS012 continuation 与隔离 `ACF_HOME` stress 中至少完成：

1. final lifecycle plan_change：PLAN/Workstream authority 同步后，以 evidence-backed adopt 消费；
2. transient one-shot：`pending -> resolved`；
3. durable directive：先 authority sync/evidence-backed `adopt`，再在完成后 `resolve`；
4. same-requirement edit：`supersede`，验证 old/new lineage；
5. explicit user cancellation：`withdraw`，验证与 resolve 语义不同；
6. fresh-owner external injection：另一个非 owner context 注入 directive，当前 owner 通过 revision/digest 在 safe control point 发现；
7. isolated `ACF_HOME` rollover stress：跨 event/byte pressure 执行 terminal rollover，验证 pending/adopted 不归档、terminal chain 完整、archive 可查询、digest 可审计、crash-safe；
8. credential-like refusal 与旧 schema migration regression 继续通过。

实现完成后同步 CLI help / JSON contracts / README / `docs/Automation.md` / dogfooding System Manual / template System Manual / tests / changelog/version/package metadata，并按风险运行 focused、full unit、strict/template、upgrade/package、完整 release gate。稳定 release + global install + installed-state dogfood 完成后，**此前 v0.0.3.83 的 `6/24` acceptance 只保留为历史证据；新的 directive lifecycle stable baseline 从 0 重新开始 24 次连续 Production Observer acceptance，不与旧窗口拼接。**

### WS012.4 — Observer Project Narrative / Project Map

当前 Dashboard 已能展示 overall health、Workstream 当前解释和 meaningful timeline，但页面仍偏“最近发生了什么”。新增项目级长期叙事层，第一屏还要回答：

1. 项目最终想做成什么；
2. 整体架构由哪些模块构成、如何关联；
3. 项目沿什么逻辑路线演进到现在；
4. 哪些 milestone 已完成、当前位于哪里、下一阶段是什么；
5. 每个逻辑节点由什么证据支撑。

计划新增 derived semantic state：

```text
Project Narrative
├─ overall_goal
├─ architecture
│  ├─ nodes
│  └─ edges
├─ milestones
│  ├─ id / title / status
│  ├─ depends_on / next
│  ├─ summary / implication
│  └─ evidence / provenance
└─ current_position
```

边界：

- 项目目标/架构/里程碑必须绑定明确 provenance，不由 Observer Core 自由猜测；
- model/agent 可根据权威 Markdown 生成语义解释，CLI 只验证、保存、版本化、stale 检测和渲染；
- 不默认扫描全部仓库，继续从项目入口、active authority、plan refs 和 observation profile 渐进读取；
- Project Narrative 是 derived semantic state，不替代 `Context.md`、Task Plan、Workstream、ADR 等事实源；
- source fingerprint 变化后旧 narrative 必须 fail-visible stale，不能继续装作 current。

Dashboard 新增：

- Overall Goal 区；
- Architecture Map；
- Logical Milestone Flow / Project Evolution；
- Current Position；
- milestone evidence/provenance 展开；
- 当前 Workstream 卡片和 Timeline 保留，作为“现在”和“最近变化”层，而不是被新图取代。

可视化要求：

- 继续生成单文件、`file://` 可打开、自包含 HTML；
- 不引入 React/Mermaid/Graphviz runtime/CDN/HTTP daemon；
- 流程和架构优先使用确定性 HTML/CSS + inline SVG；
- 丰富颜色，但颜色必须有稳定语义并配合文字/符号，不能只靠颜色传递状态；
- 建议视觉语义：Goal=indigo，architecture category=blue/cyan/violet，Completed=emerald，Active=blue，Maintenance=purple，Waiting=amber，Warning=orange，Critical=red，Future=slate。

### WS012.5 — Global continuation issue intake / triage / batch maintenance

每次 `:04` Maintenance wake 在不破坏 anti-masking 的前提下，轻量读取：

```text
acf log issues --all-projects --open-only --json
```

不能直接把原始 open count 当作真实 backlog。当前全局历史中存在大量旧版本同根因 fingerprint，因此必须先做 current-stable triage：

- 当前稳定 ACF 是否仍可复现；
- 是否已被后续 release 修复但漏写 resolution event；
- 是否与其他 fingerprint 属于同一 root-cause cluster；
- 是否真的是 ACF/continuation/automation 通用问题，而不是一次性业务失败；
- 是否已经有 deterministic regression / 修复方案 / affected files / validation plan。

逻辑队列：

```text
Immediate
Ready Batch
Observe
```

`Immediate` 不等待积累，满足任一条件即可抢占 passive acceptance：

- critical；
- 可能导致数据损坏、重复 non-idempotent side effect、ghost owner / half-committed generation；
- 阻断 continuation claim/recover/release 或 Scheduled Task 持续运行；
- 新稳定版本严重 regression；
- 同一 root cause 已影响多个真实 Workstream，且当前稳定版仍可复现。

普通 high/medium 问题先进入 triage/repair planning，不为了单个小 bug 高频发版。达到下列任一条件时启动 Maintenance Batch：

- `Ready Batch` 中至少 3 个**已验证、彼此独立的 root-cause cluster**；
- 同一 root cause 在当前稳定版影响至少 2 个真实 Workstream；
- 用户明确要求立即启动一轮 batch。

Batch 一旦启动，本轮目标是把当时已经进入 `Ready Batch`、安全且相互兼容的问题**全部执行完**：deterministic regression → fix → focused/full gates → 一次稳定 release → global install → installed-state dogfood → resolution events。证据不足的 `Observe` 项不为了凑数量强行实现。

一个 issue 完成 triage/repair plan 后，后续 wake 只检查 occurrence/reproduction/severity 是否变化，不重复从零规划，避免 maintenance busywork。

**2026-08-27 current-stable Immediate triage：** 全局 issue intake 在稳定安装态 `v0.0.3.83` 上确认了同一 fenced-owner credential transport 根因，至少已影响 WS079 与 WS080。代表 fingerprint 包括 `2571acfc1377ae41f0ce`、`590e29d4596887eacaa6`、`517bb8cb2f78705383de` 与 `a315b38f1c4bf13b429e`：`claim/recover` 返回 plaintext `fence_token`，而真实 project-access / scheduler command safety 会拒绝后续携带高熵 token 的 `assert-owner / heartbeat / workspace / checkpoint / release` 命令，导致已经完成 authenticated recovery 的 fresh owner 仍无法继续 fenced control-plane writes。该缺陷同时满足“阻断 Scheduled Task 持续运行”和“同一 current-stable root cause 影响多个真实 Workstream”，因此升级为 `Immediate`，不等待普通 Ready Batch 门槛。

本轮 repair contract 是 backward-compatible 的本地 credential handle：当调用方预先设置 `ACF_CONTINUATION_FENCE_TOKEN_FILE` 时，`claim/recover` 必须在提交新 generation/lease 前把新 token 写入调用方控制的临时文件，JSON 不再返回明文；同一环境变量随后允许所有 fenced owner command 在省略 `--fence-token` 时读取该 credential。raw `--fence-token` 继续兼容；token file 缺失、非法或不可读写必须 fail-closed；canonical continuation state 继续只持久化 hash，临时明文文件不进入 `~/.acf` 或项目 Git，并由调用方在 release/session closeout 后删除。修复必须覆盖 claim 与 challenge-backed recover 两条 credential issuance 路径，以及 assert-owner/heartbeat/workspace/checkpoint/release 的 installed-state dogfood。

该 Immediate 在 `v0.0.3.84` 已完成 merge/tag、但 trusted-publishing workflow 尚处于既有 queued identity 时被发现。**不得为此重写、重推或再次 retrigger `v0.0.3.84` tag，也不得把新代码塞入已经签定的 `.84` release identity。** 修复作为 `.84` 之后的下一稳定候选进入独立 release；在 `.84` 外部发布状态未终态前，只允许继续验证/提交本修复和只读查询现有 publish authority，禁止制造第二个 `.84` side effect。

### WS012.6 — 24-hour production watchdog window

原 24 小时 acceptance window 保留，但因为 WS012.3/4/5 将改变 continuation 和 Observer 产品，应在这些能力完成 release + global install 后**重新从新的稳定基线开始计数**。

2026-08-26 的 final directive lifecycle hardening（WS012.3A）再次改变 continuation 产品与稳定安装态，因此 `v0.0.3.83` 已取得的 `6/24` 只作为历史 dogfood evidence 保存。2026-08-27 又确认 fenced-owner credential transport 属于 current-stable Immediate，并将继续改变 continuation 产品；因此真正的新 acceptance baseline 必须是**包含该 Immediate 修复的最新稳定 global install**。即使 `v0.0.3.84` 先完成 publish/install，在 credential-transport 修复尚未进入后续稳定版前产生的 production activation 也只能作为 pre-baseline diagnostic evidence，不得计入最终连续 `24/24`。待该修复 stable release + global install + installed-state fenced-owner dogfood 完成后，从其后的第 1 次独立 Production Observer activation 重新计为 `1/24`，不得拼接 `.83` 或过渡 `.84` 样本。

至少观察 24 个连续 hourly Production Observer activation，期间 Maintenance 不做例行 snapshot。

Production Observer 的 Project Narrative 刷新属于正式 `:34` activation 自身，而不是 Maintenance 补写。每个 production activation 在初始 snapshot 后必须检查 `project_narrative.status`：

- `current`：保持当前 narrative，不制造重复版本；
- `stale | not_interpreted`：使用安装态 `acf observer narrative-source` 对**显式** authority source paths 读取精确 projection/fingerprint，由当前 Observer Agent 基于该 projection 与最小必要 authority 生成 derived narrative JSON，再用同一 fingerprint/source-path 集合执行 `acf observer narrative-apply`，最后重新 snapshot/render；
- 生成 narrative payload 所需 scratch 只能放 OS 临时目录，不得写项目文件、continuation/workstream/effect control state 或新增第二份 canonical Dashboard；完成后删除 scratch；
- source fingerprint 在 source→apply 之间变化、证据不足或 credential-like 内容触发拒绝时 fail-visible，保留 stale 并记录该 production activation 未通过 narrative freshness gate，禁止 Maintenance 事后刷新冒充 production 成功；
- 只有最终 production snapshot 中 narrative 已 `current`（或初始即 `current`）的 activation 才能计入连续 24 次 acceptance。

验收至少包括：

- scheduler run cadence 正常；
- `dashboard.html` freshness 持续更新；
- visible timestamps 始终为北京时间，canonical JSON 始终 UTC；
- Project Narrative / architecture / logical milestone map 在无 authority 变化时稳定，不产生无意义重复历史；
- project authority 变化后 narrative 正确 stale → refresh，不保留错误 current 状态；
- snapshot consistency / self-health / source consistency 可审计；
- 至少覆盖一次 Writer active/HEAD 变化后由后半小时 Observer 独立观察；
- unchanged period 不制造重复 meaningful history；
- semantic stale/current 行为不由 Maintenance 刷新所掩盖；
- 没有重复 Observer task、重复 Dashboard 或重复 shortcut。

不为了测试“miss”主动破坏 production task；scheduler miss/failure 用 deterministic test 覆盖，若真实发生则作为额外 dogfood evidence。

### WS012.7 — Longitudinal maintenance

24h gate 通过不自动把 WS012 Done。

后续 hourly Writer wake：

- 先处理 pending user directives；
- 再检查 Immediate global issues；
- 再判断 Ready Batch 是否达到启动条件；
- 再做 Production Observer passive acceptance / longitudinal evidence；
- 没有当前安全、有价值工作 → 不 claim、不制造 control-plane busywork，结束本次重复 wake；
- mission 保持为长期 Maintenance，除非用户明确关闭或另行迁移。

---

## 6. Release discipline

Observer 修复进入稳定版前必须：

1. focused tests；
2. `acf workstream guard WS012 --files ... --json`；
3. `git diff --check`；
4. `uv run acf check template --json`；
5. `uv run acf check docs/ai --strict --json`；
6. 与风险匹配的 full unit / upgrade matrix / `scripts/release_check.py --mode full`；
7. merge/tag/publish side effect 使用 continuation effect identity；
8. PyPI/remote authority 证明确认后才 terminalize effect；
9. 全局稳定安装后再跑 installed-state Observer dogfood。

普通 checkpoint、commit、测试通过或一次 hourly observation 都不是 mission 结束条件。

---

## 7. Immediate next action

截至 2026-08-31，P0 credential transport、canonical Windows `acf.cmd`、closeout authorization 与 Observer V2 P1 已分别形成独立 checkpoint；P1 checkpoint 为 `200c75f989319ae708acdf3ce8e4f8b4dfe1c1bc`。directive revision 32 的三个 durable requirement 已以本 PLAN + WS012 Workstream 为 adoption evidence 消费，directive journal 当前为 revision 35 / pending 0。P1.5 的 reviewable machine/docs/template/tests contract 已在 `04024572d890c90fa78097eb2620248e51c5ad82` 形成独立 checkpoint：Writer Scheduled Task wrapper、Production Observer wrapper、Writer runtime-generated continuation prompt 三层职责边界、named extension slots、Observer-useful execution evidence、semantic anti-laziness，以及 interactive presentation-maintenance 三生命周期/optimistic-concurrency/semantic-escalation 合同均已落地；9 个 focused automation/prompt/Observer tests 与 622 个 full unit tests 通过，file-scoped WS012 guard、strict/template checks 与 `git diff --check` 通过。P1.5 **尚未完成 acceptance**，因为真实 Scheduled Task family 的迁移/dogfood evidence 仍未收口。当前默认执行顺序为：

1. 对当前真实 ACF、FCC WS079/WS080/WS086、AStockT_AI Writer/Observer Scheduled Task wrappers 做逐项 contract audit：区分已经符合 shared common core 的 wrapper、仍复制 generic continuation state machine/volatile state 的旧 wrapper，以及只需要 project-specific extension slot 的项目专属约束；任何迁移都必须保留 exact project-access/workspace identity 与 Runtime/scientific/permission/validation 安全边界。
2. 对确认需要迁移且具备安全写入能力的现有 Scheduled Task 做原位迁移；外部 scheduler prompt update 属于 non-idempotent side effect，必须绑定 deterministic effect identity、先读当前 prompt/version、更新后回读验证，禁止创建重复 task。若当前 execution platform 只允许观测而不允许安全修改某一 task family，则记录真实 platform boundary，不伪造 live dogfood pass，并继续可执行的其他 family/evidence。
3. 取得真实 scheduled Agent 消费新合同的 dogfood evidence，至少覆盖 Writer common core 与 Production Observer common core；确认 common core 一致、项目专属 extension 未丢失、generic continuation state machine 仍只来自 stable `acf continuation prompt + execution_policy`，并验证 Maintenance 不通过例行 Observer refresh 伪造 freshness。
4. 在 P1.5 固化 interactive presentation-maintenance acceptance matrix 与阶段归属，不要求尚不存在的 runtime 在 P2 之前“验收通过”：P2 负责 semantic review + one-shot/durable lifecycle state semantics，P3 负责 immediate transient derived-presentation surface；integrated transient cleanup / durable persistence / anti-resurrection / Production-render interaction 在进入 P4 前收口。
5. 当前 context 若没有 sibling-task mutation authority，则保留 wrapper migration 为**并行 operational/release Gate**，继续执行可安全推进的 P2/P3 内部实现；不能因外部 mutation surface 暂不可写而空转，也不能把 prompt-level audit 冒充 migration pass。进入 P4 / full release/global install 前必须补齐所有当时可执行的 same-task/interactive wrapper migration + exact read-back、三生命周期 integrated acceptance 与 installed-state Gate。

### 7.1 P1.5 live Scheduled Task family audit baseline（2026-08-31；2026-09-01 evidence correction）

2026-08-31 已形成一版 wrapper-family 迁移假设；2026-09-01 generation 78 曾因当时取得的 surface 证据不足，将 sibling family 降级为 repository/history 驱动的 provisional hypothesis。generation 79 对真实 scheduler inventory 再次取证后确认：当前 management surface **实际能够回读目标 task 的 live task identity 与完整 scheduler prompt 文本**，覆盖 ACF、FCC WS079/WS080/WS086 与 AStockT_AI Writer/Project Observer family；此前“除当前 activation 外 sibling raw prompt 均不可见”的表述被 supersede。与此同时，surface 仍未提供 executable `argv`/environment、installed ACF version、definition fingerprint 等底层 execution identity。因此后续 evidence 必须分层：`prompt-level live audit` 可以成立，但 `full executable-definition migration/read-back` 与 installed-state acceptance 仍不得凭空外推。

- **ACF WS012 Writer**：live prompt 为 aligned-but-heavy。exact existing-checkout、stable/candidate split、每轮 stable doctor/prompt、generated `prompt + execution_policy` 作为唯一 generic authority、directive/live steering、anti-masking 与 long-lived mission 均已具备；static wrapper 保留较多高显著性 bootstrap/safety procedure。后续只允许在不损失这些 authority 的前提下收敛，不能为了“thin wrapper”本身改写用户需求。
- **ACF Project Observer**：live prompt 已明确 Production Observer-only、`read broad / write narrow / control none`、stable doctor/prompt/status、禁止 Writer ownership/recovery、anti-masking、Project/Map Review 与北京时间展示，prompt-level common core **aligned**。
- **FCC WS079 Writer**：live prompt 已使用 exact existing checkout、stable ACF、doctor/prompt/generated authority，并保留项目专属 scheduler-reliability 约束；仍夹带部分可由 generated authority 动态提供的 generic timeout/challenge/claim procedure，属于 **mostly aligned / thinning candidate**。
- **FCC WS080 Writer**：live prompt 的 exact project/worktree 与 stable doctor/prompt 方向正确，但仍显式复制较完整 challenge → timeout → reconcile → recovery generic sequence，属于最明确的 **generic-state-machine thinning candidate**。
- **FCC WS086 Writer**：live prompt 已采用 stable/prompt-driven continuation 并保留 v5.8.0 soak 项目约束，但仍有部分 generic continuation mechanics 可下沉，属于 **mostly aligned / thinning candidate**。
- **AStockT_AI Writer**：live prompt 已具备 exact checkout、stable ACF、doctor/prompt 与项目专属 Task State/roadmap 约束，但 static wrapper 仍较厚并复制部分 generic continuation procedure，属于 **aligned-but-heavy / thinning candidate**。
- **AStockT_AI Project Observer**：live prompt 已保持 observer-only、stable/observer control plane 与 Writer ownership 分离，prompt-level common core **aligned**；项目专属 runtime/target 语义继续作为 extension 保留。

该 live audit **只证明 prompt text 层面的 contract delta**。当前 surface 尚不能同时给出 executable identity/version/fingerprint 与完整 mutation provenance，因此不能把 prompt inventory 直接升级为“safe migration 已完成”或“installed P1.5 pass”。当前 execution authority 允许 sibling task inventory/read-back，但本轮没有 sibling-task mutation authority；原位迁移必须在具备相应 mutation authority 的 same-task/interactive management context 中，先保存 exact current prompt/task identity，绑定 deterministic same-task update，再对同一 task 做 exact post-update read-back。任何 executable/version/fingerprint 缺失都以 fail-visible `runtime_owned_fallback` 记录。条件未完整满足时不创建 duplicate task、不伪造 migration pass，并继续可执行的其他 authority/validation work；若未来平台明确承诺这些字段而持续无法提供，再按 reusable issue 流程单独登记。

### 7.2 P1.5 per-family thinning delta（generation 79）

后续迁移不再笼统追求“wrapper 越短越好”，而是按 live prompt audit 固定 **keep / move-to-generated / preserve-extension** 三类差分；generic continuation ownership/recovery/effect/fencing/checkpoint/release procedure 只有在 stable generated `prompt + execution_policy` 需要时动态提供，static wrapper 不维护第二套状态机：

- **ACF WS012 Writer**：`keep` exact existing checkout、stable/candidate control-plane split、authority refresh、directive/live steering、anti-masking、Git/release safety 与 long-lived mission；只清理能够由 generated authority 完整替代的重复 generic mechanics。该 family 已 aligned-but-heavy，优先级低于明确复制状态机的旧 wrapper。
- **ACF Project Observer**：`keep` fixed canonical project、Production Observer-only、`read broad / write narrow / control none`、stable Observer surface、anti-masking、Map Review 与 UTC+08:00 human display；`forbid` Writer claim/recover/effect ownership。当前 prompt-level aligned，默认 no-op，除非 exact read-back 暴露真实 delta。
- **FCC WS079 Writer**：`preserve-extension` PetroSim / scheduler-reliability / exact workspace-project safety；`move-to-generated` generic timeout、challenge、claim/recovery mechanics。迁移后仍必须保留 WS079 项目专属可靠性边界，而不是机械套用 WS012 文本。
- **FCC WS080 Writer**：`preserve-extension` multiprocess/conflict/source-first/scientific safety 与 exact worktree identity；`move-to-generated` 当前 static wrapper 中较完整的 challenge → timeout → reconcile → recover generic sequence。该 family 是 prompt-level 最优先 thinning candidate。
- **FCC WS086 Writer**：`preserve-extension` v5.8.0 soak、LM/TR/Runtime/acceptance 与节点/科学证据边界；`move-to-generated` 通用 continuation ownership/recovery mechanics。当前 mostly aligned，避免误删 soak/acceptance authority。
- **AStockT_AI Writer**：`preserve-extension` exact project checkout、Task State/plugin/roadmap 与项目特异数据/执行约束；`move-to-generated` generic continuation state-machine procedure。该 family aligned-but-heavy，迁移目标是 common-core 收敛而非项目语义削薄。
- **AStockT_AI Project Observer**：`keep` observer-only、stable Observer/control-plane 与 Writer ownership 分离，保留项目专属 target/runtime 语义为 extension；当前 prompt-level aligned，默认 no-op。

执行 Gate 对所有 family 相同：先取得 exact current task identity + raw prompt，计算 deterministic delta；只有具备该 sibling task 的 mutation authority 时才允许原位 update；update 后必须对**同一 task** exact read-back 并证明 common core、project extension 与 role separation 均未退化。缺失 executable argv/environment/installed-version/fingerprint 时只记录 `runtime_owned_fallback`，不把 prompt-level pass 冒充 full executable-definition 或 installed-state acceptance。任何不能安全证明 no-op/idempotent 的修改都不执行，也不通过创建 duplicate task 绕过 Gate。

2026-09-01 本次真实 WS012 scheduled activation 已提供一条有效 **pre-P1.5/shared-core Writer dogfood evidence**：activation input 明确要求 exact existing checkout、stable ACF canonical control plane、doctor/prompt generated plan、directive supersession、anti-masking、continuous useful work 与 long-lived mission；generation 77 stale owner 经正式 challenge timeout → reconcile → recover 转移到 generation 78，证明 scheduled Writer 确实消费 stable-generated owner/recovery protocol，而不是 static wrapper 自行实现第二套状态机。但 stable/candidate 对照也证明这**还不能算 P1.5 installed-state pass**：global stable `.83` 的 `scheduler_wrapper_contract` 只有旧 v1 字段，不含 `wrapper_family/role/runtime_execution_policy_source/named_extension_slot/p15_required_bootstrap_topics/execution_evidence_fields/volatile_fields_not_static/checkpoint_commit_gate_are_stop`；worktree candidate `.84` 才暴露这些 P1.5 machine-contract 字段。因此当前 activation 只能证明 shared core 已真实工作，不能证明 production scheduled Agent 已消费新的 P1.5 product contract。P1.5 installed-state acceptance 必须等包含这些字段的**新 immutable stable release + global install**后重新 dogfood；该证据也不外推为其他 task family 已通过。

同一系列 activation 也继续界定 **current-stable v0.0.3.83 fenced credential transport** 的真实边界：global `acf --version` 确认 canonical stable 仍为 `.83`；generation 78 期间“不携带 raw credential 调用 protected command”确定性返回 `fence_token_required`，说明 fail-closed 行为正确。generation 79 在 authenticated challenge timeout + receipt-bound reconcile 后使用同一 stable `.83` 正式 `recover`，recover 响应在**同一 execution context**返回 fresh fence credential，随后 `assert-owner` 成功，因此“stable `.83` 下 fresh owner 一概无法继续 protected writes”的表述被 supersede。既有 credential-file transport repair 仍必须保留：它解决的是跨 execution-context / scheduler handoff 时避免复制 raw high-entropy token 的 secret-safe transport，而不是替代 same-session raw credential 协议。不得因此把未发布 candidate `.84` 用作 canonical continuation writer，也不得重放已取消的 `.84` publishing identity；下一 immutable stable release/global install 仍需完成 credential-file transport 的 installed-state scheduler dogfood后才能关闭该产品级 repair。

generation 78 进一步确认一个必须在任何 package/release Gate 前先消除的 **immutable version collision risk**：annotated `v0.0.3.84` 已绑定历史 release identity，而当前 WS012 branch 在该 tag 之后已经包含 P0/P1/P1.5 新代码，`pyproject.toml`/egg metadata 却仍声明 `0.0.3.84`。因此当前 branch **禁止执行会生成可发布 `.84` artifact 的 package/release build，更禁止 publish**；否则会形成“同一版本号、不同源码”的冲突制品。实时 `pip index versions ai-context-framework` 仍显示 PyPI latest=`0.0.3.83`、`.84/.85` 均未占用，Git 仅存在 `v0.0.3.84` tag。下一稳定候选必须先按 release authority 切换到一个高于 `.84` 且 Git/PyPI 双重未占用的 immutable identity（按当前连续版本最自然是 `.85`，但正式 identity 仍由 release Gate 确认），同步 version/README/CHANGELOG/package metadata 后才允许 package/full release check。当前 generation 78 因 stable `.83` credential blocker 无法新增 canonical workspace intent/checkpoint，因此不在未认证状态下擅自改 release metadata；先把该 collision 作为 fail-visible release precondition 固化到 authority。

继续遵守 anti-masking：普通 WS012 Maintenance wake 不为维持 Dashboard 或 Project Narrative 新鲜而主动调用 production `observer snapshot/interpret/narrative-apply`；任何 Production acceptance 仍只能来自独立 Production Observer activation。

### 7.3 P1.5 → P2/P3 Gate dependency correction（generation 80）

generation 80 对 current PLAN、WS012 Workstream 与 candidate code/tests 做了 dependency audit，确认旧表述存在一个真实 circular Gate：一边要求“P1.5 live migration + interactive presentation lifecycle acceptance 全部收口后才进入 P2”，另一边又明确把 semantic review / presentation-maintenance runtime 的实现放在 P2，并把 narrow derived presentation surface 放在 P3。当前仓库证据也与后一种分层一致：`ai_context_framework/automation_contracts.py` 与 `tests/test_automation_contracts.py` 已冻结 `transient_patch / one_shot_semantic_review / durable_rule` machine contract，但尚不存在可对三生命周期做真实 end-to-end runtime acceptance 的产品 surface。继续沿用旧串行 Gate 只会产生两种错误结果：要么永久空转等待一个必须在后续阶段实现的能力，要么伪造“runtime 已验收”。两者都违反 fail-visible 与 continuous-useful-work 原则。

因此 durable phase/Gate 语义纠正为：

1. **P1.5 structural exit-to-P2 Gate**：contract/docs/template/tests 已冻结并通过；真实 task-family prompt-level audit 与 per-family thinning delta 已形成；platform/mutation authority boundary 已 fail-visible；interactive lifecycle acceptance matrix 与 P2/P3 implementation ownership 已明确。满足这些条件即可继续 P2 内部产品实现，不需要等待当前 scheduled context 无权执行的 sibling-task mutation。
2. **P2 Gate**：实现并验证 semantic review / one-shot request / durable-rule state machine、consume/cleanup/supersede/withdraw、Map Review escalation 与 independent staleness。P2 不实现 immediate presentation-only DOM/derived patch surface。
3. **P3 Gate**：实现 immediate transient derived-presentation maintenance、presentation revision/fingerprint optimistic concurrency、deterministic re-render、semantic-change escalation；并与 P2 state semantics 联调，完成三生命周期 integrated acceptance。
4. **跨阶段 operational/release Gate**：sibling Writer wrapper 原位迁移仍是 mandatory acceptance，不被取消或降级；但它在具备相应 same-task/interactive mutation authority 时执行 exact-before → deterministic same-task update → exact-after read-back。当前 context 只能 inventory/read-back 时继续 fail-visible，不阻断独立 P2/P3 实现。P4 / release / installed-state acceptance 前必须收口该 Gate。
5. **最终 acceptance 不放宽**：P4/full release/global install 前，必须同时具备真实 wrapper migration/read-back、三生命周期 runtime acceptance、new immutable stable installed-state dogfood；最终 Production acceptance 仍只从包含全部变化的最新稳定安装态重新起算。

该 correction 是依赖关系去环，不是削减用户需求：所有原 acceptance 项仍保留，只把“合同冻结”“runtime 实现”“外部 task migration”“integrated acceptance”的先后关系放回各自可实现的阶段，避免 synthetic progress 与 scheduler busywork。

### 7.4 P2 semantic lifecycle checkpoint（generation 84）

P2 semantic lifecycle 已在 `3fcac2815ee12003e17963a1f59c3669b5de38fd` 形成产品 checkpoint。当前实现把 target-local semantic review、独立 source fingerprint/staleness、one-shot review request、durable presentation rule、Map Review escalation、target narrative、problem model、route-impact 与 cross-project transfer linkage 落到 user-level Observer derived state，并通过 exact target revision + exact target source fingerprint 做 fail-closed optimistic concurrency。one-shot 成功 review 后退出 active context并仅在 audit event 保留 terminal evidence；durable rule 支持 supersede/withdraw；map-relevant signal 强制 authority reread；`route_change|major_replan` 不允许被 `decision=unchanged` 掩盖；foreign-project handler 只允许记录 transfer reference，不取得 foreign control authority。

P2 Gate 的验证证据已经收口：generation 83 的 durable full-unit effect 经正式 stale-owner challenge → receipt-backed reconcile/recover 证明 **640 tests PASS**；generation 84 重新执行 P2/Observer/Target + automation-contract focused regression 共 **83 tests PASS**，package skeleton **8 tests PASS**，并通过 file-scoped WS012 guard、`acf check --strict`、template check 与 `git diff --check`。该 checkpoint 只证明 **P2 semantic state semantics 已实现并验证**，不冒充 P3 或跨阶段 acceptance：immediate `transient_patch`、presentation revision/fingerprint concurrency、deterministic re-render、Dashboard V2 展示整合和三生命周期 integrated acceptance 仍属于 P3；sibling Scheduled Task wrapper 原位 migration/read-back 仍是进入 P4 / release 前必须完成的并行 operational Gate；最新 immutable stable release/global install 后的 installed-state dogfood 与 Production acceptance 规则也完全不变。

因此当前 implementation stage 正式推进到 **P3**：先实现 narrow transient derived-presentation maintenance + deterministic re-render 与 semantic-risk escalation，再把 transient / one-shot / durable 三生命周期接入 Chinese human-first self-contained Dashboard V2 并完成 integrated acceptance；不得把 `3fcac281` 当作 WS012 long-lived mission 完成、release ready 或 installed-state acceptance。


### 7.5 P3 Dashboard V2 / three-lifecycle integrated acceptance checkpoint（generation 88）

P3 产品实现在 `0e2137f9af74a9dda38553814e168f17745ea5f3` 形成 checkpoint：Chinese human-first self-contained Dashboard V2、immediate transient derived-presentation maintenance、presentation revision/fingerprint optimistic concurrency、deterministic re-render 与 semantic-risk escalation 已落盘。该产品 checkpoint 的既有 terminal validation 为 **650 full-unit tests PASS、93 P3 focused tests PASS、8 package-skeleton tests PASS**，并通过 file-scoped WS012 guard、strict docs、template 与 `git diff --check`。generation 87 在提交该 checkpoint 后失去 heartbeat；generation 88 通过 authenticated challenge timeout `28272700-c2c0-4f74-8253-459ba8338f8b`、reconcile receipt `bf489b27-8bc9-4916-bbdc-849d2364fd0c` 与 receipt-bound recover 正式接管，未重放任何 terminal effect，当前 effects unresolved=0。

generation 88 随后对当前 `0e2137f9` candidate 重新执行 `tests.test_observer_presentation`，**28 tests PASS**。该 focused runtime/CLI regression 已覆盖并联调三类 presentation lifecycle：one-shot request 只由正式 semantic review 消费且不能再次消费；durable rule 跨 review 保持 active 并支持 supersede/withdraw；transient patch 必须绑定 exact presentation revision/fingerprint，stale view fail-closed，semantic-risk signal 强制升级到 Map Review；正式 semantic review 会使旧 transient patch 失效；transient apply/clear 通过 deterministic re-render 更新 canonical Dashboard，同时验证不创建新 Observer snapshot/run、不改写 canonical current snapshot/run history；Dashboard V2 同时验证 human-first story、transient emphasis 与 stale-target fail-visible；integrated lifecycle teardown 验证已消费 one-shot、已清理 transient、已 supersede/withdraw durable guidance 均不会 resurrection。该证据满足 P3 Gate 所要求的 **candidate runtime integrated acceptance**，但明确不冒充新 stable installed-state dogfood 或 Production Observer acceptance。

因此 **P3 internal product/runtime Gate 已完成**，当前下一硬 Gate 收敛为此前已 fail-visible 的 **sibling Scheduled Task same-task wrapper migration/read-back operational Gate**。当前 scheduled execution context 对 sibling families 仍只有 inventory/full-prompt read-back，没有安全 mutation authority；不得创建 duplicate task，也不得把 prompt-level audit 冒充 migration pass。进入 P4 real-project dogfood 前必须在具备对应 same-task/interactive mutation authority 的上下文中，对需要迁移的 Writer family 执行 `exact-before → deterministic same-task update → exact-after read-back`，并保留各 family 的 project/scientific/Runtime/security/validation extension。ACF Project Observer 与 AStockT_AI Project Observer 继续保持 prompt-level aligned/no-op，除非 exact read-back 暴露真实 delta。该 platform boundary 不取消 P4/release Gate，也不授权 Maintenance 通过 Observer refresh 人为补 freshness。
