本文件记录本仓库 AI context framework 的维护手册摘要。

完整产品手册以仓库模板目录中的 System_Manual 为源；本文件只记录 dogfooding 实例中的项目内维护要点。

---

## 当前上下文层级

1. [active/Context.md](../active/Context.md)：当前阶段事实。
2. [active/Feedback_Inbox.md](../active/Feedback_Inbox.md)：人工临时反馈、问题、需求和计划碎片。
3. [active/Task_Plan.md](../active/Task_Plan.md)：当前大任务计划、子任务板和 `## 规划依据`。
4. [active/Current_Task.md](../active/Current_Task.md)：当前具体任务，`## 输入材料` 必须列出当前任务所需 active 文件和相关 reference 规划依据。
5. [active/Workstreams.md](../active/Workstreams.md)：全局并行目标线摘要。默认只读索引行，不读取任何 Workstream 详情；只有显式选择后才运行 `acf status --workstream WSxxx` 和 `acf workstream context WSxxx`。
6. `human/`：人类给 AI 的理解、规划、疑问、解释、随笔、复盘和汇报材料，默认不读取，只有显式整理 human 内容或追溯人工判断时按需读取。
7. `rules/`：默认和按需规则。
8. `reference/`：长期背景、架构、技术环境、决策和 Knowledge 索引。
9. `worklog/`：历史工作记录。
10. `archive/`：旧任务和旧计划归档。

顶层产品边界和长期设计以 [reference/ACF_Top_Level_Design.md](ACF_Top_Level_Design.md) 为准；阶段路线和近期优先级以 [reference/Product_Roadmap.md](Product_Roadmap.md) 为准。新增对象、规则、CLI 命令、模板结构或 upgrade 行为前，应先确认它属于 `check`、`audit`、`sync`、`draft`、`upgrade` 或普通维护命令中的哪一层。

Workstream 归档生命周期以 [reference/Workstream_Lifecycle_Archive_Design.md](Workstream_Lifecycle_Archive_Design.md) 为准。当前提供 `workstream archive-candidates`、`workstream archive-draft` 和显式 `workstream archive` 闭环；`workstream sync` 和 `upgrade` 都不自动归档 Done / Cancelled Workstream。

Doctor / Reconcile 诊断与安全修复边界以 [reference/Doctor_Reconcile_Design.md](Doctor_Reconcile_Design.md) 为准。`doctor` 不是事实裁决器；它先报告机械漂移和证据信号，再只对低歧义项执行安全修复。

Knowledge、ADR 和 Archive sync 的 generated marker 契约以 [reference/Generated_Marker_Sync_Design.md](Generated_Marker_Sync_Design.md) 为准。修改 sync 前必须保护 marker 外人工内容，并明确缺详情、重复 marker、不成对 marker 和删除策略。

---

## Context 审阅标记

[active/Context.md](../active/Context.md) 使用文件级审阅标记：

```markdown
## 审阅标记

- Last reviewed: YYYY-MM-DD
- Review scope: 文件级；确认当前目标、当前事实、约束和开放问题仍适合作为默认注意力入口。
```

`acf review stale` 会识别 `Last reviewed` / `上次审阅` / `最近审阅` 附近的 ISO 日期。该标记不要求条目级事实 ID，也不表示 CLI 已判断每条事实真假。

---

## 安装与入口

`acf` 已通过 `pyproject.toml` 暴露为标准 console script。真实项目中应使用非 editable 的稳定安装；本仓库开发时优先使用 `uv run acf ...` 或 `uv run python acf.py ...`。

常见安装方式：

- 正式发布版本安装：`uv tool install ai-context-framework`
- 正式发布版本更新：`uv tool upgrade ai-context-framework`
- 安装或更新后刷新 shell PATH：`uv tool update-shell`
- 仓库维护者安装当前源码快照：`uv tool install .`
- 调试 CLI 改动或安装链路时使用 editable 安装：`uv tool install -e .`
- 已取得源码时可运行 `pwsh -NoLogo -NoProfile -File scripts/install_acf.ps1` 或 `sh scripts/install_acf.sh`。

如果需要把 CLI 装进当前 Python 环境而不是 `uv tool` 工具目录，可以使用 `python -m pip install .`。不要把全局 `acf` 长期 editable install 指向开发工作区；只有调试安装链路或 CLI 改动时才临时使用 editable。正式用户应从 PyPI 安装，Git URL 只适合临时测试。

