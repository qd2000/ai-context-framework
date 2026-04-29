# Workstream Design

本文件记录 ACF 对多 agent 并行协作场景的设计计划。它是当前设计依据，不代表功能已经全部实现。

---

## 背景

当前 ACF 已有 `../active/Task_Plan.md` 和 `../active/Current_Task.md`，适合单主线任务和轻量任务板。但当多个 agents 在同一个项目中并行处理不同目标时，仅靠单个当前任务容易出现以下问题：

1. 不同目标线的 owner、边界和输出物不清晰。
2. 多个 agents 可能同时修改同一权威上下文文件。
3. 子 agent 的过程发现、待合并结论和证据缺少稳定落点。
4. 完成一条并行目标线不等于已经合并到权威上下文。

因此需要引入可选的 Workstream 层。

---

## 设计原则

1. Workstream 是可选的并行目标线协议，不是 agent runtime、调度器、线程模型或权限系统。
2. 默认单线项目仍使用 `../active/Task_Plan.md` 和 `../active/Current_Task.md`。
3. 只有当目标线需要独立 owner、独立上下文、独立写入边界或独立合并审查时，才创建 Workstream。
4. Workstream 的读取范围是推荐最小上下文，不覆盖项目级 `AGENTS.md`、rules 和人工指令。
5. Workstream 的写入范围是协作契约，用于避免并行冲突和辅助 `acf check`，不是安全沙箱。
6. 子 agent 默认不直接写入权威上下文；应写入自己的 workstream 文件、草案文件或明确分配的代码/文档文件。
7. `ReadyToMerge` 表示 workstream 已产出可审查、可落盘、可验证的合并输入；不表示权威上下文已经更新。
8. `Done` 只能在结论已合并、归档或明确不需要合并，并有证据位置后设置。

---

## Workstream 与 Task 的关系

1. Task 是项目主线执行单元；Workstream 是并行目标线。
2. 单线任务仍进入 `../active/Task_Plan.md` / `../active/Current_Task.md`。
3. Workstream 不替代 `../active/Task_Plan.md`。
4. 一个 Task 可以拆出多个 Workstream。
5. 一个 Workstream 在 `ReadyToMerge` 后，可以回填为一个或多个 Task、Context 事实、ADR、rules、worklog 或 Knowledge 草案。
6. `../active/Feedback_Inbox.md` 中 Planned 状态的反馈必须引用 Task ID、Workstream ID 或明确的草案位置。

---

## 不应创建 Workstream 的情况

以下情况仍使用 `../active/Task_Plan.md` / `../active/Current_Task.md`：

1. 只有一个 agent 或一个目标线。
2. 只是短小修复、文档补充或单文件改动。
3. 没有独立 owner。
4. 不需要单独合并审查。
5. 不涉及并行写入冲突。

---

## 建议文件结构

Workstream 层必须保持 optional。没有计划中的 Workstreams 索引文件的项目，`acf check` 不应报错或 warning。

```text
active/Workstreams.md
active/workstreams/WS001.md
active/workstreams/WS002.md
```

计划中的单个 Workstream 详情文件是该 Workstream 的事实源；计划中的 Workstreams 索引文件是索引和摘要。若二者冲突，应以详情文件为准，并由 `acf check` 报 warning。

---

## Workstreams 索引

计划中的 Workstreams 索引文件只保留低噪音字段：

```markdown
| ID | 状态 | 标题 | Owner | 写入范围 | 依赖 | 输出物 | 详情 |
|---|---|---|---|---|---|---|---|
| WS001 | Active | 并行任务治理模型 | 主 agent | owned: active/workstreams/WS001; draft: writeback-drafts/WS001-* | 无 | Workstream_Design | active/workstreams/WS001 |
```

不建议在总表维护“下一步”“当前发现”“证据”等易过期字段；这些内容应进入详情文件。

---

## Workstream 详情文件

详情文件建议包含轻量 front matter 和 Markdown 正文。front matter 用于稳定机器解析，正文用于人工审阅。

```markdown
---
id: WS001
status: Active
owner: 主 agent
title: 并行任务治理模型
depends_on: []
write_scope:
  - active/workstreams/WS001
  - worklog/writeback-drafts/WS001-*
---

# WS001 - 并行任务治理模型

## 边界说明

本 Workstream 的读取范围是推荐上下文，不是权限隔离。
所有 agent 仍必须遵守项目级 AGENTS、rules 和人工指令。
允许修改范围是协作契约，用于避免并行写入冲突。

## 目标

## 非目标

## Owner

## 读取范围

## 允许修改范围

## 冲突风险

## 当前发现

## 待合并结论

## 合并请求

### 需要合并到哪里

- Context:
- Task_Plan:
- ADR:
- rules:
- README / docs:

### 候选变更摘要

### 需要人工判断的问题

### 已知冲突

### 验证结果

### 建议合并方式

## 完成标准

## 证据
```

---

## 状态机

允许状态：

```text
Open
Active
Blocked
ReadyToMerge
Done
Cancelled
```

允许转换：

```text
Open -> Active
Active -> Blocked
Blocked -> Active
Active -> ReadyToMerge
ReadyToMerge -> Active
ReadyToMerge -> Done
Open/Active/Blocked/ReadyToMerge -> Cancelled
```

`Done` 和 `Cancelled` 是终态。若终态后需要继续推进，应新建 Workstream，而不是随意改回 Active。

---

## ReadyToMerge 合并契约

`ReadyToMerge` 不是“我做完了”，而是“我给出了可审查、可落盘、可验证的合并输入”。

