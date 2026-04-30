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

## 命名与 Metadata Schema 决议

实现和生成文件时必须统一使用 `.md` 后缀：

1. Workstreams 索引：active/Workstreams dot md。
2. Workstream 详情：active/workstreams/WS001 dot md。
3. 所有索引、metadata、JSON 输出和 check 规则都应使用同一套规范化路径。

Workstream 详情 front matter 第一版统一使用以下字段：

```yaml
---
id: WS001
status: Open
owner: 主 agent
title: 并行任务治理模型
depends_on: []
read_scope:
  - active/Context dot md
  - active/Task_Plan dot md
write_scope:
  - owned: active/workstreams/WS001 dot md
  - draft: worklog/writeback-drafts/WS001-*
---
```

字段要求：

1. `id` 必须匹配 `WS` 加三位数字。
2. `status` 必须属于 Workstream 状态机。
3. `depends_on`、`read_scope`、`write_scope` 使用字符串列表。
4. `write_scope` 使用 typed string，格式为 `type: path`。
5. 第一版不支持复杂对象、嵌套 YAML 或未带类型的写入范围。

---

## Workstreams 索引

计划中的 Workstreams 索引文件只保留低噪音字段：

```markdown
| ID | 状态 | 标题 | Owner | 写入范围 | 依赖 | 输出物 | 详情 |
|---|---|---|---|---|---|---|---|
| WS001 | Active | 并行任务治理模型 | 主 agent | owned: active/workstreams/WS001 dot md; draft: writeback-drafts/WS001-* | 无 | Workstream_Design | active/workstreams/WS001 dot md |
```

不建议在总表维护“下一步”“当前发现”“证据”等易过期字段；这些内容应进入详情文件。

---

## Workstream 详情文件

详情文件建议包含轻量 front matter 和 Markdown 正文。front matter 用于稳定机器解析，正文用于人工审阅。

