# Workstream Lifecycle and Archive Helper Design

本文件定义 Workstream 从 `active/workstreams/` 进入 `archive/workstreams/` 的生命周期边界和后续 helper 设计。它补充 `ACF_Top_Level_Design.md` 和 `Workstream_Design.md`，不替代这两个上位文档。

---

## 设计目标

Workstream lifecycle / archive helper 的目标是降低 active 长期膨胀，同时避免把仍支撑当前计划理解的终态 Workstream 过早移出默认注意力入口。

它解决的问题是：

1. Done / Cancelled Workstream 已有 keep-active gate，但长期归档仍靠人工。
2. `active/workstreams/` 中的终态详情可能积累，导致 active 层变长。
3. 直接移动文件风险较高，因为终态 Workstream 可能仍解释当前计划、Task Stage、merge result 或近期决策。
4. `workstream sync` 当前明确不删除索引旧行，也不移动详情文件，归档生命周期需要单独设计。

---

## 非目标

本设计不做：

1. 不自动判断 Workstream 是否“语义上已经不需要”。
2. 不在 `check --strict` 中要求所有 Done / Cancelled 立即归档。
3. 不让 `workstream sync` 删除缺详情的旧索引行。
4. 不让 `upgrade` 自动归档历史 Workstream。
5. 不自动修改 `active/Context.md`、`active/Current_Task.md` 或 Task Plan。
6. 不把 Workstream archive 做成调度器或 agent runtime。

---

## 状态机边界

Workstream 主状态机保持不变：

```text
Open -> Active -> ReadyToMerge -> Done -> archive
              -> Blocked -> Active
Open/Active/Blocked/ReadyToMerge -> Cancelled -> archive
```

归档不是 Workstream status 值。归档是文件所在层级变化：

1. active 状态文件示例：active/workstreams/WS001 dot md。
2. archive 状态文件示例：archive/workstreams/WS001 dot md，或日期化文件名。

Done / Cancelled 是终态；归档后的 Workstream 不应再回到 Active。如果需要继续推进，应新建 Workstream 或新任务。

---

## 当前已实现的硬边界

当前实现已经提供：

1. Done 必须有 evidence。
2. Done 必须有 `merge_resolution`。
3. ReadyToMerge / Done 声明 `merge_targets` 时必须有 merge request。
4. Done / Cancelled 留在 active 时，普通 check 对缺 keep-active metadata 给 warning。
5. strict check 下，`keep_active_until` 过期会报 error。
6. `workstream sync` 只更新 `active/Workstreams.md`，不移动详情文件，不删除缺详情旧行。

这些规则说明：ACF 已能防止“终态 Workstream 无解释长期滞留 active”，但还没有提供“如何安全归档”的 CLI 闭环。

---

## 是否可以归档的机械前置条件

后续 helper 只能把以下条件作为机械筛选，不做语义裁决：

1. Workstream status 是 Done 或 Cancelled。
2. Done 有 evidence。
3. Done 有合法 `merge_resolution`。
4. 如果声明 `merge_targets`，已有 merge request。
5. 当前日期晚于 `keep_active_until`，或用户显式指定该 Workstream。
6. `active/Current_Task.md` 的 `## 当前执行线` 没有引用该 Workstream。
7. `active/Task_Plan.md` 当前焦点不是直接要求该 Workstream 作为当前解释线。

这些条件只能说明“可能适合归档”。它们不能证明 Workstream 不再有语义价值。

---

## 不应自动归档的情况

即使 Workstream 已 Done / Cancelled，也不应被自动归档：

1. `keep_active_until` 未过期。
2. `keep_active_reason` 明确说明仍支撑当前 active plan。
3. `active/Current_Task.md` 当前执行线引用该 Workstream。
4. 当前 Task Stage 明确将该 Workstream 作为归属或关键证据。
5. merge_resolution 是 `rejected` 且拒绝原因仍需要当前计划理解。
6. Workstream 详情仍包含未处理 merge request。
7. 用户只运行 `workstream sync` 或 `upgrade`。

第一版 helper 必须偏保守：宁可生成候选草案，也不要移动仍有当前解释价值的详情。

---

## 第一版 helper 形态

第一版由三个显式步骤组成：

```bash
acf workstream archive-candidates docs/ai --json
acf workstream archive-draft docs/ai --date 2026-05-08 --json
acf workstream archive WS001 docs/ai --reason "reviewed in worklog/archive-drafts/2026-05-08.md" --json
```

`archive-candidates` 只读输出机器可读候选；`archive-draft` 生成人工 / AI 可审阅的 Markdown 草案；`archive` 才真正移动单个 Workstream。draft 不支持 apply，不批量归档。

候选命令输出：

```json
{
  "schema_version": 1,
  "ok": true,
  "command": "workstream archive-candidates",
  "context": "docs/ai",
  "candidates": [],
  "blocked": [],
  "changed_files": [],
  "summary": {
    "terminal_total": 0,
    "candidate_total": 0,
    "blocked_total": 0,
    "by_blocker": {}
  },
  "next_actions": []
}
```

candidate 建议字段：

```json
{
  "id": "WS001",
  "status": "Done",
  "detail": "active/workstreams/WS001.md",
  "archive_target": "archive/workstreams/WS001.md",
  "reason": "Done and keep_active_until has expired.",
  "blocked_by": [],
  "keep_active_until": "YYYY-MM-DD"
}
```

`blocked_by` 用于解释为什么某个终态 Workstream 没有进入候选，例如：

1. `keep_active_until_not_expired`
2. `referenced_by_current_task_execution_line`
3. `referenced_by_current_plan_focus`
4. `referenced_by_current_task_stage`
5. `missing_merge_resolution`
6. `missing_evidence`
7. `missing_merge_request`
8. `missing_cancellation_reason`
9. `invalid_keep_active_until`

