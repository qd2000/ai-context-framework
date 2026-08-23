# Bounded Continuation Control 设计

## 定位

`acf continuation` 为外部 AI 执行器、定时器或人工续跑提供一个**模型无关、调度器无关、用户级本地状态**的确定性控制层。

它解决长任务在多轮会话之间的恢复、单写者租约、人工暂停和 fail-closed 状态转换，不负责：

- 创建 ChatGPT Scheduled Task；
- 运行常驻 agent daemon；
- 保存聊天 transcript；
- 替代项目自己的 Task Plan、Workstream、Git checkpoint 或科学 checkpoint；
- 自动决定下一项技术路线。

外部执行器负责“何时唤醒和做什么”，ACF 只负责“当前是否允许继续、谁拥有本轮写权限、恢复状态在哪里”。

## 为什么属于 ACF

该能力跨项目复用，并直接依赖 ACF 已有的项目发现、Workstream/worktree 身份验证和用户级 `~/.acf` 状态根。若把它放在单个业务仓库中，会导致每个项目复制控制器，或要求业务 worktree 为了获得控制工具同步业务主线。

放入 ACF 后，任意已经存在的 worktree 都可以直接执行 `acf continuation init`，不需要重建 worktree，也不需要为了控制工具合并该任务分支。已有 dirty 不再等价于冲突：初始化会把当时的 Git dirty 记录为受保护的 `baseline_external` workspace baseline；ACF 不会自动清理或提交这些外部修改。

## 状态位置

Continuation 运行态不写入项目仓库，默认位于：

```text
~/.acf/
└─ projects/
   └─ <worktree-name>-<path-hash>/
      └─ continuation/
         └─ <task-id>/
            ├─ state.lock
            ├─ control.json
            ├─ state.json
            ├─ lease.json
            ├─ workspace.json
            ├─ pause.json
            └─ last_run.json
```

项目内长期事实仍保留在普通 Markdown、Git 和项目自己的 evidence/checkpoint 中。`state.json` 只保存有界当前状态和引用。

## 命令面

```text
acf continuation init
acf continuation doctor
acf continuation coordination status
acf continuation coordination attempt
acf continuation coordination challenge
acf continuation claim
acf continuation assert-owner
acf continuation heartbeat
acf continuation progress
acf continuation effect prepare
acf continuation effect update
acf continuation effect list
acf continuation workspace status
acf continuation workspace intent
acf continuation workspace refresh
acf continuation reconcile
acf continuation recover
acf continuation renew
acf continuation checkpoint
acf continuation release
acf continuation pause
acf continuation resume
acf continuation prompt
acf continuation issue
```

`init` 从当前 Git HEAD 建立控制状态并捕获 bounded workspace baseline。初始化前已经存在的 tracked/untracked dirty 会作为 `baseline_external` 记录路径、Git status 和 digest；这些修改保持原样，不进入 continuation 自己的提交。可选 `--workstream WSNNN` 时，同时验证 ACF registry、path、branch 和 Git common-dir；没有 Workstream 的普通项目也可只用 `--task-id`。

`doctor` 只读核对 Git top-level、branch、dirty 状态、可选 Workstream identity、pause、lease 和 compact state，并返回 `can_claim`。带 heartbeat 的 active lease 会按配置的 renew interval 区分 `fresh` 与 `stale`；stale 同时暴露 `orphan_candidate=true`，但仍然 `can_claim=false`，因为“没有新鲜 heartbeat”只能证明需要 reconciliation，不能证明接管安全。旧版没有 heartbeat/generation 的 active lease 返回 `legacy_unknown` 并继续保守阻塞。

`coordination attempt` 为每个到达 runner 记录 compact `attempt_id / started_at / objective_summary`；这里的 summary 只是当前 goal label，受字节上限约束，但不定义单次 execution 的工作量边界。没有 owner 时 attempt 只是 `claim_candidate`。有 fenced owner 时先看 lease liveness：`fresh` owner 返回 `live_owner_observed`，登记 contender observation 但**不自动 challenge**，并暴露 `duplicate_wake_safe_to_yield=true`；只有 `stale / legacy_unknown` owner 才自动 open/join 当前 owner generation 唯一的 nonterminal challenge。显式 `coordination challenge` 仍可在调用方有独立理由需要重新确认 owner 时使用；challenge 不授予写权限，也不证明 owner 已死亡。任何可定位到项目的普通 ACF 命令都可以在 stderr opportunistic 提示当前 pending challenge，但该 probe 只读、不更新 coordination state，也绝不能冒充 ACK。只有 owner-protected continuation 命令在 `lease_id + generation + fence_token` 校验成功后才记录 authenticated owner activity；正常 release 单独把 challenge 解析为 `owner_released`。deadline 到期只得到 `timed_out / ownership_forfeiture_candidate`，后续仍需 formal reconcile workspace/HEAD/effect/identity；ACK/reconcile/recover 继续共享 continuation state lock 与 generation fencing，因此竞态最多产生一个 writer。

