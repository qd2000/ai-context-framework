# ACF Top-Level Design

本文记录 ACF 的顶层产品设计。它是后续新增对象、规则、CLI 命令、模板结构、upgrade 行为和 dogfooding 评测的上位约束。

`reference/Product_Roadmap.md` 负责阶段路线和准入节奏；本文件负责回答 ACF 是什么、边界在哪里、内容如何分层、对象如何建模、CLI 各层如何分工。

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

worklog 不是当前事实源。它可以作为证据位置，但不能替代 `active/Context.md`、任务板、ADR 或 Knowledge。

### 2.5 archive/

`archive/` 放旧任务、旧计划、旧 Workstream 和已处理 feedback。archive 默认不进入读取路径。

归档原则：

1. 保留可追溯摘要，不复制冗长过程。
2. 保留 ID、最终状态、证据和原始位置。
3. 当前计划不再需要解释的 Done / Cancelled Workstream 应迁出 active。
4. archive 不是事实裁决层；它只降低默认上下文噪声。

### 2.6 rules/

`rules/` 放当前项目约束。`rules/Always_Active.md` 是默认生效规则；其他规则按场景读取。

规则文档不应夹带一次性任务计划或项目运行日志。新增规则必须能说明适用范围和触发条件。

---

## 3. 权威事实模型

### 3.1 事实源优先级

默认事实源优先级：

1. 用户当前消息。
2. `active/Current_Task.md`。
3. `active/Task_Plan.md`。
4. `active/Context.md`。
5. `active/Feedback_Inbox.md`，仅作为待处理信号。
6. `reference/Decisions_Index.md`。
7. ADR 文件。
8. `reference/Knowledge_Index.md`。
9. `worklog/`。
10. `archive/`。

如果用户当前消息与项目文件冲突，以用户当前消息为当前任务事实，并在写入时显式处理冲突。

### 3.2 唯一权威位置

写入前必须先判断唯一权威位置：

| 信息类型 | 权威位置 | 非权威位置 |
|---|---|---|
| 当前阶段目标和当前有效事实 | `active/Context.md` | worklog、archive、草案 |
| 当前具体任务 | `active/Current_Task.md` | worklog、旧计划 |
| 当前任务板和 Task Stage | `active/Task_Plan.md` | worklog、archive |
| Workstream metadata 和 stage | `active/workstreams/WS*.md` | `active/Workstreams.md` |
| Workstream 低噪音摘要 | `active/Workstreams.md` | 详情正文 |
| 待处理反馈 | `active/Feedback_Inbox.md` | worklog、最终回复 |
| 稳定决策 | ADR 文件 + `reference/Decisions_Index.md` | worklog、Task_Plan |
| 可复用经验 | `reference/Knowledge_Index.md` + knowledge 条目 | active、daily worklog |
| 历史过程 | `worklog/daily/` | active |
| 旧任务和旧计划 | `archive/` | active |

能更新旧表述时，不追加重复事实。能引用权威位置时，不复制完整内容。

### 3.3 索引与详情

索引文件是低噪音导航，不是详情事实源。当前已稳定的规则：

1. Workstream 详情 front matter 是 Workstream metadata 事实源。
2. `active/Workstreams.md` 是由详情派生或同步的索引视图。
3. `sync` 可以更新索引，但不能改详情事实。
4. 索引和详情不一致时，`check` 报告问题，并以详情为准。

未来 Knowledge、ADR、Archive 如扩展 sync，必须先定义 generated block marker、删除策略和兼容规则，不能直接套用 Workstream sync。

---

## 4. 对象模型

ACF 不把所有 Markdown 文件变成强 schema。只有状态型对象需要轻量机器字段或稳定表格字段。

### 4.1 Task

用途：项目主线任务。

位置：

1. `active/Task_Plan.md`
2. `active/Current_Task.md`

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

位置：`active/Task_Plan.md` 的 `## 任务阶段` 表。

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

未来命令可以是：

```bash
acf plan stage add ...
acf plan stage set ...
```

该命令族后置；当前优先依赖 table + check。

### 4.3 Workstream

用途：并行目标线，不是 runtime，不是调度器，不是权限系统。

位置：`active/workstreams/WS001.md`。

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
2. 不默认改 `active/Current_Task.md`。
3. 不自动合并 Context。
4. 不变成任务调度器。

### 4.5 ADR

用途：记录稳定重要决策。

位置：

1. `decisions/ADR-0001.md`
2. `reference/Decisions_Index.md`

规则：

1. ADR ID 不复用。
2. ADR 状态应与索引一致。
3. Proposed 与 Active 的语义要清楚。
4. ADR 记录决策与取舍，不记录冗长实现过程。
5. 重要路线改变优先用 ADR 固化，普通计划留在 Product Roadmap 或 Task_Plan。

### 4.6 Knowledge

用途：保存可迁移经验，不保存当前事实或一次性过程。

位置：

1. `reference/Knowledge_Index.md`
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
5. `archive/Archive_Index.md`

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

1. 只更新 `active/Workstreams.md`。
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

### 6.3 stage add

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
6. 不修改 `active/Current_Task.md` 或 `active/Context.md`。

### 6.4 focus

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
7. 不修改 `active/Current_Task.md`，除非未来明确增加 `--update-current-task`。

### 6.5 stage done

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

### 6.6 stage list

输出：

1. WS metadata。
2. `current_stage`。
3. `stages[]`。
4. `next_actions`。

### 6.7 后置能力

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

`scripts/minimal_smoke.py` 应覆盖：

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
| `Context_Audit_Design.md` | audit candidates、JSON 输出、暂缓规则和调优原则 |
| `Upgrade_Migration_Plan.md` | 旧上下文升级策略、兼容矩阵和 migration 行为 |
| `Front_Matter_Metadata_Plan.md` | 轻量 metadata 字段、适用对象和 parser 约束 |
| `../Automation.md` | 已自动化能力、后续自动化边界、验证命令 |
| `../../README.md` | 面向使用者的安装、初始化和核心使用说明 |

新增或修改这些文档时，应检查是否改变了事实源职责。如果同一规则已经在专门设计文档中详细说明，顶层设计只保留边界和引用，不复制过多实现细节。

---

## 12. 分阶段路线图

本文件只记录路线框架；具体阶段状态和任务列表见 `reference/Product_Roadmap.md`。

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
