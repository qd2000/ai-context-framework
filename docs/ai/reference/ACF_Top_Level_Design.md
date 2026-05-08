# ACF Top-Level Design

本文记录 ACF 的顶层产品设计。它是后续新增对象、规则、CLI 命令、模板结构、upgrade 行为和 dogfooding 评测的上位约束。

[reference/Product_Roadmap.md](Product_Roadmap.md) 负责阶段路线和准入节奏；本文件负责回答 ACF 是什么、边界在哪里、内容如何分层、对象如何建模、CLI 各层如何分工。

---

## 状态

Active

---

## 0. 总目标

ACF 的目标是建立一个面向 AI 协作的、模型无关、纯 Markdown、可人工审阅、可机械检查、可渐进升级的上下文治理框架。

它解决的核心问题是：AI 长期维护项目时，当前事实和历史事实容易混杂，active 层会持续膨胀，任务编号和 Workstream 阶段会漂移，权威上下文可能被子任务随意修改，索引和详情会不一致，已完成内容会滞留 active，旧项目升级后会产生结构漂移，AI 手写 Markdown 也容易漏字段、漏索引、漏证据。

ACF 的产品定位不是替 AI 思考，也不是替人裁决事实，而是让 AI 只能在可审计、可回退、可检查的边界内维护上下文。

核心判断：

1. Markdown 文件仍是事实源。
2. CLI 是确定性维护工具，不是事实裁判。
3. audit 是候选发现，不是错误判定。
4. draft 是可审阅草案，不是权威事实。
5. upgrade 是非破坏式结构补齐，不是语义迁移。
6. Workstream 是并行目标线协议，不是 agent runtime。

---

## 1. 产品定位

### 1.1 必须坚持的定位

ACF 必须保持以下属性：

1. 模型无关：不绑定 ChatGPT、Codex、Claude 或任何私有上下文格式。
2. 纯 Markdown：上下文文件是人可以直接读、直接审阅、直接 diff 的 Markdown。
3. 人工可审阅：任何权威事实变更都应能通过普通文件 diff 复核。
4. 渐进式暴露：AI 默认只读当前高信号上下文，不默认读取 archive、完整 worklog 或历史草案。
5. 单一事实源：同一类事实必须有唯一权威位置，其他位置只做引用、摘要或索引。
6. CLI 确定性：CLI 做结构维护、检查、同步、草案和升级，不做事实真假判断。
7. 兼容旧项目：旧上下文不能因为没有新对象层而立即失败；新结构应 optional 或由 upgrade 非破坏式补齐。
8. 无第三方运行依赖：优先使用 Python 标准库和 Markdown 约定，不引入数据库、向量库、常驻服务或 YAML 依赖。
9. 可测试：新增规则和命令必须能用 fixture、单元测试或 smoke 流程验证。
10. 可降级：语义不确定的信号先进入 audit candidate 或 draft，不直接进入 strict gate。

### 1.2 非目标

ACF 不做：

1. 不做 agent runtime。
2. 不做任务调度器。
3. 不做数据库或向量库。
4. 不做自动事实裁判。
5. 不做通用 Markdown 编辑器。
6. 不自动合并 Workstream 结论到 Context、ADR、rules 或 Knowledge。
7. 不自动语义去重。
8. 不为 FCC、EcSOS 或任何单个真实项目新增专用规则。
9. 不把 usage event log、原始命令输出或完整对话写入权威上下文。
10. 不因为某个模型输出习惯而改变通用模板结构。

新增功能必须说明属于哪一层：`check`、`audit`、`sync`、`draft`、`upgrade`，还是普通 CLI 维护命令。新增规则还必须说明为什么不是项目特例。

---

## 2. 内容组织模型

### 2.1 标准目录结构

标准上下文根目录为 `docs/ai/`，推荐结构如下：

```text
docs/ai/
  AGENTS dot md

  active/
    Context dot md
    Current_Task dot md
    Task_Plan dot md
    Feedback_Inbox dot md
    Workstreams dot md
    workstreams/

  rules/
    Always_Active dot md
    Project_Rules dot md
    Coding_Rules dot md
    Writing_Rules dot md
    Review_Rules dot md

  reference/
    Project_Brief dot md
    Architecture dot md
    Tech_Context dot md
    System_Manual dot md
    Context_Curation_Prompt dot md
    Product_Roadmap dot md
    ACF_Top_Level_Design dot md
    Workstream_Design dot md
    Context_Audit_Design dot md
    Upgrade_Migration_Plan dot md
    Front_Matter_Metadata_Plan dot md
    Knowledge_Index dot md
    Sources_Index dot md
    Decisions_Index dot md

  decisions/
    ADR-0001 dot md

  worklog/
    Worklog_Index dot md
    daily/
    writeback-drafts/
    curation-drafts/
    knowledge-drafts/

  archive/
    Archive_Index.md
    tasks/
    plans/
    workstreams/
    feedback/
```