---

## 常用维护命令

- `uv run acf status --json`：默认返回 `GlobalOnly`，只披露全局文件指针和 Workstream 摘要。
- `uv run acf status --workstream WS001 --json`：显式选择一个 Workstream，只返回 pointer-only 入口。
- `uv run acf next --workstream WS001 --json`：显式选择后的低风险下一入口。
- `uv run acf upgrade docs/ai --plan --json`
- `uv run acf upgrade docs/ai --dry-run --json`
- 通用升级形式：`acf upgrade [target]`
- `uv run acf check --strict`
- `uv run acf linkify docs/ai --format markdown --dry-run --json`
- `uv run acf link add docs/ai active/Current_Task.md --heading "## 输入材料" --target reference/System_Manual.md --target-heading "Markdown 链接与人工导航" --json`
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
- `uv run acf workstream archive-draft docs/ai --date YYYY-MM-DD --json`
- `uv run acf workstream archive WS001 docs/ai --reason "reviewed in worklog/archive-drafts/YYYY-MM-DD draft" --json`
- `uv run acf plan status docs/ai --json`
- `uv run acf plan stage add docs/ai --id T001.1 --parent T001 --title "任务阶段" --json`
- `uv run acf plan stage list docs/ai --json`
- `uv run acf plan stage set docs/ai --id T001.1 --status Active --next-action "完成阶段" --json`
- `uv run acf plan stage done docs/ai --id T001.1 --evidence "worklog/daily/YYYY-MM-DD.md" --json`
- `uv run acf review stale docs/ai --json`
- `uv run acf audit context docs/ai --json`
- `uv run acf doctor docs/ai --json`
- `uv run acf doctor docs/ai --fix safe --dry-run --json`
- `uv run acf doctor docs/ai --report --today YYYY-MM-DD --json`
- `uv run acf doctor docs/ai --draft-semantic --today YYYY-MM-DD --json`
- `uv run acf doctor --projects docs/ai ../other-project/docs/ai --json`
- `uv run acf curate draft docs/ai --dry-run --json`
- 需要整理、归纳、精简上下文时，按需读取 [reference/Context_Curation_Prompt.md](Context_Curation_Prompt.md)；默认产物是整理建议，不是文件修改。
- `uv run acf log projects --scan-root E:\Codes --json`
- `uv run acf log feedback docs/ai --type Problem --source manual --text "实际使用反馈。" --json`
- `uv run acf log summarize --days 7 --json`
- `uv run acf new worklog docs/ai --summary "补记一次上下文维护。" --append --dry-run --json`
- `uv run acf version show --json`
- `uv run acf version set vX.Y.Z --dry-run --json`
- `uv run python scripts/upgrade_matrix.py --mode quick`
- `uv run python scripts/upgrade_matrix.py --mode full --acf uv run acf`

Workstream 详情可用 optional `current_stage` 和 `## 阶段` 表记录内部阶段焦点；`workstream stage add/list` 只维护详情文件阶段表，`workstream focus` 只切换详情文件内的 `current_stage` 和目标阶段 Active 状态，`workstream stage done` 要求 evidence，完成当前阶段时需要 `--clear-current`，不会自动激活下一阶段或更新全局 [../active/Current_Task.md](../active/Current_Task.md)。`merge_targets` 用于记录候选合并目标，不表示 Task Workstream 可以直接写 authority 文件。Workstream 类型为 Task / Merge / Maintenance：Task 只直接修改自己的 write_scope，Merge / Maintenance 才能在显式声明 `authority:` 时修改主线；Active 类 Workstream 默认禁止重叠 `owned:` 写入；`shared:` 必须指定 `merge_owner` 或 `coordination: serial`。执行前用 `acf workstream context WSxxx` 获取 AI 专属上下文入口，扩权用 `acf workstream scope-add WSxxx --reason ...` 留痕，完成、ready、done 或切换状态前用 `acf workstream guard WSxxx --files <本次修改文件...> --json` 做文件集强验收；裸 `guard` / `--from-git` 只适合快速查看当前 git diff，旧式整工作区排他检查需显式使用 `--workspace --strict-workspace`；日常总览用 `acf workstream dashboard`。`acf check` 会检查当前阶段已注册、属于本 Workstream、状态合法，strict 下检查 Done 阶段 evidence，检查 Workstreams 索引与详情 front matter 是否一致，并在 strict 下拒绝 Task authority 直接写入、Active 类写入冲突和 shared 缺 merge owner/serial coordination；ReadyToMerge / Done Workstream 声明 `merge_targets` 时必须有合并请求；ReadyToMerge 表示任务产物完成，`ready` 需要人工确认参数 `--human-approved`，Merging 表示 Merge/Maintenance 正在合并，Done 需要 `merge_resolution`，仍留在 active 时需要 keep-active metadata。

