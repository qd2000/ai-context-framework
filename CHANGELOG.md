# 更新日志

本文件记录 ACF 稳定版本的用户可见变化。完整实现证据、测试矩阵和 Workstream 归档仍保存在 `docs/ai/archive/workstreams/` 与 `docs/ai/worklog/`；本文件只保留发布级摘要。

## Unreleased

## v0.0.3.82 — 2026-08-25

### Project Map and maintenance hardening

- Project Observer 新增 provenance-bound Project Narrative / Project Map：从显式 authority source 生成版本化 derived narrative，在静态 Dashboard 中展示 Overall Goal、Architecture Map、Logical Milestone Flow / Project Evolution 与 Current Position；source fingerprint 变化后旧 narrative 自动 fail-visible stale，仍保留 canonical Workstream、timeline 与 provenance。
- `acf continuation checkpoint` 新增精确、证据绑定的 `--supersede-constraint` 与 `--resolve-open-question`，允许 newer authority 收口已经失效的 compact-state constraint/open question；只允许删除当前确实存在的精确文本，并要求 `--evidence-ref`，避免旧高显著提示在后续 scheduler wake 重新把任务带回错误阻塞。
- Windows `scripts/install_acf.ps1` / `scripts/update_acf.ps1` 在修改全局 `uv` tool 前先检测仍占用 ACF tool environment / launcher 的进程并 fail-closed；更新脚本改用未固定版本的 `uv tool install --force --upgrade`，避免 exact-version receipt 阻止发现新稳定版，并支持 `-Reinstall` 修复中断安装。
- 新增 Windows fake-uv/process-lock regression，覆盖 unpinned latest discovery、reinstall 与“存在真实 tool-env 进程时在任何 uv mutation 之前拒绝更新”；continuation retirement 也加入成功、证据要求和 noncurrent-item 拒绝回归。

## v0.0.3.81 — 2026-08-25

### Dynamic continuation user directives

- 新增 `acf continuation directive add|list|show|adopt|resolve|supersede`，为长时间 continuation 提供用户级、可审计的 live-steering inbox；第一版 kind 固定为 `requirement / priority_change / constraint / plan_change`，CLI 只机械记录、校验和迁移状态，不把自然语言自动裁决成项目事实或第二套 Task Plan。
- directive journal 位于用户级 continuation namespace，事件历史 append-only；原始输入不会被 resolve/supersede 静默覆盖。实现加入 active inbox、事件数、单项和总字节容量边界，并拒绝 credential-like 文本进入 durable state。
- `supersede` 作为单个原子 replacement 保持 active-inbox 净增长为零；即使 inbox 已到 64/64，也可以一换一替代已有 pending/adopted directive，而不会因先创建 replacement 的瞬时中间态误触容量拒绝。
- `continuation prompt --json` 新增 `directive_context`，pending directive 明确高于旧 persisted `next_action`；claim 保存当时看到的 directive revision/digest，heartbeat 与 renew 返回 change signal，使长 session 能在下一次 scheduler wake 前发现用户 steering。
- README、Automation、项目/模板 System Manual 与 continuation schema/inventory 同步；focused directive lifecycle、supersede、prompt/heartbeat/renew steering、secret refusal、active-inbox capacity、inventory/schema 回归以及 WS012 file-scoped guard、template/strict/diff checks 通过。

## v0.0.3.80 — 2026-08-24

### Long-lived Maintenance closeout

- 长期 `Maintenance` Workstream 在 release merge 后可通过 ACF 状态机从 `Merging` 回到 `Active`，不再需要绕过状态机手工恢复，从而消除 post-release reactivation 期间的 lifecycle mismatch。
- `acf worktree merge` 的 integration cleanup 改用 semantic Git status：真实 staged/untracked/delete/rename/mode/unmerged 或内容变化仍 fail-closed 保留；只有 tracked `M` 且 normalized content 无差异的 stat-only 路径会被识别为可再生噪声，并仅在这种语义干净场景下对临时 integration worktree 使用 `git worktree remove --force`。
- Project Observer 的 semantic source fingerprint 现在纳入 continuation ownership generation 与 unresolved effect risk：正式 recovery/owner generation 切换，或 prepared/active/unknown effect 的风险状态变化，都会让可能失真的旧人类语义立即变为 stale；heartbeat 与仅增加的 terminal effect 历史计数仍被排除，避免无意义的语义抖动。
- 新增 deterministic regression 覆盖 `Merging -> Active` Maintenance reactivation，以及 uv/check 风格 stat-only rewrite 后 integration worktree 能被安全清理；完整 555-unit regression 与 WS012 file-scoped guard 通过。

## v0.0.3.79 — 2026-08-24

### Worktree reactivation anchors

- 修复长期 Workstream 在 release merge 后重新 `worktree attach --apply` 时的 reactivation/sync 死锁：重新绑定已有 registry 记录时保留原有 `base_commit` / `reservation_commit` Git anchor，不再把尚未进入 source branch 的最新 primary HEAD 写成新的 reservation authority。
- `worktree sync` 随后可正常把当前 primary 合入长期 source worktree；新增 deterministic regression 覆盖“primary 已前进、existing binding 重新激活、attach 验证通过、sync 成功推进 source”的完整生命周期。

## v0.0.3.78 — 2026-08-24

### Observer Workstream source authority

- 修复 registry-managed 多 worktree 项目中的 ghost Workstream：primary checkout 已将 Workstream 归档后，其他 registered worktree 残留的旧 Active detail 不再把该 Workstream 重新投影为 current；primary archive lifecycle 是终态 authority。
- bound Workstream worktree 只有在其 registry state 为 `active` 时才可作为当前 Workstream source；registry 已 `merged` 等非 active 状态时，primary current/terminal source 优先，避免 stale bound detail 覆盖主线终态。
- unrelated registered worktree 仍保留在 worktree diagnostics/历史证据域，但不再作为其他 Workstream 的 canonical semantic source；真实 primary/bound active source divergence 继续 fail-visible。
- 新增真实 Git worktree/registry 回归，并用 ACF 项目 candidate dry-run 验证：修复后 current 只投影 `WS012:Active`、alerts 为空，旧 WS011 不再 ghost-resurrect。

## v0.0.3.77 — 2026-08-24

### Archived Workstream recovery scope

