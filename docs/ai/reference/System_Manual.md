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
- `uv run acf observer status --json`
- `uv run acf observer snapshot --dry-run --json`
- `uv run acf observer snapshot --json`
- `uv run acf observer history --stream timeline --limit 20 --json`
- `uv run acf observer glossary --json`
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

非 WS 隔离任务使用 `--kind bugfix|docs|experiment|investigation|maintenance|refactor|release --slug ...`。`worktree list|audit|verify|attach` 用于发现和绑定，`sync` 默认把冻结 primary commit merge 到任务分支。`merge-plan|merge` 统一使用临时 integration worktree 生成候选和执行 post-check，primary 只做碰撞保护后的 fast-forward promotion；无关 staged/unstaged/untracked 修改可以保留，短时锁、路径状态和 HEAD 推进会有限等待或自动重规划。稳定冲突保留 integration 现场并通过 operation ID resume；`artifact-plan|artifact-migrate` 管理 ignored/untracked 结果分类、复制/引用和摘要验证；`close` 只删除已合并、semantic-clean 且 handoff 完成的 worktree/branch，并支持文件占用退避与部分成功恢复。真实 dirty 始终在 remove 前拒绝；只有 canonical semantic-clean 已证明内容无变化且存在 `stat_only_paths` 时，close 才会内部用 `git worktree remove --force` 绕过 raw Git 的假 dirty，branch 仍只用 `-d`。所有写操作默认 plan-only，显式 `--apply` 后执行；journal、registry、artifact manifest 和锁保存在 Git common-dir 的 `acf/` 子目录。命令禁止自动 stash、reset、clean、rebase、push、`branch -D`、目录覆盖和静默解决冲突。产品级教程与 AI 决策表见 [docs/Worktree_Lifecycle.md](../../../docs/Worktree_Lifecycle.md)，版本变化见 [CHANGELOG.md](../../../CHANGELOG.md)。

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
# durable writer 已结束且审阅确认启动前漏报的 unexpected 输出属于本 task 时，必须携带 durable evidence 显式 reclassify
acf continuation workspace reclassify C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --task-owned build/generated.txt --evidence-ref effect:release-job:terminal --reason "Reviewed durable-writer output." --json
# 旧 task 缺少 workspace manifest 且保留 reviewed WIP 时，只能在无 active owner 后显式分类全部 changed paths
acf continuation workspace adopt C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --task-owned src/reviewed.py --baseline-external notes/local.txt --evidence-ref review:legacy-handoff --reason "Reviewed legacy no-manifest WIP." --json
# 写入后/收口前刷新 bounded path/status/digest ownership metadata
acf continuation workspace refresh C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json
acf continuation heartbeat C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json
# 用户可在 owner 活跃期间写入新的 steering authority；CLI 只记录/校验，不自动改 Task Plan
acf continuation directive add C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --kind requirement --priority 80 --text "新增持久需求" --json
acf continuation directive list C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --status pending --json
acf continuation directive show C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --directive-id <directive_id> --json
# Agent authority refresh 后，把持久要求同步进正确 Markdown authority，再显式 adopt/resolve
acf continuation directive adopt C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --directive-id <directive_id> --evidence-ref docs/ai/active/Task_Plan.md --json
acf continuation directive resolve C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --directive-id <directive_id> --evidence-ref git:<commit> --json
acf continuation directive supersede C:\PROJECT\repo_worktrees\ws001-example --task-id WS001 --directive-id <directive_id> --kind priority_change --priority 95 --text "新的优先级要求" --json
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