该结构是标准模型，不表示所有旧项目必须一次性具备全部文件。`init` 生成当前标准结构，`upgrade` 非破坏式补齐安全缺口，旧项目缺少 optional 层时不应默认失败。

### 2.2 active/

`active/` 只放当前注意力入口：

1. 当前阶段目标。
2. 当前有效事实。
3. 当前具体任务。
4. 当前任务板。
5. 当前 Workstream 和内部阶段焦点。
6. 待处理 feedback。

`active/` 禁止长期承载：

1. 完整历史过程。
2. 冗长日志。
3. 旧运行状态。
4. 大段 runbook。
5. 已完成且不再支撑当前计划的内容。
6. 默认不需要 AI 当前读取的 archive、draft 或 worklog 细节。

### 2.3 reference/

`reference/` 放长期稳定背景和设计资料：

1. 项目简介。
2. 架构说明。
3. 技术环境。
4. 使用手册。
5. 产品路线。
6. 设计文档。
7. 资料索引。
8. Knowledge 索引。
9. 决策索引。

`reference/` 可以被 active 引用，但不应复制 active 当前事实。叙述型 reference 文档默认不加复杂 front matter。

### 2.4 worklog/

`worklog/` 放历史过程摘要：

1. 今天做了什么。
2. 验证了什么。
3. 发现了什么。
4. 哪些结论还未升格。
5. 哪些证据可以追溯。

worklog 不是当前事实源。它可以作为证据位置，但不能替代 [active/Context.md](../active/Context.md)、任务板、ADR 或 Knowledge。

### 2.5 archive/

`archive/` 放旧任务、旧计划、旧 Workstream 和已处理 feedback。archive 默认不进入读取路径。

归档原则：

1. 保留可追溯摘要，不复制冗长过程。
2. 保留 ID、最终状态、证据和原始位置。
3. 当前计划不再需要解释的 Done / Cancelled Workstream 应迁出 active。
4. archive 不是事实裁决层；它只降低默认上下文噪声。

### 2.6 rules/

`rules/` 放当前项目约束。[rules/Always_Active.md](../rules/Always_Active.md) 是默认生效规则；其他规则按场景读取。

规则文档不应夹带一次性任务计划或项目运行日志。新增规则必须能说明适用范围和触发条件。

---

## 3. 权威事实模型

### 3.1 事实源优先级

默认事实源优先级：

1. 用户当前消息。
2. [active/Current_Task.md](../active/Current_Task.md)。
3. [active/Task_Plan.md](../active/Task_Plan.md)。
4. [active/Context.md](../active/Context.md)。
5. [active/Feedback_Inbox.md](../active/Feedback_Inbox.md)，仅作为待处理信号。
6. [reference/Decisions_Index.md](Decisions_Index.md)。
7. ADR 文件。
8. [reference/Knowledge_Index.md](Knowledge_Index.md)。
9. `worklog/`。
10. `archive/`。

如果用户当前消息与项目文件冲突，以用户当前消息为当前任务事实，并在写入时显式处理冲突。

### 3.2 唯一权威位置

写入前必须先判断唯一权威位置：

| 信息类型 | 权威位置 | 非权威位置 |
|---|---|---|
| 当前阶段目标和当前有效事实 | [active/Context.md](../active/Context.md) | worklog、archive、草案 |
| 当前具体任务 | [active/Current_Task.md](../active/Current_Task.md) | worklog、旧计划 |
| 当前任务板和 Task Stage | [active/Task_Plan.md](../active/Task_Plan.md) | worklog、archive |
| Workstream metadata 和 stage | `active/workstreams/WS*.md` | [active/Workstreams.md](../active/Workstreams.md) |
| Workstream 低噪音摘要 | [active/Workstreams.md](../active/Workstreams.md) | 详情正文 |
| 待处理反馈 | [active/Feedback_Inbox.md](../active/Feedback_Inbox.md) | worklog、最终回复 |
| 稳定决策 | ADR 文件 + [reference/Decisions_Index.md](Decisions_Index.md) | worklog、Task_Plan |
| 可复用经验 | [reference/Knowledge_Index.md](Knowledge_Index.md) + knowledge 条目 | active、daily worklog |
| 历史过程 | `worklog/daily/` | active |
| 旧任务和旧计划 | `archive/` | active |

能更新旧表述时，不追加重复事实。能引用权威位置时，不复制完整内容。

### 3.3 索引与详情

索引文件是低噪音导航，不是详情事实源。当前已稳定的规则：

1. Workstream 详情 front matter 是 Workstream metadata 事实源。
2. [active/Workstreams.md](../active/Workstreams.md) 是由详情派生或同步的索引视图。
3. `sync` 可以更新索引，但不能改详情事实。
4. 索引和详情不一致时，`check` 报告问题，并以详情为准。

未来 Knowledge、ADR、Archive 如扩展 sync，必须先定义 generated block marker、删除策略和兼容规则，不能直接套用 Workstream sync。

