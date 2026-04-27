# ai-context-framework

一个模型无关的 AI 上下文管理框架模板。

## 设计理念

人与 AI 的协作中，人作为最高决策层，AI 同时作为执行者和策略建议者。项目知识不应随 AI 工具更换或人员离开而丢失。

本框架通过分层的 Markdown 文件结构管理项目上下文，实现：

- **模型无关**：纯 Markdown，不依赖任何 AI 工具的私有格式
- **渐进式暴露**：AI 默认只读取当前有效上下文，按需读取历史和参考资料
- **单一事实源**：每类信息有唯一的权威位置，避免重复维护和冲突
- **决策可追溯**：通过 ADR（Architecture Decision Record）记录重要决策的完整推理过程

## 目录结构

```
template/
  AGENTS.md              # AI 入口文件（~115 行）
  active/                # 当前有效上下文（AI 默认读取）
    Context.md           # 当前阶段目标、事实、约束
    Current_Task.md      # 当前具体任务
  rules/                 # 规则系统（分层加载）
    Always_Active.md     # 每次必须遵守的核心规则
    Project_Rules.md     # 项目级通用规则
    Coding_Rules.md      # 代码任务规则
    Writing_Rules.md     # 写作任务规则
    Review_Rules.md      # 评审任务规则
    ...
  reference/             # 支持性资料（按需读取）
    Project_Brief.md     # 长期目标和愿景
    Architecture.md      # 架构说明
    Tech_Context.md      # 技术环境
    Decisions_Index.md   # 决策索引
    Sources_Index.md     # 外部资料索引
    System_Manual.md     # 系统详细使用手册
  decisions/             # ADR 决策记录
  worklog/               # 工作日志
  archive/               # 历史归档
```

## 使用方法

1. 安装 CLI 后，在项目根目录运行 `acf init docs/ai`
2. `init` 会在项目根目录生成薄入口 `AGENTS.md`，在 `docs/ai/` 下生成完整入口 `AGENTS.md`
3. 根据项目需要填充模板中的占位符
4. AI 进入项目时，从根目录 `AGENTS.md` 开始读取

### 关于两层 AGENTS.md 的设计

这是"**渐进式暴露**"原则的实践：

| 层级 | 文件 | 内容 | 维护者 | 频率 |
|---|---|---|---|---|
| 第一层 | `./AGENTS.md` | 薄入口 + 仓库级约定 | 框架维护者 | 很少改 |
| 第二层 | `docs/ai/AGENTS.md` | 完整上下文导航 | 项目团队 + AI | 按阶段更新 |

目的是在不暴露过多细节的前提下，让 AI 能逐步了解项目上下文结构。

如果项目根目录已经存在 `AGENTS.md`，`init` 默认不会覆盖；确认要重写根薄入口时再传入 `--force-root-agent`。

## 信息层级

| 层级 | 目录 | 读取时机 | 说明 |
|------|------|----------|------|
| 1 | active/ | 默认读取 | 当前阶段有效信息 |
| 2 | rules/ | Always_Active 默认，其余按需 | 行为规则 |
| 3 | reference/ | 按需 | 背景资料和索引 |
| 4 | decisions/ | 按需 | 决策详情 |
| 5 | worklog/ | 按需 | 工作历史 |
| 6 | archive/ | 仅明确要求时 | 归档内容 |

## 事实源优先级

冲突时按以下顺序判断：

1. 用户当前消息
2. Current_Task.md
3. Context.md
4. Decisions_Index.md
5. ADR 文件
6. worklog
7. archive

## 命令行工具

本仓库提供一个无第三方依赖的辅助 CLI：

### 安装到 PATH

开发本仓库时，可从仓库根目录安装 editable 工具：

```bash
uv tool install -e .
uv tool update-shell
```

重新打开终端后验证：

```bash
acf --help
acf status --json
```

Windows 可用 `where acf` 查看命令位置；macOS/Linux 可用 `which acf`。后续发布后，用户可通过包名或 Git URL 安装，例如 `uv tool install ai-context-framework` 或 `uv tool install git+<repo-url>`。

“任意目录可运行 `acf`”表示命令已进入 PATH；是否能自动找到上下文，取决于当前目录是否位于包含 `docs/ai` 或上下文根目录的项目中。

### 常用命令