新 claim 或 recover 的同一 round 使用返回的 `lease_id + generation + fence_token` 调用 owner-protected 写命令。`standard` timing 为 scheduler/TTL/renew/heartbeat/stale=`60/120/30/10/30` 分钟，`long-running` 为 `60/180/45/10/25`；已有 task 可用 `configure` 原位切换。directive journal 是同一 task namespace 下独立的 user-authority inbox：kind 仅为 `requirement / priority_change / constraint / plan_change`，状态为 `pending / adopted / resolved / superseded`，原始事件 append-only 且有 schema/事件数/字节容量边界；credential-like 文本拒绝落盘。`prompt --json` 返回 `directive_context`（revision、pending-set digest、pending count、latest/pending 摘要），pending user directive 高于旧 persisted `next_action`；claim 记录已观察 revision/digest，heartbeat/renew 返回 `directive_signal.changed_since_last_observation`，使长 session 可以及时 refresh authority。directive CLI 不自动修改 Markdown；持久要求必须由 Agent 落到正确 PLAN/Workstream/Rules 后再 adopt。`progress` 只记录 generic phase/milestone/evidence；外部/non-idempotent work 必须先 `effect prepare`，再根据 authority observation 用 `effect update` 推进，不能把 raw stdout/tool output/transcript 写入 journal。current `effects.json` 达到记录/字节边界时，ACF 会透明地把完整 `completed|failed` records rollover 到 `effects.archive.NNNNNN.json`；archive 继续参与 logical-key 防重放，`prepared|active|unknown` 永不归档，若 unresolved 自身耗尽容量仍 fail-closed。workspace manifest v3 记录 bounded path/status/digest ownership，并可保存一次性 legacy adoption receipt：`baseline_external` 是受保护外部修改，显式 write intent 下产生或继承的未提交修改是 `task_owned`。worktree-level `clean/dirty` 不参与 liveness、claim、release、reconcile 或 recover；正常 release 可以保留 task-owned WIP 并让下一 generation 在 ownerless handoff digest 未漂移时继续继承，因此 Scheduled round 不要求 Git commit。无 manifest 的 changed paths 报 `workspace_provenance_missing`，doctor 会提示先审阅再使用 `workspace adopt`；adopt 只能在没有 active owner 时一次性执行，必须把当前全部 changed paths 明确列为 `--task-owned` 或 `--baseline-external`，并提供 durable evidence refs 与 reason。它记录当前 status/content digest、prior generation 与 adoption receipt，bound Workstream 的 task-owned 路径仍受直接 write_scope 约束；遗漏/重叠、HEAD drift、owner identity 不清或来源无法确认都继续 fail-closed。adopt 只补建 workspace provenance，不重置 continuation state、round/effect/coordination/directive history，也不要求先形成 Git semantic checkpoint。task-owned handoff 漂移、同路径/父子路径碰撞、HEAD/effect/identity 无法解释才 fail-closed。`heartbeat` 只刷新 liveness，不延长 TTL；`renew` 才延长 TTL。fresh active owner 永远不可 takeover；challenge timeout 只形成 ownership-forfeiture candidate，仍需 formal reconcile；stale/orphan recovery 在 workspace/effect/HEAD/identity evidence 可解释时 generation+1 fencing，并保留 task/external WIP，不 stash/reset/clean。`acf continuation prompt` 是 Scheduled Task 的 generic 协议权威。compact `state.json` 只有 `completed / evidence_refs / verification` 采用最多 64 项的 rolling history window；`constraints / open_questions / plan_refs` 继续严格限 64 项并在超限时 fail-closed。旧版本遗留的 current-schema history-list overflow 会在读取时惰性压缩，避免 `prompt/doctor/reconcile` 自锁，下一次合法 state write 再持久化 compact 结果；裁剪前仍检查全部旧条目的 forbidden raw-history 和单项大小。round/effect/coordination/directive 等独立历史账本不参与这项裁剪。人工中止使用 `pause`，确认后使用 `resume`。状态保存在用户级 `~/.acf/projects/.../continuation/`，不会自动修改项目文件。完整设计见 [Continuation_Control_Design.md](Continuation_Control_Design.md)。

`acf continuation prompt` 采用 goal-directed continuous execution：scheduler wake 只是持续任务的恢复入口，不定义独立工作回合、汇报周期、工作配额或预期停止点；bounded 只约束 ownership、写入、副作用和恢复风险，不限制当前 execution session 的有效工作量。`.72+` 中 `state.next_action` 在 authority refresh 后仍有效时是**默认执行计划**，不是仅供查看的 hint，也不是 work quota；newer Git/PLAN/Runtime/effect authority 可以覆盖它，否则 Agent 应执行而不是只解释/汇报，完成后再围绕总体目标继续选择安全、有价值的下一步。若默认计划明确要求等待下一次真实外部/项目状态变化，scheduler wake、`coordination attempt` 与 `claim` 都只属于 control-plane bookkeeping，不能把它们自身产生的 lifecycle change 当作等待条件已经满足；此时若没有其他当前可执行的安全、有价值工作，可以不 claim、不改变 task 状态地结束这次 wake。generated prompt 采用 state-conditioned progressive disclosure，只展开当前 owner/workspace/effect 状态相关的控制分支。final response、timing、测试/commit/checkpoint/Gate 的既有非停止语义保持不变；任务级 hard stop 仍只允许总体目标完成、用户明确暂停、需要新的人工授权/凭据/不可替代决策，或项目访问工具经合理重连仍不可用。

