# Front Matter Metadata Plan

本文件记录轻量 YAML front matter 在 ACF 中的采用计划。它是后续设计和实现依据，不表示现有文档已经完成迁移。

---

## 定位

Front matter 是机器可读元数据层，只承载稳定、短小、适合 CLI 解析的字段。正文仍使用 Markdown 保存人类可审阅的事实、说明、判断和证据。

它的目标不是把 ACF 改成 YAML 系统，而是减少状态型文档中的重复 section、降低索引与详情文件不同步风险，并让 `acf check` 和后续结构化命令有更稳定的解析入口。

---

## 设计原则

1. 局部采用，不全量迁移。
2. 新增状态型单文件优先采用；现有叙述型文档保持 Markdown。
3. Front matter 只放元数据，不放长正文、不放复杂嵌套、不放需要人工判断的结论。
4. 不新增第三方运行依赖，例如 PyYAML。
5. 第一版只支持极小 YAML 子集：字符串、空列表、字符串列表。
6. 如果 front matter 与正文或索引冲突，应由 `acf check` 报告，并以明确规定的事实源为准。
7. 任何迁移必须 optional、dry-run first，不应让旧项目因为没有 front matter 而检查失败。

---

## 如何提高简洁性

Front matter 的简洁性来自把固定元数据从正文 section 和索引表格中抽离。

例如 Workstream 详情不再需要为状态、owner、标题、依赖、写入范围分别维护多个 section：

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

正文可以专注于目标、非目标、当前发现、合并请求、风险和证据。CLI 也可以直接读取 `status`、`owner`、`write_scope`，不必从自然语言 heading 中推断。

---

## 适用清单