`claim` 在本地 OS 文件锁保护下取得单一 active lease；第二个执行器看到 active lease 时不能 claim 或写 worktree，但可以作为 contender 登记 attempt/challenge 并等待 authenticated response、owner release 或 formal recovery。新 claim 会把 control generation 单调递增，并返回 `lease_id`、`generation` 与高熵 `fence_token`；磁盘只保存 fence token 的 SHA-256 hash，不保存原 token。`fence_token` 是本轮 owner credential，只能保存在当前执行器的私有运行上下文，不得复制到项目文件、普通日志或 handoff 文档。

`assert-owner` 对 active lease 的 `lease_id + generation + fence_token` 做所有权校验。owner-protected continuation 命令在凭据验证成功后会执行 authenticated coordination touch，因此可以响应当前 generation 的 pending/timed-out challenge；错误凭据和普通 ACF 命令都不能 ACK。新 generation 生效后，旧 owner 的 `assert-owner`、`heartbeat`、`renew`、`checkpoint` 和 `release` 都会被确定性拒绝。该 fencing 保护的是 ACF continuation 控制协议；它不能阻止绕过 ACF 直接写外部系统，因此 non-idempotent 外部动作仍应在动作前显式 assert-owner。

`heartbeat` 只刷新 `last_heartbeat_at`，用于证明 runner liveness，不延长 `expires_at`。`renew` 在校验 owner 后同时刷新 heartbeat/renew 时间并延长同一 lease TTL，不改变外部调度周期。stale heartbeat 本身永远不授权接管。

`progress` 把当前 fenced round 的执行状态记录在用户级 `rounds.json`。核心 phase 只使用 runtime-neutral 的 `claimed / executing / waiting_external / finalizing / reconciling / released`，并允许 bounded milestone/evidence refs；不保存 runtime-specific phase、raw output 或 transcript。round journal 只保留有限条目，超过上限时只允许裁掉已经 `released` 的旧 round，不能为了腾空间丢掉未收口现场。

Workspace ownership 保存在用户级 `workspace.json`，只记录 bounded path/status/content digest metadata，不保存完整文件内容或完整 diff。v2 manifest 把任务自身未提交 WIP 从“当前 runner 临时 dirty”提升为跨 generation 的 `task_owned` ownership；active owner 在修改项目文件前用 `workspace intent --path <concrete-path>` 声明有限 write intent，绑定 Workstream 时 intent 必须命中该 Workstream 的直接 write scope。`workspace refresh` 重新观察 Git 并区分：

- `baseline_external`：claim 前已存在的受保护外部 dirty；只要不与本轮 write intent 重叠，外部 owner 后续继续修改该路径时 refresh 只更新观测 digest，不制造假并发冲突；
- `task_owned`：位于已声明 write intent 下、可归属当前 continuation task 的修改；既可以由当前 generation 新产生，也可以从前一 generation 正常 handoff / formal recovery 继承；
- `unexpected_nonoverlap`：claim 后出现、但与 baseline/write intent 不重叠的外部 dirty；
- `conflict`：write intent 与受保护 baseline/external dirty 同路径或父子路径碰撞、路径所有权无法解释，或其他 ownership evidence 出现歧义等真实冲突；单纯的非重叠外部继续编辑不是冲突。

`doctor` 不使用 worktree-level `clean/dirty` 参与 liveness、并发或 claim 判断。Git 只提供具体 path/status/content digest 观测；manifest valid 且无真实 conflict 时，即使存在 task/external 修改也允许继续。没有 workspace manifest 的 legacy task 如果存在 changed paths，不报告笼统 `worktree_dirty`，而报告 `workspace_provenance_missing`；没有 changed paths 的 legacy task 可在下一次 claim 时惰性建立 manifest。