### Workstream 编号预约与可选 Git Worktree

`acf workstream add` 保持纯上下文行为，不创建 Git branch/worktree。需要在 primary branch 先占用唯一编号时，AI 可调用：

```powershell
acf workstream reserve --title "任务" --slug task-slug --owner codex --apply --json
```

`reserve` 扫描 active/archive/index、Git refs、worktree registry 和 operation journal，在预约锁内重查编号，只提交 Workstream detail 与索引。primary checkout 可以保留与这两个 reservation 路径无关的 staged/unstaged/untracked 修改；若 reservation detail/index 自身或父子路径已被修改，命令会 fail-closed。创建 worktree 是后续可选动作：

```powershell
acf worktree create --workstream WS005 --apply --json
```

非 WS 隔离任务使用 `--kind bugfix|docs|experiment|investigation|maintenance|refactor|release --slug ...`。`worktree list|audit|verify|attach` 用于发现和绑定，`sync` 默认把冻结 primary commit merge 到任务分支。`merge-plan|merge` 统一使用临时 integration worktree 生成候选和执行 post-check，primary 只做碰撞保护后的 fast-forward promotion；无关 staged/unstaged/untracked 修改可以保留，短时锁、路径状态和 HEAD 推进会有限等待或自动重规划。稳定冲突保留 integration 现场并通过 operation ID resume；`artifact-plan|artifact-migrate` 管理 ignored/untracked 结果分类、复制/引用和摘要验证；`close` 只删除已合并、clean 且 handoff 完成的 worktree/branch，并支持文件占用退避与部分成功恢复。所有写操作默认 plan-only，显式 `--apply` 后执行；journal、registry、artifact manifest 和锁保存在 Git common-dir 的 `acf/` 子目录。命令禁止自动 stash、reset、clean、rebase、force、push、目录覆盖和静默解决冲突。产品级教程与 AI 决策表见 [docs/Worktree_Lifecycle.md](../../../docs/Worktree_Lifecycle.md)，版本变化见 [CHANGELOG.md](../../../CHANGELOG.md)。

### 外部 AI 的 bounded continuation

需要让 Scheduled Task、其他 scheduler 或人工多轮任务持续推进现有 worktree 时，使用 `acf continuation`，而不是为每个项目复制 controller：

```powershell
acf continuation init C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --workstream WS001 --title "WS001" --objective "目标" --profile long-running --json
acf continuation configure C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --profile long-running --json
acf continuation doctor C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --json
acf continuation claim C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --runner-id scheduled-agent --json
# 保存 claim 返回的 lease_id、generation、fence_token；不要把 fence_token 写入项目文件或普通日志
acf continuation assert-owner C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json
acf continuation workspace status C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --json
# 修改项目文件前声明 concrete intent；绑定 Workstream 时必须命中其直接 write_scope
acf continuation workspace intent C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --path src/example.py --json
# 旧 task 缺少 workspace manifest 且保留 reviewed WIP 时，只能在无 active owner 后显式分类全部 changed paths
acf continuation workspace adopt C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --task-owned src/reviewed.py --baseline-external notes/local.txt --evidence-ref review:legacy-handoff --reason "Reviewed legacy no-manifest WIP." --json
# 写入后/收口前刷新 bounded path/status/digest ownership metadata
acf continuation workspace refresh C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json
acf continuation heartbeat C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json
acf continuation progress C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --phase executing --milestone gate-started --json
acf continuation effect prepare C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --key campaign:wave-01 --kind external-job --json
# 只有 prepare 返回 created=true 才执行首次外部动作；created=false 时先 list/核对/复用，禁止重复 submit
acf continuation effect update C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --key campaign:wave-01 --status active --external-id runtime-job-123 --evidence-ref authority:runtime-job-123 --json
acf continuation effect list C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --json
# doctor 显示 stale/orphan/legacy_unknown/reconciliation_required 时先只读 reconcile；不要复制旧 lease-id 接管
acf continuation reconcile C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --json
# 只有确认旧 owner 已结束、effects 均已终态/可复用、HEAD 已解释后才记录 eligible receipt
acf continuation reconcile C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --owner-ended --accept-head <current-head-if-advanced> --evidence-ref scheduler:old-run-ended --reason "verified prior owner ended and durable state is reconciled" --record --json
acf continuation recover C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --reconcile-id <receipt_id> --runner-id recovery-agent --json
acf continuation renew C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json
# 已修复 dogfood issue 用 append-only resolution event 收口；历史 occurrence 不删除
acf continuation issue C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --text "fixed by validated checkpoint" --resolve-fingerprint <fingerprint> --evidence-ref git:<commit> --json
acf log issues --all-projects --open-only --json
```