---

## 4. 对象模型

ACF 不把所有 Markdown 文件变成强 schema。只有状态型对象需要轻量机器字段或稳定表格字段。

### 4.1 Task

用途：项目主线任务。

位置：

1. [active/Task_Plan.md](../active/Task_Plan.md)
2. [active/Current_Task.md](../active/Current_Task.md)

核心字段：

1. ID。
2. 状态。
3. 名称。
4. 依赖。
5. 输出物。
6. 证据。
7. 下一步。

第一阶段继续使用 Markdown table，不急于创建 `active/tasks/T001` 这类单文件。只有当任务复杂度长期超过表格能力时，再评估 Task object 文件。

### 4.2 Task Stage

用途：允许 `T001.4` 这类子阶段合法存在，并防止 Current_Task 引用漂移。

位置：[active/Task_Plan.md](../active/Task_Plan.md) 的 `## 任务阶段` 表。

推荐表结构：

```markdown
## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| T001.4 | Active | T001 | formal Morris 集成 | WS004 | WS001,WS002 | summary | active/workstreams/WS004.md | 等待结果 |
```

规则：

1. `Txxx.y` 必须注册。
2. 父任务 `Txxx` 必须存在。
3. 归属 Workstream 必须存在。
4. `Current_Task` 引用的阶段必须未终结。
5. 历史依赖可以引用 Done Workstream。

已落地的第一版普通 CLI 维护命令：

```bash
acf plan stage list ...
acf plan stage add ...
acf plan stage set ...
acf plan stage done ...
```

该命令族只维护 [active/Task_Plan.md](../active/Task_Plan.md) 的 `## 任务阶段` 表，不创建 task object 单文件，不自动修改 [active/Current_Task.md](../active/Current_Task.md)，不自动联动 Workstream。更重的 Task object 文件仍后置。

### 4.3 Workstream

用途：并行目标线，不是 runtime，不是调度器，不是权限系统。

位置：[active/workstreams/WS001.md](../active/workstreams/WS001.md)。

推荐 front matter：

```yaml
---
id: WS001
status: Active
owner: 主 agent
title: 并行任务治理模型
current_stage: WS001.2
depends_on:
  - WS000
read_scope:
  - active/Context.md
write_scope:
  - owned: active/workstreams/WS001.md
  - draft: worklog/writeback-drafts/WS001-*
merge_targets:
  - active/Context.md
merge_resolution: no_merge_required
keep_active_reason: Still needed by current active plan.
keep_active_until: 2026-05-10
---
```

规则：

1. `id` 必须匹配 `WSxxx`。
2. `status` 必须属于 Workstream 状态机。
3. `current_stage` 可选；存在时必须在本文件 `## 阶段` 表注册。
4. Done 必须有 evidence 和 `merge_resolution`。
5. Done / Cancelled 留 active 时必须有 `keep_active_reason` 和 `keep_active_until`。
6. `write_scope` 不能通过 `owned` 或 `assigned` 直接命中内置 authority path。
7. `merge_targets` 只是候选影响范围，不表示可直接写目标文件。

### 4.4 Workstream Stage

用途：表达长期 Active Workstream 内部当前推进到哪一步。

位置：对应 Workstream 详情文件的 `## 阶段` 表。

推荐表结构：

```markdown
## 阶段

| ID | 状态 | 阶段 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| WS004.1 | Done | pct25 metrics | 无 | metrics | output/... | 激活 WS004.2 |
| WS004.2 | Active | pct10 metrics | WS004.1 | metrics | output/... | 完成后进入 WS004.3 |
```

规则：

1. stage ID 必须属于当前 Workstream，例如 `WS004` 只能注册 `WS004.x`。
2. `current_stage` 必须存在于阶段表。
3. 同一 Workstream 最多一个 Active stage。
4. `current_stage` 不能是 Done、Cancelled 或 Skipped。
5. Done / Cancelled Workstream 不能有 Active stage 或非终态 current_stage。
6. Done stage 必须有 evidence。

命令闭环：

```bash
acf workstream stage add WS004 --id WS004.2 --title "pct10 metrics" --json
acf workstream stage list WS004 --json
acf workstream focus WS004 WS004.2 --json
acf workstream stage done WS004 WS004.2 --evidence "..." --clear-current --json
```

原则：

1. 不自动推进下一阶段。
2. 不默认改 [active/Current_Task.md](../active/Current_Task.md)。
3. 不自动合并 Context。
4. 不变成任务调度器。

### 4.5 ADR

用途：记录稳定重要决策。

位置：

1. [decisions/ADR-0001.md](../decisions/ADR-0001.md)
2. [reference/Decisions_Index.md](Decisions_Index.md)

规则：