正常 release 使用 workspace handoff，而不是强制 Git clean：当前 write intent 下仍存在的修改固化为 `task_owned`，本轮非重叠 external 变成下一轮受保护 external baseline，lease 可以正常删除且 state 转为 `ready`。下一 generation claim 会验证 ownerless window 内 `task_owned` 的 path/status/digest 未漂移并继承对应 WIP/write intent；如果这段 ownerless window 中 task-owned path 被未知方改变，则报告 `task_owned_handoff_drift` / `workspace_conflict`。因此 continuation checkpoint 与 Git commit 完全解耦：前者负责恢复/换轮，后者只在功能或阶段形成自然语义 checkpoint 时创建。

外部/non-idempotent work 使用 write-ahead effect contract。`effect prepare --key <logical-key> --kind <generic-kind>` 在动作之前写入 deterministic effect id；同一 task + logical key + kind 得到稳定 identity。只有返回 `created=true` 的首次 prepare 才允许执行外部动作；`created=false` 表示 effect 已经存在，必须复用、查询外部 authority 或进入 reconciliation，不能再次 submit。`effect update` 只记录 generic `prepared / active / completed / failed / unknown` status、可选 external id、milestone 与 evidence refs；terminal status 不允许重新回到 active。current `effects.json` 仍有固定记录/字节边界且 schema 不接受 raw output/transcript；达到边界时只允许把完整 `completed|failed` records rollover 到 bounded `effects.archive.NNNNNN.json` segments，`prepared|active|unknown` 永不归档。所有 archive 仍参与 logical-key duplicate detection，所以 rollover 不删除 durable replay identity；若 unresolved records 自身耗尽容量则继续 fail-closed。

只要 `state=running` 的 lease 已过期且 effect journal 非空，`doctor` 返回 `effect_reconciliation_required` 并保持 `can_claim=false`，防止普通 re-claim 绕过 durable side-effect evidence。没有 round/effect journal 的 v0.0.3.61 task 仍可保守读取。

`reconcile` 默认只读，不会“猜旧 runner 已死”。它基于当前 lease/liveness、HEAD、round/effect journal、workspace ownership manifest、coordination digest 和调用方显式 assertion 生成 `eligible|blocked` decision：没有匹配 timed-out challenge evidence 时，fresh active owner 无条件 blocked，stale 或 `legacy_unknown` active owner 必须显式 `--owner-ended` 并提供 evidence；匹配当前 owner generation 的 `ownership_forfeiture_candidate` 可以替代这项 ownership-ended assertion，但绝不跳过其他安全门。lease HEAD 与 current HEAD 不同必须用 `--accept-head <current-head>` 精确接受并附 evidence；任何未被显式 terminal reconciliation 覆盖的 `prepared/active/unknown` effect 仍 blocked。已有 durable external id 的 effect 必须 identity-match；prepared/no-id effect 可走明确证明 submit 从未启动的 `--effect-not-started`；已经执行的本地确定性 no-id effect 则可在调用方提供 durable local authority evidence 时走 `--effect-local-terminal`。后者只接受 `prepared|active`、没有 external id 的记录，`unknown`、已有 external id 或证据不足继续 fail-closed。worktree-level dirty/clean 不进入 decision；只要 workspace manifest 可验证、generation 与 interrupted owner 一致且没有真实 conflict，`baseline_external`、`unexpected_nonoverlap` 和可证明 `task_owned` 都可进入 formal recovery。缺失 provenance、generation 漂移或真实 ownership conflict 才 fail-closed。`--record --reason ...` 才把 observation、assertions、effect summary/digest、workspace ownership digest、coordination digest 和 evidence refs 写成用户级 reconcile receipt。

`recover --reconcile-id ... --runner-id ...` 只消费 recorded eligible receipt。执行前重新计算整个 observation；lease state/id/generation、liveness class、HEAD、state status、round/effect digest 或 workspace ownership digest 任一变化都会返回 `reconciliation_stale`，要求重新 reconcile。成功后旧 round（若为 fenced round）以 `reconciling/superseded_by_recovery` 收口，新 lease generation 单调递增并返回新的 fence credential；workspace manifest 同步转移到新 generation，保留原 write intents 与可证明的 `task_owned` WIP，同时继续保护不重叠的 baseline/external dirty；恢复动作不会 stash/reset/clean，也不会为了换轮次自动提交 task/external WIP。`last_recovery.json` 只记录 compact recovery identity/digest。因此旧 owner 即使随后复活，也无法 heartbeat/renew/checkpoint/release 新 generation。`reconcile/recover` 只确定性执行调用方已经明确提供的 evidence assertion，不自动裁决外部事实。

