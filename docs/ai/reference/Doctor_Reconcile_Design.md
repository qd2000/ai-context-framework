# ACF Doctor / Reconcile Design

本文定义 `acf doctor` 的整体设计：上下文自诊断、自动修复、草案生成和回归验证的一体化维护工具。它补充 [ACF_Top_Level_Design.md](ACF_Top_Level_Design.md)、[Generated_Marker_Sync_Design.md](Generated_Marker_Sync_Design.md) 和 [Workstream_Lifecycle_Archive_Design.md](Workstream_Lifecycle_Archive_Design.md)，不替代既有分层事实源。

---

## 状态

Implemented in `v0.0.3.47`。

---

## 背景

真实 dogfooding 和跨项目审查显示，ACF 当前主要风险不是目录结构错误，而是多层 Markdown 之间的当前事实漂移：

1. `Current_Task.md`、`Task_Plan.md`、`Workstreams.md` 和单个 `WSxxx.md` 可能重复表达任务和 Workstream 状态。
2. `check --strict` 能发现结构、链接、占位符和部分 Workstream scope 错误，但不能发现多数语义一致性问题。
3. 任务或 Workstream 收尾时需要同步多个文件，目前依赖人或 AI 记忆，容易遗漏。
4. 数据事实源、hash、跨项目血缘和同名副本状态缺少统一的本地可验证维护入口。
5. 当前框架要求人工友好、AI 友好、Markdown-first、模型无关，并保持无第三方运行时依赖。

因此需要一个工具把“检查、计划修复、自动修复、生成草案、验证”收成一个闭环。

---

## 外部设计参考

本设计借鉴下列公开工具的模式，但不照搬其私有实现：

1. Cursor Rules 的 scoped rules / always / auto-attached / agent-requested 思路：上下文应按作用域和触发条件暴露，而不是全部默认进入 prompt。
2. Claude Code memory 的层级指令文件、项目级记忆和按需读取思路：入口应该薄，细节应该可追溯。
3. Cline Memory Bank 的结构化项目记忆和 update memory bank 命令：适合作为“维护动作”的参考，但其“每次读取全部 memory bank”不适合 ACF 注意力治理。
4. aider 的 read-only conventions 模式：稳定约定应作为只读规则或索引被引用，不应混入当前任务事实。
5. LangGraph / Zep 类长期记忆系统的 namespace、source、fact invalidation 思路：ACF 用 Markdown、source index、archive marker 和草案流程表达这些概念，不引入数据库或向量库。

---

## 目标

1. 一条命令给出 ACF 上下文健康状态、问题证据、权威位置和建议修复方式。
2. 支持自动修复机械一致性问题，例如 generated index、Workstream 索引和非法 scope。
3. 支持基于本地可验证证据的修复，例如文件存在性、hash 一致性和索引漏项。
4. 对需要事实判断的问题只生成 draft，不直接改写权威事实。
5. 输出稳定 JSON，便于 AI agent 直接消费。
6. 输出人类可读报告，便于审阅和追踪。
7. 修复后可自动运行 `acf check` 或 doctor 自检。
8. 支持单项目和多项目审查，不把跨项目报告塞入默认读取路径。

---

## 非目标

1. 不引入数据库、向量库、后台 daemon 或 agent runtime。
2. 不让工具替代人判断事实真假。
3. 不自动把 worklog、human note 或运行日志提升为当前事实。
4. 不默认读取 archive、完整 worklog 或所有 reference。
5. 不把 doctor report 加入默认读取路径。
6. 不把全部 Markdown 改为强 schema。
7. 不自动删除人工内容；只能替换 generated marker 块或明确可机械更新的 section / table。

---

## 命令形态

首选统一入口：

```bash
uv run acf doctor [path]
uv run acf doctor [path] --json
uv run acf doctor [path] --strict --json
uv run acf doctor [path] --fix safe --check-after --json
uv run acf doctor --projects <path> <path> ... --json
```

### 参数

| 参数 | 含义 |
|---|---|
| `path` | 单个上下文路径或项目内任意路径，沿用现有 context discovery。 |
| `--projects` | 多项目只读模式；每个路径独立发现 context root，单项目失败不吞掉其他项目。 |
| `--json` | 输出稳定机器可读 JSON。 |
| `--strict` | doctor 内部调用 strict check；不改变 audit candidate 的严重度。 |
| `--fix` | 修复等级，取值 `none`、`safe`、`evidence`；默认 `none`。 |
| `--check-after` | 执行单项目修复后运行 `acf check`。 |
| `--today YYYY-MM-DD` | 覆盖当前日期，便于测试 stale / keep-active 规则。 |