新 claim 或 recover 的同一 round 使用返回的 `lease_id + generation + fence_token` 调用 owner-protected 写命令。`standard` timing 为 scheduler/TTL/renew/heartbeat/stale=`60/120/30/10/30` 分钟，`long-running` 为 `60/180/45/10/25`；已有 task 可用 `configure` 原位切换。`progress` 只记录 generic phase/milestone/evidence；外部/non-idempotent work 必须先 `effect prepare`，再根据 authority observation 用 `effect update` 推进，不能把 raw stdout/tool output/transcript 写入 journal。workspace manifest v3 记录 bounded path/status/digest ownership，并可保存一次性 legacy adoption receipt：`baseline_external` 是受保护外部修改，显式 write intent 下产生或继承的未提交修改是 `task_owned`。worktree-level `clean/dirty` 不参与 liveness、claim、release、reconcile 或 recover；正常 release 可以保留 task-owned WIP 并让下一 generation 在 ownerless handoff digest 未漂移时继续继承，因此 Scheduled round 不要求 Git commit。无 manifest 的 changed paths 报 `workspace_provenance_missing`，doctor 会提示先审阅再使用 `workspace adopt`；adopt 只能在没有 active owner 时一次性执行，必须把当前全部 changed paths 明确列为 `--task-owned` 或 `--baseline-external`，并提供 durable evidence refs 与 reason。它记录当前 status/content digest、prior generation 与 adoption receipt，bound Workstream 的 task-owned 路径仍受直接 write_scope 约束；遗漏/重叠、HEAD drift、owner identity 不清或来源无法确认都继续 fail-closed。adopt 只补建 workspace provenance，不重置 continuation state、round/effect/coordination history，也不要求先形成 Git semantic checkpoint。task-owned handoff 漂移、同路径/父子路径碰撞、HEAD/effect/identity 无法解释才 fail-closed。`heartbeat` 只刷新 liveness，不延长 TTL；`renew` 才延长 TTL。fresh active owner 永远不可 takeover；challenge timeout 只形成 ownership-forfeiture candidate，仍需 formal reconcile；stale/orphan recovery 在 workspace/effect/HEAD/identity evidence 可解释时 generation+1 fencing，并保留 task/external WIP，不 stash/reset/clean。`acf continuation prompt` 是 Scheduled Task 的 generic 协议权威。人工中止使用 `pause`，确认后使用 `resume`。状态保存在用户级 `~/.acf/projects/.../continuation/`，不会自动修改项目文件。完整设计见 [Continuation_Control_Design.md](Continuation_Control_Design.md)。

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

### 其他上下文维护命令

注意力治理规则：

Task Stage 仍以 [active/Task_Plan.md](../active/Task_Plan.md) 的 `## 任务阶段` 表为事实源；`plan stage list|add|set|done` 只维护该表，不创建 task object 单文件，不自动修改 [active/Current_Task.md](../active/Current_Task.md)，也不自动联动 Workstream。`plan stage add` 要求阶段 ID 使用 `T001.1` 格式且归属于已存在父任务，`--workstream` 只接受已存在的 Workstream ID 或空值；`plan stage done` 要求 `--evidence`。