时序参数彼此独立，不再用 renew interval 推导 runner stale：

- `standard`：scheduler interval 60 分钟、lease TTL 120 分钟、renew 30 分钟、heartbeat 建议 10 分钟、stale threshold 30 分钟；
- `long-running`：scheduler interval 60 分钟、lease TTL 180 分钟、renew 45 分钟、heartbeat 建议 10 分钟、stale threshold 25 分钟；
- 最大单次 TTL：24 小时。

新 task 可用 `acf continuation init ... --profile long-running`；已有 task 使用 `acf continuation configure ... --profile long-running` 原位更新 timing control，不重建 state/workspace manifest，也不要求 `init --force`。`configure` 在 active lease 存在时拒绝修改，避免外部控制面在 owner 运行中改变 liveness 语义；需要自定义 cadence 时可对 profile 再显式覆盖 `--interval-minutes`、`--lease-ttl-minutes`、`--renew-interval-minutes`、`--heartbeat-interval-minutes`、`--stale-after-minutes`。heartbeat 只更新 `last_heartbeat_at`，renew 才延长 lease expiry。

`checkpoint` 只覆盖一个 bounded `state.json`。状态最大 64 KiB，列表最多 64 项，单项最大约 4 KiB；`transcript/history/raw_output/tool_output/stdout/stderr` 等字段在任意嵌套层级都拒绝。历史型 `completed / evidence_refs / verification` 是**当前恢复摘要的 rolling window**，不是长期历史账本：append 后超过 64 项时确定性保留最近 64 项，完整长期证据继续由 Git、round/effect/coordination journal、项目 worklog/artifact 等权威层承担。`constraints / open_questions / plan_refs` 可能仍直接影响后续安全与计划，因此不做自动裁剪，超过 64 继续 fail-closed。为兼容旧版本已经写出的 current-schema history-list overflow，读取 state 时也会先在内存中对三个 history list 做最近窗口裁剪，使 `prompt / doctor / reconcile` 能继续工作；下一次合法 state write 再持久化 compact 结果。裁剪前仍扫描全部旧条目的 forbidden raw-history 和单项大小，所以非法旧条目不能靠落出窗口逃逸；非 list 类型或无法通过其余 schema 校验的状态也继续 fail-closed。

`release` 的收口规则：

- workspace manifest valid 且无真实 conflict → 写 last-run receipt；`task_owned` 未提交 WIP 与 external dirty 都可保留，显式 `--final-status` 时进入指定状态，未显式指定时只把仍为 `running` 的 state 转为 `ready`；删除 lease；
- release 时把仍存在的 task-owned path/status/digest 和必要 write intents 固化为 handoff metadata；下一 claim 验证它们在 ownerless window 未漂移后继承；
- 存在 workspace conflict / ambiguous provenance → 进入 `reconciling`，删除 lease并禁止下一轮自动 claim；
- 没有 workspace manifest 的 legacy task 若存在 changed paths → 以 `workspace_provenance_missing` fail-closed，而不是根据全局 dirty 布尔值裁决；
- active round 期间收到 pause → release 后进入 `paused`。

`issue` 用于记录**可复用的 ACF / continuation / 自动化工作流缺口**，不是业务任务自己的科学失败日志。事件写入用户级 ACF usage log，包含 task/workstream/stage、分类、严重度、简短描述、证据引用和稳定 fingerprint；相同 fingerprint 的多次出现保留为 occurrence，查询时自动聚合计数。修复确认后可用 `acf continuation issue ... --resolve-fingerprint <fingerprint> --text <resolution>` 追加 resolution event，不篡改历史 occurrence；`acf log issues --open-only` 只显示 open 项。同 fingerprint 后续再次出现时自动 reopen。

显式 `--task-id` 指向不存在的 continuation task 时，CLI 返回 `continuation_task_not_found`，并在 `details.available_tasks` 给出当前 worktree 已配置的 task id，避免 AI 把 task-id 拼写错误误判为 control 文件损坏。