`workspace reclassify` 只处理 active fenced owner 当前看到的 `unexpected_nonoverlap`，用于 durable writer 已结束后对启动前漏报输出做证据化归属。`--task-owned` 会同时补入 write intent，`--baseline-external` 则继续保护外部修改；两者都要求 `--evidence-ref` 和 `--reason`。task-owned 路径必须命中 bound Workstream direct write scope，已有 workspace conflict、非 unexpected 路径、父子/重复分类、scope 越界或来源无法证明时均拒绝执行。若绑定 Workstream 已通过正式 `workstream archive` 移入 archive、active detail 已不存在，恢复流程会校验 archived detail 并继续使用其原 direct scope；仅本次 archive lifecycle 所必需的 `active/Workstreams.md`、原 active detail、`archive/Archive_Index.md` 与 archived detail 四条 authority 路径额外可被证据驱动地 reclassify，不会恢复 Workstream Active 状态或扩大普通 Task 写权限。

普通 `baseline_external` 仍禁止 stash/reset/clean/stage/commit。唯一窄例外是当前 authenticated runner 刚通过 `acf workstream scope-add|merge-request|ready|merge-start|done` 为**当前绑定 Workstream**生成的两个确定性 control-plane authority 文件：[Workstreams 索引](../active/Workstreams.md) 与 active workstream 目录下当前绑定 Workstream 的 detail 文件。在 lifecycle/merge 边界，可以先逐项审阅 exact diff 并保存 durable ACF command evidence，再把**仅这两个文件**形成独立 control-plane checkpoint，使 worktree 回到 semantic-clean 后继续 ACF-managed merge。该例外不扩展普通 Task authority write_scope，不允许第三个 baseline/external path 混入提交；来源不明、人工编辑或 provenance 无法证明时继续 fail-closed。

Git/worktree 与 continuation workspace 共享同一 semantic-clean 边界：普通 tracked unstaged `M` 只有在 `GIT_OPTIONAL_LOCKS=0` 的 read-only diff 证明没有 normalized content change 时才作为 `stat_only_paths` 忽略；staged、untracked、真实 diff、rename/delete/type/mode/unmerged/submodule 仍严格视为 dirty。`acf worktree verify/list` 会暴露 `stat_only_paths`，但不会通过 index refresh“修复”状态。Workstream `## Workspace` 不持久化机器相关 mode/path/branch，只保存 slug 和 local registry/verify/list authority；Open Workstream 的 reserve/create next_actions 明确要求执行前显式切换为 Active。

官方 scheduler wrapper 不追求“薄”，而追求 **sufficient high-salience bootstrap**，同时仍不保存 generic 状态机副本。wrapper 应完整写明固定 project/worktree/branch/task/workstream identity、项目访问 connector、**打开既有 worktree 的精确模式**（例如 DevSpace 对已有 worktree 使用 `mode="checkout"`，不得再次使用 `mode="worktree"` 创建 detached/重复工作树）、稳定 ACF 版本检查与升级/迁移后的继续执行、每次 authority refresh、`prompt --runner-id <runner>`、把刷新后仍有效的 generated `next_action` 作为默认计划立即执行、owner 用户可见说明，以及项目特有 Runtime/resource/permission/security/scientific/validation/issue-reporting 约束。wrapper 不复制 claim/challenge/reconcile/workspace/effect 状态机，也不用“本轮收口”“最终汇报”制造回合终点。可能跨当前 owner/tool-call 生命周期继续写项目文件或产生非幂等副作用的本地长进程、Runtime/external job 仍必须使用 durable effect/job identity；纯只读长阻塞调用可不建立 writer effect，但下一次写入/副作用前必须重新 `assert-owner`。