---

## Archive draft 契约

draft 写入：

```bash
worklog/archive-drafts/YYYY-MM-DD.md
```

带 `--name p2-cleanup` 时写入：

```bash
worklog/archive-drafts/YYYY-MM-DD-p2-cleanup.md
```

默认不覆盖已有草案；重复运行失败并提示使用 `--name` 或 `--force`。`--dry-run` 不写文件，并返回 planned draft。

draft 必须包含：

1. `## 可归档候选`：列出 ID、status、detail、archive_target、reason 和建议命令。
2. `## 暂不归档`：列出 ID、status、detail、blocked_by、reason 和 suggested_action。
3. `## 审阅记录`：保留 approved / rejected / notes 占位。

候选项可以生成建议命令，但只作为文本：

```bash
uv run acf workstream archive WS001 docs/ai --reason "reviewed in worklog/archive-drafts/2026-05-08.md" --json
```

blocked 项不生成修复命令，只写 suggested_action，避免鼓励 AI 自动改当前事实。

---

## 显式 archive 命令契约

移动命令为：

```bash
acf workstream archive WS001 docs/ai --reason "reviewed in worklog/archive-drafts/2026-05-08.md" --json
```

第一版移动命令满足：

1. 只接受 Done / Cancelled，不支持 `--force`。
2. 要求 `--reason`。
3. 支持 `--date YYYY-MM-DD`、`--dry-run`、`--json`、`--check-after`。
4. 复用 `archive-candidates` 的 blocker assessment；有 blocker 时拒绝。
5. 自动移动 active/workstreams/WS001 dot md 到 archive/workstreams/WS001 dot md。
6. 自动删除 `active/Workstreams.md` 中对应行，并重算 `## Workstream 状态`。
7. 自动写入 `archive/Archive_Index.md`。
8. 自动在归档详情末尾追加 `ACF:WORKSTREAM-ARCHIVE` marker block。
9. 不修改 merge target，不修改 `active/Context.md`、`active/Current_Task.md`、`active/Task_Plan.md`。
10. 如果 `active/Workstreams.md` 缺少该 ID 行，warning 后继续；如果有重复行，失败。
11. 如果目标 archive/workstreams/WS001 dot md 已存在，失败。
12. 如果移动后 `active/workstreams/` 为空，保留目录并确保 `.gitkeep`。

Cancelled Workstream 不要求 `merge_resolution`，但必须有 `## 取消原因`。Done Workstream 必须有 `## 证据` 和 `merge_resolution`；声明 `merge_targets` 时必须有合并请求。

---

## Archive_Index 记录

`archive/Archive_Index.md` 使用通用 7 列表头：

```md
| 日期 | 类型 | ID | 原路径 | 归档路径 | 状态 | 原因 |
|---|---|---|---|---|---|---|
```

Workstream 归档行示例：

```md
| 2026-05-08 | workstream | WS001 | active/workstreams/WS001.md | archive/workstreams/WS001.md | Done | reviewed in worklog/archive-drafts/2026-05-08.md |
```

样例中的原路径和归档路径都不使用 Markdown 反引号引用，避免设计文档里的假想路径被 `acf check` 当成必须存在的本地引用；实际归档文件中的归档路径可以在文件存在后写成可检查引用。

---

## Archive marker

归档详情文件末尾追加稳定 marker block：

```md
<!-- ACF:WORKSTREAM-ARCHIVE:START -->
## 归档记录

- archived_at: 2026-05-08
- source_path: active/workstreams/WS001.md
- archive_path: archive/workstreams/WS001.md
- archive_reason: reviewed in worklog/archive-drafts/2026-05-08.md
<!-- ACF:WORKSTREAM-ARCHIVE:END -->
```

marker 命名采用 `ACF:<DOMAIN>:<PURPOSE>`；本功能使用 `ACF:WORKSTREAM-ARCHIVE`。`source_path` 不使用反引号，避免归档后形成 broken markdown reference。

---

## Fixture 要求

进入代码实现前至少需要 synthetic fixture 覆盖：

1. Done Workstream 有 evidence、merge_resolution、未来 `keep_active_until`，strict check clean。
2. 同一个 Workstream 的 `keep_active_until` 改为过去日期后，strict check 报 expired。
3. 当前任务执行线引用 terminal Workstream 时，check 报错，说明不能把终态 Workstream 当当前执行线。
4. Done Workstream 作为 Task Stage 历史 evidence 或 owner 引用时，不等于当前执行线，不应触发归档移动。
5. candidate -> archive-draft -> explicit archive -> strict check clean。
6. 缺 index 行时 archive warning 后继续；重复 index 行时 archive 失败。
7. archive target 已存在时 archive 失败。

这些 fixture 证明 helper 必须区分“终态但仍需解释”和“可归档候选”。

---

## 推荐实施顺序

1. 本设计文档。
2. `tests/fixtures/context_matrix/workstream_lifecycle_archive`。
3. fixture 测试覆盖 keep-active clean / expired / current execution line rejected。
4. 只读 `workstream archive-candidates` 命令。已完成。
5. archive draft 命令。已完成。
6. 显式 `workstream archive` 移动命令。已完成。

---

## 版本策略

1. 只新增本设计文档和 fixture：不 bump 版本。
2. 新增 `workstream archive-candidates` 或 `archive-draft` 命令：bump patch。
3. 新增会移动文件的 `workstream archive`：bump patch，并需要更完整 smoke / matrix 验证。
4. 若改变 `workstream sync` 删除策略或 strict 默认行为：考虑 minor。