- 修复 Workstream 已由 `acf workstream archive` 确定性移入 `archive/workstreams/`、但 archive Git checkpoint 前 owner 异常结束时的 continuation 恢复死锁：recovered fenced owner 现在可以从经过 schema 校验的 archived Workstream detail 恢复原 direct write scope，而不要求重新创建 active Workstream。
- 对 archived bound Workstream 只额外开放本次归档所需的四个精确 lifecycle authority 路径：`active/Workstreams.md`、原 `active/workstreams/WSxxx.md`、`archive/Archive_Index.md` 与 `archive/workstreams/WSxxx.md`。这条恢复路径只服务已经发生的 ACF-managed archive WIP，不扩大普通 Task authority，也不放宽 `unexpected_nonoverlap` 的 durable evidence / provenance / conflict 检查。
- 新增回归覆盖 archived detail fallback 与精确 lifecycle scope，并用 WS011 自身 interrupted archive closeout 真实复现验证该缺陷。

### Observer Dashboard 北京时间展示

- Observer structured state、history 与 semantic 的 canonical 时间戳继续统一保存为 UTC，不改写排序、去重、fingerprint 或 provenance；仅在人类可见的静态 `dashboard.html` 中，把“最后观察”和 Meaningful Timeline 等时间统一显示为北京时间 `UTC+08:00`。
- Dashboard 明确标注“北京时间 (UTC+08:00)”，并新增回归验证 `2026-08-24T01:51:10Z` 在可见 HTML 中渲染为 `2026-08-24 09:51:10 北京时间 (UTC+08:00)`，同时内嵌 canonical JSON 仍保留原 UTC 值。

## v0.0.3.76 — 2026-08-24

### Continuation autonomy and recovery-prompt alignment

- 修复长时 Scheduled Task 的自激式续跑：当 authority refresh 后的 `next_action` 明确要求“等待下一次真实外部/项目状态变化”且该条件尚未满足时，generated continuation prompt 不再把 scheduler wake、`coordination attempt` 或 `claim` 本身当作可执行进展；这些动作属于 control-plane bookkeeping，不能用来人为制造一个新的 lifecycle change 再让 Observer 观察自己。
- `execution_policy` 新增 `claim_requires_present_safe_useful_work=true`、`control_plane_activity_satisfies_wait_condition=false` 与 `no_useful_work_may_end_wake_without_claim=true`。如果当前确实没有满足条件的安全、有价值工作，单次 scheduler wake 可以在**不 claim、不改变 task 状态**的前提下结束；一旦真实 authority 变化或存在其他可执行工作，仍按原有 fenced ownership 协议 claim 并持续推进。
- generated prompt 同步当前稳定恢复合同：对于没有外部标识、但已由 durable local evidence 明确证明终态的本地确定性 effect，可按现有 evidence-backed local-terminal 恢复路径处理；不确定或外部 effect 继续保持 fail-closed，避免实现能力和 AI-facing guidance 漂移。

## v0.0.3.75 — 2026-08-23

### Active local-effect ownerless recovery

- 修复 Scheduled Task 在本地确定性 dogfood 动作已经写出 durable state、effect 已推进到 `active`、但 owner 随后异常结束时的恢复死锁：`acf continuation reconcile --effect-local-terminal` 现在可在 owner-ended/forfeiture、`external_id=null` 且 durable local authority evidence 明确证明 terminal 的前提下收口 `prepared|active` effect；`unknown`、已有 external id、证据不足和模式冲突继续 fail-closed。
- 新增回归覆盖 active local effect → owner expiry → evidence-backed reconcile/recover → terminal effect 的完整闭环，并把 CLI help、README、Automation、dogfood/manual 与 template manual 同步到同一合同。

## v0.0.3.74 — 2026-08-22

### Project Observer stable release 与 WS011 integration closeout

- 正式把 WS011 Project Observer 合入稳定产品：新增 `acf observer status|snapshot|interpret|glossary-set|glossary|history`，同一项目 primary checkout 与注册 worktree 共用用户级 Observer namespace，边界固定为 **read broad / write narrow / control none**，不会 claim/challenge/recover continuation，也不会写 Writer 项目文件。
- Observer snapshot 使用稳定重读、一致性 fingerprint、credential-like 值过滤、轻量锁与原子替换；current/history/self-health/semantic/glossary 与自包含 `file://` Dashboard 只写入用户级 ACF_HOME。meaningful history 默认永久保留，通过无损 rotation/index 控制文件规模。
- 语义解释必须绑定当前 `source_fingerprint`；CLI 维护 canonical identity、confidence、provenance、版本历史与 source-drift stale-cache fail-closed。Dashboard 不启动 HTTP/daemon，不依赖外部资源，颜色同时配文字/符号，缺少明确分母时不伪造进度百分比。
- release smoke 现在从 wheel 与 sdist 的隔离安装环境实际验证 Observer status/snapshot/dashboard，而不是只验证源码树；minimal smoke 与专用 Observer abnormal-scenario tests 覆盖锁竞争/废弃锁恢复、unstable snapshot、owner liveness、render last-good、history rotation/reconstruction、source divergence、敏感值拒绝与 effect-risk 语义。
- WS011 dogfood 纠正了旧 `.69` 发布状态漂移：不可变 PyPI `0.0.3.69` wheel 与 Git tag 实际没有 Observer，因此两个历史 `prepared + external_id=null` installed-state Observer effects 在 `.73` 的 `--effect-local-terminal` 路径下凭不可变发布证据原子收口为 `failed`，没有伪造“已完成”事实。
- 将 WS011 发现的 reviewed Workstream lifecycle checkpoint exception 重新适配到 `.72+` 的 state-conditioned generated prompt：只有 authenticated current writer 自己执行确定性 `scope-add|merge-request|ready|merge-start|done` 后，才允许审阅并单独 checkpoint `Workstreams.md + 当前 Workstream detail` 两个 control-plane 文件；不恢复旧的全量协议文本，也不扩大普通 Task write scope。

## v0.0.3.73 — 2026-08-22

### Legacy local-effect terminal reconciliation

