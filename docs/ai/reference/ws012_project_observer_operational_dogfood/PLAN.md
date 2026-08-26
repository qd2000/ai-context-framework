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

## 2. Scheduler topology

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

### WS012.6 — 24-hour production watchdog window

原 24 小时 acceptance window 保留，但因为 WS012.3/4/5 将改变 continuation 和 Observer 产品，应在这些能力完成 release + global install 后**重新从新的稳定基线开始计数**。

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

截至 2026-08-26，WS012.3/4/5 已随 `v0.0.3.83` 之前的稳定版本完成实现、release/global install 与 installed-state dogfood；ordered source-lineage 修复也已随 `v0.0.3.83` 安装并验证。当前默认执行顺序改为：

1. 修复并验证正式 `ACF Project Observer` 的 Project Narrative production refresh operational flow（issue `530d8683b093945f0b4a`）；首个 `.83` 独立 production revision 175 已证明 snapshot/Workstream semantic/source/self-health/history 正常，但 narrative 仍 stale，因此不能计为通过样本；
2. 修复后从下一次独立 `:34` activation 重新开始连续 24 次 acceptance，严格按本节 production-only 证据计数；
3. 并行保持 `5067de152f19558f2d8b` 为 current-stable Ready Batch candidate；只有达到 WS012.5 的 Immediate/Batch 门槛才启动代码 maintenance release，不为了单个普通 high issue 高频发版；
4. 每个 `:04` wake 继续先查 pending directive / Immediate issue / batch threshold，再做 production acceptance 只读核验；无当前安全有价值工作则不 claim、不制造 control-plane busywork。

继续遵守 anti-masking：普通 WS012 Maintenance wake 不为了让 Dashboard 或 Project Narrative 看起来新鲜而例行调用 production `observer snapshot/interpret/narrative-apply`。
