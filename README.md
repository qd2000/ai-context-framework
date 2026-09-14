# ai-context-framework

一个模型无关的 AI 上下文管理框架模板。

## 当前推荐版本

`v0.0.3.89` 是当前已完成 immutable tag / publish / global install 的 **Agent-first Project Observer Beta 稳定安装态**；canonical Windows `acf` 当前即为 `.89`。`.89` 保留 Writer continuation/effect/fencing/Git safety 与 Production anti-masking，同时把 Production Observer 默认合同切换为 Agent-first：ACF 只是可选导航、数据和兼容工具，Target Registry、semantic-review、Map Review、`primary_visualization` 与 fixed renderer 均不再是页面生成前置；Observer Agent 可以从当前授权的一手资料自主理解项目并维护 Observer-owned HTML/CSS/SVG/JS。旧 derived-presentation/runtime 能力继续作为显式 legacy compatibility helper，且不得覆盖 Agent-owned 稳定入口。现有 ACF/FCC/AStockT_AI 三个 Production Observer Scheduled Task 已由用户原位迁移到 Agent-first 提示并进入自然 Production dogfood；当前 WS012 worktree 中 `.89` 之后的修复仍属于 successor candidate，不能冒充已安装 stable。

- 版本变化：[CHANGELOG.md](CHANGELOG.md)
- Workstream/Worktree 教程：[docs/Worktree_Lifecycle.md](docs/Worktree_Lifecycle.md)
- 详细 CLI 参数：`acf --help`、`acf workstream reserve --help`、`acf worktree --help`、`acf continuation --help`、`acf observer --help`

ACF 的默认 AI 入口采用 global-first progressive disclosure：无论项目有一个还是多个 Active / Blocked / ReadyToMerge / Merging Workstream，只要没有明确选择，agent 都只读取全局上下文和 Workstreams 摘要，不读取任何 WS detail、read_scope、reference、output 或专属 worklog。显式选择后，`acf status|next --workstream WSNNN` 仍只返回 pointer-only 入口；随后调用 `acf workstream context WSNNN` 才披露专属上下文和边界。`reference/` 是项目内中间材料层，Knowledge 是有来源、证据和适用边界的高可信精炼层，均按需读取。

`acf check --strict` 只能证明结构、断链、状态和索引一致性；不能证明项目事实完全正确。升级后仍需人工或 AI 审查 `Context.md`、`Project_Brief.md`、`Tech_Context.md`、`AGENTS.md` 和项目特有规则是否准确。

稳定入口和开发入口需要分开：真实项目中使用非 editable 安装的稳定 `acf`；在本仓库开发时使用 `uv run acf` 或 `uv run python acf.py`。只有在调试安装链路或 CLI 改动时，才临时使用 editable install。

## 设计理念

人与 AI 的协作中，人作为最高决策层，AI 同时作为执行者和策略建议者。项目知识不应随 AI 工具更换或人员离开而丢失。

本框架通过分层的 Markdown 文件结构管理项目上下文，实现：

- **模型无关**：纯 Markdown，不依赖任何 AI 工具的私有格式
- **渐进式暴露**：AI 默认只读取当前有效上下文，按需读取历史和参考资料
- **单一事实源**：每类信息有唯一的权威位置，避免重复维护和冲突
- **注意力治理**：默认注意力入口只保留低噪声、高权威、任务相关的信息
- **决策可追溯**：通过 ADR（Architecture Decision Record）记录重要决策的完整推理过程

## 目录结构

