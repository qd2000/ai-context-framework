本文件记录本仓库 AI context framework 的维护手册摘要。

完整产品手册以仓库模板目录中的 System_Manual 为源；本文件只记录 dogfooding 实例中的项目内维护要点。

---

## 当前上下文层级

1. `active/Context.md`：当前阶段事实。
2. `active/Feedback_Inbox.md`：人工临时反馈、问题、需求和计划碎片。
3. `active/Task_Plan.md`：当前大任务计划和子任务板。
4. `active/Current_Task.md`：当前具体任务。
5. `active/Workstreams.md`：可选并行目标线索引，仅在显式启用且存在 Active、Blocked 或 ReadyToMerge workstream 时按需读取。
6. `rules/`：默认和按需规则。
7. `reference/`：长期背景、架构、技术环境、决策和 Knowledge 索引。
8. `worklog/`：历史工作记录。
9. `archive/`：旧任务和旧计划归档。

顶层产品边界和长期设计以 `reference/ACF_Top_Level_Design.md` 为准；阶段路线和近期优先级以 `reference/Product_Roadmap.md` 为准。新增对象、规则、CLI 命令、模板结构或 upgrade 行为前，应先确认它属于 `check`、`audit`、`sync`、`draft`、`upgrade` 或普通维护命令中的哪一层。

Workstream 归档生命周期以 `reference/Workstream_Lifecycle_Archive_Design.md` 为准。当前已提供只读 `workstream archive-candidates` helper，用于报告可考虑归档的终态 Workstream 和 `blocked_by`；显式移动文件命令仍未实现，`workstream sync` 和 `upgrade` 都不自动归档 Done / Cancelled Workstream。

---

## Context 审阅标记

`active/Context.md` 使用文件级审阅标记：

```markdown
## 审阅标记

- Last reviewed: YYYY-MM-DD
- Review scope: 文件级；确认当前目标、当前事实、约束和开放问题仍适合作为默认注意力入口。
```

`acf review stale` 会识别 `Last reviewed` / `上次审阅` / `最近审阅` 附近的 ISO 日期。该标记不要求条目级事实 ID，也不表示 CLI 已判断每条事实真假。

---

## 常用维护命令

- `uv run acf status --json`
- `uv run acf upgrade docs/ai --dry-run --json`
- 通用升级形式：`acf upgrade [target]`
- `uv run acf check --strict`
- `uv run acf workstream status docs/ai --json`
- `uv run acf workstream add docs/ai --id WS002 --title "并行线" --owner "主 agent" --goal "验证并行目标线。" --output "验证记录" --dry-run --json`
- `uv run acf workstream set WS002 docs/ai --goal "补充或替换目标。" --dry-run --json`
- `uv run acf workstream merge-request WS001 docs/ai --target Context --summary "候选摘要" --verification "测试通过" --dry-run --json`
- `uv run acf workstream claim WS001 docs/ai --read reference/Architecture.md --write "draft: worklog/writeback-drafts/WS001-note.md" --dry-run --json`
- `uv run acf workstream note WS001 docs/ai --section 当前发现 --text "记录一个局部发现。" --dry-run --json`
- `uv run acf workstream show WS001 docs/ai --json`
- `uv run acf workstream stage add WS001 docs/ai --id WS001.1 --title "内部阶段" --json`
- `uv run acf workstream stage list WS001 docs/ai --json`
- `uv run acf workstream focus WS001 WS001.1 docs/ai --json`
- `uv run acf workstream stage done WS001 WS001.1 docs/ai --evidence "worklog/daily/YYYY-MM-DD.md" --clear-current --json`
- `uv run acf workstream archive-candidates docs/ai --json`
- `uv run acf plan status docs/ai --json`
- `uv run acf plan stage add docs/ai --id T001.1 --parent T001 --title "任务阶段" --json`
- `uv run acf plan stage list docs/ai --json`
- `uv run acf plan stage set docs/ai --id T001.1 --status Active --next-action "完成阶段" --json`
- `uv run acf plan stage done docs/ai --id T001.1 --evidence "worklog/daily/YYYY-MM-DD.md" --json`
- `uv run acf review stale docs/ai --json`
- `uv run acf audit context docs/ai --json`
- `uv run acf curate draft docs/ai --dry-run --json`
- 需要整理、归纳、精简上下文时，按需读取 `reference/Context_Curation_Prompt.md`；默认产物是整理建议，不是文件修改。
- `uv run acf log feedback docs/ai --type Problem --source manual --text "实际使用反馈。" --json`
- `uv run acf log summarize --days 7 --json`
- `uv run acf new worklog docs/ai --summary "补记一次上下文维护。" --append --dry-run --json`
- `uv run acf version show --json`
- `uv run acf version set v0.0.3.30 --dry-run --json`
- `uv run python scripts/upgrade_matrix.py --mode quick`
- `uv run python scripts/upgrade_matrix.py --mode full --acf uv run acf`