- 为旧版 continuation 遗留的 `prepared + external_id=null` 本地确定性 effect 增加显式、证据驱动的 ownerless recovery 路径：`acf continuation reconcile --effect-local-terminal ...`。该模式只在 owner 已结束或已有 ownership-forfeiture evidence、effect 仍为 `prepared`、历史记录没有 external id、且提供非空 durable local authority evidence 时允许声明 `completed|failed`。
- `--effect-local-terminal` 与 `--effect-not-started` / `--effect-external-id` 互斥；已有 external id 的 effect 仍必须 identity-match，`active|unknown` effect 仍 fail-closed。ACF 不根据 effect kind、文件名或项目内容自动判断“本地动作已完成”，事实裁决继续由调用方的可审计 evidence assertion 承担。
- 同一 interrupted generation 可在一个 reconcile receipt 中对多个 legacy local terminal effects 原子收口；receipt 继续绑定完整 observation/effect digest，`recover` 前任何 state/effect/HEAD/workspace 漂移都会触发 `reconciliation_stale`。
- generated prompt 的 unresolved-effect 分支新增该窄恢复提示，避免升级后的 Agent 面对已由 durable local artifacts 证明完成的旧 local effect 时只能在“谎称未启动”和“永久 fail-closed”之间二选一。
- 新增回归覆盖：两个无 external-id 的 prepared local effects 可凭 durable evidence 原子收口；已有 external id、active effect 以及 local-terminal/not-started 模式冲突均继续拒绝。

## v0.0.3.72 — 2026-08-21

### Scheduler bootstrap、owner overlap 与 prompt attention hardening

- Scheduled Task wrapper 的产品合同从“越薄越好”改为 **sufficient high-salience bootstrap**：wrapper 应完整提供精确项目/既有 worktree/connector 入口、DevSpace existing-checkout 打开语义、稳定 ACF 升级/迁移后的继续执行、authority refresh、generated-plan 执行、owner 用户可见说明和项目专用 Runtime/resource/permission/security/scientific/validation/issue-reporting 约束；仍禁止复制 generic claim/challenge/reconcile/workspace/effect 状态机。
- `acf continuation prompt --json` 新增可选 `--runner-id` 与稳定 `owner_context`，将 lease record、当前 owner、verified live other owner、stale/unverified owner、expired owner 与 no-owner 分开。未提供 caller runner identity 时不会把 fresh lease 武断解释为“另一个 owner”；会要求以 runner identity 重新渲染后再判断 duplicate wake。
- healthy hourly overlap 不再自动制造 contention：`coordination attempt` 遇到 **fresh** owner 时登记 `live_owner_observed`，返回 `duplicate_wake_safe_to_yield=true` 且不自动 challenge；只有 stale / legacy-unverified owner 才自动 open/join challenge。显式 `coordination challenge` 仍保留，formal reconcile/recover 与 generation fencing 安全边界不变。
- generated prompt 改为 state-conditioned progressive disclosure：always-on 只突出 overall objective、当前 stage/status、default execution plan、authority refresh、continue-by-default、4 个 hard stop、owner 摘要与当前 relevant action；claim、duplicate-owner、stale recovery、workspace provenance、unresolved effect 等控制细节只在当前状态相关时展开，正常 happy path 不再加载整套 recovery/effect 操作手册。
- `state.next_action` 的机器语义收敛为“**authority refresh 后的默认执行计划，但不是 work quota**”：新增 `next_action_is_default_execution_plan=true`、`next_action_requires_authority_refresh=true` 和 `next_action_may_be_superseded_by_newer_authority=true`，保留 `next_action_is_work_quota=false`。generated prompt 明确要求如果 newer Git/PLAN/Runtime/effect authority 没有覆盖它，就执行而不是只读取/解释/汇报；完成后继续围绕总体目标推进。
- 移除 Agent-facing `<bounded-objective>` 暗示，`--objective-summary` 示例改为 `<current-goal-summary>`；coordination summary 仍保持字节上限和 compact contract，但 bounded 只表示 ownership/write/effect/recovery 风险边界，不再暗示业务工作量边界。
- execution policy 新增 `active_lease_requires_liveness_verification`、`active_lease_is_session_end_reason=false`、`verified_duplicate_owner_may_end_duplicate_wake=true`、`duplicate_wake_exit_is_task_stop=false`、`stale_owner_requires_recovery=true` 与 `contender_must_create_busywork=false`：结束一个 verified duplicate scheduler wake 不等于 mission 的 paused/blocked/done，也不要求 contender 为了延长 session 人为制造 read-only busywork。
- worktree artifact 默认分类补充标准 Python 可再生缓存：`.venv/`、`__pycache__/`、`.pyc/.pyo`、`.pytest_cache/.mypy_cache/.ruff_cache` 直接识别为 `reproducible_cache/acknowledged`，避免每个真实项目都手工声明相同缓存，同时真实 output/result 仍保持 unknown/fail-closed。

### Continuation compact-state capacity self-healing

- 修复 compact `state.json` 的 list capacity 自锁：旧实现允许 `checkpoint` / `recover` 等路径在内存中继续 append `completed / evidence_refs / verification` 等列表，但最终 64 项硬上限会让后续 `prompt / doctor / reconcile` 直接报 `state_invalid`，真实 WS079 曾达到 `evidence_refs=78 / verification=88` 后无法进入 generated continuation protocol。
- 历史型 compact state list（`completed / evidence_refs / verification`）现在采用确定性的 rolling bounded window，写入只保留最近 `MAX_LIST_ITEMS=64` 项；`constraints / open_questions / plan_refs` 属于仍可能有效的语义状态，继续超过 64 就 fail-closed，绝不为容量静默丢掉安全/计划语义。状态仍保持 64 KiB 总量、单项约 4 KiB 与 forbidden raw-history 字段约束，不扩大 transcript/raw-output 持久化边界。
- 对已经由旧版本写出的 current-schema list overflow 增加惰性兼容：`prompt / doctor / reconcile` 读取时先在内存中裁到最近 64 项，因此不会因历史容量溢出形成 control-plane deadlock；下一次合法 state write 会持久化 compact 结果。round/effect/coordination/Git/worklog 等权威历史文件不受裁剪。
- `recover` 在写入新的 control/lease/round/workspace generation 之前先完成最终 state 的 compact + validation，避免旧 `.70` 那种“state 写入失败但 generation/lease 已前移、调用方又拿不到 fence token”的半提交 recovery。
- 新增四条回归：单次 checkpoint 写入 70 条 evidence/verification 仍保持 state 可读；手工构造旧版 70 条 history overflow 后 `doctor / prompt / claim` 可恢复并在下一次写入时落成合法 bounded state；overflow 前缀中的 forbidden raw-history item 不能通过裁剪逃逸校验；semantic `constraints` overflow 仍必须 `state_invalid`。

### Continuation terminal-effect rollover