`continuation prompt --json` 返回 `identity`、`current`、`owner_context`、`directive_context`、`resume_context`、`execution_policy`、`project_context`、`scheduler_wrapper_contract`、当前 `next_actions` 与 generated `prompt`。`owner_context` 将 lease record 与 caller identity/liveness 分开；传 `--runner-id` 后可稳定区分 `current_owner / verified_live_other_owner / stale_or_unverified_owner / expired_owner / no_active_owner`，未传时 fresh lease 使用 caller-unknown 分类，不武断判 duplicate。`directive_context` 是本次 prompt 看到的 user-authority inbox snapshot；只要存在 pending directive，generated prompt 明确要求先 authority refresh，并由 `pending_user_directive_supersedes_persisted_next_action=true` 表达优先级。`coordination attempt` 对 fresh owner 不再自动 challenge；stale / legacy-unverified 才自动进入 challenge。`execution_policy` 包含 `next_action_is_default_execution_plan=true`、`next_action_requires_authority_refresh=true`、`active_lease_requires_liveness_verification=true`、`verified_duplicate_owner_may_end_duplicate_wake=true`、`duplicate_wake_exit_is_task_stop=false`、`stale_owner_requires_recovery=true`、`contender_must_create_busywork=false`，并保留 `next_action_is_work_quota=false`、`final_response_is_terminal=true` 等既有字段；条件等待计划还暴露 `claim_requires_present_safe_useful_work=true`、`control_plane_activity_satisfies_wait_condition=false` 与 `no_useful_work_may_end_wake_without_claim=true`，避免控制面活动自证等待条件。`scheduler_wrapper_contract.bootstrap_policy=sufficient_high_salience`，但 `copy_generic_state_machine=false`。

同一 stale generation 若同时存在多个已有 durable external id、且由外部 authority 明确证明 terminal 的 unresolved effects，可在一次 `reconcile` 中按相同顺序重复 `--effect-key`、`--effect-terminal-status`、`--effect-external-id`，以一个 receipt 原子绑定全部 effect assertions；本次重复 assertions 共享 `--effect-evidence-ref` 集合，数量、identity 或 digest 不一致仍 fail-closed。如果中断发生在 write-ahead `effect prepare` 之后、真正 external submit 之前，且单个记录仍是 `prepared`、`external_id=null`，外部 authority 又能明确证明 submit 从未启动，则 owner 结束/forfeiture 后可用 `acf continuation reconcile ... --effect-key <key> --effect-terminal-status failed --effect-not-started --effect-evidence-ref <ref>` 记录 no-start receipt，再由 `recover` 原子收口为 failed。`--effect-local-terminal` 用于已经执行的**本地确定性动作**：当记录仍为 `prepared` 或 `active`、没有 external id、durable local artifact/state/hash 等 authority evidence 已能证明 `completed|failed` 时，允许显式生成 receipt；同一 receipt 可覆盖多个此类 local effects。该模式与 `--effect-not-started` / `--effect-external-id` 互斥，已有 external id、`unknown` effect、证据不足或 receipt 后 observation 漂移仍 fail-closed。ACF 不自动判断 effect 是否“本地”或已完成，只验证机械边界并持久化调用方的可审计 assertion。

continuation state 的 canonical 位置是 `ACF_HOME/projects/<root-slug>-<path-hash>/continuation/<task-id>/`；默认 `ACF_HOME=~/.acf`，override 只替换根目录，不改变 namespace/schema。`directives.json` 与 control/state/round/effect 等文件同属该用户级 task namespace，不进入项目 Git。使用 `acf continuation list <worktree> --json` 查看当前项目 task，或 `acf continuation list --all-projects --json` 只读盘点全部 project/task；输出稳定区分 `task_id` 与 `workstream_id`，并列出 control generation、timing profile、每个 state 文件 schema 以及 `current / migration_available / blocked`。已知 legacy workspace schema 用 `acf continuation migrate <worktree> --task-id <id> --dry-run --json` 先预览；确认无 active/expired lease record 后再 `--apply --reason ...`。迁移 receipt 写入 `last_migration.json`，记录 from/to schema 与 workspace digest，同时保存其余 control/state/round/effect/coordination/directive/reconcile/recovery 历史文件的 byte digest；未知/future schema 继续 fail-closed，任何 scheduler/Agent 都不得手改这些 JSON。

### Project Observer

`acf observer` 是项目级只读可观测入口，和 continuation Writer 控制面严格分离。一个项目只对应一个用户级 Observer namespace；primary checkout 与 ACF 注册的同项目 worktree 会被统一扫描。Observer 的固定权限边界是 **read broad / write narrow / control none**：它可以读取 Git、Workstream、continuation、计划、evidence 和必要代码，但只把派生状态写入 `~/.acf/projects/<project-id>/observer/`，不会 claim/challenge/recover continuation、不会提交 Git、不会修改 Writer 的项目文件。