Workstream 详情可用 optional `current_stage` 和 `## 阶段` 表记录内部阶段焦点；`workstream stage add/list` 只维护详情文件阶段表，`workstream focus` 只切换详情文件内的 `current_stage` 和目标阶段 Active 状态，`workstream stage done` 要求 evidence，完成当前阶段时需要 `--clear-current`，不会自动激活下一阶段或更新全局 `../active/Current_Task.md`。`merge_targets` 用于记录候选合并目标，不表示 Workstream 可以直接写 authority 文件。`acf check` 会检查当前阶段已注册、属于本 Workstream、状态合法，strict 下检查 Done 阶段 evidence，检查 Workstreams 索引与详情 front matter 是否一致，并在 strict 下拒绝 `owned` / `assigned` 直接命中内置 authority path；ReadyToMerge / Done Workstream 声明 `merge_targets` 时必须有合并请求；Done Workstream 需要 `merge_resolution`，仍留在 active 时需要 keep-active metadata。

Task Stage 仍以 `active/Task_Plan.md` 的 `## 任务阶段` 表为事实源；`plan stage list|add|set|done` 只维护该表，不创建 task object 单文件，不自动修改 `active/Current_Task.md`，也不自动联动 Workstream。`plan stage add` 要求阶段 ID 使用 `T001.1` 格式且归属于已存在父任务，`--workstream` 只接受已存在的 Workstream ID 或空值；`plan stage done` 要求 `--evidence`。

`acf workstream archive-candidates --json` 只读扫描 Done / Cancelled Workstream，输出 `candidates`、`blocked`、`blocked_by` 和 `changed_files: []`；机械 blocker 包括 keep-active 未过期、当前执行线引用、当前任务阶段归属、缺 evidence、缺 merge_resolution 或缺 merge request。该命令不写文件、不修改 `active/Workstreams.md`、不移动详情文件、不接入 strict。

`acf workstream sync --dry-run --json` 只根据 `active/workstreams/*.md` front matter 预览或更新 `active/Workstreams.md`；第一版不会删除索引中缺失详情文件的旧行，也不会移动 Done / Cancelled 文件。

Done / Cancelled Workstream 留在 `active/workstreams/` 时，应有 `keep_active_reason` 和 `keep_active_until`；strict check 会拒绝过期的 `keep_active_until`。仍被当前计划解释所需的终态 Workstream 不应被自动归档；当前 archive helper 只输出候选，不替用户做移动决策。

`acf audit context --json` 是只读上下文审计 MVP，只报告 candidates，不判断事实真假、不写文件、不生成 patch、不接入 `check --strict`。当前规则只覆盖长 active section、陈旧当前任务 / Workstream 阶段和 ReadyToMerge 待合并或 Done 缺合并结果候选。

PowerShell 中反引号是转义字符。写入包含 Markdown 反引号或多行正文时，优先使用 `--input <file>`。

### AI 调用 worklog 模式