标准 `acf continuation prompt` 是唯一 generic Scheduled Task protocol 权威，但 `.72` 不再每次渲染整份状态机手册。`prompt --runner-id <runner>` 先读取当前 doctor/status authority，并稳定返回 `owner_context`；generated prose 的 always-on 层只展示 overall objective、stage/status、authority refresh、default execution plan、continuous execution / hard-stop contract、owner 摘要与当前 relevant actions，claim、duplicate-owner、stale/expired recovery、workspace provenance、unresolved effect 等细节只在当前状态相关时 progressive disclosure。未传 `--runner-id` 且存在 fresh owner 时返回 `fresh_owner_caller_unknown`，不会把 caller 武断判为 owner 或 duplicate。外部 wrapper 不复制 generic 状态机细节，但也不追求“越薄越好”：它必须完整承担 exact existing workspace / project-access tool mode、stable ACF upgrade-adaptation、authority refresh、execute generated plan、owner 用户可见说明和项目专用 Runtime/resource/permission/security/scientific/validation/issue-reporting 约束。只有发现具体、可复用、证据支持的产品或工作流问题时才调用 `acf continuation issue`；healthy duplicate overlap、active lease no-op、正常等待、业务模型未收敛等预期状态不得当作产品 issue。

generated prompt 使用 goal-directed continuous execution，而不是把 scheduler wake、bounded Gate 或某个局部里程碑当成 Agent 工作量限制：scheduler wake 只负责从持久状态恢复持续任务，不定义独立工作回合、汇报周期、工作配额或预期停止点；bounded 只约束 ownership、写入范围、外部副作用和恢复风险。`.72` 将 `state.next_action` 从“仅恢复 hint”细化为“**authority refresh 后仍有效时的默认执行计划**”：newer Git/PLAN/Runtime/effect authority 可以覆盖它，否则 Agent 应执行而不是只读取、解释或汇报；完成 default plan 后仍需根据总体目标继续选择安全、有价值的下一步，因此它仍不是 work quota。Agent 在有效 ownership 内自主决定工作范围、执行顺序、实现策略和验证深度。checkpoint、Git commit、Gate 与成功测试只保存/证明进度，不产生 session-end 信号。final assistant response 本身会结束当前 execution session，因此不能为了汇报进展、已经运行了一段时间、完成了若干步骤、上下文看起来很长或主观感觉“该收尾了”而触发。某个动作被 fail-closed 只禁止该动作，Agent 应继续安全诊断、证据核查、issue 记录、规划、测试或其他不冲突工作。

任务级硬停止条件固定为四类：总体目标真正完成；用户明确暂停；需要新的人工授权、凭据或不可替代决策；配置的项目访问工具或连接（例如 DevSpace）经合理重连仍不可用。另一个 authenticated owner、durable external wait 或某个 fail-closed 动作只有在它们实际阻断了当前所有安全、有价值、非冲突工作时，才构成 execution-session handoff 理由；否则继续推进可做的工作。platform boundary 只有在平台、系统或工具明确发出当前执行即将终止的信号时才成立，不能由 elapsed time、tool-call count、context length、已完成工作量或“该汇报了”的主观判断推断。任何 execution-session handoff 都不等于 mission 的 paused、blocked_human 或 done；正常自愿 handoff 时，live owner 应在 final response 前完成必要刷新/checkpoint 并 release，避免把网页回复结束变成 stale owner。

`continuation prompt --json` 稳定暴露 `identity`、`current`、`owner_context`、`resume_context`、`execution_policy`、`project_context`、`scheduler_wrapper_contract` 和当前 `next_actions`。`execution_policy` 在既有字段上新增 `next_action_is_default_execution_plan=true`、`next_action_requires_authority_refresh=true`、`next_action_may_be_superseded_by_newer_authority=true`、`active_lease_requires_liveness_verification=true`、`verified_duplicate_owner_may_end_duplicate_wake=true`、`duplicate_wake_exit_is_task_stop=false`、`stale_owner_requires_recovery=true`、`contender_must_create_busywork=false`，同时保留 `next_action_is_work_quota=false`、`final_response_is_terminal=true` 等语义。`scheduler_wrapper_contract.bootstrap_policy=sufficient_high_salience` 并列出 wrapper 必须覆盖的 bootstrap topic；`copy_generic_state_machine=false` 保持 generic state machine 单一权威。

