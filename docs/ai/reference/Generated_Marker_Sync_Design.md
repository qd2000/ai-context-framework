# Generated Marker Sync Design

本文定义 Knowledge、ADR 和 Archive sync 命令共同遵守的 generated marker 契约。它是长期设计文档；当前 `knowledge sync`、`decisions sync` 和 `archive sync` MVP 已按该契约落地，后续扩展仍以本文边界为准。

---

## 状态

Draft

---

## 背景

当前 ACF 已实现 Workstream sync：详情文件是事实源，[active/Workstreams.md](../active/Workstreams.md) 是索引视图，sync 只更新索引中的可派生字段，并保留无法安全判断的旧行。

Knowledge、ADR 和 Archive 曾主要依赖人工或专用创建命令维护索引。实现 `knowledge sync`、`decisions sync` 或 `archive sync` 时有两个风险：

1. 误删人工维护的历史行或说明。
2. 把索引内容和详情事实源的责任边界混在一起。

因此先定义 generated marker，再按同一契约逐步实现跨文件 sync。

---

## 目标

1. 让机器维护的索引片段可识别、可替换、可审查。
2. 保护 marker 外的人工内容，sync 不重排全文。
3. 支持 dry-run、JSON、changed_files 和 check-after。
4. 保持 Markdown-first，不引入数据库、front matter 解析依赖或第三方运行依赖。
5. 允许旧项目逐步迁移；没有 marker 的旧索引默认不被自动覆盖。

---

## 非目标

1. 不自动判断事实真假。
2. 不自动把 worklog 或 human notes 升格为 Knowledge、ADR 或 Archive。
3. 不自动删除 marker 外的人工行。
4. 不把所有对象都改成强 schema。
5. 不把 sync 接入 strict；strict 只检查低误报结构错误。

---

## Marker 规范

机器维护块使用 canonical ACF marker：

```md
<!-- ACF:<DOMAIN>:<PURPOSE>:START -->
... generated content ...
<!-- ACF:<DOMAIN>:<PURPOSE>:END -->
```

命名规则：

1. `DOMAIN` 使用大写对象域：`KNOWLEDGE`、`DECISIONS`、`ARCHIVE`。
2. `PURPOSE` 使用大写用途：`INDEX-GENERATED`、`SUMMARY-GENERATED`、`ARCHIVE-RECORD`。
3. 一个文件内同一 marker pair 只能出现一次。
4. 缺 START 或 END 是结构错误；重复 marker 是 check candidate，是否进入 strict 需按误报风险单独评估。
5. 旧 marker 继续兼容，但 upgrade 只能迁移明确等价的旧 marker，不猜测人工块。

---

## 同步边界

### Knowledge

候选命令：`acf knowledge sync`

事实源：

1. `reference/knowledge/*.md` 中已 apply 的 Knowledge 详情。
2. [reference/Knowledge_Index.md](Knowledge_Index.md) 中 marker 外的人工说明。

generated 目标：

```md
<!-- ACF:KNOWLEDGE:INDEX-GENERATED:START -->
| ID | 状态 | 标题 | Tags | 摘要 | 来源 | 详情 |
...
<!-- ACF:KNOWLEDGE:INDEX-GENERATED:END -->
```

第一版行为：

1. 只生成或替换 marker 内表格。
2. 不删除 marker 外人工行。
3. 详情缺失或 metadata 不完整时，保留现状并在 JSON warnings 中报告。
4. 不从 worklog 自动创建 Knowledge。

### ADR / Decisions

候选命令：`acf decisions sync`

事实源：

1. `decisions/ADR-*.md`。
2. [reference/Decisions_Index.md](Decisions_Index.md) 中 marker 外的人工说明。

generated 目标：

```md
<!-- ACF:DECISIONS:INDEX-GENERATED:START -->
| ID | 标题 | 状态 | 摘要 | 详情 |
...
<!-- ACF:DECISIONS:INDEX-GENERATED:END -->
```

第一版行为：

1. 可从 ADR heading section 提取 `状态`、标题和摘要；不要求旧 ADR 具备 front matter。
2. 缺状态或状态非法时不猜测，输出 warning。
3. 不修改 ADR 正文。
4. 不删除 marker 外旧行。