1. ADR ID 不复用。
2. ADR 状态应与索引一致。
3. Proposed 与 Active 的语义要清楚。
4. ADR 记录决策与取舍，不记录冗长实现过程。
5. 重要路线改变优先用 ADR 固化，普通计划留在 Product Roadmap 或 Task_Plan。

### 4.6 Knowledge

用途：保存可迁移经验，不保存当前事实或一次性过程。

位置：

1. [reference/Knowledge_Index.md](Knowledge_Index.md)
2. `reference/knowledge/*.md`
3. `worklog/knowledge-drafts/`

规则：

1. Knowledge 草案不进入默认读取路径。
2. apply 前必须可审阅。
3. Knowledge 不重复 ADR、rules 或 active 当前事实。
4. 可复用经验必须有来源或适用边界。

### 4.7 Archive item

用途：保存已退出当前注意力入口的旧任务、旧计划、旧 Workstream 和已处理反馈。

位置：

1. `archive/tasks/`
2. `archive/plans/`
3. `archive/workstreams/`
4. `archive/feedback/`
5. [archive/Archive_Index.md](../archive/Archive_Index.md)

规则：

1. 归档项保留最终状态、证据、原位置和摘要。
2. 不复制完整过程。
3. archive 默认不读。
4. 归档不是删除；仍需可追溯。

---

## 5. CLI 能力分层

ACF CLI 必须分层清楚。每个新命令和新规则都要明确所在层。

### 5.1 check --strict

用途：低误报、可机械裁决的硬门禁。

适合进入 strict 的规则：

1. ID 未注册。
2. 状态非法。
3. 引用断链。
4. metadata 缺必填字段。
5. Workstream 直接写 authority path。
6. ReadyToMerge 缺合并请求。
7. Done 缺 evidence。
8. Done 缺 `merge_resolution`。
9. `keep_active_until` 过期。
10. 索引和详情不一致。
11. 模板占位符在真实上下文中残留。

不适合进入 strict 的规则：

1. 疑似重复事实。
2. 疑似无证据强结论。
3. 疑似易变事实位置错误。
4. section 可能太长。
5. 当前任务可能 stale。

实施要求：

1. 每个 strict rule 必须有 fixture 或单元测试。
2. 每个 error 必须有稳定 message 或 error_code。
3. JSON 输出必须能让 AI 解析下一步。
4. strict rule 不能依赖具体项目业务语义。

### 5.2 audit context

用途：只读候选发现，不裁决事实，不写文件。

当前命令：

```bash
acf audit context [path] --json
```

MVP candidates：

1. `active_section_too_long`
2. `stale_current_task_or_workstream_stage`
3. `terminal_conclusion_not_merged`

输出结构：

```json
{
  "schema_version": 1,
  "ok": true,
  "command": "audit context",
  "context": "docs/ai",
  "candidates": [],
  "summary": {
    "total": 0,
    "by_kind": {},
    "by_path": {},
    "by_severity": {}
  },
  "next_actions": []
}
```

candidate 字段：

```json
{
  "kind": "active_section_too_long",
  "severity": "P1-candidate",
  "path": "active/Context.md",
  "section": "当前有效事实",
  "reason": "...",
  "suggested_action": "..."
}
```

暂缓规则：

1. `duplicate_active_fact_candidate`
2. `strong_claim_without_evidence`
3. `volatile_fact_in_wrong_authority_location`

这些规则只有在多项目样本和 fixture 证明低噪声后，才能作为 audit candidate 实现；不得直接进入 strict。

### 5.3 sync

用途：同步 generated / index view，不改事实源。

当前典型命令：

```bash
acf workstream sync docs/ai --dry-run --json
```

边界：

1. 只更新 [active/Workstreams.md](../active/Workstreams.md)。
2. 详情 front matter 是事实源。
3. 不修改 Workstream 详情正文。
4. 不删除缺详情的旧索引行，除非未来单独设计 cleanup。
5. 不碰 Knowledge、ADR、Archive。

未来可扩展：

```bash
acf knowledge sync
acf decisions sync
acf archive sync
```

扩展前必须先设计 generated block marker、删除策略、索引详情事实源关系和升级兼容行为。

### 5.4 upgrade

用途：非破坏式补齐结构。

原则：

1. dry-run first。
2. 不覆盖用户正文。
3. 不移动 active 当前任务。
4. 不自动升格事实。
5. 不因旧项目缺新结构而失败。
6. 无法安全迁移时添加 marker notes，而不是重写全文。

典型流程：

```bash
acf status docs/ai --json
acf check docs/ai --json
acf upgrade docs/ai --dry-run --json
acf upgrade docs/ai --json
acf check docs/ai --strict --json
acf audit context docs/ai --json
```

upgrade 可以补文件、补目录、补手册 section、补 marker notes。upgrade 不可以改当前事实、完成当前任务、补审阅结论、归档历史、判断业务事实或自动修 stale。

### 5.5 draft

用途：生成可审阅草案，不写权威上下文。

已有或建议命令：

```bash
acf writeback draft
acf curate draft
acf knowledge draft
```

