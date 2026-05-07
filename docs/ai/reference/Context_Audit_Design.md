# Context Audit Design

本文记录 P1 `audit context` 的设计边界。该能力用于发现上下文污染候选，不用于裁决事实真假，也不自动修改任何权威上下文。

---

## 状态

MVP implemented

---

## 设计目标

1. 提供只读的上下文审计入口，帮助发现 active 层中的重复、过期、无证据或合并状态不清的问题。
2. 输出 candidates、summary 和 next_actions，供主代理或人工审阅。
3. 保持 `acf check --strict` 的确定性边界；P1 audit 不进入默认 strict。
4. 保持 Markdown-first、模型无关、人工可审阅，不引入数据库、向量库、agent runtime 或自动事实裁决。

---

## 命令草案

```bash
acf audit context docs/ai --json
```

第一版只读，不生成 patch，不修改文件，不创建 curation draft。

---

## JSON 输出草案

```json
{
  "command": "audit context",
  "context": "docs/ai",
  "ok": true,
  "schema_version": 1,
  "candidates": [],
  "summary": {},
  "next_actions": []
}
```

字段约定：

1. `candidates` 只表示候选问题，不表示事实错误。
2. `summary` 只做机械汇总，例如按 kind、path 或 severity 计数。
3. `next_actions` 给出低风险审阅建议，不给出自动合并或自动删除指令。

---

## MVP Command Contract

第一版 `acf audit context` 是只读候选发现命令，不写文件、不生成 patch、不创建 curation draft、不进入 strict。

### Command

```bash
acf audit context [path] --json
```

参数约定：

1. `[path]` 指向 ACF context root，例如 `docs/ai`。
2. 第一版只要求 `--json` 输出契约稳定；人类可读输出可后置。
3. 不支持 `--fix`、`--write`、`--patch` 或自动 draft 生成参数。

### Top-level JSON fields

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

字段约定：

| 字段 | 含义 |
|---|---|
| `schema_version` | audit JSON 输出 schema 版本，第一版为 `1`。 |
| `ok` | 命令是否成功完成读取和候选生成；存在 candidates 时仍可为 `true`。 |
| `command` | 固定为 `audit context`。 |
| `context` | 输入 context root，输出为调用方传入或规范化后的路径。 |
| `candidates` | 候选问题数组；候选不等于事实错误。 |
| `summary` | 机械汇总，第一版包含 `total`、`by_kind`、`by_path`、`by_severity`。 |
| `next_actions` | 低风险审阅建议，不是自动修复指令。 |

### Candidate fields

```json
{
  "kind": "active_section_too_long",
  "severity": "P1-candidate",
  "path": "active/Context.md",
  "section": "当前有效事实",
  "reason": "section has 90 non-empty lines, above the MVP threshold",
  "suggested_action": "Review whether process detail should move to worklog or reference material."
}
```

字段约定：

| 字段 | 含义 |
|---|---|
| `kind` | 候选类型，使用稳定 snake_case。 |
| `severity` | `P0-candidate`、`P1-candidate` 或 `P2-candidate`。 |
| `path` | context-root 相对路径，使用 POSIX slash。 |
| `section` | 可选，命中的 Markdown section heading；无法定位时可省略或为空。 |
| `reason` | 机械触发原因，说明阈值、状态或结构信号。 |
| `suggested_action` | 审阅建议，不是自动修复指令。 |

### MVP rules

第一版只实现低误报、偏结构化的候选规则：

1. `active_section_too_long`
2. `stale_current_task_or_workstream_stage`
3. `terminal_conclusion_not_merged`

暂缓以下规则，避免 MVP 过早引入高误报语义判断：

1. `duplicate_active_fact_candidate`
2. `strong_claim_without_evidence`
3. `volatile_fact_in_wrong_authority_location`

### MVP acceptance

1. clean context 输出 `ok: true`、空 `candidates` 和稳定 `summary`。
2. 发现候选时仍输出 `ok: true`，除非读取或解析发生命令级错误。
3. 每个候选必须有稳定 `kind`、`severity`、`path`、`reason` 和 `suggested_action`。
4. 第一版不写文件，不改变 `acf check`、`acf review stale` 或 `acf curate draft` 行为。