处于 `ReadyToMerge` 的 workstream 必须提供：

1. 合并请求 section。
2. 候选变更摘要。
3. 需要合并到哪些目标文件或上下文层。
4. 需要人工判断的问题。
5. 已知冲突。
6. 验证结果或未验证说明。
7. 建议合并方式。

若合并审查发现还需返工，应从 `ReadyToMerge` 回到 `Active`。

---

## 写入类型

Workstream 的写入范围按类型声明：

| 类型 | 示例 | 并行规则 |
|---|---|---|
| authority | `../active/Context.md`、`../active/Task_Plan.md`、ADR、rules | 默认只能主 agent 写；多个 Active workstream 不应同时声明同一 authority 文件为可写 |
| draft | worklog/writeback-drafts/WS001-context | 可并行；文件名应包含 Workstream ID |
| owned | active/workstreams/WS001 | 仅对应 Workstream 写 |
| assigned | src/foo、docs/Feature | 同一时间只分配给一个 Active Workstream |
| evidence | 测试结果、日志、worklog、产物引用 | 可引用，不代表拥有 |

第一版检查应先覆盖 authority、owned、assigned 的明显冲突。draft 和 evidence 允许并行，但 draft 文件名应可追溯到 Workstream ID。

---

## CLI 计划

第一版 `acf workstream` 只做结构维护和一致性检查，不做语义判断或 agent 调度。

建议命令：

```bash
uv run acf workstream init
uv run acf workstream add --id WS001 --title "并行任务治理模型"
uv run acf workstream list --json
uv run acf workstream show WS001 --json
uv run acf workstream set WS001 --status Active
uv run acf workstream claim WS001 --owner "agent-a" --write "assigned: src/foo.py"
uv run acf workstream note WS001 --section "当前发现" --text "..."
uv run acf workstream ready WS001
uv run acf workstream done WS001 --evidence "docs/ai/reference/Workstream_Design"
```

可延后命令：

```bash
uv run acf workstream validate WS001
uv run acf workstream changed WS001
```

`changed` 涉及 git diff，容易受用户未提交改动影响；应作为 opt-in 命令，不应第一版塞进默认 `check --strict`。

---

## Check 规则计划

Workstream 层是 optional：

1. 如果计划中的 Workstreams 索引文件不存在，`acf check` 不因 Workstream 缺失报错或 warning。
2. 如果计划中的 Workstreams 索引文件存在，`acf check` 校验 Workstream 一致性。
3. 如果用户运行 `acf workstream init`，则创建 Workstream 结构并启用相关检查。

建议检查：

1. 计划中的 Workstreams 索引文件存在时，Workstream 详情目录也应存在。
2. 总表中的详情文件链接必须存在。
3. 详情文件存在但总表无记录时 warning。
4. 总表状态与详情文件状态不一致时 warning，并以详情文件为准。
5. Active workstream 必须有 owner、目标、读取范围、写入范围和输出物。
6. Blocked workstream 必须有 blocker 说明。
7. ReadyToMerge workstream 必须有合并请求和候选变更摘要。
8. Done workstream 必须有证据位置。
9. Cancelled workstream 必须有取消原因。
10. 多个 Active workstream 不得声明同一 authority 或 assigned 文件为可写。
11. Feedback Planned 条目必须引用 Task ID、Workstream ID 或草案位置。

---

## Front Matter 判断

轻量 YAML front matter 可以用于现有文档，但不应全量改造。

适合使用 front matter 的文档：

1. 状态型、记录型、索引型文档，例如 Workstream 详情、ADR、Knowledge 草案、source 条目、task/worklog 元数据。
2. 需要 CLI 稳定解析的文档。
3. 容易出现“总表与详情不同步”的文档。

不适合优先改造的文档：

1. `AGENTS.md`、rules、System Manual、Architecture、Project Brief 等叙述型文档。
2. 已经稳定且主要由人阅读的文档。
3. 只需按 heading 或 table 维护的简单 Markdown。

采用 front matter 的收益：

1. CLI 解析更稳定，少依赖自然语言 heading。
2. 总表可由详情文件派生，降低重复维护。
3. 状态、owner、依赖、写入范围等高频字段更紧凑。
4. 有利于 `acf check` 做一致性检查。

约束：

1. 不新增第三方运行依赖，例如 PyYAML。
2. 只支持极小 YAML 子集：字符串、空列表、字符串列表。
3. front matter 只承载机器字段；正文仍用 Markdown 保存可审阅语义。
4. 不对现有文档做大规模迁移；先在新增 Workstream 详情文件中试用。

结论：front matter 有利于信息简洁化和 CLI 高效解析，但应作为新增结构的局部能力，而不是现有文档的全局迁移策略。

---

## 落地顺序

1. 将 F007 编号并映射到当前计划。
2. 沉淀本设计文档。
3. 设计 optional 模板结构和读取规则。
4. 设计并实现 `acf workstream` 第一版结构维护命令。
5. 增加 optional check 规则。
6. 同步 README、System Manual、Automation、template data-files、init/upgrade/check 测试。
7. 根据对外行为变化判断版本号；若保持完全可选且旧项目无新增错误，bump patch；若默认 init/check 行为影响旧项目，考虑 minor 或 migration note。

---

## 当前结论

Workstream 方案可行，且符合 ACF 的核心边界：纯 Markdown、模型无关、人工可审阅、无常驻 runtime。关键不是增加更多 CLI 命令，而是先稳定协议：协作契约、结构化合并请求、详情文件事实源和 optional 兼容性。