### Archive

候选命令：`acf archive sync`

事实源：

1. `archive/tasks/*.md`
2. `archive/plans/*.md`
3. `archive/workstreams/*.md`
4. [archive/Archive_Index.md](../archive/Archive_Index.md) marker 外人工说明。

generated 目标：

```md
<!-- ACF:ARCHIVE:INDEX-GENERATED:START -->
| 日期 | 类型 | ID | 原路径 | 归档路径 | 状态 | 原因 |
...
<!-- ACF:ARCHIVE:INDEX-GENERATED:END -->
```

第一版行为：

1. 只为可机械识别的归档文件生成行。
2. 旧索引中 marker 外历史行保持不动。
3. 若归档文件缺少可识别标题或日期，从文件名推断并输出 warning。
4. 不自动归档 active 文件；归档仍通过显式 `archive current-task`、`archive task-plan` 或 `workstream archive`。

---

## 写入策略

1. 没有 marker 时，第一版 sync 默认安全拒绝，并提示先运行 `--init-marker --dry-run` 或使用专门的迁移任务。
2. `--init-marker` 只插入空 generated block 或把可确定的现有表格迁入 marker；不能确定时生成 warning，不覆盖。
3. `--dry-run` 输出 planned block、changed_files、warnings 和 skipped_items。
4. 正式写入只替换 marker 内内容。
5. `--check-after` 写后运行 context check；失败时保留写入结果并通过 JSON 返回 check errors，与现有写命令一致。

---

## 删除策略

1. sync 不删除 marker 外内容。
2. marker 内行可以消失，但必须可由详情文件不存在或状态变更机械解释。
3. 对缺详情的旧索引行，第一版应移动到 `skipped_items`，不自动删除。
4. 真正删除或归档旧人工行必须是单独命令或人工 patch。

---

## JSON 契约

成功 payload 至少包含：

```json
{
  "schema_version": 1,
  "ok": true,
  "command": "knowledge sync",
  "changed_files": [],
  "generated_count": 0,
  "skipped_items": [],
  "warnings": [],
  "next_actions": []
}
```

失败 payload 继续使用稳定字段：

1. `ok=false`
2. `error_code`
3. `message`
4. `next_actions`

建议 error_code：

| error_code | 场景 |
|---|---|
| `generated_marker_missing` | 未找到目标 marker 且未显式 init |
| `generated_marker_duplicate` | 同一 marker 重复 |
| `generated_marker_unclosed` | START/END 不成对 |
| `sync_source_invalid` | 详情源无法机械解析 |

---

## 测试计划

第一批应先覆盖 marker helper 和一个最小对象域，不一次实现三类 sync。

推荐顺序：

1. 新增 marker helper 单元测试：缺 marker、重复 marker、不成对 marker、替换 marker 内内容、保留 marker 外人工内容。
2. 新增 `knowledge_sync_generated_marker` fixture：详情文件生成 Knowledge_Index marker block。
3. 新增 `knowledge sync --dry-run --json`，只实现 Knowledge。
4. 已按同一契约扩到 `decisions sync`。
5. 已按同一契约扩到 `archive sync`，Archive sync 最后做，因为历史行和多类型归档文件最多。

---

## 下一代码切片

已完成的第一批 PR：

```text
Generated marker helper and Knowledge sync MVP
```

已完成的第二批 PR：

```text
Decisions sync MVP
```

已完成的第三批 PR：

```text
Archive sync MVP
```

范围：

1. 通用 marker replace helper。
2. `acf knowledge sync --dry-run --json`。
3. `--init-marker` 第一版。
4. `acf decisions sync --dry-run --json`。
5. `acf archive sync --dry-run --json`，覆盖 `archive/tasks`、`archive/plans` 和 `archive/workstreams`。
6. 不接入 strict。

验收：

1. marker helper tests 通过。
2. Knowledge sync、Decisions sync 和 Archive sync JSON contract tests 通过。
3. `uv run python -m unittest` 通过。
4. `uv run acf check docs/ai --strict --json` 通过。
5. minimal smoke 不必扩大，除非新增命令进入 smoke 主路径。