边界：

1. 草案不进入默认读取路径。
2. 草案不等于事实。
3. 草案需要人工或主代理审阅后才 apply。
4. 子 agent 更适合产出草案或建议 patch，而不是直接写权威上下文。

### 5.6 普通维护命令

普通维护命令用于确定性结构落盘，例如 `plan`、`task`、`archive`、`knowledge apply`、`new worklog`、`new adr`、`edit section`、`edit table upsert`。

要求：

1. 支持 JSON 输出。
2. 写命令支持 dry-run。
3. 写命令报告 changed files。
4. 高风险写入支持 check-after。
5. 失败输出包含 `error_code`、`message` 和 `next_actions`。
6. 路径必须限制在设计好的安全边界内。

### 5.7 JSON 与错误码契约

所有 AI-facing 命令都必须让调用方无需解析自然语言即可判断下一步。不同命令可以有不同 payload，但必须遵守最小字段和命名习惯。

成功输出的最小契约：

```json
{
  "schema_version": 1,
  "ok": true,
  "command": "...",
  "next_actions": []
}
```

写命令成功时还应包含：

```json
{
  "dry_run": false,
  "changed_files": [],
  "warnings": []
}
```

检查、审计或查询命令可按命令语义增加 `check`、`candidates`、`summary`、`items`、`stages`、`workstreams` 等字段，但字段名必须稳定，路径输出优先使用 context-root 或 repo-root 相对 POSIX slash。

失败输出的最小契约：

```json
{
  "schema_version": 1,
  "ok": false,
  "command": "...",
  "error_code": "...",
  "message": "...",
  "next_actions": []
}
```

约束：

1. `schema_version` 表示该命令族 JSON 契约版本，当前统一从 `1` 开始。
2. `ok=false` 必须有稳定 `error_code`。
3. `message` 面向人阅读，不能作为机器分支唯一依据。
4. `next_actions` 必须是低风险、可执行的下一步，不得暗示自动事实裁决。
5. `warnings` 表示命令成功但存在需复核的结构信号；warning 不等于失败。
6. `errors` 如出现，应是结构化问题列表；命令级失败仍以 `error_code` 为主。
7. 新增或重命名 JSON 字段时，必须评估版本号和测试。
8. 对 AI 常用恢复路径，优先使用稳定错误码，例如 duplicate、not_found、invalid_transition、scope_conflict、check_failed、path_outside_context。

---

## 6. Workstream 管理闭环

### 6.1 目标

Workstream 支持长期并行目标线，而不是让 active 文档变成巨大过程日志。

目标体验：

```text
WS004 是 Active。
WS004.current_stage = WS004.2。
WS004.1 Done。
WS004.2 Active。
WS004.3 Pending。
AI 进入项目时能知道当前推进哪个阶段。
```

### 6.2 已解决能力

当前设计和实现方向已经覆盖：

1. Workstream front matter。
2. Workstream 状态机。
3. `current_stage` 检查。
4. `## 阶段` 表检查。
5. authority gate。
6. `merge_targets`。
7. `merge_resolution`。
8. `keep_active_reason` / `keep_active_until`。
9. Workstreams index check + sync。
10. stage add/list/focus/done 命令闭环。

### 6.3 生命周期

Workstream 的生命周期用于降低 active 长期膨胀风险：

```text
Open -> Active -> ReadyToMerge -> Done -> archive
              -> Blocked -> Active
Open/Active/Blocked/ReadyToMerge -> Cancelled -> archive
```

规则：

1. Open 表示目标线已登记但尚未推进。
2. Active 表示当前正在推进。
3. Blocked 表示有明确阻塞原因，阻塞解除后可回到 Active。
4. ReadyToMerge 表示已有可审阅、可落盘、可验证的合并输入，不表示权威上下文已更新。
5. Done 表示结论已合并、归档或明确不需要合并，并有 evidence 和 `merge_resolution`。
6. Cancelled 表示目标线明确终止，不再推进。
7. Done / Cancelled 是终态；需要继续推进时应新建 Workstream 或新建后续任务，不默认复活旧 ID。
8. Done / Cancelled 留在 `active/workstreams/` 只能短期解释当前计划，必须有 `keep_active_reason` 和 `keep_active_until`。
9. 当前计划不再需要解释的 Done / Cancelled Workstream 应进入 `archive/workstreams/`，archive 默认不读取。
10. 第一版不自动归档；归档必须由显式 archive 流程或人工审阅完成。

归档项应保留：ID、最终状态、标题、owner、处理结果、证据位置、merge_resolution、原详情文件位置和简短摘要。不复制冗长过程。

### 6.4 stage add

输入：

1. WS ID。
2. stage ID。
3. title。
4. depends 可选。
5. output 可选。

规则：