### MVP implementation status

已实现：

1. `acf audit context [path] --json`。
2. `active_section_too_long`。
3. `stale_current_task_or_workstream_stage`。
4. `terminal_conclusion_not_merged`。
5. clean 状态、summary、next_actions 和 read-only 行为测试。

---

## 默认读取范围

第一版默认只读取当前注意力入口和 Workstream 当前状态：

- `active/Context.md`
- `active/Current_Task.md`
- `active/Task_Plan.md`
- `active/Workstreams.md`
- `active/workstreams/*.md`

如候选规则需要引用索引，只读取与 active 文件直接相关的 reference index。默认不读取 archive、全量 worklog 或历史 curation draft。

---

## Candidate Rules

### duplicate_active_fact_candidate

发现 active 层多个文件中疑似重复承载同一事实的候选。

第一版只做机械信号，例如归一化短段落、表格行或列表项后的 token overlap / 指纹重复。该规则不判断哪一处是真的，也不自动删除重复内容。

### volatile_fact_in_wrong_authority_location

发现易变事实疑似出现在低权威或不适合长期保存的位置。

候选事实包括 runtime 状态、当前任务状态、当前 Workstream 阶段、临时 worker / PID / tmux 信息、短期实验进度等。第一版只报告候选，不移动内容。

### strong_claim_without_evidence

发现 active 层强结论附近缺少证据入口。

强结论可由机械短语触发，例如“已完成”“已修复”“已通过”“当前为”“正式结论”“用户确认”。证据入口可以是 worklog、output、ADR、Decision、测试命令或用户确认日期。

### terminal_conclusion_not_merged

发现 ReadyToMerge 相关结论仍待合并审阅，或 Done Workstream 仍缺少合并状态说明。

该规则与 P0 hardening 区分：P0 strict 只检查确定性 metadata 和 merge request 结构；P1 audit 可提示“结论看起来仍停留在 Workstream 中，可能需要人工决定是否合并”。已明确 `merged`、`rejected`、`no_merge_required` 或 `archived` 的 Done Workstream 不应作为本规则的 MVP 候选。

### active_section_too_long

发现 active 层 section 过长，可能包含过程日志、runbook、历史细节或可归档材料。

第一版只按行数、列表项数量或代码块长度做候选提示，不判断内容价值。

### stale_current_task_or_workstream_stage

发现当前任务、Active Workstream 或 `current_stage` 长时间未更新。

该规则可复用现有 stale review 思路，但应保持为 audit candidate，不自动切换状态、不归档、不写入 Task_Plan。

---

## Severity

第一版 severity 只用于排序，不驱动 strict 失败：

- `P0-candidate`：很可能阻塞当前上下文治理，需要人工优先看。
- `P1-candidate`：可能造成噪声或重复，建议本轮整理。
- `P2-candidate`：低风险清理建议。

---

## 与 P0 的关系

P0 governance hardening 已覆盖确定性门禁：

1. Task Stage registry。
2. Workstream Stage Focus。
3. Authority write gate + `merge_targets`。
4. Merge resolution + active retention gate。
5. Workstream index consistency check + sync。

P1 audit 不替代这些规则，也不把启发式候选升级为默认 strict error。只有长期稳定、低误报、可机械裁决的 audit rule，未来才可单独评估是否进入 `acf check --strict`。

---

## 非目标

本阶段不做：

1. 不做自动事实裁决。
2. 不做自动语义去重。
3. 不默认修改 `active/Context.md`。
4. 不进入 `acf check --strict` 默认路径。
5. 不读取 archive 或全量 worklog。
6. 不生成 patch。
7. 不自动合并 Workstream 结论到权威上下文。

---

## MVP 边界

如果进入实现，第一版只新增只读命令：

```bash
acf audit context docs/ai --json
```

验收重点：

1. clean 项目输出空 `candidates`、稳定 `summary` 和 `next_actions`。
2. 有候选时输出稳定 `kind`、`path`、`reason`、`suggested_action`。
3. 不写文件。
4. 不依赖第三方包。
5. 不改变 `acf check`、`acf review stale` 或 `acf curate draft` 的现有行为。