- long-running continuation 不再靠继续放大 `MAX_EFFECTS` 延后容量自锁：当当前 `effects.json` 因记录数或字节数达到边界而无法接受新 effect 时，ACF 只把 `completed|failed` 的 terminal records 搬入 bounded `effects.archive.NNNNNN.json` segments，再写入新的 current journal；`prepared|active|unknown` 永不归档，若 unresolved records 自身耗尽容量仍继续 fail-closed。
- archived terminal records 保留完整 deterministic `logical_key/kind/external_id/status/evidence` identity；后续 `effect prepare` 会同时检查 current + archive，所以旧 logical key 仍返回 `created=false`，不会因为 rollover 丢失 durable replay protection。`effect update` 与 `effect list` 同样覆盖 archive history。
- rollover 采用 archive-first/current-second 原子文件顺序；若进程恰好在两次原子写之间中断，current/archive 的 exact duplicate 被视为可恢复 alias，不一致 duplicate 则 fail-closed。archive 损坏、包含 unresolved record 或与 current identity 冲突也会进入 continuation journal invalid，而不是被 doctor/recovery 静默忽略。
- continuation state migration receipt 的 preserved-history digests 现在同时纳入 `effects.archive.*.json`。这使原 `.66` 的 64→256 容量 hardening 从“延迟下一次上限”升级为可持续 rollover，而不删除历史防重放 identity。
- merge promotion 的 primary snapshot 现在携带同一套 read-only semantic-Git `stat_only_paths`；collision analyzer 会忽略已经由内容级 Git diff 证明为 stat-only 的普通 tracked `M`，避免 release/build 生成的 line-ending/stat metadata 假 dirty 与候选真实文件更新相交时误报 `wait_or_resolve_primary_paths`。真实 staged、untracked、rename/delete/type/mode/unmerged/submodule 或内容变化仍继续保护。

## v0.0.3.71 — 2026-08-21

### Continuation resume authority / session-end hardening

- generated prompt 将 persisted stage/status/next_action 明确降为 recovery metadata：执行前必须重新读取 local Git/project/Runtime/effect authority；newer authority 可以覆盖旧 hint，不能因为旧 hint 仍存在就重放已发生副作用。
- `continuation prompt --json` 新增 compact `resume_context`，只暴露 state 更新时间、round count、effect count/status 与 unresolved count，不把 raw journal/history 复制进默认 prompt。
- execution policy 明确 startup probe、fresh owner detection 和进度汇报本身都不是 session-end reason；contender 只有在安全、有价值、非冲突工作确实耗尽时才可结束当前 execution session，并必须说明具体 session-end reason。
- 这些 `.71` 规则在 `.72` 中继续保留，但由新的 state-conditioned prompt 与 duplicate-owner 分类降低无关控制面注意力。

## v0.0.3.70 — 2026-08-21

### Continuation workspace handoff status normalization

- 修复 tracked unstaged task-owned WIP 在正常 `continuation release` 后立即被误报 `task_owned_handoff_drift` 的问题。根因是 Git porcelain 状态 `" M"` 参与 digest 计算，而 workspace manifest 持久化时状态被规范化为 `"M"`，导致同一份未改变文件在 ownerless handoff 校验时必然 digest 不一致。
- `git_snapshot()` 现在先 canonicalize workspace status，再将同一 canonical status 同时用于 entry status 和 content digest；不放宽真实 provenance drift 保护，文件内容确实变化时仍继续 fail-closed。
- 对 `.69` 已经写入的旧 manifest 提供窄兼容：只有旧 digest 能由**当前同一文件内容 + 当前 Git 原始 porcelain status**精确重算时，才把它视为状态空白规范化产生的 legacy alias，并在下一次成功 claim 时写回 canonical digest；内容有任何变化都不会命中兼容分支。
- 新增 tracked unstaged handoff 回归测试，并保留 ownerless task-owned 内容真实变化必须阻断下一次 claim 的既有测试。

## v0.0.3.69 — 2026-08-21

### Continuation session-boundary hardening

- 修复 `acf continuation prompt` 仍可能被模型解释成“每次 scheduler wake 是一个需要主动收口的独立回合”的语义漏洞：scheduler wake 现在明确只是持续任务的恢复入口，不定义工作回合、汇报周期或预期停止点。
- generated prompt 明确 final assistant response 本身会终止当前 execution session；进度汇报、elapsed time、tool-call count、context length、完成若干步骤、测试/commit/checkpoint/Gate 成功或主观感觉“该收尾了”都不是 session-end reason。只要总体目标仍 open 且当前仍有安全、非重复、有价值工作，就继续使用工具推进而不是 final。
- generic protocol 从 1→14 顺序 checklist 重构为按条件适用的 startup/ownership、contention/recovery、workspace writes、ownership liveness、effects、progress/checkpoints、actual handoff 与 issue-reporting 规则组；明确规则组不是工作流程，读到最后一节也不产生 session-end 信号。stage/next_action 只作为 resume context/hint，不再形成工作配额暗示。
- timing profile 与 scheduler/TTL/heartbeat/stale/renew 数值降到 ownership-liveness 规则中，并明确只服务 lease liveness，不是 execution-duration target、work quota、reporting interval 或 stop signal；release 也明确不是默认流程最后一步。
- platform boundary 不再允许由 Agent 主观推断；只有平台、系统或工具明确发出当前执行即将终止的信号时才成立。另一个 owner、external wait 或 fail-closed 也只有在实际阻断当前所有安全有价值工作时才允许 handoff。
- 正常自愿 handoff 的 live owner 必须在 final response 前完成必要 workspace refresh/checkpoint 并 release；避免网页回复已经结束、continuation lease 却继续 active，进而让下一次 scheduler wake 误入 stale-owner challenge/recovery。
- `continuation prompt --json` 的 `execution_policy` 新增 session-boundary 机器字段：`scheduler_wake_is_resume_only`、`protocol_is_sequential_checklist=false`、`next_action_is_work_quota=false`、`final_response_is_terminal`、`final_response_requires_session_end_reason`、`progress_report_is_session_end_reason=false`、`elapsed_time_is_session_end_reason=false`、`timing_is_execution_duration_target=false`、`platform_boundary_requires_explicit_signal=true` 和 `release_is_default_end_step=false`。

## v0.0.3.68 — 2026-08-20

### Goal-directed continuous execution prompt