[active/Task_Plan.md](../active/Task_Plan.md) 必须在 `## 规划依据` 显式列出当前大任务必须对齐的 reference 设计、路线或差距文档，只放路径和一句话用途，不复制详细规划。`acf plan reference list|add|remove` 维护该小节；`add` 默认要求 `reference/*.md` 目标存在，可用 `--allow-missing` 显式允许缺失，用 `--force` 更新同一路径，用 `--sync-current-task` 显式同步标准 bullet 到 Active [active/Current_Task.md](../active/Current_Task.md) 的 `## 输入材料`。

`acf workstream archive-candidates --json` 只读扫描 Done / Cancelled Workstream，输出 `candidates`、`blocked`、`blocked_by` 和 `changed_files: []`；机械 blocker 包括 keep-active 未过期、当前执行线引用、当前任务阶段归属、缺 evidence、缺 merge_resolution、缺 merge request、缺取消原因或非法 keep-active 日期。

`acf workstream archive-draft --json` 将 candidates + blocked 渲染到 worklog/archive-drafts/YYYY-MM-DD dot md，供人工或 AI 审阅；候选项只生成建议命令，blocked 项只写 suggested_action，不自动执行归档。重复草案默认失败，可用 `--name` 创建独立草案或 `--force` 覆盖。

`acf workstream archive WS001 --reason "..." --json` 是显式移动命令：只接受 Done / Cancelled，复用 archive-candidates blocker，移动详情到 archive/workstreams/WS001 dot md，删除 active 索引对应行并重算 Workstream 状态，写入 [archive/Archive_Index.md](../archive/Archive_Index.md)，追加 `ACF:WORKSTREAM:ARCHIVE-RECORD` marker。该命令不修改 merge target、不修改 [active/Context.md](../active/Context.md) / [active/Current_Task.md](../active/Current_Task.md) / [active/Task_Plan.md](../active/Task_Plan.md)，默认不跑完整 check，可加 `--check-after`。

`acf workstream sync --dry-run --json` 只根据 `active/workstreams/*.md` front matter 预览或更新 [active/Workstreams.md](../active/Workstreams.md)；第一版不会删除索引中缺失详情文件的旧行，也不会移动 Done / Cancelled 文件。

Done / Cancelled Workstream 留在 `active/workstreams/` 时，应有 `keep_active_reason` 和 `keep_active_until`；strict check 会拒绝过期的 `keep_active_until`。仍被当前计划解释所需的终态 Workstream 不应被归档；归档必须由显式 `workstream archive` 命令触发。

`acf audit context --json` 是只读上下文审计 MVP，只报告 candidates，不判断事实真假、不写文件、不生成 patch、不接入 `check --strict`。当前规则只覆盖长 active section、陈旧当前任务 / Workstream 阶段和 ReadyToMerge 待合并或 Done 缺合并结果候选。

`acf doctor docs/ai --json` 是面向人和 AI 的上下文健康诊断入口。它复用 `check` 的结构校验结果，并额外报告跨文件生命周期漂移、终态 Workstream authority scope 残留、Workstreams / Archive generated index 漂移、Workstream 协议漏 `Merging`、Decisions_Index 摘要截断、Sources_Index 本地文件缺失、active 过厚、根目录探针输出和本地数据副本 hash / missing evidence。`--projects` 可一次只读诊断多个项目，每个项目独立输出 summary、findings、check 和 next_actions。

`acf doctor docs/ai --fix safe --dry-run --json` 用于预览确定性修复；去掉 `--dry-run` 后才落盘。safe 修复只包含低歧义规则：当 Task_Plan 焦点指向 Done 任务且没有可推荐下一任务时清空焦点，修正 Current_Task 完成回写要求中明确回写目标行且无额外任务引用的错误 Txxx，移除 Done / Cancelled Workstream 中残留的 authority `assigned:` 写入范围，同步 Workstreams / Archive generated index，以及补齐 Workstream 协议中的 `Merging` 状态。`--projects` 保持只读，不能与写入型参数组合；`--fix evidence` 不改写语义权威文件，只把项目根内相对路径的数据证据信号计入 planned evidence repairs，实际写回仍通过 report / draft 或人工审阅完成。