| 文档类型 | 当前或未来位置 | 适用度 | 计划 |
|---|---|---|---|
| Workstream 详情 | 未来 active/workstreams/WS001 | 高 | 第一批采用，作为试点。 |
| ADR 详情 | decisions/ADR-000* | 高 | 新 ADR 采用；旧 ADR 暂不批量迁移。 |
| Knowledge 草案/条目 | worklog/knowledge-drafts/*、未来 reference/knowledge/* | 高 | 新文件采用，利于状态、标签、来源追踪。 |
| Daily worklog | worklog/daily/YYYY-MM-DD | 中 | 新 worklog 可采用，但不作为第一优先级。 |
| Archive 条目 | archive/plans/*、未来 archived task/current-task | 中 | 新归档文件可采用，便于索引和追踪归档原因。 |
| Current_Task | active/Current_Task | 中 | 仅在 CLI 解析和状态维护收益明确时采用少量字段。 |
| Task_Plan | active/Task_Plan | 中低 | 暂不迁移；任务表继续使用 Markdown table。 |
| Source 条目 | 当前 reference/Sources_Index | 低到中 | 仅当 source 从表格拆成单文件时采用。 |
| Feedback_Inbox | active/Feedback_Inbox | 低 | 继续使用表格。 |
| Context | active/Context | 低 | 不建议采用，当前事实正文比元数据更重要。 |
| AGENTS / rules / System Manual | AGENTS、rules/*、reference/System_Manual | 不建议 | 保持纯 Markdown。 |
| Architecture / Tech Context / Project Brief | reference/* | 不建议 | 主要给人和 AI 阅读，不做 metadata 迁移。 |
| 各类 Index | *_Index | 通常不建议 | index 本身是摘要表，front matter 收益小。 |

---

## 建议字段

### Workstream

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

### ADR

```yaml
---
id: ADR-0005
status: Proposed
title: 使用可选 Workstream 层管理并行目标线
date: 2026-04-30
supersedes: []
related:
  - reference/Workstream_Design
---
```

### Knowledge

```yaml
---
id: K001
status: Draft
title: Workstream 适合表达目标线而非 agent
source: worklog/daily/2026-04-30
tags:
  - collaboration
  - context-governance
---
```

### Worklog

```yaml
---
date: 2026-04-30
type: daily
status: Recorded
related:
  - reference/Workstream_Design
---
```

### Current Task

```yaml
---
status: Active
title: 设计可选模板与读取规则
plan: 并行 Workstream 任务与信息管理方案
subtask: T002
updated: 2026-04-30
---
```

---

## 实施阶段

### 阶段 1：格式规范和解析器

目标：

1. 在 System Manual 或相关参考文档中定义 front matter 极小子集。
2. 在 `acf.py` 中实现无依赖解析器。
3. 只支持字符串、空列表和字符串列表。
4. 对复杂 YAML 明确拒绝或忽略，并输出可理解错误。

验收：

1. 单元测试覆盖合法字段、空列表、字符串列表、缺失结束 marker、复杂嵌套拒绝。
2. 没有第三方运行依赖。

### 解析器实施细节

Front matter 只在文件开头识别。第一行必须是 `---`，结束 marker 必须也是单独一行 `---`。结束 marker 之后保留原 Markdown 正文。

第一版支持的语法：

```text
key: value
key: []
key:
  - value
  - value
```

约束：

1. key 只允许 ASCII 字母、数字、下划线和短横线。
2. value 按原始字符串保存，去掉首尾空白。
3. 不支持对象、嵌套列表、数字类型、布尔类型、引号转义或多行字符串。
4. 空行允许出现在字段之间。
5. 重复 key 报错。
6. 列表项必须属于最近的空值 key。
7. 非法缩进报错。

建议内部接口：

```text
parse_front_matter(text) -> (metadata, body, diagnostics)
format_front_matter(metadata, body) -> text
validate_front_matter(metadata, schema) -> diagnostics
```

建议错误码：

```text
front_matter_unclosed
front_matter_duplicate_key
front_matter_invalid_key
front_matter_invalid_list_item
front_matter_unsupported_syntax
front_matter_schema_failed
```

字段 schema 不应写死在解析器中。Workstream、ADR、Knowledge、Worklog 各自定义允许字段、必填字段和枚举值。

### 阶段 2：Workstream 试点

目标：

1. 新增 Workstream 详情模板时使用 front matter。
2. `acf workstream` 命令优先读取详情文件 front matter。
3. 计划中的 Workstreams 索引作为索引摘要，可由详情文件校验或派生。

验收：

1. 没有计划中的 Workstreams 索引的旧项目不受影响。
2. Workstream 详情 metadata 与索引不一致时，`acf check` 给出 warning 或 error。

Workstream metadata 最小字段：

```yaml
---
id: WS001
status: Open
owner: 主 agent
title: 并行任务治理模型
depends_on: []
read_scope:
  - docs/ai/AGENTS
write_scope:
  - owned: active/workstreams/WS001 dot md
  - draft: worklog/writeback-drafts/WS001-*
---
```

其中 `status` 必须属于 Workstream 状态机；`write_scope` 建议使用 `type: path` 字符串，避免第一版解析复杂对象。

路径字段必须使用规范化路径。实现生成的真实文件名必须带 `.md` 后缀；计划文档中尚未创建的未来路径可用 `dot md` 写法避免当前断链检查误报。

### 阶段 3：新生成记录采用

目标：

1. 新 ADR、新 Knowledge 草案、新 worklog、新 archive 条目可以带 front matter。
2. 旧文件不自动迁移。
3. 相关索引仍保持 Markdown table，但 check 可以比对 metadata 与索引状态。

验收：

1. `acf new adr`、`acf knowledge draft`、`acf new worklog`、`acf archive ...` 的输出格式和测试同步。
2. 旧文件仍能通过 check。

### 阶段 4：评估 Current_Task 和 Task_Plan

目标：

1. 只有当 heading/table 解析成为实际维护风险时，才为 Current_Task 增加少量 front matter。
2. Task_Plan 暂时保持表格模型，不做默认迁移。

验收：

1. 不因统一格式而增加维护负担。
2. CLI 解析收益明确大于格式成本。

### 阶段 5：可选迁移工具

目标：

1. 提供 dry-run first 的迁移预览。
2. 只对单文件或明确范围执行。
3. 不默认批量改写用户项目。

候选命令：

```bash
uv run acf metadata preview <file>
uv run acf metadata apply <file>
uv run acf metadata check
```

迁移工具第一版只做预览，不默认写入。`preview` 输出可提取字段、无法确定字段和建议 front matter；`apply` 必须要求目标文件没有现有 front matter，或显式 `--force`。

---

## Check 规则计划

1. 没有 front matter 的旧文件默认不报错。
2. 对声明需要 front matter 的新模板文件，缺失 metadata 才报错。
3. `acf check --strict` 可检查字段类型、允许状态值、索引一致性和断链。
4. ADR/Knowledge/Workstream 等详情文件如果有 metadata，应与对应 index 中的 ID、状态、标题保持一致。
5. 如果 metadata 中引用路径，应继续参与现有 Markdown 断链检查或增加专门的路径校验。

---

## 版本与兼容性

若 front matter 只用于新增可选文件和新命令输出，旧项目无新增检查错误，则可按 patch 版本处理。

若 `acf init` 默认生成结构明显变化，或 `check --strict` 对旧项目产生新错误，则应考虑 minor 版本，至少在 README、System Manual 和 worklog 中记录 migration note。

---

## 当前结论

Front matter 可以提高状态型文档的简洁性和 CLI 解析效率，但不应成为全仓库统一格式。最佳路径是：新增 Workstream 详情先试点；新 ADR、Knowledge、worklog 和 archive 条目按需采用；现有叙述型文档保持纯 Markdown。