- `acf continuation prompt` 不再要求 Agent “只执行当前 bounded Gate”。bounded 现在明确只约束 ownership、写入范围、外部副作用和恢复风险，不限制一次有效 activation 可连续完成的子任务、测试、修复、commit、checkpoint 或 Gate 数量。
- generated prompt 明确 stage/next_action 是恢复入口而不是唯一微任务；Agent 根据总体目标、本地计划、约束和证据自主决定工作范围、顺序、实现策略和验证深度。checkpoint 只保存进度，Git commit 只形成自然语义检查点，Gate 完成只进入下一次判断，均不构成 release 或退出理由。
- 安全拒绝只阻止具体不安全的 claim、写入、恢复或副作用动作；Agent 应继续安全诊断、证据核查、issue 记录、规划、测试或其他不冲突工作。没有输入、证据、环境或策略变化时，不允许原样重复同一个失败动作。
- 任务级硬停止条件固定为四类：总体目标真正完成；用户明确暂停；需要新的人工授权、凭据或不可替代决策；配置的项目访问工具或连接（例如 DevSpace）经合理重连仍不可用。另一个 owner 正在推进、durable external job 等待、具体动作 fail-closed 或平台 activation 接近边界，只能形成让行、等待或可恢复 handoff，不得擅自把 mission 标为 paused、blocked_human 或 done。
- `continuation prompt --json` 新增稳定 `current`、`execution_policy` 和 `project_context`。`project_context` 渲染 state 中的 `plan_refs`、`constraints`，并通过 `scheduler_wrapper_contract.project_specific_constraints_slot` 预留 tooling、Runtime、resource/VM/node、permission、security、scientific、validation 和 issue-reporting 项目专用约束；外层薄 wrapper 仍不得复制 generic continuation 状态机。

## v0.0.3.67 — 2026-08-20

### Worktree close semantic-clean bridge

- 修复 `acf worktree close` 的最后一跳语义不一致：ACF 已把 content-identical tracked `M` 识别为 `stat_only_paths` / semantic-clean 后，原生 `git worktree remove` 仍可能按 porcelain dirty 拒绝，旧实现会把这个确定性拒绝误当文件占用重试直至 `worktree_close_timeout`。
- close 现在仍先用 canonical semantic-clean 严格拒绝 staged、真实 unstaged、untracked、rename/delete/type/mode/unmerged/submodule 等真实 dirty；只有已经证明 semantic-clean 且存在 `stat_only_paths` 时，内部才给 `git worktree remove` 加 `--force` 作为 raw-Git 兼容桥。branch 仍只用安全 `-d`，artifact handoff 仍必须先 verified，不扩大强制删除权限。

## v0.0.3.66 — 2026-08-19

### Release portability

- 修复 WS009 semantic-Git stat-only 测试的跨平台 fixture：在验证 `eol=crlf` normalization 前先删除工作树文件，再由 Git checkout 强制重建，避免 Linux runner 因原有 LF 文件无需 checkout rewrite 而错误假设 CRLF 已出现。
- fixture 初始内容显式写成 LF bytes，只有删除后由 Git 按 `.gitattributes eol=crlf` 重建才能满足断言，从而不再依赖宿主平台 `write_text` 的换行转换。
- `reconcile --effect-not-started` 为 write-ahead `effect prepare` 尚未跨过外部 submit 边界的中断提供显式收口：只允许 `prepared + external_id=null + failed`，仍要求 owner-ended/forfeiture 与外部 authority evidence；已有 external id、active effect、completed 声明或证据缺失继续 fail-closed。
- ownerless recovery 现在允许在同一个 `reconcile` receipt 中原子收口多个已经由外部 authority 证明 terminal 的既存 durable effects：按相同顺序重复 `--effect-key`、`--effect-terminal-status`、`--effect-external-id`，并共享本次 `--effect-evidence-ref` 集合；数量/identity 不一致继续 fail-closed。`--effect-not-started` 仍保持单 effect 专用分支。
- 修复 Windows hosted runner 的 TEMP 8.3 short-path alias（例如 `RUNNER~1`）与 canonical long path（例如 `runneradmin`）等价性：context containment / relative-display 统一按 resolved path 判定，避免合法 Workstream/ADR 被误报为 context-root 外路径；JSON `changed_files` 与 worktree target 的测试也改为比较 canonical path，而不是把 alias 字符串拼写当成语义。
- `scripts/minimal_smoke.py` 的最终汇总 JSON 改为 ASCII-safe escaping；即使 Windows hosted runner 的父进程 stdout 是 cp1252，也不会因为结果中包含中文/Unicode 路径或文本而在所有 smoke scenario 已执行完成后触发 `UnicodeEncodeError`。
- continuation round journal 达到 16 条上限时，现在会把已经带 `ended_at` 的 recovery-superseded `reconciling` round 视为可安全裁剪历史，与 `released` round 一样为下一 generation 腾出 bounded journal 空间；仍在运行、没有 `ended_at` 的 reconciling round 不会被裁剪，避免长期多次 formal recovery 后出现 `round_journal_full` 自锁。
- 新增 fenced-owner `continuation workspace reclassify`：durable writer 已权威结束后，如果审阅确认某个启动前漏报的真实产出当前处于 `unexpected_nonoverlap`，可以携带 durable evidence 与 reason 显式归入 `task_owned`，或明确保护为 `baseline_external`；命令不能接管已有 conflict/非 unexpected 路径，task-owned 仍受 Workstream direct write scope 约束，来源不确定继续 fail-closed。
- long-running continuation 的 durable effect journal 仍保持硬边界与完整 logical-key 防重放历史，但记录上限由 64 提升到 256、effect-journal 字节上限同步提升到 256 KiB；不会通过删除 terminal effect 来腾容量。该调整直接解除 WS080 已真实达到 64/64 terminal effects、`unresolved=[]` 后仍无法 `effect prepare` 的 `effect_journal_full` 自锁，同时继续由记录数和序列化字节数双重 fail-closed。
- `v0.0.3.65` tag 保持不可变；其 GitHub release run `32256066761` 在 Ubuntu full unittest 中仅因上述两条 CRLF fixture 断言失败而未进入 PyPI publish。`v0.0.3.66` 使用新的 immutable version；本地 full release gate 通过后，以 GitHub Ubuntu release gate 作为跨平台发布权威，不重打 `.65`。

## v0.0.3.65 — 2026-08-19

### Continuation recovery 与 durable writer hardening