`acf doctor docs/ai --report --today YYYY-MM-DD --json` 写入 worklog/doctor-reports/YYYY-MM-DD dot md，供人工查看完整 findings；`acf doctor docs/ai --draft-semantic --today YYYY-MM-DD --json` 写入 worklog/writeback-drafts/YYYY-MM-DD-doctor dot md，只包含 `draft_only` 和 `evidence_fix` findings；即使没有 findings，也会生成明确的 clean report 或空语义草案。两者默认不覆盖既有文件，确需替换时使用 `--force`；report 和 draft 都不进入默认读取路径。

PowerShell 中反引号是转义字符。写入包含 Markdown 反引号或多行正文时，优先使用 `--input <file>`。

### AI 创建上下文对象

1. 当前具体任务用 `uv run acf new task docs/ai --title "..." --goal "..." --json`，Active 任务未归档时默认拒绝覆盖。
2. 外部资料索引用 `uv run acf new source docs/ai --title "..." --type "..." --location "..." --relation "..." --json`。
3. 长期 reference 文档用 `uv run acf new reference docs/ai --title "..." --summary "..." --body "..." --json`；可用 `--file reference/X.md` 指定路径，命令拒绝写到 context 外或 `reference/knowledge/` 托管目录。
4. 按需规则文件用 `uv run acf new rule docs/ai --title "..." --condition "..." --purpose "..." --rule "..." --json`；命令会写 `rules/*.md` 并维护 `rules/Rules_Index.md`。
5. 待整理反馈用 `uv run acf new feedback docs/ai --type "..." --content "..." --source "YYYY-MM-DD user" --json`；命令只写 Feedback_Inbox，不把反馈直接升格为事实。
6. 人工异步笔记用 `uv run acf new human-note docs/ai --type "..." --content "..." --json`；命令写 `human/Human_Notes.md` 并同步 `human/Human_Index.md`，不进入 active 默认注意力。
7. human 材料治理用 `uv run acf human index sync docs/ai --json`、`uv run acf human list docs/ai --status Open --json` 和 `uv run acf human mark docs/ai <ID-or-path> --status Extracted --extracted-to reference/X.md --json`；命令只维护索引和显式状态，不自动提取事实。
7. 重要决策仍使用 `uv run acf new adr docs/ai --title "..." --summary "..." --decision "..." --json`；可复用经验仍先走 `knowledge draft/apply`。

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

1. 人工可直接写入 [active/Feedback_Inbox.md](../active/Feedback_Inbox.md)。
2. AI 处理 Open 条目时，先判断归属。
3. 可执行事项进入 [active/Task_Plan.md](../active/Task_Plan.md)。
4. 当前任务所需输入材料进入 Active [active/Current_Task.md](../active/Current_Task.md) 的 `## 输入材料`，其中应包含相关 reference 规划依据。
5. 当前事实进入 [active/Context.md](../active/Context.md)。
6. 重要决策进入 ADR。
7. 历史过程进入 worklog。
8. 可复用经验进入 Knowledge 草案流程。
9. Done/Rejected 条目必须保留证据位置或拒绝原因；超过 10 条，或完成超过 30 天且不再支撑当前计划时，整理到 `archive/feedback/`。
10. Feedback 生命周期优先使用 `uv run acf feedback list|triage|done|reject|archive-candidates|archive docs/ai ... --json`；这些命令只维护状态、处理结果和单条显式归档，不自动转写事实源。

## 人工笔记与 Obsidian

1. 标准上下文包含 [human/Human_Index.md](../human/Human_Index.md)、[human/Human_Notes.md](../human/Human_Notes.md)、`human/weekly/` 和 `human/reports/`，用于人类给 AI 的理解、规划、疑问、解释、随笔、复盘和汇报材料。
2. `human/` 默认不读取，也不作为已确认当前事实；需要进入 AI 当前事实时，整理到 `active/`、ADR、Knowledge、reference 或 worklog 的权威位置。
3. `human/Human_Index.md` 是可发现索引；`acf human index sync` 可机械补齐缺失索引行，`acf human list` 可按状态查看，`acf human mark` 可显式标记 Reviewed / Extracted / Archived。
4. 可以把项目 `docs/` 作为 Obsidian vault 根目录，使用 `[[双链]]` 方便人工查看和导航。
5. ACF 不解析、不校验、不依赖 Obsidian 双链；CLI 和 AI 的结构化依据仍使用普通 Markdown 路径。
6. [active/Feedback_Inbox.md](../active/Feedback_Inbox.md) 继续用于待处理反馈和需求碎片，`human/` 用于更自由的人工记录、复盘和汇报材料。