生成 prompt 仍输出当前 timing profile 与五个时序参数，但把它们放在 ownership liveness 规则中，并明确这些数字只管理 lease TTL/heartbeat/renew/stale，不是工作量、执行时长目标、汇报周期、session 边界或 Gate 的硬截止时间。项目 Scheduled Task 不应冻结一份手写 generic recovery 状态机；wrapper 只保留固定 worktree/branch/task-id、每次 wake 的 prompt 入口和项目专用约束，每次重新消费当前安装态 `acf continuation prompt`。

## ACF_HOME schema discovery 与迁移

continuation runtime state 统一位于 `ACF_HOME/projects/<root-slug>-<path-hash>/continuation/<task-id>/`；path hash 用于隔离同名仓库/不同 worktree，task_id 再作为项目 namespace 内的任务键。`ACF_HOME` 只允许整体替换根目录，项目不能复制一套私有 state 实现。

`acf continuation list` 是只读 schema/discovery 入口：当前项目模式按 control 中的 `workspace_root` 精确过滤，`--all-projects` 扫描全部 namespace；输出明确区分 `task_id` 与 `workstream_id`，并报告 control generation、timing profile、control/state/workspace/round/effect/coordination/reconcile/recovery 等文件的 schema compatibility。`doctor` 在 task 可正常加载时复用同一 contract 返回 `state_compatibility`，因此升级问题不会再伪装成普通 owner/workspace 故障。

schema migration 必须显式、可审计、history-preserving。当前只对代码明确支持向后兼容的 legacy workspace schema 提供 `continuation migrate --dry-run` / `--apply --reason`：apply 要求没有 lease record，只重写目标 schema 文件并写 `last_migration.json` receipt；control/state/rounds/effects/coordination/reconcile/recovery/last-run 等历史文件在 lock 内以 byte digest 证明未被改写。未知、future 或损坏 schema 不自动猜测，也不通过 `init --force` 静默抹掉历史，继续 fail-closed。

## Dogfood 可观测性与问题积累

ACF 使用两层用户级日志，不要求用户把多个聊天的问题重新手工汇总：

1. **usage event**：`continuation`、`worktree` 等 CLI 命令自动记录 command、exit code、error code、duration 和 changed files；
2. **continuation issue**：agent 在真实 dogfood 中发现可复用缺口时写结构化 issue event。

查询入口：

```text
acf log summarize <project> --errors-only --json
acf log issues <project> --json
acf log issues --all-projects --json
acf log issues --all-projects --open-only --json
acf log projects --json
```

`log issues --all-projects` 按 fingerprint 聚合不同 worktree / 任务中的相同问题，输出 occurrence count、首次/最近出现时间、最高严重度、tasks/projects、相关命令、evidence refs 与 `open|resolved` lifecycle。多任务并行运行产生的经验可以直接作为下一轮 ACF 改进的输入。

## 固定小时调度与租约

外部 Scheduled Task 可以固定每小时一次，无需由 ACF 动态改时间。租约不是调度器，而是本地并发安全门；一次 scheduler wake 只是恢复持续任务的入口，当前 execution session 可以在同一有效 lease 中连续推进多个自然完整工作步骤，只需按当前 timing 做 heartbeat/renew，不因完成一个 Gate、测试、commit 或 checkpoint，也不因为“该汇报本次结果”而人为结束。只有具体事实使当前 session 无法继续安全有价值工作，或平台/系统/工具明确发出当前执行即将终止的信号，才进入 handoff：

```text
每小时触发
    ↓
doctor
    ↓
coordination attempt
    ├─ fresh owner → live_owner_observed → 不自动 challenge、不写 worktree
    │      ├─ 当前 runner-id = owner → 继续当前 writer session
    │      └─ 当前 runner-id != owner → verified duplicate wake；可让行结束本重复 session，mission 继续
    ├─ stale/legacy-unknown owner → contender + open/join challenge → 不写 worktree
    │      ├─ owner authenticated touch → owner_active → 回到 fresh owner 语义
    │      ├─ owner release → owner_released → 重新 doctor/attempt
    │      └─ challenge timeout → ownership_forfeiture_candidate → formal reconcile
    ├─ expired running + effect records → effect_reconciliation_required → reconcile
    ├─ paused/reconciling/真实 workspace conflict → no-op
    └─ no owner + can_claim=true → claim → 持续推进总体目标，真正交接时再 release
```