- workspace manifest 升级到 v3，并新增 `acf continuation workspace adopt`：legacy pre-manifest WIP 可以在明确分类、digest/evidence 与 Workstream scope 校验后原位纳入 continuation provenance，不再要求为了迁移而强制 commit 或 `init --force`。
- ownerless unresolved effect 支持 receipt-bound terminal observation：只有已有 durable external id、challenge forfeiture / owner 结束证据与外部终态 identity 全部匹配时，`recover` 才会原子收口 effect；unknown、identity mismatch 或 receipt drift 继续 fail-closed，不重放 submit/collect/cancel。
- generated continuation prompt 明确 durable writer/job contract 与 thin Scheduled Task wrapper 边界；可能跨 owner 生命周期继续写项目文件或产生 non-idempotent side effect 的本地 subprocess、DevSpace session、Runtime job 必须先有可持久核对 identity。
- 新增用户级 continuation inventory/schema compatibility 与显式 migration 可见性，保持 `ACF_HOME` 单一状态实现、history-preserving 原位迁移与 future-schema fail-closed。

### Git / Workstream / attention governance

- worktree 与 continuation workspace 共用 semantic Git clean：content-identical/stat-only tracked 变化不再误阻塞 verify/sync/merge/close/recovery，同时 staged、真实 unstaged、untracked、delete/rename 等内容变化仍保持安全门；只读诊断不通过隐式 index refresh 制造 clean。
- Workstream `## Workspace` 只保留稳定 slug 与 local registry/`worktree verify|list` authority，不再持久化易漂移 `mode: none`；reserve/create 在 Open Workstream 上明确给出 Open -> Active 的 bounded next action。
- `review stale` 新增 `current_task_terminal_retained` / `task_plan_terminal_retained`；`doctor` 统一复用这两个 terminal-retention signal 与 `context_missing_review_marker` / `context_review_stale`，仅作为 `attention_hygiene` warning + `draft_only`，不进入 `check --strict`，也不自动判断或改写自然语言事实。

### 验证与兼容性

- WS009 在真实 ACF/FCC dogfood 中覆盖 legacy WIP adoption、ownerless terminal effect、generation fencing、long-lived durable session、Windows stat-only false dirty、active authority drift 与 schema discovery/migration；发布前再次执行 full release gate、upgrade matrix、wheel/sdist 隔离安装 smoke 与 installed-state adoption。
- `v0.0.3.64` 已被应急 control-plane tag 占用但未作为本次完整 WS009 release 复用；本版本使用新的 immutable `v0.0.3.65`。
- `v0.0.3.65` 的 GitHub release run 在 Ubuntu 上暴露两条 Windows-only CRLF fixture 假设并在 publish 前失败，因此该 tag 未发布到 PyPI；修复进入 `v0.0.3.66`，不重打 `.65`。

## v0.0.3.63 — 2026-08-18

### Continuation 长轮次时序与统一协议

- continuation timing 拆分 scheduler interval、lease TTL、renew interval、heartbeat recommendation 与 stale threshold；`doctor` 不再用 renew interval 推导 stale。新增 `standard` / `long-running` profile，其中 long-running 默认 `60/180/45/10/25` 分钟。
- 新增 `acf continuation configure`，已有 task 可原位更新 timing control，不需要 `init --force`；active lease 存在时拒绝 configure，避免运行中改变 owner liveness 语义。
- `acf continuation prompt` 输出当前 timing 并明确 scheduler 只是唤醒频率、Gate 可自然持续 1-2 小时以上；Scheduled Task 应只保留项目 wrapper，每轮消费当前安装态生成协议。
- continuation 不再把 worktree-level `clean/dirty` 作为 claim/release/reconcile/recover 安全门。workspace manifest v2 使用 path/status/digest 区分 external 与 `task_owned` WIP；正常 release 可保留未提交 task WIP，下一 generation 验证 ownerless handoff 期间 digest 未漂移后直接继承。Git commit 只在自然语义 checkpoint 创建；真正的 unknown provenance 报 `workspace_provenance_missing`，同路径/父子路径或 task-owned ownerless drift 才进入 `workspace_conflict`。
- 新增 bounded `coordination attempt|challenge|status`：后来的 runner 可以登记 contender 并针对当前 fenced owner generation open/join challenge，但 challenge 本身不授予写权限。owner-protected continuation 操作在 `lease_id + generation + fence_token` 验证成功后作为 authenticated response；正常 release 解析为 `owner_released`。
- challenge deadline 到期只产生 `ownership_forfeiture_candidate`，不宣称旧 Agent 已死亡。formal reconcile receipt 同时绑定 workspace/effect/HEAD/identity 与 coordination digest；owner ACK 与 recover 的竞态由同一 state lock 和 generation fencing 保证最多一个 writer，旧 generation 复活后确定性失败。
- 所有可定位项目的普通 ACF 命令都会 opportunistic 只读提示当前 owner generation 的 pending challenge，但绝不 ACK 或改变 ownership。`acf continuation prompt` 现在是唯一 generic Scheduled Task protocol 权威，项目 wrapper 只保留固定 project/worktree/branch/task identity 与项目特有 Runtime/科学/权限/验收约束。

### Failure injection 与真实项目兼容性

- 冻结 12 场景 failure matrix，覆盖模拟 2h+ 同 generation heartbeat/renew、clean crash、可归属 task WIP、external dirty、路径 overlap、ownerless digest drift、HEAD advance、unresolved effect、challenge ACK/recover race 与旧 generation resurrection。
- WS008 开发版已对 FCC WS079、WS080、WS086 的真实既有 continuation state 原位生成 v0.0.3.63 协议，无需 force re-init，并保留各自科学/runtime next_action；真实 task-id alias 也会被原样保留。
- AStockT_AI WS003 在 qdspc 的 v0.0.3.61 安装态仍生成旧协议，作为发布后安装/cutover 的明确 adoption 基线；新版本安装前不提前修改生产 Scheduled Task wrapper。

## v0.0.3.62 — 2026-08-17

### Continuation 可恢复执行协议