`--draft-semantic` 和 `--report` 已实现：前者生成 grouped writeback draft，后者生成人类可读 doctor report；即使没有 findings，也会生成明确的空草案或 clean report。两者只在单项目模式写入，默认不覆盖既有文件，`--force` 才允许替换。

### 修复等级

`--fix safe` 只应用 `safe_fix`。

`--fix evidence` 应用 `safe_fix`，并允许对 `evidence_fix` 生成明确的 planned repair；首版不直接改写 `active/Context.md`、`reference/Decisions_Index.md` 等语义事实源。证据类事实默认仍以 finding 或 writeback draft 表达，避免工具从“本地证据”滑到“事实裁决”。

---

## 内部架构

### Context Graph Collector

运行时从 Markdown 文件抽取临时事实图。事实图不落盘，不进入默认上下文。

实体：

| 实体 | 来源 |
|---|---|
| `CurrentTask` | `active/Current_Task.md` section |
| `TaskPlan` | `active/Task_Plan.md` section 和子任务表 |
| `TaskStage` | `active/Task_Plan.md` 阶段表 |
| `WorkstreamIndex` | `active/Workstreams.md` |
| `WorkstreamDetail` | `active/workstreams/` 下的单个 Workstream detail front matter |
| `SourceEntry` | `reference/Sources_Index.md` |
| `DecisionEntry` | `reference/Decisions_Index.md` |
| `FeedbackEntry` | `active/Feedback_Inbox.md` |
| `ArchiveEntry` | `archive/Archive_Index.md` |
| `DataFile` | 本地文件系统和 hash |

### Rule Engine

规则只读运行，产生 finding。规则不得直接修改文件。

规则域：

1. `structure`：复用 `check_context()`。
2. `task_lifecycle`：任务状态、当前焦点、Current_Task 指针。
3. `workstream_lifecycle`：Workstream index、front matter、scope、keep-active。
4. `generated_index`：Archive / Knowledge / Decisions / Human / Workstreams 索引漂移。
5. `data_source`：本地文件存在性、hash、同名副本和数据血缘。
6. `attention_hygiene`：active 层膨胀、入口文件过厚、历史过程留在当前事实。
7. `rule_drift`：AGENTS / rules / template 协议不一致。
8. `cross_project`：项目关系和上游数据来源缺失。

### Repair Planner

每个 finding 标注修复方式：

| repair mode | 含义 | 是否可自动应用 |
|---|---|---|
| `safe_fix` | 纯机械一致性修复 | 是 |
| `evidence_fix` | 本地证据充分的事实修复候选 | 首版不直接写语义事实源；只写 generated/index 类机械位置或生成草案 |
| `draft_only` | 需要人工或 AI 判断的语义修复 | 否，只生成草案 |
| `manual_only` | 工具无法可靠生成修复 | 否 |

### Repair Executor

执行器只接收 repair plan，不重新判断事实。所有写入遵守现有 `.acf.lock`、`--dry-run`、`changed_files`、`--check-after` 契约。

允许直接写入：

1. generated marker block。
2. 工具维护的索引行。
3. 可机械定位的 table cell。
4. 可确定替换的 stale literal，例如协议枚举缺少 `Merging`。

不允许直接写入：

1. `Context.md` 的事实段落语义改写。
2. `Current_Task.md` 从一个活跃任务切换到另一个任务。
3. Workstream 是否归档的语义判断。
4. 跨项目血缘的上游版本解释。

### Report Writer

默认不落盘。显式请求时写入：

```text
worklog/doctor-reports/YYYY-MM-DD.md
worklog/writeback-drafts/YYYY-MM-DD-doctor.md
```

报告和草案不加入默认读取路径。

---

## Finding JSON Schema