1. stage ID 必须属于 WS。
2. 不能重复。
3. 默认状态 Pending。
4. 只修改对应 WS 文件。
5. 不自动 focus。
6. 不修改 [active/Current_Task.md](../active/Current_Task.md) 或 [active/Context.md](../active/Context.md)。

### 6.5 focus

输入：

1. WS ID。
2. stage ID。

规则：

1. stage 必须存在。
2. stage 不能 Done、Cancelled 或 Skipped。
3. 同一 WS 不能已有其他 Active stage。
4. 同一 WS 内部依赖未 Done 时默认拒绝。
5. 更新 front matter `current_stage`。
6. 将 stage 状态改为 Active。
7. 不修改 [active/Current_Task.md](../active/Current_Task.md)，除非未来明确增加 `--update-current-task`。

多 Active stage 策略：

1. 第一版 `focus` 遇到同一 Workstream 已有其他 Active stage 时必须拒绝。
2. `focus` 不自动把旧 Active stage 改回 Pending、Blocked 或 Skipped。
3. 拒绝输出必须使用稳定错误码，并在 `next_actions` 中提示先完成、取消或显式调整旧 Active stage。
4. 如果未来需要支持替换当前 Active stage，必须新增显式参数，例如 `--replace-active`，并要求记录 reason。
5. `--replace-active` 若进入设计，也只能维护同一 Workstream 详情文件，不得自动修改全局 Current_Task 或 Context。

### 6.6 stage done

输入：

1. WS ID。
2. stage ID。
3. evidence。
4. `--clear-current` 可选。

规则：

1. evidence 必填。
2. stage 状态改为 Done。
3. 写入 evidence。
4. 如果 stage 是 `current_stage`，必须 `--clear-current` 或未来传 `--next`。
5. 不自动激活下一阶段。
6. 不自动合并 Context。

### 6.7 stage list

输出：

1. WS metadata。
2. `current_stage`。
3. `stages[]`。
4. `next_actions`。

### 6.8 后置能力

暂不做：

1. `--update-current-task`。
2. 自动 next stage。
3. 自动归档 WS。
4. 自动合并 Context。
5. 图形化 kanban。
6. agent runtime 调度。

---

## 7. Audit 规划

### 7.1 当前 MVP

已实现：

1. `active_section_too_long`
2. `stale_current_task_or_workstream_stage`
3. `terminal_conclusion_not_merged`

这些规则用于发现候选，不表示事实错误。

### 7.2 调优原则

新增或调整 audit 规则前必须回答：

1. 这是通用治理问题吗？
2. 能否机械检测？
3. 是否能构造 fixture？
4. 会不会伤害 minimal / legacy？
5. 应进入 strict 还是 audit？
6. 是否需要多项目验证？
7. reason 是否能解释触发依据？
8. suggested_action 是否是低风险审阅建议？

### 7.3 暂缓规则准入条件

`duplicate_active_fact_candidate` 风险是容易误把合理摘要当重复。进入条件：

1. 至少 3 个 fixture。
2. ACF / FCC / EcSOS 中至少 2 类样本。
3. 只输出 candidate。
4. reason 必须说明重复依据。

`strong_claim_without_evidence` 风险是中文自然语言强结论难以稳定识别。进入条件：

1. 先定义强结论短语白名单。
2. 只检查 active 层。
3. 附近找 evidence path、日期、worklog 或 ADR。
4. 不进入 strict。

`volatile_fact_in_wrong_authority_location` 风险是易变事实依赖项目类型。进入条件：

1. 先定义通用 volatile kinds。
2. 只报告明显 runtime、status、PID、tmux、worker 字样。
3. 项目可配置后再扩展。

---

## 8. 多项目验证矩阵

任何新规则、对象字段或 CLI 行为都不能只由一个真实项目驱动。

必需样本：

| 样本 | 作用 | 要求 |
|---|---|---|
| ACF 自身 | 产品自洽、中等复杂 dogfooding | 每个阶段默认检查 |
| FCC | 复杂工程压力测试、Workstream-heavy | 只读优先，反馈必须抽象后进入 ACF |
| EcSOS | 非 PetroSim、论文 / 数据分析 / Python 工具项目 | 验证 upgrade、stale、audit 低噪声 |
| minimal project | 验证空白/小项目不增加负担 | init/status/check/audit 必须低噪声 |
| legacy project | 验证旧项目升级兼容 | upgrade 不破坏旧正文，不强制新对象 |
| synthetic fixtures | 边界复现、防止过拟合 | 新规则必须优先补 fixture / unit test |
| non PetroSim project | 防止领域过拟合 | 进入高误报 audit 前必须覆盖至少一个 |

新规则准入至少需要：

1. 一个 synthetic fixture。
2. 一个 minimal 或 legacy 不误伤测试。
3. 一个真实项目 dogfooding 观察。
4. 明确 strict/audit/sync/draft/upgrade 分层。

---

## 9. 升级兼容原则

### 9.1 标准流程

旧项目建议流程：