- 新 claim 使用递增 `generation` 与本轮专属 fence credential；持久态只保存 token hash。新增 `continuation assert-owner|heartbeat`，并让 heartbeat/renew/progress/effect/checkpoint/release 全部受 generation fencing 保护；旧 generation 复活后不能继续写控制面。
- `doctor` 区分 fresh、stale/orphan candidate、legacy-unknown 与 expired lease，不再把 TTL-active 等同于 runner live。stale 只触发 reconciliation，不授权自动 steal。
- 新增 bounded `rounds.json` / `effects.json` journal 与 `continuation progress`、`effect prepare|update|list`。non-idempotent 外部动作先 write-ahead `effect prepare`；只有 `created=true` 才允许首次执行，已存在 identity 必须复用或核对而不是 replay；raw transcript/tool output 禁止进入 journal。
- 新增 `continuation reconcile|recover`：fresh owner、dirty Git、未接受的 HEAD advance、unresolved effect 一律 fail-closed；eligible receipt 记录 observation/evidence，recover 前重新校验 lease/liveness/HEAD/state/round/effect digest，任何 drift 都使 receipt stale；成功后 generation+1 fencing 并写 recovery receipt。

### 兼容性与 dogfooding 修复

- clean release 未显式 `--final-status` 时，只把仍为 `running` 的 state 转回 `ready`；已经 checkpoint 的 `waiting_external`、`blocked_human`、`done` 等非 running 状态保持不变，关闭 WS079 的真实 `waiting_external -> ready` 回归。
- wrong task-id 返回 `continuation_task_not_found` 与 `available_tasks`，避免把拼写错误误判为 control 损坏。
- `continuation issue --resolve-fingerprint` 使用 append-only resolution event 收口已修复 dogfood issue；`log issues --open-only` 只列 open 项，同 fingerprint 再次出现会自动 reopen。
- 旧 v0.0.3.61 control/state/legacy lease 无需 force re-init。WS007 自身 legacy active lease 已在 TTL 到期前通过 formal reconcile/recover 原位恢复；WS086 历史 orphan/finalization 使用真实 state 副本隔离 replay，未重复 Runtime submit/collect；WS079 当前 live/dirty legacy round 被新协议正确拒绝接管。

### 验证

- 冻结的 9-point crash matrix 覆盖 claim、effect prepare、external acknowledgement、terminal、collect、aggregate、Git commit、continuation checkpoint 与 pre-release，并验证旧 generation 的全部 owner-protected 操作被拒绝。
- continuation/state compatibility focused suites 全绿；完整 unittest 在 WS007.5 阶段达到 434/434、零 expected failure；wheel 与 sdist package smoke 均通过。最终 v0.0.3.62 full release gate 在发布前再次执行。

## v0.0.3.61 — 2026-08-17

### Dogfooding 可观测性

- `continuation` 与 `worktree` CLI 命令现在进入用户级 usage event log，记录 command、exit/error code、duration 和 changed files；不再因为缺少 context routing 而静默漏记。
- 新增 `acf continuation issue`：外部 agent 可在发现具体、可复用、证据支持的 ACF / continuation / 自动化工作流缺口时写入结构化 issue event，包含 task/workstream/stage、category、severity、evidence refs、related command 和稳定 fingerprint。
- 新增 `acf log issues [--all-projects]`：按 fingerprint 聚合不同 worktree / task 中的重复 issue occurrence，保留 count、首次/最近出现时间、最高严重度、任务/项目和证据引用，便于多任务并行 dogfood 后直接进入下一轮产品改进。
- `acf continuation prompt` 自动包含 issue 记录协议；正常 active-lease no-op、等待和任务自身业务失败明确不作为产品 issue。

### 验证

- 新增 continuation usage logging、issue 记录/去重聚合和 prompt 协议回归测试。

## v0.0.3.60 — 2026-08-17

### 安全修复

- `acf continuation` 不再把“lease 已过期但 Git HEAD 已从该 lease 的起始 HEAD 前进”的 `running` 轮次自动判定为可恢复。该场景可能表示前一轮已经完成并提交了非幂等写操作、但在 checkpoint/release 前中断；自动重新 claim 会有重复执行风险。
- `doctor` 现在返回 `expired_round_head_changed=true`、`can_claim=false` 和 `blocked_reasons=[..., "expired_round_head_changed"]`；直接 `claim` 返回 `continuation_reconciliation_required`，并提供 lease HEAD 与当前 HEAD 供审计。
- 保留原有安全恢复路径：如果 lease 过期、state 仍为 `running`、worktree clean 且 HEAD 未变化，则仍允许从 clean checkpoint 重新 claim。

### 验证

- 新增 failure-injection 回归测试，覆盖“上一轮提交后崩溃、lease 随后过期”的 clean-but-advanced-HEAD 场景，确认不会重复自动执行。

## v0.0.3.59 — 2026-08-16

### 新增

- 新增 `acf continuation init|doctor|claim|renew|checkpoint|release|pause|resume|prompt`，为外部 Scheduled Task、其他 AI scheduler 和人工多轮任务提供模型无关的 bounded continuation 控制面。
- continuation 运行态保存在用户级 `~/.acf/projects/.../continuation/`，不会因为 lease、pause 或 compact state 更新污染目标 Git worktree；现有 clean worktree 可直接初始化，不需要重建。
- 可选 `--workstream WSNNN` 会复用 ACF worktree registry/path/branch/common-dir 验证；无 Workstream 项目仍可使用独立 `--task-id`。
- 增加单写者 lease、续期、expired recovery、人工 pause/resume、dirty release → reconciling 和 compact state 原始历史字段拒绝。

### 边界

- ACF continuation 不创建 Scheduled Task、不读取聊天历史、不运行常驻 agent、不保存 transcript，也不替代 Task Plan、Workstream、Git/scientific checkpoint 或 evidence。
- 外部调度周期可以固定；本地 lease 只承担并发与恢复安全门，不动态修改 scheduler 时间。

## v0.0.3.58 — 2026-08-10

### 发布与安装

- 新增 `scripts/release_check.py`，覆盖发布前检查、wheel/sdist 构建、隔离安装和 console script smoke。
- 新增 uv 一键安装/更新脚本，以及 GitHub Actions CI 和 `v*` tag PyPI 发布 workflow。

## v0.0.3.57 — 2026-08-10

### 修复

- `acf workstream reserve --apply` 不再因为 primary checkout 存在其他 agent 的无关 staged、unstaged 或 untracked 修改而失败。
- 预约提交改为只提交 reservation detail/index；只有预约路径本身或父子路径发生冲突时才 fail-closed，并保留其他本地修改。
- 补充预约路径冲突、并行 dirty 状态保留和冲突修复后恢复测试及对应 JSON error contract。

### 验证