因此本地 worktree 不依赖外部平台未文档化的并发、顺延或重试语义保证单写者。

## 长计算

Continuation lease 只保护当前 AI 轮次的仓库写所有权。小时级或更长计算应由项目自己的 background job/runtime 承担：启动作业并保存 `job_id`/checkpoint/manifest，将 continuation state 设为 `waiting_external` 后 release；后续轮次检查同一个 job，不重复提交。

## 恢复事实源

建议每轮按以下顺序恢复：

1. 项目 `AGENTS.md` / 当前规则；
2. `acf continuation doctor`；
3. 项目当前计划 / Workstream；
4. Git HEAD/status/checkpoint；
5. continuation `state.json` 中的 `next_action` 与 evidence refs；
6. 只有本地事实缺失、冲突无法消解或用户明确要求时，才读取历史聊天。

Continuation 状态不是 transcript cache，而是低噪声恢复索引。

## 安全边界

- `init` 捕获已有 dirty 为受保护 baseline，不要求为了 continuation 人工清空整个 worktree；
- 不自动 stash/reset/clean/rebase/force/push；
- `workspace intent` 只接受具体路径；绑定 Workstream 时必须落在直接 write scope 内；与 baseline/external dirty 同路径或父子路径碰撞时拒绝 intent；
- active round 的非重叠 external dirty 可以共存；task-owned WIP 也可以在未 Git commit 的情况下正常 release/claim 跨 generation handoff。ACF 不自动提交两者；
- active lease 不可被第二个 claimant 覆盖；后续 runner 只能作为 contender 登记 attempt/challenge，challenge 本身不授予写权限；
- 普通可定位项目的 ACF 命令只读提示 pending challenge，不构成 authenticated response；
- challenge timeout 只形成 ownership forfeiture candidate，仍必须 formal reconcile，并由 coordination digest + generation fencing 处理 ACK/recover race；
- fenced round 的 owner credential 只返回给 claimant，持久态只保存 hash；
- generation 前进后，旧 owner 的 heartbeat/renew/checkpoint/release 必须失败；
- stale/orphan candidate 只触发 reconciliation 信号，不允许自动 steal；
- reconcile receipt 只在当前 observation 未漂移时有效；workspace path/status/content digest 变化也会使 receipt stale。可证明的 task-owned WIP 已纳入 normal handoff 与 formal recovery，并由新 generation 继承原 write intent/ownership；fresh owner、provenance missing、workspace conflict、generation 漂移、未接受 HEAD advance 或 unresolved effects 仍不可 recover；
- pause 不强杀外部进程，只阻止 renew，并在 release 收口；
- malformed lease/state fail-closed；
- Workstream 绑定可选，绑定后必须通过 registry/path/branch/common-dir 验证；
- ACF 不调用浏览器、不读取 ChatGPT 历史，也不负责 Scheduled Task 产品生命周期。

## Dogfooding

2026-08-16 已使用开发版 ACF 对 FCC `WS088` 的既有 worktree 完成：

```text
init → doctor → claim → renew → checkpoint → release → doctor
```

验证结果：复用现有 `codex/ws088-chatgpt-web-scheduled-devspace`，未重建 worktree；ACF worktree 身份验证通过；运行态只写用户级 `~/.acf`；WS088 HEAD 保持 `8e2729a2...`；结束后 worktree clean、lease absent、`can_claim=true`。

后续 WS088 已继续通过无人值守只读 Scheduled Task、真实写入/commit/checkpoint/release、expired-lease 恢复和既有 WS082 worktree 直接 adoption smoke。并行任务正式接入后，新的产品问题通过上述 usage/issue 双层日志持续积累。

2026-08-17 的 WS007 自身 Scheduled Task 又形成了真实 orphan dogfood 现场：旧 runner 获取 lease 并留下 WS007.2 dirty 修改后，后续独立调度轮次只能对仍处于 120 分钟 TTL 内的 `running` lease 安全 no-op；旧 lease 没有 heartbeat/generation，因此开发版只能保守分类为 `legacy_unknown`，无法从控制面证明旧 runner 是否仍 live。该案例直接验证了“TTL active 不等于 runner live”，也是 heartbeat/fencing 这一阶段的验收证据；在正式 reconcile/recover 完成前仍不允许据此自动接管。