```powershell
# 只读查看当前 Observer runtime、自健康和数据年龄
acf observer status --json

# 只生成/验证本轮事实，不写 Observer runtime
acf observer snapshot --dry-run --json

# 原子更新 current/history/self-health，并生成自包含 dashboard.html
acf observer snapshot --json

# 读取 live + rotated 历史；stream 可选 timeline/observations/alerts/runs/interpretations/narratives
acf observer history --stream timeline --limit 20 --json

# 读取项目级 semantic glossary
acf observer glossary --json

# 只读计算 Project Narrative 的显式 authority source projection/fingerprint
acf observer narrative-source . --source-path docs/ai/reference/Project_Brief.md --json

# 把模型/Agent 生成的 Project Narrative JSON 绑定到精确 source fingerprint 后写入 derived semantic state
acf observer narrative-apply . --source-fingerprint <fingerprint> `
  --source-path docs/ai/reference/Project_Brief.md --input project-narrative.json --json

# 只读检查当前 Project Narrative 是否仍与最新 authority 一致
acf observer narrative . --json
```

`snapshot` 会对项目事实做开始/结束 fingerprint；第一次读取期间发生变化时自动重读一次，仍不稳定则把 `snapshot_consistency=unstable` 并生成 critical Alert，不把混合快照包装成高置信度事实。Observer 自己使用独立轻量锁，正常 overlap fail-closed；只有锁已超过 grace 且本机只读进程检查明确证明旧 PID 不存在时才回收 abandoned lock。`current.json`、`observer_status.json` 和 `dashboard.html` 都用 temp → validate → atomic replace；HTML render 失败会保留上一份 last-good Dashboard。meaningful timeline/observation/alert/run/interpretation 默认永久保留，只按月无损 rotation 到 `history/<stream>/YYYY-MM.jsonl` 并维护 `history/index.json`，不做按时间删除。

机器层把 Execution、Progress、Health 分开：`waiting_external` 不等于故障；缺少明确分母时不生成百分比。continuation running 且 fresh lease 时可以健康，stale owner 为 warning，expired owner 为 critical；Observer 只报告，不执行 contention/recovery。Workstream 在不同 source 中出现不一致时保留 canonical identity 与所有来源，并提升 Alert，而不是静默挑一个版本当事实。

人类语义由 AI 负责解释，CLI 只提供确定性持久化合同：先从当前 snapshot 取得 Workstream 的 `semantic.source_fingerprint`，再使用 `observer interpret` 写入解释；如果底层 meaning-relevant facts 已变化，命令返回 `observer_semantic_source_changed`，旧解释在下一次 snapshot 中标记 `stale`，Dashboard 不继续把它当作当前事实。

```powershell
acf observer interpret . --workstream WS001 --source-fingerprint <fingerprint> `
  --human-title "人类可读标题" `
  --current-focus "当前在解决什么" `
  --why-now "为什么现在做" `
  --recent-proof "最近证明或排除的事实" `
  --implication "这些结果意味着什么" `
  --next-step "下一步以及为什么这样走" `
  --confidence high `
  --provenance "active/workstreams/WS001.md" `
  --json

acf observer glossary-set . --term "LM/TR" --human-term "LM/信赖域优化" `
  --explanation "利用局部模型和信赖域限制优化步长的方法。" `
  --confidence high --provenance "reference/Optimization.md" --json
```

confidence 支持 `authoritative / high / medium / low`；medium/low 会在展示层明确标记“当前理解/暂译”，canonical 原始名称始终保留。interpretation 以 append-only 版本历史记录，`observer history --stream interpretations` 可追溯 old/new interpretation、source fingerprint 和 provenance。结构化 Observer state 与 HTML 共用 credential-like 值过滤；API key、password、token、private key、license、fence token 等值拒绝写入或替换为 `[redacted]`。

Project Narrative 是 Workstream interpretation 之上的**项目级 derived semantic state**，不是新的 Markdown authority。`narrative-source` 只接受显式、项目相对的 authority 文件路径；它记录文件 content digest，并把稳定的 Workstream/continuation meaning projection 一起纳入 source fingerprint，不默认全仓扫描。`narrative-apply` 只负责机械验证/版本化/原子写入，要求 JSON 明确提供 `overall_goal`、architecture nodes/edges、milestones、`current_position`、confidence 和逐项 provenance/evidence；未知 node/milestone 引用、credential-like 文本或读取后 authority fingerprint 漂移都会 fail-closed。当前 narrative 写入 `semantic/project_narrative.json`，历史追加到 `semantic/project_narratives.jsonl` 并参与无损 monthly rotation；source 文件或相关项目 authority 改变后，下一次只读 snapshot 会把旧 narrative 标记 `stale` 并生成 warning Alert，而不是继续当作 current project story。