- 通过 template/strict check、编译检查、diff check 和分片 unittest；分片覆盖 423 项测试。
- 完整 `uv run python -m unittest` 在工具 10 分钟窗口内超时，但各测试分片均通过，未将聚合超时计作通过。

## v0.0.3.56 — 2026-08-06

### 新增

- `acf worktree merge` 统一改为临时 integration worktree 执行：真实 no-ff merge、冲突解决和 post-check 不再发生在 primary checkout；primary 只执行候选验证后的 fast-forward promotion。
- primary checkout 允许保留与候选无碰撞的 staged、unstaged 和 untracked 修改；merge-plan 输出结构化工作区快照、候选写入集合、相同重叠和分歧碰撞。
- 新增有限等待、指数退避、lock heartbeat、stale-lock 安全隔离、primary/source HEAD 自动重规划和 operation v2 resume。
- 新增 `acf worktree artifact-plan|artifact-migrate`，对 ignored/untracked 结果执行显式分类、复制或稳定引用和 SHA-256 验证；普通路径默认 `unknown`，不能静默删除。
- 冲突、post-check 失败和 artifact 未完成时保留 integration worktree；修复或分类后使用原 operation ID 继续。
- close 与 merge 共用来源 lifecycle 锁，支持 Windows 文件占用退避、部分成功 journal 和幂等恢复。

### 配置与安全

- 新增 `primary_dirty_policy = "allow_non_overlapping"|"require_clean"`；两种策略都使用同一 integration 引擎，不恢复旧的 primary direct merge。
- 新增 `artifact_cache_patterns` 和 `artifact_discardable_patterns`；只有项目配置或本次 CLI 明确声明的路径才自动放行。
- 相同 untracked/ignored 重叠只在内容、mode 和类型全部与候选一致时使用可恢复 quarantine；promotion 失败会原子恢复，成功后才删除冗余副本。
- 继续禁止自动 stash、reset、clean、rebase、force、push 和静默冲突选择。

### 验证

- 新增临时真实 Git 仓库场景，覆盖无关 staged/unstaged 保留、相同/不同重叠、ignored 碰撞、短时路径竞争、锁等待、HEAD 推进重规划、冲突解决、post-check 修复、artifact 迁移、close 重试和部分恢复。
- 完整测试、模板/strict check、构建制品、隔离安装和真实 dogfooding 升级记录见 2026-08-06 worklog。

## v0.0.3.55 — 2026-08-04

### 变更

- `acf status|next` 未显式选择 Workstream 时改为 `GlobalOnly`：只披露全局上下文文件指针和 Workstream 摘要，不再因为一个或多个 active-class Workstream 自动进入任务。
- `attention: Now/Next/Waiting/Retained` 降级为 dashboard 管理元数据，不再决定默认上下文入口。
- 新增 `acf status|next --workstream WSNNN` 显式选择；Active `Current_Task` 唯一绑定和经过 registry/path/branch/common-dir 校验的专属 worktree 也可作为明确选择来源。
- 选择结果采用两级渐进式披露：状态命令只返回 pointer-only 入口，必须再调用 `acf workstream context WSNNN` 才读取专属 detail/read_scope，并继续按需读取 reference/output。
- 显式来源冲突或选择不存在、非活动 Workstream 时返回 `SelectionConflict` / `SelectionInvalid`，保持全局上下文并 fail-closed。

### 兼容性与安全

- 原 Workstream/Worktree 生命周期接口和 attention front matter 保持兼容；不要求旧项目批量修改 attention。
- 多个活动 Workstream 是正常项目状态，不再作为 `Ambiguous`；只有真正的显式选择冲突才报错。
- 默认 JSON 不包含任一 Workstream 正文、read_scope、reference、output 或专属 worklog 内容，降低 AI 上下文污染风险。

### 验证

- 新增 global-only、pointer-only、Current Task、显式选择、verified worktree、冲突/无效选择和专属预算隔离测试。
- 完整测试、Python 3.10、升级矩阵、模板/strict check、wheel 隔离安装和生产 console-script smoke 见 WS006 发布证据。

## v0.0.3.54 — 2026-08-04

### 新增

- 新增 `acf workstream reserve`：在 primary branch 上预约并提交唯一 Workstream 编号，扫描 active/archive/index、Git refs、worktree registry 和 operation journal；创建 Workstream 时不隐式创建 branch/worktree。
- 新增 `acf worktree create|attach|verify|list|audit|sync|merge-plan|merge|close|resume`，覆盖正式 Workstream 与分类非 Workstream 的完整 Git worktree 生命周期。
- 新增 `.acf/project.toml` 可选 Git 配置、Git common-dir operation journal、registry 和分层操作锁。
- 新增冲突预演、冻结 source/base commit、`--no-ff` 合并、部分失败恢复和幂等关闭。
- 新增 `docs/Worktree_Lifecycle.md` 教程、真实 Git 仓库测试矩阵和安装态完整生命周期 smoke。

### 兼容性

- 原 `acf workstream add`、状态流转、guard、archive 及不创建 worktree 的项目逻辑保持不变。
- 未配置或未调用 `acf worktree` 时，旧项目不依赖 Git worktree 配置。
- 支持 Python 3.10 及以上；Python 3.10 核心矩阵 46/46 通过。

### 安全边界

- 所有 Git 写命令默认只输出计划，显式 `--apply` 才执行。
- 不自动执行 `stash`、`reset`、`clean`、`rebase`、`branch -D`、`worktree remove --force`、`push` 或冲突解决。
- 错误仓库、detached HEAD、dirty 状态、路径占用、分支占用、primary 前进和内容冲突均 fail-closed。

### 验证

- 完整测试：353/353。
- 新增 worktree 生命周期测试：34/34。
- 完整旧项目 upgrade matrix、模板检查、dogfooding strict check、源码安装态 smoke、wheel 隔离安装 smoke 和生产 `acf.exe` 生命周期 smoke 全部通过。
- 发布 merge commit：`c16e0d1925ae444bec74ecdd4eeea72b74f873e5`。

## v0.0.3.53 — 2026-08-04

- 完善 Workstream guard 文件集强验收、旧项目升级迁移说明和注意力路由。
- 明确裸 `guard` / `--from-git` 仅用于快速查看；完成与状态切换优先使用 `--files`。

## v0.0.3.52 — 2026-06-09

- 发布旧项目升级审计、Workstream-first 上下文入口和模块化 CLI 稳定基线。
- 提供 `upgrade --plan --json`、全局项目日志盘点及稳定安装入口。