```bash
acf status docs/ai --json
acf check docs/ai --json
acf upgrade docs/ai --dry-run --json
acf upgrade docs/ai --json
acf check docs/ai --strict --json
acf audit context docs/ai --json
acf review stale docs/ai --json
```

### 9.2 upgrade 只做结构

upgrade 可以：

1. 补缺失文件。
2. 补缺失目录。
3. 补手册 section。
4. 补 marker notes。
5. 非破坏式补齐新的可选入口。

upgrade 不可以：

1. 改当前事实。
2. 完成当前任务。
3. 补审阅结论。
4. 归档历史。
5. 判断论文或业务事实。
6. 自动修 stale。

### 9.3 版本策略

需要 bump 版本的情况：

1. CLI 对外命令变更。
2. JSON 输出契约变更。
3. check 行为变更。
4. 模板结构变更。
5. upgrade 行为变更。
6. 用户文档行为变更。

patch / minor 判断：

1. patch：兼容新增，旧项目不新增失败。
2. minor：默认结构或 strict 行为明显改变，旧项目可能需要迁移。

更细规则：

1. patch：新增向后兼容 CLI 命令；新增 optional JSON 字段；修复错误码 message；新增文档说明；新增不影响旧项目 strict 结果的 check warning；新增 optional template 文件且 upgrade 可非破坏式补齐。
2. patch：新增 audit candidate 规则但默认只读、低噪声、minimal / legacy 不误伤，并有 fixture 覆盖。
3. minor：默认 init 结构改变；`check --strict` 对旧项目产生新的失败类型；已有 JSON 字段重命名或语义改变；upgrade 默认行为明显改变；对象模型从 optional 变成默认要求。
4. minor：sync 从单一索引扩展到新的 generated view，且可能影响用户手写索引内容。
5. 不需要 bump：只修改 dogfooding `docs/ai/` 内部规划、worklog、当前任务或非用户可见的评测记录，且不改变 CLI、模板、手册对外行为和检查结果。
6. 是否 bump 的判断必须写入最终报告；做了版本更新时优先使用 `uv run acf version set <version>`。

---

## 10. 测试规划

### 10.1 单元测试

每个命令必须按风险覆盖：

1. happy path。
2. dry-run。
3. JSON output。
4. error_code。
5. next_actions。
6. check-after。
7. invalid input。
8. path traversal / out-of-context。

### 10.2 fixture 测试

当前和建议 fixture：

```text
tests/fixtures/context_matrix/
  minimal_clean
  legacy_old_context
  audit_long_section
  workstream_complex
  authority_gate
  task_stage_registry
  workstream_stage_flow
  upgrade_custom_agents
  audit_stale_stage
  audit_terminal_merge
```

### 10.3 smoke

[scripts/minimal_smoke.py](../../../scripts/minimal_smoke.py) 应覆盖：

1. init。
2. status。
3. check。
4. worklog create/append。
5. workstream init/add/stage/focus/done/sync。
6. audit context clean。

### 10.4 upgrade matrix

upgrade matrix 必须覆盖：

1. old minimal。
2. old standard。
3. custom AGENTS。
4. missing Feedback。
5. missing Task_Plan。
6. old Workstream absent。
7. old ADR without front matter。

---

## 11. 文档体系

稳定文档职责：

| 文档 | 职责 |
|---|---|
| `ACF_Top_Level_Design.md` | 顶层产品设计、边界、对象模型、CLI 分层和验证原则 |
| `Product_Roadmap.md` | 分阶段路线、优先级、准入门槛和当前下一步 |
| `Architecture.md` | 仓库和 CLI 架构说明 |
| `System_Manual.md` | 项目内维护者和 AI 的操作手册摘要 |
| `Workstream_Design.md` | Workstream 协议、状态机、stage/focus、merge/retention、sync 细节 |
| `Workstream_Lifecycle_Archive_Design.md` | Done / Cancelled Workstream 从 active 保留到 archive 的 helper 边界 |
| `Context_Audit_Design.md` | audit candidates、JSON 输出、暂缓规则和调优原则 |
| `Upgrade_Migration_Plan.md` | 旧上下文升级策略、兼容矩阵和 migration 行为 |
| `Front_Matter_Metadata_Plan.md` | 轻量 metadata 字段、适用对象和 parser 约束 |
| [../Automation.md](../../Automation.md) | 已自动化能力、后续自动化边界、验证命令 |
| [../../README.md](../../../README.md) | 面向使用者的安装、初始化和核心使用说明 |

### 11.1 权威关系

设计文档之间采用“上位边界 + 专题细节 + 使用入口”的关系：