| 目标状态 | 推荐命令 | 结果 |
|---|---|---|
| 不确定是否已有今日 worklog | `uv run acf new worklog docs/ai --summary "..." --dry-run --json` | 根据 `error_code` 判断下一步 |
| 今日 worklog 不存在 | `uv run acf new worklog docs/ai --summary "..." --json` | 创建 |
| 今日 worklog 已存在，想补记 | `uv run acf new worklog docs/ai --summary "..." --append --json` | 追加到稳定 anchor |
| 今日 worklog 已存在，想重建 | `uv run acf new worklog docs/ai --summary "..." --force --json` | 替换 |
| anchor 缺失 | 不自动修复 | 返回 `ANCHOR_NOT_FOUND` |

`new worklog --append` 的 JSON 面向 AI 稳定解析：`target` 和 `changed_files` 使用 repo-relative POSIX slash 路径；成功输出包含结构化 `warnings` 数组；`insert_after_line` 是 1-based 行号；`--dry-run --json` 不写文件；append 不是幂等操作，每运行一次都会新增一段内容。目标已存在但未传 `--append` 或 `--force` 时，`error_code=TARGET_EXISTS_APPEND_REQUIRED`；`--append --force` 返回 `APPEND_FORCE_CONFLICT`；anchor 缺失返回 `ANCHOR_NOT_FOUND`。

---

## 人工反馈处理

1. 人工可直接写入 `active/Feedback_Inbox.md`。
2. AI 处理 Open 条目时，先判断归属。
3. 可执行事项进入 `active/Task_Plan.md`。
4. 当前事实进入 `active/Context.md`。
5. 重要决策进入 ADR。
6. 历史过程进入 worklog。
7. 可复用经验进入 Knowledge 草案流程。
8. Done/Rejected 条目必须保留证据位置或拒绝原因；超过 10 条，或完成超过 30 天且不再支撑当前计划时，整理到 `archive/feedback/`。

## 注意力治理

1. 默认上下文只保留当前目标、当前事实、当前任务和下一步。
2. 写入前必须判断唯一权威位置；能更新旧表述时，不追加重复事实。
3. worklog 记录历史过程，archive 保存历史材料，Feedback_Inbox 保存待处理信号；它们默认不作为当前事实。
4. 整理事实时优先读取 changed files、`active/`、相关索引和最近 worklog。
5. 不为 curation 默认读取 archive 或全部历史日志；writeback draft 和 curation draft 不进入默认读取路径。
6. 能引用权威位置时，不复制完整表述。

## 会话结束回写

1. 不再默认打印完整“无需更新”清单。
2. 可确定的计划、任务、Context、worklog、Knowledge、archive 或 ADR/rules 变化，优先用 `acf` 命令或结构化编辑落盘。
3. 不能安全落盘但需要保留的判断，生成 `writeback draft` 草案；草案应列出当前事实变更、唯一权威位置、仅保留为历史的信息和待确认信号。
4. 最终回复只报告实际修改、草案路径、验证结果和仍需人工判断的风险。

---

## Strict 检查策略

真实项目 strict 检查不应被标准模板中的示例文件阻塞。ADR template 和 YYYY-MM-DD daily worklog 是模板示例，不是项目事实；模板源自身仍应通过 `acf check template` 暴露占位符 warning。

---

## Upgrade 兼容性维护

开发修改 `template/`、默认上下文结构、打包清单或 `acf upgrade` 行为时，必须同时评估旧版本上下文的升级路径：

1. 新增目录或文件时，同步更新 init 文件清单、upgrade 补齐清单和 `pyproject.toml` data-files。
2. 修改入口、手册或默认读取顺序时，检查 `acf upgrade` 是否能非破坏式更新旧 AGENTS/System Manual，不能安全重排时应追加 marker notes。
3. 补充或更新 init/upgrade 单元测试，覆盖新项目生成和旧项目 dry-run/正式 upgrade。
4. 验证 `uv run acf check template`、`uv run acf upgrade docs/ai --dry-run --json`、`uv run acf check docs/ai --strict --json`、`uv run python -m unittest` 和 upgrade compatibility quick/full 模式。