```json
{
  "code": "current_task_points_to_done_task",
  "severity": "error",
  "domain": "task_lifecycle",
  "message": "Current_Task points to T002, but T002 is Done in Task_Plan.",
  "authority": "active/Task_Plan.md",
  "locations": ["active/Current_Task.md"],
  "evidence": [
    {"path": "active/Task_Plan.md", "detail": "T002 status is Done"},
    {"path": "active/Current_Task.md", "detail": "子任务 ID is T002 and status is Active"}
  ],
  "repair_mode": "draft_only",
  "safe_to_apply": false,
  "suggested_actions": [
    "Clear Current_Task or start the next unfinished task."
  ]
}
```

顶层 doctor payload：

```json
{
  "schema_version": 1,
  "command": "doctor",
  "ok": true,
  "context": "E:/Codes/Tools/ai-context-framework/docs/ai",
  "profile": "standard",
  "strict": true,
  "fix": "none",
  "changed_files": [],
  "summary": {
    "findings_total": 3,
    "by_severity": {"error": 1, "warning": 2},
    "by_repair_mode": {"safe_fix": 1, "draft_only": 2},
    "planned_repairs": 1,
    "applied_repairs": 0,
    "planned_evidence_repairs": 0,
    "changed_repair_files": 0
  },
  "findings": [],
  "check": {},
  "error_code": null,
  "next_actions": []
}
```

`ok` 语义：

1. 命令无法读取上下文或 strict check 失败时 `ok=false`。
2. 仅存在 audit / stale / semantic finding 时 `ok=true`，但 `summary.findings_total > 0`。
3. 写入修复后 `check-after` 失败时 `ok=false`。

---

## 首批规则

### Task Lifecycle

| code | 条件 | repair mode |
|---|---|---|
| `current_task_points_to_done_task` | Current_Task Active 且子任务 ID 在 Task_Plan 中为 Done / Skipped / Superseded | `draft_only` |
| `plan_focus_points_to_done_task` | `## 当前焦点` 指向 Done / Skipped / Superseded 任务 | `safe_fix`；首版仅在没有可推荐 next task 时置为 `无。`，存在候选 next task 时只报告 finding |
| `plan_current_task_status_mismatch` | Task_Plan Active 但 Current_Task Paused / Empty，或 Task_Plan Empty 但 Current_Task Active | `draft_only` |
| `current_task_wrong_completion_target` | Current_Task 完成后回写要求中明确回写目标行引用的 Txxx 与当前子任务 ID 不一致 | 条件 `safe_fix`；只有明确目标行且无额外任务引用时自动修复，否则 `draft_only` |

### Workstream Lifecycle

| code | 条件 | repair mode |
|---|---|---|
| `workstream_index_detail_status_mismatch` | Workstreams index 状态与 detail front matter 不一致 | `safe_fix` |
| `terminal_workstream_assigned_authority` | Done / Cancelled / merged WS 仍把 authority path 放在 `assigned` | `safe_fix` |
| `terminal_workstream_keep_active_expired` | Done / Cancelled WS 的 `keep_active_until < today` 且仍在 active | `draft_only` |
| `workstream_index_protocol_missing_merging` | AGENTS / Workstreams 读取协议漏掉 `Merging` | `safe_fix` |

### Generated Index

| code | 条件 | repair mode |
|---|---|---|
| `archive_index_missing_workstream` | archive/workstreams 有文件但 Archive_Index 缺 generated 行 | `safe_fix` |
| `archive_index_generated_block_out_of_sync` | Archive_Index generated block 与非 Workstream 归档文件或现有 generated 行漂移 | `safe_fix` |
| `decisions_index_summary_truncated` | generated 摘要以冒号结尾或过短，不是可读摘要 | `safe_fix` 或 `draft_only`，取决于 ADR 正文能否抽取稳定句 |
| `source_index_missing_file` | Sources_Index 指向本地文件不存在 | `evidence_fix`，首版只报告或生成草案 |

### Data Source

数据源规则必须是通用规则，不能硬编码 `factory_vs_ecsos_matched_full.csv`、`beta_sweep.csv` 等具体文件名。真实项目文件名只能出现在验收样本里。第一版只比较同一段落或同一 Markdown 表格行内显式同时出现的本地路径；路径按所在 Markdown 文件和项目根解析，但只有最终落在项目根内的文件才参与 hash 读取。绝对路径和 URI 不参与 hash 读取。不同段落或不同行中的同名文件不被视为“声明的副本关系”。