1. `ACF_Top_Level_Design.md` 是上位架构和边界，回答 ACF 是什么、不是什么、对象和 CLI 怎么分层。
2. `Product_Roadmap.md` 是阶段路线，回答先做什么、后做什么、准入门槛和近期优先级。
3. `Workstream_Design.md` 是 Workstream 专题细节，回答状态机、stage/focus、merge/retention、sync 和具体命令契约。
4. `Workstream_Lifecycle_Archive_Design.md` 是 Workstream archive helper 专题细节，回答终态 Workstream 何时只生成候选、何时可显式归档。
5. `Context_Audit_Design.md` 是 audit 专题细节，回答 candidates、JSON 输出、调优记录、暂缓规则和误报控制。
6. `Upgrade_Migration_Plan.md` 是 upgrade 专题细节，回答旧项目迁移、marker notes、兼容矩阵和 dry-run 行为。
7. `Front_Matter_Metadata_Plan.md` 是 metadata 专题细节，回答哪些对象适合 front matter、字段约束和 parser 限制。
8. `System_Manual.md` 是项目内维护者和 AI 的操作手册，回答日常怎么用命令和失败后怎么办。
9. [../Automation.md](../../Automation.md) 是自动化路线和验证命令，回答当前已自动化什么、下一步自动化什么、发布前怎么验。
10. [../../README.md](../../../README.md) 是公开入口摘要，回答用户如何理解、安装和开始使用。

### 11.2 防漂移规则

新增或修改这些文档时，应检查是否改变了事实源职责，并遵守：

1. 细节只写在对应专题文档；Top-Level 只保留原则、边界和入口。
2. 同一命令的完整参数说明只应出现在 System Manual、README 或对应专题文档，不在多个规划文档重复维护。
3. 同一规则如果同时影响 strict、audit 和 sync，Top-Level 只说明分层边界，具体触发条件写入对应专题文档。
4. Product Roadmap 只维护阶段状态和优先级，不复制专题设计全文。
5. 专题文档改变边界时，必须回查 Top-Level 是否需要更新；只改实现细节时，不必同步 Top-Level。
6. 公开用户行为改变时，必须评估 README、System Manual、Automation、template、upgrade matrix 和版本号是否需要同步。

---

## 12. 分阶段路线图

本文件只记录路线框架；具体阶段状态和任务列表见 [reference/Product_Roadmap.md](Product_Roadmap.md)。

### Phase A：顶层设计收敛

目标：把 Product Roadmap、Workstream Design、Audit Design、Upgrade Plan、System Manual 对齐。

产物：

1. 顶层设计蓝图。
2. 明确 strict/audit/sync/draft/upgrade 职责。
3. 明确所有新增规则的准入门槛。

### Phase B：Workstream Task Flow 收口

目标：Workstream 内部阶段可注册、聚焦、完成、验证。

产物：

1. `acf workstream stage add/list/done`
2. `acf workstream focus`
3. 对应 unit tests、context matrix、minimal smoke。

### Phase C：对象模型补齐

目标：统一 Task、Task Stage、Workstream、Workstream Stage、ADR、Knowledge、Archive item 的字段口径。

产物：

1. metadata schema 文档。
2. 表格 schema 文档。
3. check rules。

不急于全文件对象化。

### Phase D：Audit 稳定化

目标：让 audit candidates 低噪声、可行动。

先做阈值调优、message 调优、candidate 输出稳定。再评估 duplicate、evidence、volatile。

### Phase E：Upgrade / Sync 扩展

目标：旧项目可以安全进入新结构，索引可以由详情派生。

产物：

1. 更多 upgrade fixture。
2. sync generated block design。
3. archive/workstream lifecycle design。

### Phase F：多项目 dogfooding

目标：ACF 不过拟合某个项目。

样本：

1. ACF。
2. FCC。
3. EcSOS。
4. minimal。
5. legacy。
6. fixtures。
7. 再选一个非 PetroSim 项目。

---

## 13. 决策准则

任何新增能力前，先回答：

1. 这是通用上下文治理问题，还是某个项目的业务事实？
2. 它属于 `check`、`audit`、`sync`、`draft`、`upgrade` 还是普通维护命令？
3. 这是确定性错误，还是候选信号？
4. 最小 fixture 怎么构造？
5. minimal 和 legacy 项目会不会被迫承担新负担？
6. JSON 输出能否让 AI 稳定决定下一步？
7. 是否需要版本号变化？
8. 是否需要同步 README、System Manual、Automation、template、upgrade 测试？
9. 是否有至少一个非 FCC 场景也能解释这条规则？

只有这些问题有清晰答案，才进入实现。

---

## 14. 当前结论

ACF 应成为一个 Markdown-first 的 AI 上下文治理框架。它通过轻量对象模型、确定性 strict check、只读 audit candidates、索引 sync、非破坏式 upgrade 和多项目验证矩阵，降低 AI 长期维护上下文时的漂移、重复、污染和人工复核成本。

实施上必须坚持：先顶层设计，再薄切片实现；每个规则都要 fixture；每个真实项目反馈都要通用化；每个启发式先 audit；每个确定性问题才 strict；每次新增 CLI 都要 JSON、dry-run、check-after、tests、docs 和 upgrade 评估。