Dashboard 将 Project Narrative 与 Meaningful Timeline 明确分层：Project Map 展示 Overall Goal、Architecture Map、Logical Milestone Flow / Project Evolution、Current Position 和 milestone Evidence/Provenance；Workstream 卡片继续解释“现在”，Timeline 继续表达“最近发生了什么”。项目地图仍使用确定性 HTML/CSS、文本/符号和静态自包含数据，不引入 Mermaid/Graphviz/React runtime、CDN、HTTP server 或外部 fetch；颜色只做稳定语义引导，并始终同时保留文字状态。

`dashboard.html` 是纯静态、自包含、可直接 `file://` 打开的展示层，不启动 HTTP/daemon，也不依赖外部 CSS/JS/fetch。红色只用于 critical，琥珀用于 warning，绿色用于 healthy/verified，蓝色用于 active/info，灰色用于 canonical/历史/metadata；颜色必须同时配文字/符号，主标题约 24px、Workstream 标题约 17px，不用巨大字号制造重点。Observer structured state/history 中的 canonical 时间戳保持 UTC；Dashboard 头部和 Meaningful Timeline 等人类可见时间统一转换为北京时间 `UTC+08:00` 并明确标注，底层 UTC 不因展示需求改写。Dashboard 是派生视图，Observer structured state 才是观测事实层。

正式 production Observer scheduler 与开发/维护 Writer 必须分离。production task 才承担例行 snapshot/render；Maintenance 普通 wake 应先读取 `observer_status.json`、runs/current/history 与 Dashboard mtime 判断 watchdog 是否真实按期成功，不得为了维持 freshness 自己例行刷新，否则会掩盖 scheduler miss、data-age stale 和 Observer 自身故障。Maintenance snapshot 只用于诊断、修复后验证、release smoke、installed-state dogfood 或 migration，并应保留故障前 evidence。

Workstream source authority 以 primary lifecycle 为 project-level 边界：primary active detail 是主线当前 source，primary archive 表示该 Workstream 已进入历史终态，其他 linked/registered worktree 中残留的旧 Active detail 不得将其复活。Workstream 自己的 bound worktree 只有在 registry state=`active` 时才可作为当前专属 source；非 active registry 下优先 primary current/terminal source。unrelated registered worktree 仍保留在 worktree diagnostics 与历史 evidence 中，但不成为其他 Workstream 的 canonical semantic source；真正的 primary/bound active divergence 继续用 source consistency/Alert 显式暴露。

Observer Core 不硬编码 MCP 名称、电脑、盘符或项目实例。Scheduled Task 需要调用哪个项目访问工具由项目自己的 wrapper/adapter 决定；例如某个具体项目的 wrapper 可以指定一个 DevSpace connector，但该名字不能进入通用 Observer Core。开发 Observer 自身时，稳定安装态 ACF 继续作为 continuation canonical control plane，worktree 内 `uv run acf observer ...` 作为 product-under-test；先在 ACF 项目连续 dogfood 并收口高优先级 issue，再进入合并、PyPI 和全局稳定安装。

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

`acf doctor docs/ai --json` 是面向人和 AI 的上下文健康诊断入口。它复用 `check` 的结构校验结果，并额外报告跨文件生命周期漂移、终态 Workstream authority scope 残留、Workstreams / Archive generated index 漂移、Workstream 协议漏 `Merging`、Decisions_Index 摘要截断、Sources_Index 本地文件缺失、active 过厚、根目录探针输出和本地数据副本 hash / missing evidence。attention hygiene 复用 `review stale` 的机械 signals：Done 的非空 Current_Task / Task_Plan 分别报告 `current_task_terminal_retained` / `task_plan_terminal_retained`，Context 缺审阅标记或超过 stale 窗口分别报告 `context_missing_review_marker` / `context_review_stale`。这些 findings 只作为 warning / draft-only 建议，不进入 `check --strict`，不自动判断 Context 正文事实真假。`--projects` 可一次只读诊断多个项目，每个项目独立输出 summary、findings、check 和 next_actions。

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