| code | 条件 | repair mode |
|---|---|---|
| `duplicate_data_hash_confirmed` | 上下文声明待确认的本地文件副本都存在且 hash 相同 | `evidence_fix`，首版只报告或生成草案 |
| `declared_duplicate_missing` | 上下文声明本地文件副本关系，但其中一个不存在 | `evidence_fix`，首版只报告或生成草案 |
| `data_lineage_missing` | 项目使用上游数据但无 Project_Relationships / Data_Lineage 入口 | `draft_only` |

### Attention Hygiene

| code | 条件 | repair mode |
|---|---|---|
| `active_terminal_workstreams_excessive` | active 中 Done / Cancelled WS 超过阈值 | `draft_only` |
| `context_too_thick` | Context 超过配置阈值且包含明显运行流水 | `draft_only` |
| `root_probe_outputs_detected` | 项目根目录存在大量 probe/result JSON | `draft_only` |

---

## 三项目验收样本

### fcc_workspace

1. 捕获 WS014 / WS020 在 Current_Task / Task_Plan 与 Workstream detail 之间的状态漂移。
2. 捕获 archive/workstreams 中 WS001-WS008 与 Archive_Index 漏项。
3. 捕获 AGENTS.md Workstream 默认读取条件缺少 `Merging`。
4. 捕获 Done Workstream 的 keep_active_until 到期候选。
5. 对 human/weekly 被 active 索引引用的问题生成 draft，不自动改。

### CrackingFurnaceSimulation

1. 捕获 WS010 Done / merged 后仍把 `Context.md`、`Task_Plan.md` 放在 assigned write_scope。
2. 捕获 T005 Active 与 Current_Task Paused 的状态冲突。
3. 捕获 Feedback 仍 Planned 但对应 WS009/WS010 已合并。
4. 捕获 Decisions_Index 摘要截断候选。
5. 对 Open Workstream 是否应让 Workstreams 状态保持 Inactive 生成 draft。

### cracking-yield-prediction-system

1. 捕获 T002 Done 但 Current_Task 仍 Active。
2. 捕获 Task_Plan focus 指向 Done T002。
3. 捕获 Current_Task 完成后回写要求写 T001 但当前任务是 T002。
4. 捕获 beta sweep 双副本事实错误，作为数据源规则的项目验收样本，而不是写死在 CLI 中。
5. 捕获 factory CSV 双副本 hash 一致但仍写待确认，作为通用 hash 规则的项目验收样本。

---

## 实现边界

短期可在 `acf.py` 中新增函数簇，以符合当前单文件 CLI 结构；后续如果 `acf.py` 继续膨胀，再拆成包内模块。

建议函数边界：

```python
def collect_doctor_findings(root: Path, *, strict: bool, today: date) -> DoctorResult: ...
def collect_task_lifecycle_findings(root: Path) -> list[DoctorFinding]: ...
def collect_workstream_lifecycle_findings(root: Path, today: date) -> list[DoctorFinding]: ...
def collect_generated_index_findings(root: Path) -> list[DoctorFinding]: ...
def collect_data_source_findings(root: Path) -> list[DoctorFinding]: ...
def plan_doctor_repairs(root: Path, findings: Sequence[DoctorFinding], fix: str) -> list[DoctorRepair]: ...
def apply_doctor_repairs(root: Path, repairs: Sequence[DoctorRepair], dry_run: bool) -> tuple[list[Path], int]: ...
def doctor_command(args: argparse.Namespace) -> int: ...
```

---

## 测试策略

1. TDD：先在 `tests/test_cli.py` 或 context matrix fixtures 中写 red tests。
2. 单项目 doctor JSON contract：clean context、strict failure、semantic finding、safe fix dry-run。
3. 修复行为测试：focus 指向 Done 时 dry-run / apply 都正确；非法 assigned authority 清理只动 front matter。
4. 数据源测试：hash 一致与缺失文件产生 evidence finding。
5. 多项目测试：`--projects` 返回每项目独立 payload，单项目失败不吞掉其他项目结果。
6. 回归验证：

```bash
uv run acf check template
uv run acf check --strict
uv run python -m unittest
```

---

## 后续扩展

1. `Data_Lineage.md` / `Project_Relationships.md` 模板和索引命令。
2. 多项目关系图审计。
3. doctor 规则配置阈值，例如 active terminal WS 数量、Context 行数。
4. 更丰富的 report 格式，例如按 owner、severity 或修复等级分组。