```bash
acf status
acf init docs/ai
acf init docs/ai-min --profile minimal
acf simplify docs/ai docs/ai-min
acf new task --title "实现一个维护任务" --goal "写清当前目标。"
acf new source --title "资料标题" --type "文档" --location "https://example.com" --relation "说明为什么相关。"
acf new worklog --summary "完成一次上下文维护。"
acf new adr --title "记录一个重要决策" --summary "一句话摘要。" --decision "具体决策。"
acf writeback draft --name "session-note" --text "会话结束回写建议。"
acf edit section get active/Context.md --heading "## 当前有效事实" --json
acf edit section append active/Context.md --heading "## 当前开放问题" --text "1. 新问题。"
acf edit table upsert reference/Sources_Index.md --key-column "资料" --key "资料标题" --cell "状态=Useful"
acf check
acf check --strict
acf log enable
acf log status --json
acf log tail --limit 20 --json
acf log summarize --json
acf log prune --days 30
acf status --json
acf new task --title "预览任务" --goal "只预览。" --dry-run --json
```

未安装全局命令时，在本仓库开发环境中也可以使用 `uv run acf ...`。

命令说明：

- `status`：从当前目录向上自动发现上下文，输出项目根、上下文目录、profile、当前任务状态和检查结果。
- `init`：从 `template/` 生成标准或简化上下文目录。
- `init --force-root-agent`：在根入口已存在时重写根薄入口。
- `simplify`：从已有上下文生成只包含核心文件的简化版本，并保留真实 ADR 与 daily worklog，排除占位模板文件。
- `new task`：生成或重置 `active/Current_Task.md`，默认拒绝覆盖 Active 任务，除非传入 `--force`。
- `new source`：向 `reference/Sources_Index.md` 添加或更新资料索引行，默认拒绝重复资料标题，除非传入 `--force`。
- `new worklog`：按日期生成 daily worklog，并更新 `worklog/Worklog_Index.md`。
- `new adr`：生成下一个 ADR 文件，并更新 `reference/Decisions_Index.md`。
- `writeback draft`：把会话结束回写建议保存为可审阅草案，不直接修改权威上下文文件。
- `edit section get|replace|append`：读取、替换或追加指定 Markdown 标题下的 section body。
- `edit table upsert`：按 key column 更新或追加 Markdown 表格行。
- `check`：检查目录结构、必需文件、乱码、空文件、内部引用、状态枚举、索引一致性和占位符残留。
- `log enable|disable|status|tail|summarize|prune`：管理本地使用状态日志，默认关闭，启用后记录命令结果元数据。

`check`、`new ...` 和 `writeback draft` 可以省略上下文路径；省略时 CLI 会从当前目录向上查找 `docs/ai` 或上下文根目录。显式传入路径时，以显式路径为准。

`status`、`check` 和 `edit section get` 支持 `--json` 输出。写命令支持 `--json`、`--dry-run`、`--check-after`，并会输出 changed files；`--dry-run` 只验证和预览，不落盘。

`edit` 命令只操作上下文根目录内已有的 `.md` 文件，拒绝路径穿越和非 Markdown 目标。它提供的是 section/table 级确定性编辑原语，不做语义判断，也不是通用 Markdown 编辑器。

`log` 命令默认写入用户级全局目录 `%USERPROFILE%\.acf\projects\<project-id>\`（Windows）或 `~/.acf/projects/<project-id>/`（macOS/Linux），也可通过 `ACF_HOME` 指定根目录。它不写入项目 `worklog/`，也不记录 `--text` 正文、stdin 内容、Markdown diff 或完整 stdout/stderr。日志写入失败不会改变原命令退出码。

JSON 输出包含稳定字段：`schema_version`、`ok`、`error_code`、`next_actions`。检查失败时 `error_code` 为 `check_failed`，`next_actions` 给出 AI 可直接读取的后续动作。

退出码和错误分类：

- `0`：成功。
- `1`：检查失败，`error_code=check_failed`。
- `2`：输入错误，`error_code=input_error`。
- `3`：安全拒绝，例如重复写入或需要 `--force`，`error_code=safety_refused`。
- `70`：非预期运行时错误，`error_code=runtime_error`。

`check` 默认关注结构完整度；`--strict` 适合检查已投入使用的项目上下文，会把占位符残留视为错误。

## 维护与验证

修改模板或 CLI 后运行：

```bash
uv run acf check template
uv run acf check --strict
uv run python -m unittest
```

自动化边界和后续路线见 `docs/Automation.md`。