## Markdown 链接与人工导航

1. ACF 的结构化引用优先使用普通 Markdown 链接，例如 `[reference/System_Manual.md](../reference/System_Manual.md)`；Obsidian、GitHub 和常规 Markdown 工具都能点击。
2. `[[双链]]` 只作为人工导航补充，不作为 ACF 机器校验或 AI 读取增强的依据。
3. 文档中引用上下文内其他文件时，链接目标按当前文件所在目录计算；需要链接标题时使用 `path.md#heading-anchor`。
4. `acf check` 会校验本地 Markdown 链接和图片链接的目标文件是否存在；对 `.md#anchor` 会校验目标标题 anchor。`http://`、`https://` 和其他 URI scheme 不做本地校验。
5. `acf linkify [target] --format markdown` 可把安全识别到的本地路径引用转换为 Markdown 链接；默认只处理 active、reference、rules、decisions、Worklog_Index 和 Archive_Index。
6. `acf link add [target] <file> --heading "## 输入材料" --target reference/X.md` 可向指定小节追加确定性链接 bullet，不做语义判断、不自动猜 section。
7. `acf archive current-task|task-plan` 归档移动当前任务或计划时，会按归档文件的新位置重写已有本地 Markdown 相对链接，并追加 `ACF:ARCHIVE:RECORD` marker 供 `archive sync` 恢复归档原因；URL、URI、缺失目标和代码块内链接保持原样。

## 注意力治理

1. 默认上下文只保留当前目标、当前事实、当前任务和下一步。
2. 写入前必须判断唯一权威位置；能更新旧表述时，不追加重复事实。
3. worklog 记录历史过程，archive 保存历史材料，Feedback_Inbox 和 human 保存待处理或未整理信号；它们默认不作为当前事实。
4. 整理事实时优先读取 changed files、`active/`、相关索引和最近 worklog。
5. 不为 curation 默认读取 archive 或全部历史日志；writeback draft 和 curation draft 不进入默认读取路径。
6. 能引用权威位置时，不复制完整表述。

Global-first progressive disclosure：没有明确选择时，无论存在多少 Active / Blocked / ReadyToMerge / Merging Workstream，`acf status|next` 都保持 `GlobalOnly`，只披露全局文件指针和索引摘要；attention 只用于 dashboard 管理。显式 `--workstream`、Active Current_Task 唯一绑定或 verified worktree 可以选择单一 WS，但状态结果仍只给 pointer-only 入口，必须再调用 `acf workstream context WSxxx` 才披露专属 detail/read_scope，并继续按需读取 reference/output。选择来源冲突或指向不存在、非活动 WS 时返回 `SelectionConflict` / `SelectionInvalid`，保持全局上下文，不自动改选。`reference/` 是中间材料层，Knowledge 高可信但不默认全量读取；ReadyToMerge 不表示权威事实已经合并，只表示有可审查输入。

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
4. 验证 `uv run acf check template`、`uv run acf upgrade docs/ai --plan --json`、`uv run acf upgrade docs/ai --dry-run --json`、`uv run acf check docs/ai --strict --json`、`uv run python -m unittest` 和 upgrade compatibility quick/full 模式。

ACF 维护块统一使用 `<!-- ACF:<DOMAIN>:<PURPOSE>:START -->` 与对应 `END` marker，例如 `ACF:UPGRADE:NOTES`、`ACF:ARCHIVE:RECORD`、`ACF:WORKSTREAM:ARCHIVE-RECORD`、`ACF:KNOWLEDGE:INDEX-GENERATED`、`ACF:DECISIONS:INDEX-GENERATED` 和 `ACF:ARCHIVE:INDEX-GENERATED`；旧 marker 保持兼容，但 `check` 会给出 future warning。`acf knowledge sync`、`acf decisions sync` 和 `acf archive sync` 只重算对应 generated marker 内表格，旧索引首次接入需显式 `--init-marker`。模板占位符统一使用 ACF-keyed placeholder form，表格单元格内使用无提示形式，避免 `|` 破坏 Markdown 表格。