```
template/
  AGENTS.md              # AI 入口文件（~115 行）
  active/                # 当前有效上下文（AI 默认读取）
    Context.md           # 当前阶段目标、事实、约束
    Feedback_Inbox.md    # 人工反馈、问题、需求和计划碎片
    Task_Plan.md         # 当前大任务计划、规划依据、轻量子任务板和可选任务阶段表
    Current_Task.md      # 当前具体小任务，可记录当前执行 Workstream
  human/                 # 人类给 AI 的半结构化材料层（默认不读，按需读取）
    Human_Index.md       # human 材料索引和处理状态
    Human_Notes.md       # 人工随笔、疑问、规划草稿 inbox
    weekly/              # 周记录
    reports/             # 复盘、解释、整理和汇报材料
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
    Knowledge_Index.md   # 可复用经验索引
    Context_Curation_Prompt.md # 按需上下文整理 prompt
    Sources_Index.md     # 外部资料索引
    System_Manual.md     # 系统详细使用手册
  decisions/             # ADR 决策记录
  worklog/               # 工作日志
  archive/               # 历史归档
    feedback/            # 已处理反馈归档
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
| 1 | active/ | 默认读取 | 当前阶段事实、人工反馈 inbox、当前大任务计划和当前小任务 |
| 2 | human/ | 按需 | 人类给 AI 的理解、规划、疑问、解释、随笔、复盘和汇报材料 |
| 3 | rules/ | Always_Active 默认，其余按需 | 行为规则 |
| 4 | reference/ | 按需 | 背景资料、知识和索引 |
| 5 | decisions/ | 按需 | 决策详情 |
| 6 | worklog/ | 按需 | 工作历史 |
| 7 | archive/ | 仅明确要求时 | 归档内容 |

## 事实源优先级

冲突时按以下顺序判断：

1. 用户当前消息
2. Current_Task.md
3. Task_Plan.md
4. Context.md
5. Feedback_Inbox.md（只作为待整理信号，不作为已确认事实）
6. human/（只作为人工未整理笔记或汇报材料，不作为已确认事实）
7. Decisions_Index.md
8. ADR 文件
9. Knowledge_Index.md
10. worklog
11. archive

## 人工笔记与 Obsidian

标准 profile 会生成 `docs/ai/human/`，用于人类给 AI 上下文系统留下的主观、半结构化材料，包括理解、规划、疑问、解释、整理、随笔、复盘和汇报。它默认不进入 AI 注意力，只在用户要求整理/修改 human 内容、当前任务显式引用 human 材料，或需要追溯人工判断来源时按需读取；需要成为当前事实的内容，应整理到 `active/`、ADR、Knowledge、reference 或 worklog 的权威位置。

`human/Human_Index.md` 是 human 层的可发现索引；`acf human index sync` 会扫描 `Human_Notes.md`、`weekly/*.md` 和 `reports/*.md` 并补齐缺失索引行。工具只做机械索引维护，`Reviewed` / `Extracted` / `Archived` 等语义状态需要人或 AI 在整理后显式标记。

可以把项目 `docs/` 作为 Obsidian vault 根目录，用 `[[双链]]` 连接 `docs/ai/` 和其他项目文档。双链只服务人工查看和编辑；ACF 不解析、不校验、不依赖 Obsidian 双链，CLI 结构化引用仍使用普通 Markdown 路径。

ACF 结构化引用优先使用普通 Markdown 链接，例如 `[reference/System_Manual.md](../reference/System_Manual.md)`。`acf check` 会校验上下文内本地 Markdown 链接和图片链接的文件是否存在，并校验 `.md#anchor` 能匹配目标文件标题；URL 和其他 URI scheme 不做网络校验。需要批量转换时使用 `acf linkify [target] --format markdown --dry-run --json`；需要向指定小节追加确定性链接时使用 `acf link add [target] <file> --heading "## 输入材料" --target reference/X.md --json`。

## 注意力治理

ACF 不追求保存更多上下文，而是维护一个低噪声、高权威、任务相关的默认注意力入口。

- `active/` 只保留当前目标、当前事实、当前任务和下一步。
- 写入当前事实前先判断唯一权威位置；能更新旧表述时，不追加重复事实。
- worklog 记录历史过程，archive 保存历史材料，Feedback_Inbox 和 human 保存待处理或未整理信号；它们默认不作为当前事实。
- 整理事实时优先读取 changed files、`active/`、相关索引和最近 worklog，不默认读取 archive 或全部历史日志。
- writeback draft 和 curation draft 不进入默认读取路径；能引用权威位置时，不复制完整表述。

## 命令行工具

本仓库提供一个无第三方依赖的辅助 CLI：

### 安装到 PATH

`acf` 已经通过 `pyproject.toml` 暴露为标准 console script。Windows 和 WSL/Linux 是两套独立环境：在哪个环境里运行 `acf`，就需要在哪个环境里安装一次。

- 正式用户安装发布版本：`uv tool install ai-context-framework`
- 已安装发布版本后一键更新：交互式、确认没有其他 ACF 进程时可用 `uv tool upgrade ai-context-framework`；Windows 自动化/并行 Writer 环境优先使用 `scripts/update_acf.ps1`
- 安装或更新后刷新 shell PATH：`uv tool update-shell`
- 仓库维护者安装当前源码快照：`uv tool install .`
- 开发安装（仅调试 CLI 修改时使用）：`uv tool install -e .`

#### Windows PowerShell

正式发布版本安装（Windows canonical 路径，已取得仓库/发布包脚本时推荐）：

```powershell
pwsh -NoLogo -NoProfile -File scripts/install_acf.ps1
```

正式发布版本更新：

```powershell
pwsh -NoLogo -NoProfile -File scripts/update_acf.ps1
```

Windows install/update 脚本会在任何全局 ACF tool 进程仍占用 `uv` tool 环境时先 fail-closed，避免 `uv` 已开始替换文件后因句柄占用留下半损坏环境；安装完成后会在 uv tool bin 中生成 canonical `acf.cmd`，让它通过该 tool environment 自己的 Python 执行 `python -m acf`，并删除同目录 uv 生成的 `acf.exe`，避免 Windows `PATHEXT` 让 `.EXE` 抢在 `.CMD` 前面。更新脚本使用未固定版本的 `uv tool install --force --upgrade ai-context-framework`，既能发现最新 PyPI 稳定版，也能修复先前中断造成的缺失包。需要强制重装当前最新稳定版时使用 `-Reinstall`。裸 `uv tool install/upgrade` 仍是底层 bootstrap/debug 路径，但在 Windows 上会重新生成 `acf.exe`，因此自动化和正式 installed-state 应再经过上述脚本 canonicalize。

如果已经取得本仓库源码，也可以使用一键脚本：

```powershell
pwsh -NoLogo -NoProfile -File scripts/install_acf.ps1
pwsh -NoLogo -NoProfile -File scripts/update_acf.ps1
```

开发安装（仅仓库维护或调试安装链路时使用）：

```powershell
uv tool install -e .
uv tool update-shell
```

重新打开 PowerShell 后验证：

```powershell
Get-Command acf
acf --help
acf --version
acf status --json
```

Windows 正式 installed-state 中，`Get-Command acf` 应解析到 uv tool bin 下的 `acf.cmd`；Windows CMD 可用 `where.exe acf` 查看命令位置，同目录不应再存在 `acf.exe`。`acf.cmd` 只是 launcher shim，不复制 ACF 业务逻辑，也不引入 binary signing/certificate 子系统。

#### WSL / Linux / macOS

正式发布版本安装（推荐）：

```bash
uv tool install ai-context-framework
uv tool update-shell
```

正式发布版本更新：

```bash
uv tool upgrade ai-context-framework
uv tool update-shell
```

如果已经取得本仓库源码，也可以使用一键脚本：

```bash
sh scripts/install_acf.sh
sh scripts/update_acf.sh
```

开发安装（仅仓库维护或调试安装链路时使用）：

```bash
uv tool install -e .
uv tool update-shell
```

重新打开 shell，或按 `uv tool update-shell` 的提示刷新 PATH 后验证：

```bash
which acf
acf --help
acf --version
acf status --json
```

如果 WSL 项目目录位于 `/mnt/*` 挂载盘，`uv` 可能提示 hardlink 失败并降级为 copy；这是跨文件系统性能提示，不影响安装。需要消除提示时可设置 `export UV_LINK_MODE=copy`。

如果需要把 CLI 装进当前 Python 环境而不是 `uv tool` 工具目录，也可以使用 `python -m pip install .`。Git URL 只适合临时测试；正式用户应从 PyPI 安装，以便 `uv tool upgrade ai-context-framework` 能从发布源获取新版本。

“任意目录可运行 `acf`”表示命令已进入 PATH；是否能自动找到上下文，取决于当前目录是否位于包含 `docs/ai`、`docs-acf/ai` 或上下文根目录的项目中。

### 常用命令

```bash
acf status
acf init docs/ai
acf init docs/ai-min --profile minimal
acf simplify docs/ai docs/ai-min
acf upgrade --dry-run --json
acf plan init --title "跨项目评测" --goal "完成一轮完整路径验证。"
acf plan add-task --title "验证 init/status/check" --output "命令结果摘要" --next-action "运行命令并记录结果"
acf task start --id T001
acf task done --id T001 --evidence "worklog/daily/YYYY-MM-DD.md"
acf archive current-task --reason "任务已完成"
acf knowledge draft --title "任务拆分经验" --source "worklog/daily/YYYY-MM-DD.md"
acf knowledge apply worklog/knowledge-drafts/YYYY-MM-DD-task.md --allow-similar
acf review stale --json
acf audit context --json
acf doctor --json
acf doctor --fix safe --dry-run --json
acf doctor --report --today YYYY-MM-DD --json
acf doctor --draft-semantic --today YYYY-MM-DD --json
acf doctor --projects ../project-a/docs/ai ../project-b/docs/ai --json
acf curate draft --dry-run --json
acf workstream status --json
acf workstream init --dry-run --json
acf workstream add --id WS002 --title "并行线" --owner "主 agent" --goal "验证并行目标线。" --output "验证记录"
acf workstream add --id WS003 --type Merge --title "合并线" --owner "主 agent" --goal "合并 ReadyToMerge 产物。" --output "合并记录"
acf workstream set WS002 --goal "补充或替换目标。"
acf workstream set WS002 --status Active
acf workstream context WS002
acf workstream scope-add WS002 --write "owned: src/foo.py" --reason "需要修改实现文件。"
acf workstream guard WS002 --files src/foo.py docs/ai/active/workstreams/WS002.md --json
acf workstream dashboard
acf workstream merge-request WS002 --target Context --summary "候选变更摘要" --verification "测试通过"
acf workstream authorization status WS002 --action ready --json
acf workstream authorization approve WS002 --action ready --actor "human-owner" --authority-source "user-authority:conversation" --evidence-ref "conversation:explicit-ready-approval"
acf workstream ready WS002
acf workstream merge-start WS003
acf workstream done WS002 --evidence "worklog/daily/YYYY-MM-DD.md" --merge-resolution merged
acf workstream claim WS002 --read reference/Architecture.md --write "assigned: src/foo.py"
acf workstream note WS002 --section 当前发现 --text "记录一个局部发现。"
acf workstream stage add WS002 --id WS002.1 --title "内部阶段"
acf workstream stage list WS002 --json
acf workstream focus WS002 WS002.1
acf workstream stage done WS002 WS002.1 --evidence "worklog/daily/YYYY-MM-DD.md" --clear-current
acf workstream sync --dry-run --json
acf workstream archive-candidates --json
acf workstream archive-draft --date YYYY-MM-DD --json
acf workstream archive WS002 --reason "reviewed in worklog/archive-drafts/YYYY-MM-DD.md" --json
acf feedback list --status Open --json
acf feedback triage docs/ai F001 --next-action "进入任务计划评估。" --json
acf feedback done docs/ai F001 --result "已整理。" --evidence "active/Task_Plan.md T001" --json
acf feedback archive-candidates --json
acf feedback archive docs/ai F001 --reason "已整理到 active/Task_Plan.md T001" --json
acf plan stage add --id T001.1 --parent T001 --title "任务阶段"
acf plan stage list --json
acf plan stage set --id T001.1 --status Active --next-action "完成阶段"
acf plan stage done --id T001.1 --evidence "worklog/daily/YYYY-MM-DD.md"
acf workstream block WS002 --reason "等待依赖"
acf workstream cancel WS002 --reason "方向取消"
acf workstream list
acf workstream show WS001
acf observer status --json
acf observer snapshot --dry-run --json
acf observer snapshot --json
acf observer history --stream timeline --limit 20 --json
acf observer glossary --json
acf observer narrative-source . --source-path docs/ai/reference/Project_Brief.md --json
acf observer narrative-apply . --source-fingerprint <fingerprint> --source-path docs/ai/reference/Project_Brief.md --input project-narrative.json --json
acf observer narrative . --json
acf observer targets . --json
acf observer target-set . --target-id ws012-writer --mode fixed_workstream --title "WS012 Writer" --automation-ref automation:ws012-writer --workstream WS012 --continuation-task-id WS012 --json
acf observer target-run-start . --target-id ws012-writer --run-id activation-001 --json
acf observer target-run-finish . --target-id ws012-writer --run-id activation-001 --result success --major-outcome "activation completed" --json
acf observer project-overview-set . --decision disabled --reason "Targets are intentionally heterogeneous." --evidence-ref docs/ai/active/Task_Plan.md --authority-fingerprint <fingerprint> --json
acf observer presentation-status . --json
acf observer review-request-add . --target-id ws012-writer --request-id review-route-next --expected-target-revision 0 --reviewed-intent "下一次 Map Review 重新判断主线与分支关系" --scope "target route semantics" --rationale "当前 authority 已改变" --evidence-ref docs/ai/active/Task_Plan.md --json
acf observer presentation-rule-add . --target-id ws012-writer --rule-id route-human-first --expected-target-revision 1 --reviewed-intent "长期展示当前位置、why-now 与下一步理由" --scope "target route cards" --rationale "这是明确的长期展示规则" --evidence-ref docs/ai/reference/System_Manual.md --json
acf observer presentation-rule-withdraw . --target-id ws012-writer --rule-id route-human-first --expected-target-revision 2 --reason "该长期规则已被新 authority 取消" --evidence-ref docs/ai/active/Task_Plan.md --json
acf observer semantic-review-apply . --target-id ws012-writer --review-id map-review-001 --expected-target-revision 3 --source-fingerprint <target-fingerprint> --authority-fingerprint <authority-fingerprint> --authority-reread --decision rebuild --reason "路线语义发生变化" --evidence-ref docs/ai/active/Task_Plan.md --map-relevant-signal "route changed" --presentation-type roadmap --input target-review.json --consume-one-shot review-route-next --json
acf observer transient-patch-apply . --target-id ws012-writer --patch-id inspect-route --expected-target-revision 4 --expected-presentation-revision 2 --presentation-fingerprint <presentation-fingerprint> --reviewed-intent "本次人工检查临时突出路线与运行证据" --scope "presentation only" --rationale "不改变事实，只调整当前 Dashboard 可读性" --evidence-ref user:review --density detailed --emphasize-section route --emphasize-section runs --json
acf observer transient-patch-clear . --target-id ws012-writer --expected-target-revision 5 --expected-presentation-revision 3 --presentation-fingerprint <presentation-fingerprint> --reason "本次人工检查结束" --evidence-ref user:review-complete --json
acf new task --title "实现一个维护任务" --goal "写清当前目标。"
acf new source --title "资料标题" --type "文档" --location "https://example.com" --relation "说明为什么相关。"
acf new reference --title "设计文档标题" --summary "一句话说明。" --body "核心内容。"
acf new rule --title "规则标题" --condition "何时读取。" --purpose "索引用途。" --rule "具体规则。"
acf new feedback --type "需求" --content "待整理反馈。" --source "2026-05-08 user"
acf new human-note --type "想法" --content "人工异步笔记。"
acf human index sync --json
acf human list --status Open --json
acf human mark reports/example.md --status Extracted --extracted-to reference/Example.md
acf new worklog --summary "完成一次上下文维护。"
acf new worklog --summary "补记一次上下文维护。" --append --json
acf new adr --title "记录一个重要决策" --summary "一句话摘要。" --decision "具体决策。"
acf writeback draft --name "session-note" --text "会话结束回写建议。"
acf edit section get active/Context.md --heading "## 当前有效事实" --json
acf edit section append active/Context.md --heading "## 当前开放问题" --text "1. 新问题。"
acf edit table upsert reference/Sources_Index.md --key-column "资料" --key "资料标题" --cell "状态=Useful"
acf check
acf check --strict
acf log status --json
acf log feedback --type Problem --source manual --related-command "workstream add" --text "实际使用反馈。" --json
acf log tail --limit 20 --json
acf log summarize --json
acf log summarize --days 7 --errors-only --json
acf log prune --days 30
acf version show --json
acf version set v0.0.3.34 --dry-run --json
acf status --json
acf new task --title "预览任务" --goal "只预览。" --dry-run --json
```

未安装全局命令时，在本仓库开发环境中也可以使用 `uv run acf ...`。

命令说明：

- `status`：从当前目录向上自动发现上下文，输出项目根、上下文目录、profile、当前任务状态和检查结果。
- `init`：从 `template/` 生成标准或简化上下文目录。
- `init --force-root-agent`：在根入口已存在时重写根薄入口。
- `simplify`：从已有上下文生成只包含核心文件的简化版本，并保留真实 ADR 与 daily worklog，排除占位模板文件。
- `init` / `simplify --force` 在执行 destructive replacement 前会保护当前 `ACF_HOME`（默认 `~/.acf`）：若既有 target 等于、位于或包含该 runtime tree，会以 `acf_home_target_protected` fail-closed，避免删除 continuation、Observer、closeout authorization 与 usage-log state。普通非破坏性 target 行为保持原语义；destructive dogfood/测试应显式使用隔离的临时 `ACF_HOME`。
- `upgrade`：非破坏式补齐新版本上下文结构，包括标准 profile 的 human 层和 `Human_Index.md`、反馈归档目录和 active -> reference 规划依据追溯入口；不自动移动或覆盖 Active 当前任务；自定义旧文档无法识别时会追加 canonical marker 包围的升级说明块。
- `plan init|add-task|set-task|focus|status`、`plan reference list|add|remove` 和 `plan stage list|add|set|done`：维护 `active/Task_Plan.md` 中的大任务、子任务板、`## 规划依据` 和 `## 任务阶段` 表；`plan reference add --path reference/X.md --purpose "用途"` 只记录 reference 路径和一句话用途，可用 `--sync-current-task` 显式同步到 Active `active/Current_Task.md` 的输入材料；Task Stage CLI 只维护任务阶段表，要求 `T001.1` 这类阶段 ID 归属于已存在父任务，不创建 task object 单文件，不自动修改 `active/Current_Task.md`，也不自动联动 Workstream。
- `plan complete`：在子任务完成后将大任务计划标记为 Done。
- `linkify`：把默认范围内安全识别到的本地路径引用转换为可点击 Markdown 链接；默认处理 active、reference、rules、decisions、Worklog_Index 和 Archive_Index，跳过 archive 详情和 daily worklog；`--include-archive` / `--include-worklog-daily` 可显式扩大范围，`--allow-missing` 可允许缺失目标。
- `link add`：向上下文内指定 Markdown 文件的小节追加链接 bullet；`--target-heading` 会生成并校验 Markdown heading anchor，重复链接默认拒绝，`--force` 才允许重复。
- `task start|done|block|clear`：从任务板启动、完成、阻塞或清空当前小任务；`task start` 默认拒绝启动依赖未完成的子任务，除非传入 `--force`。
- `archive current-task|task-plan|list|sync`：归档旧当前任务或旧大任务计划，并更新 archive 索引；归档 current task / task plan 时会按归档文件的新位置重写本地 Markdown 相对链接，并追加 `ACF:ARCHIVE:RECORD` marker；`sync` 从 `archive/tasks`、`archive/plans` 和 `archive/workstreams` 重算 `ACF:ARCHIVE:INDEX-GENERATED` marker 内表格，优先使用归档 record marker 恢复 Task/Plan 归档原因，旧索引首次接入 sync 时需显式 `--init-marker`，旧手写表会保留在 marker 外。
- `decisions sync`：从 `decisions/ADR-*.md` 重算 `ACF:DECISIONS:INDEX-GENERATED` marker 内表格；旧索引首次接入 sync 时需显式 `--init-marker`，命令只替换 marker 内内容，不修改 ADR 正文。
- `knowledge draft|apply|list|show|mark|sync`：生成可审阅 Knowledge 草案，审阅后写入可复用经验索引，并可用 `sync` 从 `reference/knowledge/K*.md` 重算 `ACF:KNOWLEDGE:INDEX-GENERATED` marker 内表格；`apply` 默认拒绝疑似重复条目，可用 `--allow-similar` 显式覆盖；旧索引首次接入 sync 时需显式 `--init-marker`。
- `feedback list|triage|done|reject|archive-candidates|archive`：维护 `active/Feedback_Inbox.md` 的确定性生命周期；`triage/done/reject` 只更新状态和处理结果，不自动转写 Context、Task、ADR 或 Knowledge；`archive-candidates` 只读列出 Done/Rejected 候选，`archive` 只显式移动单条反馈到 archive/feedback/YYYY-MM dot md。
- `human index sync|list|mark`：维护 `human/Human_Index.md`；`index sync` 机械扫描 `Human_Notes.md`、`human/weekly/*.md` 和 `human/reports/*.md` 并补缺失索引行，不删除旧行、不覆盖人工状态；`list` 按状态或类型查看 human 材料；`mark` 按 ID 或路径把条目标记为 `Reviewed`、`Extracted` 或 `Archived` 并可记录整理目标。
- `review stale`：只读检查默认注意力入口是否可能过期，报告 stale candidates，不判断内容真假、不写文件；支持 `--json` 和 `--days`。除了日期型 stale signal，还会机械报告 Done 的非空 `active/Current_Task.md` / `active/Task_Plan.md` 仍被保留时的 `current_task_terminal_retained` / `task_plan_terminal_retained`。JSON 输出包含 `summary.total`、`summary.by_kind`、`summary.by_path`，每个候选包含 `kind`、`signal`、`path`、`reason`、`age_days`、`status` 和 `suggested_action`；`next_actions` 会在 clean 状态或按 stale `kind` 给出机械下一步建议。
- `audit context`：只读检查 active 层上下文污染候选，不判断事实真假、不写文件、不生成 patch、不接入 `check --strict`；MVP 只报告 `active_section_too_long`、`stale_current_task_or_workstream_stage` 和 `terminal_conclusion_not_merged`（ReadyToMerge 待合并或 Done 缺合并结果）。JSON 输出包含 `candidates`、`summary.total`、`summary.by_kind`、`summary.by_path`、`summary.by_severity` 和 `next_actions`。
- `doctor`：面向人和 AI 的上下文健康诊断入口，默认只读并复用 `check` 结果，同时报告 Task_Plan / Current_Task 生命周期漂移、终态 Workstream authority scope 残留、Workstreams / Archive generated index 漂移、Workstream 协议漏 `Merging`、Decisions_Index 摘要截断、Sources_Index 本地文件缺失、active 过厚、根目录探针输出和本地数据副本 hash / missing evidence。attention hygiene 会直接复用 `review stale` 的机械 `current_task_terminal_retained`、`task_plan_terminal_retained`、`context_missing_review_marker` 和 `context_review_stale` signals；这些 finding 是 warning / draft-only，不进入 `check --strict`，也不会自动裁决或改写自然语言事实。支持 `--json`、只读 `--projects`、单项目 `--fix safe|evidence`、`--report`、`--draft-semantic`、`--force`、`--dry-run` 和 `--check-after`。`--fix safe` 只做确定性低风险修复，例如清空无下一任务的 Done 焦点、修正 Current_Task 中明确回写目标行且无额外任务引用的目标 ID、移除终态 Workstream authority `assigned:` scope、同步 Workstreams / Archive generated index 和补齐 Workstream 协议 `Merging`；语义项只进入 report 或 writeback draft，数据 hash 证据只读取项目根内的相对路径。
- `curate draft`：复用 `review stale` 的 stale candidates 生成 `worklog/curation-drafts/YYYY-MM-DD.md` 注意力治理草案；空信号时不创建草案，同名草案已存在时安全拒绝；支持 `--json`、`--dry-run`、`--days` 和 `--name`。
- `workstream init|status|list|dashboard|archive-candidates|archive-draft|archive|sync|show|context|add|reserve|set|block|cancel|merge-request|merge-start|ready|done|claim|scope-add|guard|note|focus|authorization` 和 `workstream stage add|list|done`：显式启用可选 Workstream 层，读取并行目标线索引与详情 metadata，并维护强隔离状态转换、合并请求、完成证据、scope claim/扩权、详情备注、内部阶段焦点和显式归档；`reserve` 是可选的 Git-aware 编号预约入口，只在 primary branch 创建并提交 detail/index，不创建 branch/worktree；原 `add` 行为保持不变；`context WS001` 输出 AI 专属任务入口，`guard` 检查变更文件是否符合当前 Workstream 写入边界，完成或切换状态前优先用 `--files` 显式传入本次修改文件做强验收；`scope-add` 以工具化方式扩展 read/write scope 并写入 Activity Log，`dashboard` 显示冲突、陈旧任务、缺 evidence 和待合并 authority 目标；Workstream 类型为 Task / Merge / Maintenance，Task 不能直接写 authority 文件，Active 类 Workstream 默认禁止重叠 `owned:` 写入，`shared:` 必须指定 merge_owner 或 serial coordination；`archive-candidates` 只读报告 Done / Cancelled Workstream 的归档候选和 `blocked_by`；`archive-draft` 写入 `worklog/archive-drafts/` 供人工或 AI 审阅；`archive WS001 --reason "..."` 只在显式指定单个终态 Workstream 时移动详情、清理 active 索引并写入 `archive/Archive_Index.md`；`sync` 只根据 `active/workstreams/*.md` front matter 更新 `active/Workstreams.md`，不会删除缺详情的旧索引行；Workstream 详情可用 optional `current_stage` 和 `## 阶段` 表记录内部阶段焦点，`stage add/list` 只维护详情文件，`focus` 不更新全局 Current_Task，`stage done` 要求 evidence 且完成当前阶段时需要 `--clear-current`；`merge_targets` 记录候选合并目标。`ready / merge / done / archive` 统一经过用户级 closeout authorization resolver：`authorization policy-set` 记录可按 Workstream id/type/class/action 限定的 durable `auto|manual|deny` policy，`authorization approve` 记录仅对当前 Workstream、单个 action 和当前 material authority fingerprint 有效的人工批准，`authorization revoke` 可显式撤销旧 policy/approval。更窄且更新的 policy 优先，WS-specific manual/deny 可覆盖项目默认 auto；material authority 变化会让旧 approval stale，Activity Log 追加不会。`merge` action 的同一次 deterministic `ReadyToMerge -> Merging` transition 是例外：该 transition 自身写入的 lifecycle status / `当前发现` 不会使既有 merge approval 失效，因此 `merge-start` 与随后 worktree merge 的 resolver 复查可安全复用同一批准；其他 material authority 变化仍会 stale。缺少匹配 authority 时稳定返回 `approval_required`，显式 deny 返回 `denied`；裸 `--human-approved` 仅为兼容参数，不能创建证据或绕过 Gate。authorization ledger 位于用户级 ACF_HOME，不写项目 Git；未知 schema 或语义损坏均 fail-closed。Merging 表示 Merge/Maintenance 正在合并，Done 需要 `--merge-resolution` 写入合并或处置结果；`add --goal` 可在创建时写入详情目标，`set --goal` 可替换已有详情目标，`--write-scope` 必须使用 `TYPE: PATH` 格式，例如 owned: src/foo.py；`upgrade` 和旧项目默认不启用 Workstream。

- `worktree create|attach|verify|list|audit|sync|merge-plan|merge|artifact-plan|artifact-migrate|close|resume`：供 AI 按任务需要调用的可选 Git 生命周期能力。创建 Workstream 不会隐式创建 worktree；`create` 同时支持正式 WS 与 `bugfix/docs/experiment/investigation/maintenance/refactor/release` 非 WS 任务。每次 `merge` 都在临时 integration worktree 中产生和验证候选，primary checkout 只执行路径碰撞保护后的 fast-forward promotion，因此可以保留无关 staged/unstaged/untracked 修改；短时锁、index、路径碰撞和 HEAD 推进会有限等待或自动重规划，稳定冲突留在 integration worktree 并可用 operation ID 恢复。ignored/untracked 结果必须通过 artifact handoff 分类和摘要验证后才能 promotion/close。所有写操作默认只输出计划，显式 `--apply` 后才执行；实现继续禁止自动 stash、reset、clean、rebase、push、`branch -D` 和静默解决冲突。唯一内部例外是 close 已证明 semantic-clean 且只剩 `stat_only_paths` 时，可用 `git worktree remove --force` 作为 raw-Git 兼容桥；它不授权移除真实 dirty worktree。完整说明见 [docs/Worktree_Lifecycle.md](docs/Worktree_Lifecycle.md)。

Worktree lifecycle 的 `clean` 使用只读 **semantic Git clean**：staged、untracked、真实 unstaged diff、rename/delete/type/mode/unmerged/submodule 仍是 dirty；仅普通 tracked unstaged `M` 且 read-only Git diff 证明 index 与规范化 working-tree 内容完全相同时，归入 `stat_only_paths` 而不阻塞 verify/sync/merge/close。诊断统一使用 `GIT_OPTIONAL_LOCKS=0`，不会用 `update-index --refresh` 修改 index。新 reservation 的 `## Workspace` 只持久化稳定 slug 与“local registry/verify/list 为机器绑定权威”的说明，不保存 `mode:none` 或绝对路径；Open reservation/create 的 `next_actions` 会明确提示先执行 `acf workstream set WSxxx --status Active`。
- `continuation init|configure|list|migrate|doctor|coordination status|coordination attempt|coordination challenge|coordination wait|claim|assert-owner|heartbeat|directive add|directive list|directive show|directive adopt|directive resolve|directive supersede|directive withdraw|progress|effect prepare|effect update|effect list|workspace status|workspace intent|workspace adopt|workspace refresh|reconcile|recover|renew|checkpoint|release|pause|resume|prompt|issue`：为外部 AI scheduler 或人工长任务提供有界续跑控制。`init --profile standard|long-running` 可选择时序配置；已有 task 使用 `continuation configure --profile long-running` 原位更新，无需 `init --force`。long-running profile 为 scheduler 60 分钟、lease TTL 180 分钟、renew 45 分钟、heartbeat 建议 10 分钟、stale threshold 25 分钟；这些 timing 只服务 lease liveness，不是 execution-duration target、工作配额或汇报周期。`continuation directive` 提供用户级 live-steering inbox：`add` 写入 requirement / priority_change / constraint / plan_change，并可声明 `lifetime=transient|durable|unspecified`；状态为 pending/adopted/resolved/superseded/withdrawn。resolve 表示完成、withdraw 表示显式取消、supersede 表示同一 active requirement 被新版本替换；durable/transient adopt 需要 durable evidence，持久语义必须先同步到正确 Markdown authority，不能因“读到了文本”就 adopt。当前 session 实际消费过的 directive 必须在 safe control point 明确 disposition，pending authority 始终优先于 stale persisted `next_action`。claim 记录 directive revision/digest，heartbeat/renew 返回 revision/digest change、pending/adopted/active count 和 pressure 摘要；非 Writer owner 可以 add/supersede 用户 authority，但不会因此获得 writer lease/fence/workspace write authority。`continuation doctor` 只机械报告 stale adopted/high-priority pending、adoption evidence 和容量/rollover pressure，不按年龄自动完成。current directive journal 在软 event/byte pressure 时只归档完整 terminal prefix 到 `directives.archive.NNNNNN.json`，pending/adopted 不归档；archive-first/current-second 允许 crash 后 exact duplicate 去重，archive 历史继续可 list/show 和 digest 审计，active authority 自身耗尽容量时仍 fail-closed。新 runner 用 `coordination attempt` 记录 compact current-goal intent：无 owner 时只成为 claim candidate；遇到 fresh owner 时返回 `live_owner_observed`、不自动 challenge，并允许 duplicate scheduler wake 在不改变 task 状态的前提下让行；只有 stale / legacy-unverified owner 才自动 open/join generation-bound challenge。显式 `coordination challenge` 仍可用于独立证据表明需要重新确认 ownership 的场景，但 challenge 本身不授予写权限。stale owner 的 challenge 已形成后，`coordination wait`（别名 `await`）用单次 tool-backed blocking 调用读取持久化 `deadline_at`，等待 `owner_active | owner_released | timeout`，避免依赖模型纯 idle；pending challenge 不是 session-end signal，wait 自身从不授予 ownership。`timeout` 后仍必须立即刷新 physical execution / HEAD / workspace / effect / provenance 并 formal reconcile/recover；若当前 activation 仍存在，recover 后应在同一 activation 继续安全有价值的项目工作。只有通过 `lease_id + generation + fence_token` 的 owner-protected continuation 操作才是 authenticated owner response。`prompt --runner-id <runner>` 将 caller identity 与 lease owner 对照，并通过 `owner_context` 稳定暴露 current owner / verified live other owner / stale-or-unverified / expired / no-owner，同时返回 `directive_context`；旧调用未传 runner-id 时保持保守的 caller-unknown 分类，不武断宣称 duplicate。workspace manifest v3、legacy adoption、task-owned handoff、effect replay protection 与 generation fencing 继续保持既有安全语义。generated prompt 改为 state-conditioned progressive disclosure：always-on 展示目标、默认计划、authority refresh、directive disposition obligation、continuous/hard-stop contract、owner 摘要和当前 relevant action，claim、duplicate、recovery、workspace provenance、effect reconciliation 细节只在对应状态出现时展开。**若 authority refresh 后的默认计划明确要求等待下一次真实外部/项目状态变化，而当前条件仍未满足，则 scheduler wake、coordination attempt 与 claim 都不算“真实状态变化”；此时没有其他安全有价值工作就应在不 claim、不改变 task 状态的前提下结束当前 wake，避免定时任务通过 claim 自己制造进度。** final response、commit/checkpoint/Gate、timing 的既有非停止语义继续保留。详细设计见 [Continuation Control](docs/ai/reference/Continuation_Control_Design.md)。
- fenced owner credential 在命令安全层拒绝高熵 token 时可使用 `ACF_CONTINUATION_FENCE_TOKEN_FILE`：在 `claim/recover` 前指向调用方控制的 temp 文件，ACF 会把新 token 写入该文件并从 JSON 移除明文；后续 owner-protected 命令省略 `--fence-token` 时从同一文件读取。token file 不进入 canonical continuation state，缺失/非法时 fail-closed，release 后由调用方删除。`continuation execution run` 的父 supervisor 可以继续使用该 handle 维持 owner liveness，但被监督 child/descendants 不继承这个环境变量，防止 child 中的普通 ACF 操作或测试意外覆盖父 owner credential；这只做 credential containment，不是通用环境 sandbox。
- `continuation workspace reconcile-handoff` 是 graceful running handoff 后的 ownerless provenance 死锁恢复口：只允许把**已经记录为 task-owned 且仍有 write intent、当前已经 semantic-clean** 的 WIP cleanup 以 durable evidence 显式收口；latest round 必须是 `released_to_running_handoff`，lease 必须 absent，unresolved effect 必须为空，而且指定 cleanup paths 必须精确解释全部 `task_owned_handoff_drift` conflict。若 closeout 同时推进 Git HEAD，还必须用与当前 HEAD 精确相等的 `--accept-head` 显式接受。仍 dirty 的改写、普通 release、active/expired owner、未知 conflict、未接受 HEAD drift 或 effect ambiguity 都 fail-closed。成功只写新的 workspace baseline 与 `last_workspace_reconcile.json` 审计 receipt，不取得 ownership、不执行 recover；随后重新 `doctor` 并正常 claim。
- `continuation coordination wait|await` 是 stale-owner challenge 的确定性 blocking observer，不是 takeover 命令。它只读取一个已持久化 challenge 的终态和 `deadline_at`，本地轮询间隔只影响观察延迟，不改变 challenge 的语义等待窗口；返回 `owner_active` 时让行、`owner_released` 时重新 doctor/正常 claim、`timeout` 时刷新全部 recovery evidence 后 formal reconcile/recover。该命令始终返回 `ownership_granted=false`；pending challenge 不能被当作当前 activation 的结束理由，也不要求模型在无工具活动下“空等”。

long-running Writer 不把“等待 fresh opportunity”当成 mission-open 时的默认策略。若一条 lane 暂时 blocked，Agent 必须先主动审计 blocker/root-cause diagnosis、adjacent gap implementation、validation/evidence、reusable contract hardening、accessible-target dogfood、release preparation 与 low-side-effect diagnostics 等替代工作；anti-busywork 只禁止在输入、环境、证据和策略都未变化时机械重复同一失败动作。默认以 overall mission / 当前 PLAN stage 为 work unit，不为单个 bug、实验、test、checkpoint 或 release Gate 拆新 Workstream；自然 checkpoint 后 refresh authority 并继续。只有当前安全增量替代项均经审计无价值，或命中正式 hard stop，execution session 才可结束。控制面检查必须与 evidence-backed risk 成比例；active lease、历史异常 generation、task-owned dirty、scheduler wake、checkpoint/test/commit/Gate 或单 lane blocked 都不是独立 stop signal。wall-clock 与 liveness timing 只作诊断，不是固定执行预算。genuine safe session end 可用 authenticated `continuation release --handoff` 释放 owner/round 同时保持 long-lived state=`running`，避免人为遗留 stale owner；verified-live physical execution 仍必须 yield 且禁止 duplicate。`continuation prompt --json` 的 `execution_observability` 分离 bootstrap/control-plane、project work、physical execution、graceful handoff、abnormal/incomplete termination 与 recovery overhead，telemetry 不形成 timing policy。
- continuation compact state 中历史型摘要 `completed / evidence_refs / verification` 使用最多 64 项的 rolling window；超过容量时保留最近项，不会再把 `state.json` 写到自己无法读取的状态。`constraints / open_questions / plan_refs` 继续严格限 64 项，超限仍 fail-closed，避免容量管理静默丢失仍有效的安全/计划语义。`constraints` 与 `open_questions` 是当前高显著语义提示而不是 append-only 历史：当 newer authority 明确推翻旧 constraint 或关闭旧 question 时，authenticated owner 可在 `continuation checkpoint` 中使用 exact-match `--supersede-constraint` / `--resolve-open-question`，并同时提供 durable `--evidence-ref`；不存在的条目、缺少证据或模糊匹配均拒绝，避免旧状态与新 `next_action` 并列产生矛盾。旧版本遗留的 current-schema history-list overflow 会在读取时惰性压缩，因此升级后 `prompt/doctor/reconcile` 可先恢复工作，再由下一次合法 state write 持久化 compact 结果；round/effect/coordination 等独立历史账本不受影响。

effect history 采用 replay-safe rollover：current `effects.json` 到达记录/字节边界时，只把完整 terminal `completed|failed` records 移入 bounded `effects.archive.NNNNNN.json` segments；所有 archive 继续参与 `logical_key/kind/external_id` 去重检查，所以旧 effect 不会因为容量滚动而被重放。任何 `prepared|active|unknown` record 都留在 current journal；如果 unresolved records 自身已经耗尽容量，ACF 继续 fail-closed，而不是删除或覆盖它们。

`continuation prompt --json` 同时返回稳定的 `identity`、`current`、`owner_context`、`directive_context`、`execution_policy`、`project_context`、`scheduler_wrapper_contract` 和当前 `next_actions`。`directive_context` 给出 global revision、pending-set digest、pending/adopted/active count、latest pending、current-journal pressure、archive count/history digest 和按优先级排序的 pending 摘要；存在 pending 时 `authority_refresh_required=true`。`execution_policy` 在既有 goal-directed continuous / hard-stop contract 上包含 `pending_user_directive_supersedes_persisted_next_action=true`、`consumed_user_directive_requires_disposition=true`、`next_action_is_default_execution_plan=true`、`next_action_requires_authority_refresh=true`、`active_lease_requires_liveness_verification=true`、`verified_duplicate_owner_may_end_duplicate_wake=true`、`duplicate_wake_exit_is_task_stop=false`、`stale_owner_requires_recovery=true` 与 `contender_must_create_busywork=false`，并继续保留 `next_action_is_work_quota=false`、`final_response_is_terminal=true` 等既有字段；条件等待计划另外暴露 `claim_requires_present_safe_useful_work=true`、`control_plane_activity_satisfies_wait_condition=false`、`no_useful_work_may_end_wake_without_claim=true`，明确控制面 bookkeeping 不能自证等待条件已经满足。`scheduler_wrapper_contract.bootstrap_policy=sufficient_high_salience`：wrapper 应完整携带 exact existing workspace / project access tool mode / stable ACF upgrade-adaptation / authority refresh / execute-generated-plan / owner disclosure / project constraints / final-response contract，但不得复制 generic contention/recovery/workspace/effect 状态机。

长期自治字段同时包含 `mission_open_requires_active_alternative_search=true`、`blocked_lane_should_switch_to_safe_alternative=true`、`anti_busywork_scope=unchanged_failed_action_only`、`no_useful_work_end_requires_alternative_audit=true`、`prefer_mission_stage_over_microtask_fragmentation=true` 与 `checkpoint_requires_authority_refresh_and_continue=true`。P1.5 `automation_prompt_execution_contract` 的 `writer_continuous_execution` / Writer wrapper / runtime-generated prompt 也暴露同一语义，使 future Scheduled Agent 在不复制 generic state machine 的前提下稳定执行“主动找替代工作、checkpoint 后继续、无增量结论需 alternative audit”的 contract。

Observer Agent-first P1.5/S2 继续通过 `automation_prompt_execution_contract` 保持 Writer 与 Production Observer 的角色边界，但 **Production Observer 已不再以 Target Registry、semantic-review、Map Review、`primary_visualization` 或固定 renderer 作为页面生成前置**。Writer Scheduled Task 的静态 wrapper 仍负责 sufficient high-salience bootstrap 和命名的 project/task extension slot；动态 owner/generation/directive/current-plan/checkpoint/release/exit 仍只由每轮 `acf continuation prompt + execution_policy` 负责。Production Observer wrapper 保留 `read broad / write narrow / control none`、existing-checkout、anti-masking、truthful run history、human-first-but-detailed 与 project/target extension slot，并明确允许 Agent 从当前授权的一手来源自主选择展示对象、直接维护 Observer-owned HTML/CSS/SVG/JS。Target Registry 只是可选导航提示，旧 semantic-review / Map Review / presentation lifecycle / deterministic renderer 只作为兼容 helper；缺少这些 helper 不得阻止仍可由合法来源完成的观察。旧 helper 被显式调用时仍保留原有 fingerprint、evidence、optimistic concurrency 与 fail-closed 规则，也不得覆盖 Agent-owned 稳定入口。Agent-owned 稳定入口更新失败时必须保留 last-good 可读版本，失败或部分来源缺失要保持 fail-visible，freshness 也不能因为旧页面仍可打开而被伪装为成功刷新。`acf observer status --json` 与 `acf continuation prompt --json` 暴露同一 Agent-first family contract，供 wrapper、文档和 regression tests 做一致性检查。

Agent-owned 文本稳定入口还要求在晋升前以 strict UTF-8 回读候选并拒绝 Unicode replacement character（U+FFFD）；失败继续走既有 last-good 更新失败策略。该规则只保护文本完整性，不引入统一 renderer 或页面 schema。

旧 Observer V2 P2 的 semantic-review / one-shot / durable-rule runtime 继续保留为**可选 legacy derived-state helper**。`presentation-status`、`review-request-add`、`semantic-review-apply`、`presentation-rule-*` 仍可在明确需要兼容旧状态时使用，并继续要求 exact revision/fingerprint/evidence、foreign-project non-interference 与 fail-closed concurrency；但新 Agent-authored 页面不需要先创建或消费这些状态，也不需要为了页面更新强制执行 Map Review。

旧 Observer V2 P3 的 `transient_patch` / deterministic re-render 同样只服务 legacy ACF-derived Dashboard，并继续保留 exact target/presentation revision + fingerprint 的并发保护。**“禁止直接编辑 `dashboard.html`”只约束这条 legacy derived-state surface，不约束 Agent 在明确 Observer-owned 输出目录维护自己的页面。** Agent-first 输出应维护独立稳定入口，legacy snapshot/render 不得覆盖该入口。

`continuation workspace reclassify` 是 active fenced owner 的窄恢复工具，不是事后泛化的 `workspace intent`：durable writer 已结束后，如果某个启动前漏报的真实产出当前被分类为 `unexpected_nonoverlap`，只有在来源已审阅且提供 durable `--evidence-ref` 与 `--reason` 时，才能显式用 `--task-owned <path>` 纳入任务，或用 `--baseline-external <path>` 继续保护为外部修改。task-owned reclassification 仍受 bound Workstream direct write scope 约束；已有 conflict、非 unexpected 路径、重叠分类、scope 越界、证据缺失或来源不确定都继续 fail-closed。若绑定 Workstream 已经由 ACF 正式归档、active detail 因该 lifecycle 动作不存在，recovery 可从 schema-valid 的 `archive/workstreams/WSxxx.md` 恢复原 direct scope，并仅额外允许 `active/Workstreams.md`、原 active detail、`archive/Archive_Index.md` 和 archived detail 四个确定性归档 authority 路径；这不恢复 Active 状态，也不扩大普通 Task authority。

普通 `baseline_external` 默认仍不可 stage/commit。唯一窄例外是当前 authenticated runner 刚通过 `acf workstream scope-add|merge-request|ready|merge-start|done` 为绑定 Workstream 生成 `docs/ai/active/Workstreams.md` 与该 Workstream detail 时，允许在 lifecycle/merge 边界审阅 exact diff 与 durable ACF command evidence 后，把**仅这两个确定性 control-plane 文件**形成独立 checkpoint。它不扩展普通 Task authority write_scope，也不允许第三个 baseline/external path 混入提交。

ownerless effect recovery 有三条明确、互斥且 fail-closed 的收口路径：已经取得 durable external id 的 effect 必须继续用 `--effect-external-id` 与外部终态证据做 identity-matched reconciliation；同一 stale generation 若有多个此类 externally-proven terminal effects，可按相同顺序重复 `--effect-key`、`--effect-terminal-status`、`--effect-external-id`，由一个 receipt 原子收口全部 assertions，并共享本次 `--effect-evidence-ref` 集合。若 write-ahead `effect prepare` 后能够由外部 authority 明确证明 submit **从未启动**，则可在 owner-ended/forfeiture 条件下使用 `reconcile --effect-not-started --effect-terminal-status failed --effect-evidence-ref <ref>`；该 no-start 分支仍只接受单个 `prepared`、`external_id=null` 记录，不能声明 completed，也不能用于 active/unknown effect。若已经实际执行了**本地确定性动作**，但记录仍为 `prepared|active + external_id=null`，且 durable local artifact/state/hash 等 authority evidence 已明确证明 terminal 结果，则可显式使用 `--effect-local-terminal`（可一次对多个 effect 使用同一 receipt）；它不和 `--effect-not-started` 或 `--effect-external-id` 混用，`unknown` effect、已有 external id 或证据不足仍继续拒绝。

`observer status|snapshot|interpret|glossary-set|glossary|history` 提供项目级 Global Observer。一个项目只有一个用户级 Observer runtime namespace；primary checkout 与 ACF 注册 worktree 统一进入观察域。Observer 可以广泛读取 Git、Workstream、continuation、计划和 evidence，但只把结构化 current/history/self-health/semantic/glossary 与自包含 `dashboard.html` 写入用户级 ACF_HOME，不修改 Writer 项目文件，也不参与 continuation ownership。candidate/dogfood 若使用临时 `ACF_HOME` 隔离 Observer writable runtime、但仍需读取真实 stable continuation，可设置只读 `ACF_OBSERVER_CONTINUATION_READ_HOME=<existing absolute canonical home>`；它只影响 Observer continuation reads，Target Registry/presentation/snapshot/dashboard 仍写当前 `ACF_HOME`，非法路径 fail-visible 且不会被创建。`snapshot --dry-run` 只验证；`snapshot` 使用稳定重读、一致性 fingerprint、credential-like 值过滤、轻量锁和原子替换更新状态并生成可直接 `file://` 打开的静态 Dashboard。canonical structured state/history 始终保留 UTC 时间戳；Dashboard 的“最后观察”、Meaningful Timeline 等人类可见时间统一显示为北京时间 `UTC+08:00`。在 registry-managed 项目中，primary active/archive lifecycle 是 Workstream project-level authority；只有 registry state=`active` 的 bound Workstream worktree 才能作为当前专属 source，其他 registered worktree 中的历史副本只保留诊断/证据价值，不能复活已归档 Workstream。meaningful history 默认永久保留，只做无损 rotation/index；`interpret` 必须绑定当前 `source_fingerprint`，CLI 负责 canonical identity、confidence、provenance、版本历史与 stale-cache fail-closed；没有明确分母时不伪造进度百分比。

`acf continuation list [<worktree>] --json` 只读展示当前 ACF_HOME 中的 continuation identity、`task_id/workstream_id`、timing profile、每个 state 文件的 schema 与 `current / migration_available / blocked` 兼容状态；`--all-projects` 可扫描全部 path-hash namespace。已知 legacy workspace schema 使用 `acf continuation migrate ... --dry-run --json` 先生成迁移计划，并在**没有 lease record** 时显式 `--apply --reason ...`；迁移只改已声明可兼容的 state 文件并写 `last_migration.json` receipt，round/effect/coordination/reconcile/recovery 等历史文件用 byte digest 证明未被改写。未知或未来 schema 不自动猜测，继续 fail-closed；外部 scheduler 不得手工编辑 `~/.acf` JSON。

### Workstream 编号预约与可选 Worktree

```powershell
acf workstream reserve --title "任务" --slug task-slug --owner codex --apply --json
acf worktree create --workstream WS005 --apply --json
acf worktree verify --workstream WS005 --json
```

第一条命令只预约并提交 WS 编号；第二条只有在 AI 判断需要隔离环境时才调用。未配置或未调用 `acf worktree` 的项目继续使用原有 Workstream 和上下文逻辑。

`reserve --apply` 不要求 primary checkout 完全 clean：与 reservation detail/index 无关的 staged、unstaged、untracked 修改会被保留；reservation 路径自身或父子路径发生冲突时才会 fail-closed。

### Workstream guard 模式

`acf workstream guard` 检查的是“变更文件是否符合当前 Workstream 的写入范围”，不是默认独占整个工作区。多个 agent 或多个 Workstream 在同一仓库并行时，完成、ready、done 或切换状态前，优先显式传入本次要验收的文件集：

```bash
acf workstream guard WS001 --files src/foo.py docs/ai/active/workstreams/WS001.md --json
```

| 场景 | 推荐命令 | 语义 |
|---|---|---|
| 本次变更文件明确 | `acf workstream guard WS001 --files path1 path2 --json` | 权威文件集强验收；失败表示这些文件越过当前 Workstream scope。 |
| 单个文件验收 | `acf workstream guard WS001 --file path --json` | `--files` 的单文件形式，可重复传入。 |
| 快速查看当前 git diff | `acf workstream guard WS001 --from-git --json` 或裸 `guard` | 读取 git diff；若存在其他 Workstream 或未归属 dirty files，结果不能直接作为完成证据。 |
| 旧式整工作区排他检查 | `acf workstream guard WS001 --workspace --strict-workspace --json` | 要求整个工作区没有无关改动；只适合单线或需要强制清空工作区的场景。 |
| 禁止 shared 写入 | `acf workstream guard WS001 --files path --owned-only --json` | shared scope 也会失败，用于严格 ownership 验收。 |

只有显式文件集模式可作为完成或切换状态的强验收证据；裸 guard 和 `--from-git` 适合发现当前工作区风险，不应在存在并行 dirty files 时替代 `--files`。
- `new task`：生成或重置 `active/Current_Task.md`，默认拒绝覆盖 Active 任务，除非传入 `--force`。
- `new source`：向 `reference/Sources_Index.md` 添加或更新资料索引行，默认拒绝重复资料标题，除非传入 `--force`。
- `new reference`：在 `reference/` 下创建长期按需读取的 Markdown 文档；默认使用标题 slug 生成文件名，也可用 `--file reference/X.md` 指定路径；拒绝写到 context 外或 `reference/knowledge/` 托管目录。
- `new rule`：在 `rules/` 下创建按需规则文件，并更新 `rules/Rules_Index.md` 的按需规则表；minimal context 首次使用时会补一个轻量 Rules_Index，不把 whole context 升级为 standard。
- `new feedback`：向 `active/Feedback_Inbox.md` 添加反馈行，自动分配下一个 `Fxxx`，默认状态为 Open，默认来源包含当天日期；重复 ID 需传入 `--force` 才能覆盖。
- `new human-note`：向标准 profile 的 `human/Human_Notes.md` Inbox 添加人工异步笔记行，自动分配下一个 `Hxxx`，并同步更新 `human/Human_Index.md`；minimal context 没有 human 层时会拒绝，建议使用 `new feedback` 或先升级为 standard。
- `new worklog`：按日期生成 daily worklog，并更新 `worklog/Worklog_Index.md`；同日已有记录且需要补记时使用 `--append`，需要重建时使用 `--force`，二者不能混用。
- `new adr`：生成下一个 ADR 文件，并更新 `reference/Decisions_Index.md`。
- `writeback draft`：把不能安全直接落盘的会话结束回写建议保存为注意力治理草案；可确定的任务、计划、worklog、Knowledge 或归档变化应优先写入对应文件或草案。
- `edit section get|replace|append`：读取、替换或追加指定 Markdown 标题下的 section body。
- `edit table upsert`：按 key column 更新或追加 Markdown 表格行。
- `check`：检查目录结构、必需文件、乱码、空文件、内部引用、human index 路径、状态枚举、索引一致性、任务板、任务阶段注册、archive、Knowledge 和显式启用的 Workstream；Workstream 检查包含 optional `current_stage` 与 `## 阶段` 表一致性、strict 下 Done 阶段 evidence、Workstreams 索引与详情 front matter 一致性、Task authority 写入门禁、Active 类 Workstream 写入冲突、`shared:` merge owner/serial coordination 要求和 `merge_targets` 合并请求要求；没有 `active/Workstreams.md` 时不触发 Workstream 检查。
- `log enable|disable|status|tail|summarize|projects|feedback|prune`：管理本地使用状态日志，默认开启以便开发调试收集反馈，可用 `log disable` 按项目关闭；`log projects --scan-root <path> --json` 可只读盘点全局日志中的项目并匹配磁盘上的 context root；普通 usage event 不记录正文，显式 `log feedback --text/--input` 才记录人工反馈正文。
- `version show|set`：查看或一键更新 CLI、包配置和本地元数据版本号。

`check`、`new ...` 和 `writeback draft` 可以省略上下文路径；省略时 CLI 会从当前目录向上查找 `docs/ai`、`docs-acf/ai` 或上下文根目录。显式传入路径时，以显式路径为准。

`status`、`check`、`review stale`、`audit context`、`doctor`、`feedback list|archive-candidates`、`workstream status|list|archive-candidates|show` 和 `edit section get` 支持 `--json` 输出。`archive-draft`、`archive`、`doctor --fix safe|evidence`、`doctor --report`、`doctor --draft-semantic`、`feedback triage|done|reject|archive`、`curate draft` 和其他写命令支持 `--json`、`--dry-run`、`--check-after`，并会输出 changed files；`--dry-run` 只验证和预览，不落盘。

`edit` 命令只操作上下文根目录内已有的 `.md` 文件，拒绝路径穿越和非 Markdown 目标。它提供的是 section/table 级确定性编辑原语，不做语义判断，也不是通用 Markdown 编辑器。

PowerShell 中反引号是转义字符。写入包含 Markdown 反引号或多行正文时，优先使用 `--input <file>`，避免命令行字符串被 shell 改写。

`log` 命令默认开启并写入用户级全局目录 `%USERPROFILE%\.acf\projects\<project-id>\`（Windows）或 `~/.acf/projects/<project-id>/`（macOS/Linux），也可通过 `ACF_HOME` 指定根目录。自动 usage event 不写入项目 `worklog/`，也不记录 `--text` 正文、stdin 内容、Markdown diff 或完整 stdout/stderr；事件只保存命令元数据、结果、相对路径、changed files，并保存本机可解释的 `project_root` / `context_root` 绝对路径用于用户自己的审计。需要保存实际使用反馈时，显式运行 `acf log feedback --text ...` 或 `--input <file>`，该命令会把反馈正文作为 `event_kind=feedback` 事件写入同一日志。`acf log projects --json` 只读汇总全局日志，`--scan-root` 可把旧日志 project id 映射到真实 context root，`--log-root` 可读取测试或备份日志目录。日志写入带用户级锁，配置和 prune 重写使用原子替换；自动日志写入失败不会改变原命令退出码。

JSON 输出包含稳定字段：`schema_version`、`ok`、`error_code`、`next_actions`。检查失败时 `error_code` 为 `check_failed`，`next_actions` 给出 AI 可直接读取的后续动作。

AI 调用 `new worklog` 的推荐模式：

| 目标状态 | 推荐命令 | 结果 |
|---|---|---|
| 不确定是否已有今日 worklog | `acf new worklog --summary "..." --dry-run --json` | 根据 `error_code` 判断下一步 |
| 今日 worklog 不存在 | `acf new worklog --summary "..." --json` | 创建 |
| 今日 worklog 已存在，想补记 | `acf new worklog --summary "..." --append --json` | 追加到稳定 anchor |
| 今日 worklog 已存在，想重建 | `acf new worklog --summary "..." --force --json` | 替换 |
| anchor 缺失 | 不自动修复 | 返回 `ANCHOR_NOT_FOUND` |

`new worklog --append` 的 JSON 面向 AI 稳定解析：`target` 和 `changed_files` 使用 repo-relative POSIX slash 路径；成功输出包含结构化 `warnings` 数组；`insert_after_line` 是 1-based 行号；`--dry-run --json` 不写文件；append 不是幂等操作，每运行一次都会新增一段内容。目标已存在但未传 `--append` 或 `--force` 时，`error_code=TARGET_EXISTS_APPEND_REQUIRED`；`--append --force` 返回 `APPEND_FORCE_CONFLICT`；anchor 缺失返回 `ANCHOR_NOT_FOUND`。

退出码和错误分类：

- `0`：成功。
- `1`：检查失败，`error_code=check_failed`。
- `2`：输入错误，`error_code=input_error`。
- `3`：安全拒绝，例如重复写入或需要 `--force`，`error_code=safety_refused`。
- `70`：非预期运行时错误，`error_code=runtime_error`。

`check` 默认关注结构完整度；`--strict` 适合检查已投入使用的项目上下文，会把占位符残留视为错误。

### 旧版本上下文升级

旧项目升级到当前模板结构时，先预览再应用：

```bash
acf status --json
acf upgrade --plan --json
acf upgrade --dry-run --json
acf upgrade --check-after --json
acf check --strict --json
```

`upgrade --plan --json` 是只读升级评估：不写项目文件、不写 usage log、不获取写锁，输出 `readiness`、`risk_summary`、`findings`、`structural_changes`、`manual_actions` 和 `recommended_commands`。它把“可由 upgrade 补齐的结构问题”和“占位符、断链、Workstream lifecycle 等语义债务”分开，帮助 agent 判断是否可以先做结构升级。

`upgrade` 只补齐当前 schema 缺失的 `active/Task_Plan.md`、标准 profile 的 human 层（含 `human/Human_Index.md`）、archive、archive/feedback 和 Knowledge 文件/目录，并为旧 `active/Task_Plan.md` 补 `## 规划依据` 结构、为 Active `active/Current_Task.md` 的 `## 输入材料` 保守追加规划依据提示；它不移动旧内容、不自动归档任务、不覆盖 Active `active/Current_Task.md`，也不自动判断哪些 reference 是正确依据。`--json` 输出包含 `detected_features`、`planned_changes`、`skipped_changes` 和 `changed_files`，用于审查升级原因、预期写入和已跳过项。如果旧任务或旧计划需要归档，升级后再显式运行 `acf archive current-task` 或 `acf archive task-plan`。对高度自定义的旧入口文档，`upgrade` 会追加 `ACF:UPGRADE:NOTES` marker 块而不是强行重排原文；旧 `ACF:UPGRADE-NOTES` marker 保持兼容并在可管理文档中迁移。

模板占位符统一使用 `【ACF:KEY|提示】`。Markdown 表格单元格里使用无提示形式 `【ACF:KEY】`，避免 `|` 破坏表格。机器维护块统一使用 `<!-- ACF:<DOMAIN>:<PURPOSE>:START --> ... END -->`，例如 `ACF:UPGRADE:NOTES`、`ACF:ARCHIVE:RECORD` 和 `ACF:WORKSTREAM:ARCHIVE-RECORD`；旧 marker 仍兼容，`check` 会给出 future warning。

如果全局 `acf` 未安装，可在本仓库源码环境中对其他项目运行：

```bash
uv run --project path/to/ai-context-framework acf upgrade --plan --json
uv run --project path/to/ai-context-framework acf upgrade --dry-run --json
```

## 维护与验证

修改模板或 CLI 后运行：

```bash
uv run acf check template
uv run acf check --strict
uv run python -m unittest
```

发布前可额外运行本地最小 smoke runner：

```bash
uv run python scripts/minimal_smoke.py --acf uv run acf
```

该脚本只使用隔离临时目录和 CLI JSON 输出，覆盖 `init -> nested status/check`、`new worklog create/append/error_code` 和 Workstream 最小 happy path。它不做真实项目批量评测、漂移样本诊断或复杂 upgrade 审查。

发布前完整验收（包含 wheel/sdist 构建、隔离安装和 console script smoke）：

```bash
uv run python scripts/release_check.py --mode full
```

只验证发布制品安装链路：

```bash
uv run python scripts/release_check.py --mode package
```

修改 `template/`、默认上下文结构、打包清单或 `acf upgrade` 行为时，还必须评估旧版本上下文升级兼容性：新增结构同步到 init 文件清单、upgrade 补齐清单和 data-files，并用 init/upgrade 测试覆盖旧项目可非破坏式升级。快速升级兼容矩阵随单元测试运行；发布前可运行完整矩阵：

```bash
uv run python scripts/upgrade_matrix.py --mode full --acf uv run acf
```

自动化边界和后续路线见 `docs/Automation.md`。