```markdown
---
id: WS001
status: Open
owner: 主 agent
title: 并行任务治理模型
depends_on: []
read_scope:
  - active/Context dot md
  - active/Task_Plan dot md
write_scope:
  - owned: active/workstreams/WS001 dot md
  - draft: worklog/writeback-drafts/WS001-*
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

## ID 规则

1. Workstream ID 格式为 `WS001`、`WS002`，即 `WS` 加三位数字。
2. ID 一旦创建不应复用，即使原 Workstream 已 Done、Cancelled 或归档。
3. 自动分配 ID 时，应同时扫描 active/workstreams 和 archive/workstreams。
4. 重命名 Workstream 只能修改 title，不能修改 ID。
5. 删除 Workstream 详情文件应视为高风险操作；优先使用 Cancelled 或归档。
6. 索引、详情 metadata、JSON 输出和 evidence 引用必须保持同一 ID。

---

## 归档与清理

Done / Cancelled workstream 不应长期堆积在 active 区域。

1. 当前计划仍需要解释的 Done / Cancelled 可以暂留在 active 索引和详情目录。
2. 当前计划结束后，Done / Cancelled workstream 应归档到 archive/workstreams。
3. active/Workstreams dot md 只长期保留 Open、Active、Blocked、ReadyToMerge，以及当前计划仍需解释的 Done / Cancelled。
4. 归档摘要应保留 ID、最终状态、标题、owner、处理结果、证据位置和原详情文件位置。
5. 归档不应复制冗长过程；过程发现应已进入 worklog、ADR、Context 或 Knowledge 草案。

archive/workstreams 应由 `acf workstream init` 创建空目录；如果旧上下文缺少该目录，也可以由首次 workstream archive/done 归档时惰性创建。

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
| owned | active/workstreams/WS001 dot md | 仅对应 Workstream 写 |
| assigned | src/foo、docs/Feature | 同一时间只分配给一个 Active Workstream |
| evidence | 测试结果、日志、worklog、产物引用 | 可引用，不代表拥有 |

第一版检查应先覆盖 authority、owned、assigned 的明显冲突。draft 和 evidence 允许并行，但 draft 文件名应可追溯到 Workstream ID。

---

## Scope Path 规范

Scope path 是协作契约，不是权限沙箱。为了让冲突检查稳定，第一版采用以下规则：

1. `authority`、`owned` 和 `draft` 默认相对 context root。
2. `assigned` 和 `evidence` 默认相对 project root，除非路径明确以 context 内目录开头。
3. 比较前统一将分隔符 normalize 为 `/`。
4. Windows 下路径冲突判断默认大小写不敏感。
5. 目录 claim 覆盖其所有子路径。
6. glob 第一版只允许用于 `draft` 和 `evidence`。
7. `authority` 和 `assigned` 第一版不支持复杂 glob。
8. 实际生成文件必须带 `.md` 后缀；如果输入缺少后缀，parser 应规范化或报错，不能静默产生两个不同目标。
9. 规范化后的路径用于 metadata、索引、JSON 输出和 check 规则。

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

## 接口细节

### 命令分层

第一版命令分为四类：

1. 初始化：`init`
2. 查询：`list`、`show`、`status`
3. 状态维护：`add`、`set`、`claim`、`block`、`ready`、`done`、`cancel`
4. 内容追加：`note`、`merge-request`

命令必须继承现有写命令契约：`--json`、`--dry-run`、`--check-after`、`--strict`、changed files 和统一 error code。

### init

```bash
uv run acf workstream init --json --check-after
```

行为：

1. 创建计划中的 Workstreams 索引和详情目录。
2. 创建 archive/workstreams 空目录。
3. 如果索引已存在，保持幂等。
4. 不创建任何 Active workstream。
5. 不修改 `Task_Plan` 或 `Current_Task`。

### add

```bash
uv run acf workstream add --id WS001 --title "并行任务治理模型" --owner "主 agent" --json
```

行为：

1. 创建详情文件。
2. 写入 front matter。
3. 在索引中追加摘要行。
4. 默认状态为 `Open`，除非显式传入 `--status Active`。

### set / 状态命令

```bash
uv run acf workstream set WS001 --status Active --json
uv run acf workstream block WS001 --reason "等待人工判断" --json
uv run acf workstream cancel WS001 --reason "不再适用" --json
uv run acf workstream ready WS001 --summary "候选变更已整理" --json
uv run acf workstream done WS001 --evidence "worklog/daily/2026-04-30" --json
```

行为：

1. 校验状态转换是否合法。
2. 更新详情 front matter。
3. 同步索引摘要。
4. `ready` 必须校验合并请求 section 存在。
5. `done` 必须要求 evidence。
6. `block` 和 `cancel` 必须要求 reason。

第一版提供 `block` 和 `cancel` 语义命令，不只依赖通用 `set`，避免漏填 blocker 或取消原因。`status` 作为查询命令返回索引摘要和当前 Active/Blocked/ReadyToMerge 数量。

### claim

```bash
uv run acf workstream claim WS001 --read "docs/ai/AGENTS" --write "assigned: src/foo" --json
```

行为：

1. 追加读取范围或写入范围。
2. 写入范围必须带类型前缀：`authority:`、`draft:`、`owned:`、`assigned:`、`evidence:`。
3. 对 `authority` 和 `assigned` 检查 Active workstream 冲突。
4. 冲突时默认拒绝，未来可考虑显式 override 并记录原因。

### note

```bash
uv run acf workstream note WS001 --section "当前发现" --text "..." --json
```

行为：

1. 只允许追加到详情文件的白名单 section。
2. 不写入权威上下文。
3. 支持 `--input`，避免 PowerShell 多行文本问题。

### merge-request

```bash
uv run acf workstream merge-request WS001 --target Context --summary "..." --json
```

行为：

1. 更新详情文件的合并请求 section。
2. 可重复追加 target。
3. 不直接修改目标权威文件。

### JSON 输出

查询命令输出：

```json
{
  "schema_version": 1,
  "ok": true,
  "command": "workstream show",
  "id": "WS001",
  "status": "Active",
  "owner": "主 agent",
  "title": "并行任务治理模型",
  "read_scope": [],
  "write_scope": [],
  "merge_request": {
    "targets": [],
    "summary": "",
    "open_questions": [],
    "conflicts": [],
    "verification": ""
  },
  "next_actions": []
}
```

写命令输出应包含 `changed_files`，失败时包含 `error_code`、`message` 和 `next_actions`。

建议 error code：

```text
workstream_not_initialized
workstream_not_found
workstream_duplicate_id
workstream_invalid_transition
workstream_missing_merge_request
workstream_missing_evidence
workstream_scope_conflict
workstream_schema_failed
```

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

### Check Severity 矩阵

| 规则 | 普通 check | strict |
|---|---|---|
| Workstreams 索引存在但详情目录缺失 | error | error |
| 总表详情链接不存在 | error | error |
| 详情存在但总表缺行 | warning | error |
| 总表状态与详情 metadata 不一致 | warning | error |
| Active 缺 owner / 目标 / 输出物 | error | error |
| Active 缺读取范围 / 写入范围 | error | error |
| Blocked 缺 blocker | error | error |
| ReadyToMerge 缺合并请求 | error | error |
| ReadyToMerge 缺候选变更摘要 | error | error |
| Done 缺 evidence | error | error |
| Cancelled 缺取消原因 | error | error |
| 多个 Active claim 同一 authority / assigned | error | error |
| draft 文件名不含 Workstream ID | warning | error |
| scope path 无法规范化 | error | error |

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

## Dogfooding Gate

在 T002 和 T004 之间，应先做一次手工 dogfooding gate，不依赖完整 CLI：

1. 在 `docs/ai` 显式启用一个最小 Workstream。
2. 确认 `AGENTS` 默认读取不明显变重。
3. 确认 `ReadyToMerge` 合并请求足够指导主 agent 合并。
4. 确认 `Done` 后 evidence 可追溯。
5. 确认无 Workstream 的旧上下文 check 不报错。
6. 确认 Done / Cancelled 的归档规则不会让 active 长期膨胀。

---

## ADR 候选

后续应生成 ADR 候选：ADR-0005，主题为“使用可选 Workstream 层管理并行目标线”。

ADR 应只记录稳定取舍：

1. 为什么需要 Workstream。
2. 为什么不做 agent runtime。
3. 为什么默认不启用。
4. 为什么 `ReadyToMerge` 和 `Done` 分开。
5. 为什么写入范围是协作契约，不是安全沙箱。

---

## 当前结论

Workstream 方案可行，且符合 ACF 的核心边界：纯 Markdown、模型无关、人工可审阅、无常驻 runtime。关键不是增加更多 CLI 命令，而是先稳定协议：协作契约、结构化合并请求、详情文件事实源和 optional 兼容性。
