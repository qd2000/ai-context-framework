# 自动化与 subagent 路线

本项目的核心价值是模型无关、纯 Markdown、可人工审阅的上下文治理。自动化的目标不是替代判断，而是减少结构漂移、索引遗漏和重复手工维护。

顶层产品设计见 `docs/ai/reference/ACF_Top_Level_Design.md`，通用产品路线见 `docs/ai/reference/Product_Roadmap.md`。后续真实项目反馈进入 ACF 前，必须先抽象成通用上下文治理问题，并能用 fixture 或最小上下文测试验证；FCC 只作为压力测试样本之一，不作为产品需求唯一来源。

非 PetroSim dogfooding 样本见 `docs/ai/reference/Non_PetroSim_Dogfooding_Sample.md`。当前选择 EcSOS `cracking-yield-prediction-system` 作为论文 / 数据分析 / Python 工具类真实样本；默认只读或 dry-run，写入前需确认目标项目状态。

## 当前已自动化

### Continuation dogfood 反馈闭环

并行 Scheduled Task / 外部 agent 使用 `acf continuation` 时，命令级成功/失败自动进入用户级 usage log；遇到具体、可复用、证据支持的 ACF / continuation / 调度工作流缺口时，agent 通过 `acf continuation issue` 写结构化 issue。`acf log issues --all-projects --json` 按稳定 fingerprint 聚合不同 worktree 的重复 occurrence，供后续产品改进直接复用。正常 active-lease no-op、等待外部任务和业务算法失败不得记录为产品 issue。

ACF 自身的 WS012 Maintenance Writer 负责把该跨项目 issue 池真正消费起来，而不是只累计日志：每次 `:04` wake 可以只读获取 `acf log issues --all-projects --open-only --json`，先按当前稳定版重新验证、识别已修复但未 resolve 的历史项、聚合同根因 fingerprint，再分为 Immediate / Ready Batch / Observe。critical、数据损坏/重复副作用风险、continuation 自锁、阻断 Scheduled Task 或当前稳定版的跨 Workstream 严重 regression 应立即进入修复；普通 high/medium 先形成 deterministic regression、affected files、repair plan 和 validation plan，达到 WS012 PLAN 定义的 batch 条件后一次性处理当时全部 Ready Batch root-cause clusters。原始 open issue 数量本身不作为 batch 触发条件。

### WS012 动态用户需求与 live steering

长时间 continuation 任务通过 `acf continuation directive ...` 正式接收用户中途新增的 requirement、priority change、constraint 和 plan change。directive 是用户级、可审计的 authority inbox；它不是第二套 Task Plan，也不会让 CLI 自动裁决自然语言事实。每条 directive 可声明 `lifetime=transient|durable|unspecified`。pending directive 只负责可靠表达“用户 authority 已变化”；transient one-shot 可以在证据充分时直接 `pending -> resolved`，需要跨轮执行的 transient 只有形成 durable execution evidence 后才可 adopt；durable requirement / constraint / priority / plan change 必须先把持久语义同步进正确 Markdown PLAN / Workstream / Rules / Task authority，再以 evidence-backed adopt 消费。

第一版合同包括：

- `directive add|list|show|adopt|resolve|supersede|withdraw` 机械维护用户级事件账本；状态为 `pending|adopted|resolved|superseded|withdrawn`，其中 resolve 表示完成、withdraw 表示用户/更高 authority 明确取消、supersede 表示同一 active requirement 被新版本替换，三者不得混用；
- durable/transient adopt 需要 durable evidence；CLI 不允许仅因为 Agent “读过 directive”就 adopt。当前 session 实际消费过的 directive 必须在 safe control point 明确 resolve/adopt/supersede/withdraw，或保留 pending 并说明理由；resolved 历史不重新打开；
- `continuation prompt --json` 暴露 `directive_context` 的 pending 摘要、digest/revision，并在 generated prompt 中高显著提示 pending user authority 优先于旧 persisted `next_action`；
- claim 会记录当时已观察的 directive revision/digest；heartbeat/renew 返回 `directive_signal`，同时暴露 pending/adopted/active count、journal pressure 与 archive audit 摘要；当 inbox 在长 session 中变化时用 `changed_since_last_observation=true` 提示立即 authority refresh，而不是等下一次 scheduler wake；
- `supersede` 创建新的 pending replacement 并把旧 directive 终结为 superseded，保留双方 identity/历史；`adopt/resolve` 是显式状态迁移，不自动修改 Markdown authority；
- `continuation doctor` 对 directive 只做机械 hygiene：stale adopted、stale high-priority pending、durable adoption evidence 缺失、active-count pressure 与 event/byte rollover pressure；这些 finding 不会按年龄自动 resolve，也不会推断自然语言 requirement 是否语义完成；
- directive current journal 达到软 event/byte pressure 时，只把**完整 terminal prefix**（全部 directive 均已 `resolved|superseded|withdrawn`）archive 到 `directives.archive.NNNNNN.json`；任何 pending/adopted authority 都留在 current。archive-first/current-second 原子写允许崩溃窗口内出现 exact duplicate，加载时按 event identity/revision 精确去重；不一致 duplicate 或 revision gap 直接 fail-closed。archive history 继续参与 list/show、history digest 与 migration-preservation audit；如果 active authority 自身耗尽容量，不会为腾空间删除它。
- 非 Writer owner 的外部 Agent 可以代表新的用户 authority 执行 directive add/supersede，而不因此获取 writer lease/generation/fence/workspace write authority；当前 Writer 只通过 prompt/heartbeat/renew 的 revision/digest change signal 在下一 safe control point 发现 steering。
- 第一轮 dogfood 使用该渠道正式注入并消费“Observer Project Narrative / Project Map”和“Global continuation issue maintenance”两个真实需求；
- 正式稳定版发布/安装前，worktree candidate 只在隔离 ACF_HOME 测试该接口，不得用候选实现改写 canonical continuation；发布后再用安装态命令对 WS012 做真实 steering dogfood。

WS012 已使用安装态 directive channel 对上述两个真实需求完成 add → prompt exposure → authority refresh → adopt dogfood。Project Map 的实现保持 Observer anti-masking：Maintenance Writer 只构建/验证产品代码与隔离 runtime，正式 `:34` Production Observer 仍独立负责 canonical snapshot/render。项目级叙事由 `observer narrative-source` 对显式 authority 文件和稳定项目 meaning facts 计算 fingerprint，再由 `observer narrative-apply` 保存版本化 derived state；Dashboard 只渲染已经通过 fingerprint/provenance 校验的 Overall Goal、Architecture Map、Logical Milestone Flow、Current Position 和 evidence，不从整个仓库自动猜项目故事。authority 变化后 narrative 必须 stale，直到新的显式语义解释被应用。

### Continuation 长时间物理执行 liveness

长时间确定性本地命令不能把“DevSpace/tool 调用尚未返回”误当成 owner 已结束。对于可能跨过 continuation stale window 的本地命令，Writer 使用 `acf continuation execution run <worktree> ... --key <deterministic-key> -- <exact argv>`：supervisor 先在现有 effect journal 建立 generation-bound deterministic identity，再启动**同一个**物理子进程，记录 PID + OS process-start identity，并在该精确进程仍存活时自动 heartbeat/按需 renew；进程退出后 effect 必须 terminalize 为 completed/failed。下一次 scheduler wake 只有在 lease 仍 active、普通 heartbeat 已 stale、且 persisted PID + start identity 仍精确命中同一 live process 时，才可用 `liveness_source=physical_execution` 继续判定 verified-live；裸 PID、PID reuse、zombie/dead process、unverifiable probe 或仅剩 active label 都不是正向 liveness evidence。physical execution 不绕过 expired lease/fencing；正常 supervisor 会通过 renew 防止 TTL 到期。

该机制不引入 daemon、数据库或第二套 scheduler，也不允许 replay 已存在的 deterministic key。若父 owner 使用 `ACF_CONTINUATION_FENCE_TOKEN_FILE`，supervisor 自己保留该 handle 以完成 heartbeat/renew/terminalize，但启动 child 时会从 child environment 中删除该变量，因此被监督 child/descendants 不能无意读取或覆盖父 owner credential。普通环境仍照常继承；这里只做 continuation credential containment，不提供通用 sandbox。child stdout/stderr 仅作为 bounded diagnostic tail 返回；父命令自身仍遵守 DevSpace command-session terminality：拿到 `running=true/sessionId` 后必须持续 poll **同一个 session** 到明确 exit，不能启动 replacement/retry 或依赖该结果的后续 side effect。worktree candidate 只在隔离 `ACF_HOME` 测试该能力；正式 immutable release/global install 前不得让 candidate 改写 canonical continuation control plane。

`pause` 在 physical execution 尚未启动时继续阻止新执行；若 durable pause marker 是在 supervised child 已经启动并取得精确 process identity 之后到达，则 supervisor 不得因为 pause 强制终止该 child。它继续维持当前 owner liveness，等待同一个 child 到达 terminal，再以 `pause_pending=true` 返回；随后当前 owner 执行正常 `continuation release`，由既有 release 语义把 continuation 转为 `paused`。这样既不遗弃/杀死已经开始的确定性执行，也不允许 pause 之后继续启动新 work。

正式 Production Observer 的 narrative 刷新不能只停留在“检测 stale”：每次 `:34` activation 的初始 snapshot 若显示 Project Narrative 为 `stale | not_interpreted`，Observer Agent 必须读取显式 `narrative-source` projection/fingerprint，以当前项目 authority 生成 secret-safe derived narrative payload，再用**同一** fingerprint/source-path 集合执行 `narrative-apply`，最后重新 snapshot/render；source 在 source→apply 间变化或证据不足时保持 stale/fail-visible。该语义写入属于 Production Observer 的用户级 `.acf/.../observer/` narrow-write，不得由 `:04` Maintenance 普通 wake 代刷。临时 payload 只能放 OS scratch/temp 并在 apply 后删除，不得写进项目或形成第二份 Dashboard。只有最终 production snapshot 的 Project Narrative 为 `current`（或初始即 current）的 activation 才可计入 WS012 连续 acceptance。

`acf.py` 先覆盖确定性工作：

- 可安装入口：`pyproject.toml` 提供 `acf` console script；正式用户从 PyPI 使用 `uv tool install ai-context-framework`，更新使用 `uv tool upgrade ai-context-framework`；仓库开发期可用 `uv tool install -e .`，本仓库开发入口仍保留 `uv run python acf.py ...`。
- 上下文自动发现：`check`、`new ...` 和 `writeback draft` 在省略路径时，会从当前目录向上查找 `docs/ai` 或上下文根目录；显式路径仍优先。
- `status`：输出项目根、上下文目录、profile、当前任务状态和检查结果。
- AI 友好输出第一版：`status` 和 `check` 支持 `--json`；写命令支持 `--json`、`--dry-run`、`--check-after` 并输出 changed files。
- `init`：生成标准或简化上下文模板，并在推断出的项目根目录生成缺失的薄入口 AGENTS.md；已有根入口默认不覆盖，需要 `--force-root-agent` 才覆盖。
- `upgrade`：非破坏式补齐旧上下文缺失的 `active/Feedback_Inbox.md`、`active/Task_Plan.md`、标准 profile 的 human 层、archive、archive/feedback、Knowledge 结构和 active -> reference 规划依据追溯入口，不自动移动或覆盖 Active 当前任务。
- `simplify`：从已有上下文导出简化版本，保留真实 ADR 与 daily worklog，排除占位模板文件。
- `check`：检查目录、必需文件、UTF-8、乱码、空文件、内部 Markdown 引用、任务状态、决策状态、资料状态、ADR 状态一致性和 worklog 日期路径；`--strict` 会将占位符残留视为错误。
- `plan init|add-task|set-task|focus|status`、`plan reference list|add|remove` 与 `plan stage list|add|set|done`：维护当前大任务计划、轻量子任务板、`## 规划依据` 和 `## 任务阶段` 表；`plan reference` 只写 reference 路径和一句话用途，可用 `--sync-current-task` 显式同步到 Active `active/Current_Task.md`；Task Stage CLI 不创建 task object 单文件，也不自动修改 `active/Current_Task.md`。
- `task start|done|block|clear`：从任务板启动、完成、阻塞或清空当前小任务。
- `archive current-task|task-plan|list`：归档旧当前任务或旧大任务计划，并维护 `archive/Archive_Index.md`。
- `knowledge draft|apply|list|show|mark`：生成可审阅 Knowledge 草案，审阅后写入可复用经验索引，并维护状态。
- `new task`：生成或重置 `active/Current_Task.md`，默认拒绝覆盖 Active 任务，除非传入 `--force`。
- `new source`：向 `reference/Sources_Index.md` 添加或更新资料索引行，默认拒绝重复资料标题，除非传入 `--force`。
- `new worklog`：按日期生成 daily worklog，并向 `worklog/Worklog_Index.md` 添加或更新索引行。
- `new adr`：生成下一个 ADR 文件，并按 Active 或 Proposed 状态更新 `reference/Decisions_Index.md`。
- `writeback draft`：把会话结束回写建议保存到 `worklog/writeback-drafts/`，生成可审阅草案，不直接修改权威上下文文件。
- `edit section get|replace|append`：读取、替换或追加上下文根目录内 Markdown 文件的指定 section body。
- `edit table upsert`：按 key column 更新或追加上下文根目录内 Markdown 表格行。
- `doctor`：面向人和 AI 的健康诊断入口，复用 `check` 并报告跨文件生命周期漂移、终态 Workstream authority scope 残留、generated index 漂移、attention hygiene 和本地数据副本证据信号。attention hygiene 直接复用 `review stale` 的 terminal Current_Task/Task_Plan retention 与 Context review marker/stale signals；这些结果保持 warning / draft-only，不进入 `check --strict`，也不自动判断自然语言事实真假。`--fix safe` 只执行确定性低风险修复，`--report` 和 `--draft-semantic` 生成可审阅产物，`--projects` 支持多项目只读诊断。
- `workstream reserve`：在 primary branch 上通过预约锁、跨 active/archive/Git/journal 编号扫描和 reservation-path 冲突校验，创建唯一 WS 占位提交；使用 Git 的路径限定提交保留其他 agent 的 staged/unstaged/untracked 修改，只阻断 detail/index 自身或其父子路径发生碰撞；它不创建 branch/worktree，原 `workstream add` 不加载 Git 生命周期。
- `workstream authorization status|list|policy-set|approve|revoke`：提供用户级 closeout authorization ledger。`ready / merge / done / archive` 以及对应 worktree closeout path 必须经同一个 resolver；项目级 `auto|manual|deny` policy 可按 Workstream id/type/class/action 缩窄，显式 approval 只绑定一个 Workstream/action/current material authority fingerprint，不能跨 action/Workstream 转移。更窄、更新的 policy 优先，WS-specific manual/deny 可覆盖 broad auto；material authority 变化使旧 approval stale，Activity Log 变化不使其失效。`merge` 的同一次 deterministic `ReadyToMerge -> Merging` transition 自身不 stale merge approval，使 lifecycle `merge-start` 与随后 worktree merge 可以复用同一明确批准；其他 material authority 变化仍 fail-closed。自动化不得凭空写 policy/approval，也不得用裸 `--human-approved` 自证授权；只有已有 durable user authority/evidence 时才记录，未知 schema、语义损坏、缺证据或显式 deny 均 fail-closed。
- `worktree create|attach|verify|list|audit|sync|merge-plan|merge|artifact-plan|artifact-migrate|close|resume`：供 AI 选择调用的可选 Git 生命周期。merge 固定使用临时 integration worktree，primary 只做 collision-aware fast-forward promotion；operation journal 记录候选、检查、artifact、等待、重规划、冲突现场和 promotion。短时锁、路径状态和 HEAD 推进有限重试；冲突或检查失败保留 integration worktree供 resume；ignored/untracked 结果通过 handoff manifest 分类和摘要验证；close 与 merge 共用 lifecycle 锁并支持文件占用退避和部分成功恢复。close 先用 canonical semantic-clean 拒绝真实 dirty；只有 content-identical `stat_only_paths` 仍令 raw Git remove 拒绝时，内部才使用 `git worktree remove --force` 作为兼容桥，branch 仍禁止 `-D`。

- Worktree clean 判定使用统一 read-only semantic helper：porcelain 的普通 tracked unstaged `M` 只有在 `GIT_OPTIONAL_LOCKS=0 git diff` 证明无真实 normalized content diff 时才作为 `stat_only_paths` 放行；其余 staged/untracked/rename/delete/type/mode/unmerged/submodule/真实 diff 一律保持 dirty。`verify/list` 暴露 stat-only diagnostics，continuation workspace snapshot 复用同一 helper，因此历史 false-dirty baseline 会在后续 refresh 自然消失。reserve Markdown 不复制机器 binding 状态，只声明 local registry/verify/list authority；Open reserve/create 必须在 AI-facing next_actions 中提示显式 Active transition。
- `continuation init|configure|list|migrate|doctor|coordination status|coordination attempt|coordination challenge|coordination wait|claim|assert-owner|heartbeat|directive add|directive list|directive show|directive adopt|directive resolve|directive supersede|directive withdraw|progress|effect prepare|effect update|effect list|workspace status|workspace intent|workspace reclassify|workspace reconcile-handoff|workspace adopt|workspace refresh|reconcile|recover|renew|checkpoint|release|pause|resume|prompt|issue`：为外部 AI scheduler 或人工多轮任务提供模型无关的 bounded continuation 控制面。bounded 只约束 ownership、写入、副作用和恢复风险，不限制业务工作量；既有 generation fencing、workspace provenance、effect identity、reconcile/recover 与 handoff 安全语义保持不变。`workspace reconcile-handoff` 只处理 graceful running handoff 后、已记录 task-owned WIP 被有证据 closeout 确定性清理成 semantic-clean 而造成的 ownerless provenance deadlock：要求 lease absent、latest round=`released_to_running_handoff`、无 unresolved effect、generation 对齐、cleanup path 原本 task-owned 且有 write intent、当前已 semantic-clean，并精确解释全部 handoff-drift conflict；仍 dirty 的改写和未知漂移继续 fail-closed。成功只重建 provenance baseline、写 `last_workspace_reconcile.json` 审计 receipt，不取得 ownership、不执行 recover。stale / legacy-unverified owner 的 generation-bound challenge 形成后，`coordination wait`（alias `await`）以单次 blocking tool call 读取持久化 `deadline_at`，等待 `owner_active | owner_released | timeout`；它不依赖模型纯 idle、不改变 challenge window、永不授予 ownership。pending challenge 本身不是 session-end signal；timeout 后必须 fresh evidence + formal reconcile/recover，且当前 activation 仍存在时应在同一 activation 继续真正项目工作。directive inbox 是独立的用户 authority signal，不是第二套 Task Plan；pending directive 在 authority refresh 中优先于旧 persisted `next_action`，长 session 通过 heartbeat/renew 的 revision/digest change signal 发现 steering；generated guidance 要求实际 consumed directive 在控制点显式 disposition。`.72` 将 scheduler bootstrap 与 generic state machine 重新分层：wrapper 必须是 sufficient high-salience bootstrap，完整携带 exact existing workspace / connector mode、stable ACF upgrade-adaptation、authority refresh、execute-generated-plan、owner disclosure 与项目专用约束；generated prompt 则按当前 owner/workspace/effect 状态 progressive disclosure，只输出当前相关控制分支。`state.next_action` 在 authority refresh 后仍有效时是默认执行计划，不是 quota。`prompt --runner-id` 通过 `owner_context` 区分 current owner、verified live other owner、stale/unverified、expired 与 no-owner；未提供 runner identity 时保持 caller-unknown。`coordination attempt` 遇到 fresh owner 时不再自动 challenge，healthy duplicate wake 可以让行结束当前重复 session 且不改变 mission；stale / legacy-unverified owner 才进入自动 challenge + blocking wait + formal reconcile/recover。**当默认计划显式等待真实外部/项目状态变化时，scheduler wake、coordination attempt 与 claim 只属于 control-plane bookkeeping，不算满足该等待条件的项目进展；如果 authority refresh 后没有其他当前可执行的安全、有价值工作，当前 wake 应在不 claim、不改变 task 状态的前提下结束，而不是通过 claim 人为制造 lifecycle change。** final response、commit/checkpoint/Gate、timing 的既有非停止语义继续保持，任务级 hard stop 仍只有总体目标完成、用户暂停、需要新的人工授权/凭据/不可替代决策或项目访问工具经合理重连仍不可用。
- credential-redacting / high-entropy-rejecting command transport 应设置 `ACF_CONTINUATION_FENCE_TOKEN_FILE`：`claim/recover` 将新 fence token 写入调用方控制的临时文件并只返回非敏感 file-transport metadata；同一环境变量随后为 `assert-owner/heartbeat/renew/checkpoint/release/progress/effect/workspace` fenced 命令提供 credential，避免 raw token 进入命令文本。文件缺失或非法时 fail-closed，canonical `~/.acf` 仍只保存 token hash，临时文件由调用方在 release 后删除。
- `workspace reconcile-handoff` 不隐式接受 Git HEAD 漂移：若 reviewed closeout 在清理 task-owned handoff WIP 的同时推进了 HEAD，调用方必须显式传入与当前 HEAD 精确相等的 `--accept-head`，并附 durable evidence；参数缺失或不匹配继续 fail-closed，防止借 cleanup 顺带吞掉未知 commit。
- `coordination wait|await` 只观察一个已持久化 challenge：`owner_active` 立即让行，`owner_released` 重新 doctor 后走正常 claim，`timeout` 只表示旧 owner 的 ownership claim 可进入正式恢复裁决。wait 的本地 poll interval 不是语义超时，唯一边界来自 challenge `deadline_at`；wait 始终 `ownership_granted=false`，因此不会把“等到超时”偷换成自动抢锁。

长期 Writer 的“没有其他安全有价值工作”不是默认假设，而是需要证据支持的结论。只要 overall mission 仍 open，Agent 必须先主动审计并切换到 blocker/root-cause diagnosis、adjacent gap implementation、validation/evidence、reusable contract hardening、accessible-target dogfood、release preparation 或 low-side-effect diagnostics 等替代 lane；某一条路径 blocked 不等于整个 activation 应 waiting/no-op。anti-busywork 只禁止输入、环境、证据和策略都未变化时机械重复同一失败动作；新的诊断、changed strategy 或低副作用实验只要能降低不确定性就仍是合法工作。默认以 overall mission/当前 PLAN stage 作为 work unit，不为单个 bug、实验、test、checkpoint 或 release Gate 拆新 Workstream；自然 checkpoint 后 refresh authority 并继续。只有 alternative audit 证明当前安全增量 lane 均无价值，或者命中正式 hard stop，当前 execution session 才可结束。控制面检查必须与 evidence-backed risk 成比例，优先使用最便宜、确定且可审计的安全 continuation 路径；active lease、历史 abnormal generation、task-owned dirty、scheduler wake、checkpoint/test/commit/Gate 或一个 blocked lane 本身都不是结束理由。wall-clock 和 lease timing 只作诊断/liveness mechanics，不是固定 work budget。genuine safe session end 应先持久化准确 progress/next_action/evidence，再用 authenticated `continuation release --handoff` 释放 owner/round 且保持 state=`running`，避免故意留下 stale owner；verified-live physical execution 仍严格禁止 duplicate。`continuation prompt --json` 的 `execution_observability` 将 bootstrap/control-plane、project work、physical execution、graceful handoff、abnormal/incomplete termination 与 recovery overhead 分开报告，所有 timing/overhead 字段均不得转化为固定执行时限。
- compact `state.json` 中只有 `completed / evidence_refs / verification` 这三个历史型摘要采用 rolling 64；`constraints / open_questions / plan_refs` 继续严格限 64 项并在超限时 fail-closed，避免静默丢失仍有效的语义约束。`constraints / open_questions` 表示当前 compact authority hint，不是不可撤销历史：newer authority 明确 supersede/resolve 后，fenced owner 可用 `continuation checkpoint --supersede-constraint <exact-text>` / `--resolve-open-question <exact-text>` 加 durable `--evidence-ref` 原子退休旧项并同步新的 stage/status/next_action/constraint；CLI 只做 exact-match 机械状态维护，不推断自然语言是否失效。对旧版本已经产生的 current-schema history-list overflow，读取时先做相同的内存裁剪，下一次合法 state write 再落盘；这不会裁剪独立的 rounds/effects/coordination journal，也不放宽 state 总字节、单项大小或 forbidden raw-history 字段限制。

effect journal 容量治理使用 terminal rollover，而不是定期放大一个最终仍会触顶的单文件上限：`effects.json` 满时只归档 `completed|failed` records 到 bounded `effects.archive.NNNNNN.json` segments，archive 继续参与 deterministic logical-key replay protection；unresolved records 不归档，若它们自身耗尽容量则继续 fail-closed。rollover 先原子写 archive 再替换 current journal；中断造成的 exact duplicate 可恢复，不一致 duplicate 直接拒绝。

wrapper / generated prompt 的机器合同由 `continuation prompt --json` 的 `identity`、`current`、`owner_context`、`execution_policy`、`project_context`、`scheduler_wrapper_contract` 与当前 `next_actions` 暴露。`scheduler_wrapper_contract.bootstrap_policy=sufficient_high_salience`，列出 exact workspace/tool mode、stable ACF upgrade、authority refresh、execute generated plan、owner disclosure、project constraints 与 final-response contract 等 wrapper 必须覆盖的启动主题；`copy_generic_state_machine=false` 继续禁止复制 claim/challenge/reconcile/workspace/effect 状态机。`execution_policy` 包含 `next_action_is_default_execution_plan=true`、`next_action_requires_authority_refresh=true`、`active_lease_requires_liveness_verification=true`、`verified_duplicate_owner_may_end_duplicate_wake=true`、`duplicate_wake_exit_is_task_stop=false`、`stale_owner_requires_recovery=true`、`stale_owner_wait_is_tool_backed=true`、`stale_owner_wait_bound_source=persisted_challenge_deadline`、`challenge_pending_is_session_end_reason=false`、`pure_idle_wait_required=false`、`coordination_wait_grants_ownership=false`、`same_activation_recovery_after_timeout=true`、`same_activation_recovery_continues_project_work=true` 与 `contender_must_create_busywork=false`，并继续保留 `next_action_is_work_quota=false`、`final_response_is_terminal=true` 等既有机器语义；对于条件等待计划，还明确给出 `claim_requires_present_safe_useful_work=true`、`control_plane_activity_satisfies_wait_condition=false` 与 `no_useful_work_may_end_wake_without_claim=true`，防止定时唤醒通过 claim 自己制造“新状态”并形成无意义循环。

长期自治在同一 `execution_policy` 上额外机器化：`mission_open_requires_active_alternative_search=true`、`blocked_lane_should_switch_to_safe_alternative=true`、`anti_busywork_scope=unchanged_failed_action_only`、`no_useful_work_end_requires_alternative_audit=true`、`prefer_mission_stage_over_microtask_fragmentation=true`、`checkpoint_requires_authority_refresh_and_continue=true`。这些字段不放宽 ownership/fencing/effect/Git/anti-masking，而是把“先主动寻找安全替代工作，再决定当前 activation 是否可结束”变成稳定 Prompt Execution 语义。

Agent-first P1.5/S2 将上述关系固化为 `automation_prompt_execution_contract` v2，并保持 Writer `acf.continuation.scheduler_wrapper.v1` 的兼容键不变。Writer static wrapper 继续只保存 sufficient high-salience bootstrap、project/task extension slot 与不可静态固化的 volatile fields；dynamic generic authority 仍唯一来自每轮 `acf continuation prompt + execution_policy`。Production Observer static wrapper 则保留 existing-checkout、`read broad / write narrow / control none`、anti-masking、truthful run history、human-first-but-detailed 与 project/target extension slot，同时明确 **Agent 是页面主作者**：可从当前授权的一手来源自主选择展示对象并直接维护 Observer-owned HTML/CSS/SVG/JS。Target Registry 降为 optional navigation hint，semantic-review / Map Review / `primary_visualization` / fixed renderer / presentation lifecycle 均不再是 Agent-authored output 的前置。旧 helper 被显式使用时，其 exact revision/fingerprint/evidence、optimistic concurrency、foreign-project non-interference 与 fail-closed 规则仍保留；legacy render 也不得覆盖 Agent-owned 稳定入口。Agent-owned 稳定入口的更新失败同样必须保留上一份可读的 last-good 页面，不能用失败/半成品替换稳定入口；部分来源失败要显式降级，页面 freshness 也必须继续反映真实失败/陈旧状态，而不是因为 last-good 仍可打开就伪装成新鲜成功。

旧 P2 semantic-review / one-shot / durable-rule runtime 继续作为可选兼容层。`presentation-status`、`review-request-add`、`semantic-review-apply`、`presentation-rule-*` 在调用时仍执行原有 target-local staleness、exact revision/fingerprint/evidence 与 consume/supersede/withdraw 规则，但新 Production Observer 不需要为了更新 Agent-owned 页面机械创建这些状态或执行 Map Review。

旧 P3 `transient-patch-apply|clear` / deterministic re-render 继续只针对 legacy ACF-derived Dashboard，并保留 exact target/presentation revision + fingerprint 的并发保护。该兼容面中的“不得直接改 dashboard”不限制 Agent 在明确 Observer-owned 输出空间直接维护自己的页面；Agent-owned stable entry 与 legacy `dashboard.html` 必须身份可辨，legacy snapshot/render 不得反写新入口。

durable writer 已权威结束但在启动前遗漏真实输出 intent 时，输出先保持 `unexpected_nonoverlap`，不能由后续 refresh 静默归入 task。当前 fenced owner 审阅来源并提供 durable evidence 后，可使用 `continuation workspace reclassify --task-owned <path> --evidence-ref <ref> --reason <review>` 显式纳入任务，或用 `--baseline-external <path>` 明确保留为外部修改。reclassify 只接受当前 unexpected path，task-owned 仍受 Workstream direct write scope 约束；conflict、路径重叠、scope 越界、证据缺失或 provenance 不确定继续 fail-closed。若 ACF-managed `workstream archive` 已把绑定 Workstream detail 从 active 移到 archive、但其 Git checkpoint 尚未形成就发生 owner recovery，scope resolver 可读取并校验 archived detail，保留其原 direct scope，同时只增加 active index/detail 与 archive index/detail 四个精确 lifecycle authority 路径，以便安全接纳已完成的 archive WIP；该窄桥不重新激活 Workstream，也不授予更宽的 Task authority。

普通 `baseline_external` 默认不可 stage/commit。唯一窄例外是当前 authenticated runner 刚通过 `acf workstream scope-add|merge-request|ready|merge-start|done` 为绑定 Workstream 生成 `docs/ai/active/Workstreams.md` 与该 Workstream detail；在 lifecycle/merge 边界，Agent 可审阅 exact diff 与 durable ACF command evidence，并把**仅这两个确定性 control-plane 文件**形成独立 checkpoint。该例外不扩展普通 Task authority write_scope，也不得夹带第三个 baseline/external path。

同一 stale generation 同时残留多个已有 durable external id、且已由 authority 证明 terminal 的 unresolved effects 时，`reconcile` 可按相同顺序重复 `--effect-key`、`--effect-terminal-status` 与 `--effect-external-id`，用一个 receipt 原子绑定全部 assertions；`--effect-evidence-ref` 是该次多 effect observation 的共享 authority evidence 集合。各组数量、external identity 或 observation digest 任一不匹配都继续 fail-closed。write-ahead `effect prepare` 与真正 external submit 之间仍保留更窄的 ownerless abandonment 分支：仅当单个记录仍为 `prepared`、从未取得 `external_id`，且 scheduler/API/Git remote 等外部 authority 能明确证明 submit 未启动时，`reconcile --effect-not-started --effect-terminal-status failed --effect-evidence-ref <ref>` 才能生成 receipt；`recover` 再原子把该 effect 标为 failed。对于没有 external id、但 durable local artifact/state/hash 已明确证明 terminal 的本地确定性动作，`--effect-local-terminal` 可显式收口 `prepared|active` 记录；`unknown`、已有 external id、证据不足或 receipt observation 漂移继续 fail-closed。

ACF_HOME continuation schema 也属于 control-plane contract：`continuation list --all-projects --json` 只读扫描 `ACF_HOME/projects/<root-slug>-<path-hash>/continuation/<task-id>/`，同时暴露 project/task identity、control generation、timing profile、各 state 文件 schema 与 migration/blocked 状态。`continuation doctor` 在可正常加载的 task 上同步返回 `state_compatibility`。支持的 legacy workspace schema 只通过显式 `continuation migrate --dry-run` → `--apply --reason ...` 升级；apply 要求没有 lease record，生成 `last_migration.json` receipt，并对 rounds/effects/coordination/reconcile/recovery 等历史文件保存 byte digest。未知 schema 不自动写回、不丢历史，保持 blocked。
- `observer status|snapshot|interpret|glossary-set|glossary|history`：提供项目级 Global Observer。一个项目对应一个用户级 Observer namespace，同项目 primary checkout 与 ACF 注册 worktree 统一进入观测域；边界固定为 **read broad / write narrow / control none**。Observer 可广泛读取 Git、Workstream、continuation、计划和 evidence，但只写 `~/.acf/projects/<project-id>/observer/` 下的 current/history/self-health/semantic/glossary 与自包含 `dashboard.html`，不 claim/challenge/recover Writer continuation。snapshot 使用稳定重读、一致性 fingerprint、credential-like 值过滤、轻量锁与原子替换；meaningful history 默认永久保留，只做无损 rotation/index。语义解释必须绑定当前 `source_fingerprint`，CLI 负责 canonical identity、confidence、provenance、版本历史与 stale-cache fail-closed；Dashboard 保持 static `file://`、无 HTTP daemon、颜色+文字/符号双重语义。Observer canonical state/history 时间戳继续统一使用 UTC；所有人类可见 Dashboard 时间统一渲染为北京时间 `UTC+08:00`，避免为了展示改写底层排序、去重或证据时间。registry-managed 项目中，primary active/archive lifecycle 是 Workstream project-level authority；只有 registry state=`active` 的 bound Workstream worktree 才参与该 Workstream 当前 source，其他 registered worktree 的历史副本只保留 diagnostics/evidence，不得 ghost-resurrect 已归档 Workstream。production Observer Scheduled Task 与 Maintenance Writer 必须职责分离：production task 才负责例行 snapshot/render，Maintenance 普通 wake 先检查 runs/status/dashboard freshness，不得自己刷新来掩盖 scheduler miss/stale；只有诊断、修复验证、release smoke、installed-state dogfood 或 migration 才允许显式 maintenance snapshot。ACF 自身当前 dogfood 使用 Writer `:04`、Observer `:34` 错峰。Observer Core 不硬编码 MCP、电脑、盘符或项目实例。
- Observer V2 的 Dashboard 可见范围由**显式 user-level Target Registry** 决定，而不是由 Workstream/worktree 的存在自动推断。`acf observer targets` 只读查看注册目标；`target-set` / `target-remove` 管理 `fixed_workstream` 或 `project_dynamic` target；无 continuation 的外部自动任务用 `target-run-start` / `target-run-finish` 写窄范围 run marker，异常/中断 run 不伪造结束时间；`project-overview-set --decision enabled|disabled|undecided` 记录是否存在可解释的统一项目路线，其中 enabled/disabled 必须带 authority fingerprint 与 evidence。每个注册 target 有独立 tab、Workstream/continuation scope、run chain、Alerts 与 Timeline；未注册 Workstream 的状态/Alert 不得泄漏到 target 可见范围或 Overall Health。Project Overview 只有 authority 明确 enabled 时才显示统一 Narrative/Map，异构目标可保持 disabled/undecided，不能为了页面完整度强拼路线。
- 使用状态日志：`log enable|disable|status|tail|summarize|projects|prune` 管理默认开启的用户级全局 usage event log，按项目子目录记录命令结果元数据；`log projects --scan-root <path> --json` 支撑跨项目 dogfooding 和旧项目升级盘点。
- CLI 渐进式披露入口：`acf status|next` 未显式选择 Workstream 时返回 `GlobalOnly`，只给全局文件指针和 Workstream 摘要；attention 不参与路由。显式 `--workstream`、Active Current_Task 唯一绑定或 verified worktree 只返回 pointer-only 入口，随后再调用 `acf workstream context WSNNN` 才披露专属内容。冲突或无效选择保持全局并以结构化错误 fail-closed。模板和 minimal init 产物只提示这些入口、`acf --help` 和系统手册发现路径，不在默认入口列完整命令手册。
- 最小 smoke runner：`scripts/minimal_smoke.py` 使用隔离临时目录和 CLI JSON 输出，覆盖 `init -> nested status/check`、`new worklog create/append/error_code`、Workstream 最小 happy path、archive-candidates / archive-draft / explicit archive 主路径和 Task Stage 最小 happy path；最终汇总 JSON 使用 ASCII-safe escaping，避免 Windows legacy console code page 因 Unicode 文本导致 release smoke 假失败。Git worktree 事务由 `tests/test_worktree_cli.py` 的临时真实仓库矩阵单独覆盖，不接触用户仓库。
- 升级兼容 runner：`scripts/upgrade_matrix.py` 使用风险驱动 fixture 验证旧上下文可被非破坏式带到当前工具可治理状态；quick 模式随单元测试运行，full 模式用于 release 前扩展检查。
- 发布验收 runner：`scripts/release_check.py` 可运行 template/strict、minimal smoke、unit、full upgrade matrix，并在隔离 uv 环境中分别安装 wheel 与 sdist，验证 `acf --version`、`acf init`、`acf check --strict` 和 `uv tool install` console script。
- 一键安装/更新脚本：`scripts/install_acf.ps1`、`scripts/update_acf.ps1` 和对应的 `sh` 入口只依赖已安装的 uv；Windows PowerShell 路径在修改全局 tool 前先检查 `uv` tool 环境/`acf.exe` 是否仍被 ACF 进程占用，有占用时 fail-closed，不让 `uv` 先删一半再因文件锁失败。Windows 脚本在 uv mutation 完成后原子生成 uv tool bin 下的 canonical `acf.cmd`，由该 tool environment 的 Python 执行 `-m acf`，再删除同目录 uv console-script `acf.exe`；这是为了机械消除 `.EXE` 在常见 `PATHEXT` 中先于 `.CMD` 的解析歧义，而不是新增第二套 CLI 或 signing/certificate policy。若 tool bin 已在 PATH，脚本还要求 `Get-Command acf` 的第一应用解析结果就是该 `acf.cmd`。`update_acf.ps1` 使用未固定版本的 `uv tool install --force --upgrade`，避免精确版本 receipt 让 `uv tool upgrade` 长期停在旧版；`-Reinstall` 用于无并发进程时修复当前最新稳定版。自动化/多 Writer 环境应优先走该脚本而不是裸跑 `uv tool upgrade/install --force`，因为裸 uv mutation 会重新生成 `acf.exe`。GitHub Actions 的 CI 和 `v*` tag 发布 workflow 负责测试、构建和 PyPI 发布，Trusted Publishing 配置仍需在 GitHub/PyPI 侧完成。
- Context governance fixture matrix：`tests/fixtures/context_matrix/` 和 `tests/test_context_matrix.py` 覆盖 minimal clean、legacy reference、audit long section、complex Workstream、Workstream lifecycle/archive candidate 和 authority gate，作为 P3 audit rule expansion 前的防过拟合样本。

这些检查不需要模型判断，适合作为每次模板修改后的基础验证。

## 长期阶段计划：AI-facing CLI

长期方向是把 `acf` 从仓库内脚本演进为可安装、可在任意目录调用、主要面向 AI 使用的上下文维护 CLI。它的定位是上下文文件 API，而不是通用 Markdown 编辑器。

### 阶段 1：可安装命令和上下文发现

状态：已实现第一版；PyPI 发布、安装、更新和发布前验收闭环已加入仓库，正式启用还需配置 PyPI 项目和 Trusted Publishing。

目标：

- 提供可安装命令 `acf`，保留 `uv run python acf.py ...` 作为本仓库开发入口。
- 支持从任意子目录自动发现上下文根目录。
- 增加 `acf status`，输出当前项目根、上下文目录、profile、当前任务状态和最近检查结果；默认不选择 Workstream，显式 `--workstream` 才返回专属 pointer。
- 写操作默认作用于发现到的上下文目录，也允许显式传入目标路径覆盖。

验收：

- 在项目任意子目录运行 `acf status` 能定位同一套上下文。
- 不传路径即可运行常用 `check` 和 `new` 命令。
- 无新增第三方运行依赖。

### 阶段 2：AI 友好输出和安全执行模式

状态：已实现第一版，并完成 JSON schema 基础字段、exit code 和错误分类细化。

目标：

- 全局支持 `--json`，让 AI 能稳定读取 changed files、warnings、errors 和 next actions。
- 全局支持 `--dry-run`，预览写入结果。
- 写命令输出被修改文件列表，并可选执行写后 `check`。
- 统一 exit code，区分成功、检查失败、输入错误和安全拒绝。

验收：

- AI 无需解析自然语言输出即可判断下一步。
- 所有写命令都有 dry-run 测试。
- 失败输出包含足够定位问题的信息。

已完成：

- `status --json` 和 `check --json` 输出可解析 JSON。
- JSON 输出包含 `schema_version`、`ok`、`error_code` 和 `next_actions`。
- 检查失败时 `error_code` 为 `check_failed`，AI 可以读取 `next_actions` 决定后续动作。
- 退出码已区分成功、检查失败、输入错误、安全拒绝和非预期运行时错误。
- 写命令输出 changed files，支持 `--dry-run --json` 预览。
- 写命令支持 `--check-after`。
- `check template` 会校验 `pyproject.toml` 中模板 data-files 与 `template/` 文件同步，避免打包漏文件。

### 阶段 3：安全结构化编辑

状态：已实现第一版。

目标：

- 提供面向 AI 的结构化 Markdown 编辑原语，而不是自由文本编辑器。
- 支持 section get、section replace、section append。
- 支持 table upsert，用于维护索引类文件。
- 所有编辑必须限制在上下文根目录内，拒绝路径穿越。

验收：

- 常见上下文维护任务可以通过 CLI 完成，不需要 AI 手工拼接整文件。
- 写入后 `check --strict` 能稳定发现结构漂移。
- CLI 不理解语义，只做确定性文件编辑和校验。

已完成：

- section get 支持读取精确 Markdown heading 下的正文，并可输出 JSON。
- section replace 和 section append 支持 `--text`、`--input`、stdin、`--json`、`--dry-run` 和 `--check-after`。
- table upsert 支持精确表头或首表匹配，按 key column 更新或追加行。
- edit 写操作只允许目标为上下文根目录内已有 `.md` 文件，并拒绝路径穿越和非 Markdown 目标。

### 阶段 4：草案和 subagent 接入

目标：

- 保持权威上下文由人或主代理审阅后写入。
- 让 subagent 产出分类草案或建议 patch，而不是静默修改权威文件。
- 优先完善 `writeback-curator`、`decision-curator`、`history-distiller` 和 `source-curator`。

验收：

- subagent 输出可以直接转成 `writeback draft` 或 dry-run patch。
- 权威文件写入仍有明确审阅点。
- 不引入常驻 runtime、数据库或私有存储。

### 阶段 5：跨项目 dogfooding 评测

目标：

- 在其他真实项目中验证初始化、发现、检查、写入和回写流程。
- 默认启用用户级全局 usage event log，按项目子目录记录命令成功率、错误类型、dry-run 使用和 changed files 规模。
- 记录 AI 使用 CLI 与直接手改 Markdown 的错误率差异。
- 只把重复出现的人工动作产品化成新命令。

验收：

- 任意目录调用的成功率和错误信息可评估。
- 常见维护动作中，大多数可以由 CLI 完成。
- 新能力没有破坏“纯 Markdown、模型无关、人工可审阅”的边界。
- usage event log 只记录状态元数据，不记录正文输入，不进入 `worklog/`。

### 阶段 6：事实与注意力治理

状态：P0 governance hardening 已以 `v0.0.3.26` 作为稳定基线收口；P1 `audit context` MVP 已实现为只读 candidates 命令，不生成 patch，不接入默认 strict。既有 `review stale`、`curate draft` 最小版、upgrade compatibility runner 和 Context Curation Prompt Template 继续保留。

目标不是保存更多上下文，而是持续维护一个低噪声、高权威、任务相关的默认注意力入口。

原则：

- `active/` 只保留当前目标、当前事实、当前任务和下一步。
- 写入前必须判断唯一权威位置；能更新旧表述时，不追加重复事实。
- worklog 记录历史过程，archive 保存历史材料，Feedback_Inbox 和 human 保存待处理或未整理信号；它们默认不作为当前事实。
- 整理事实时优先读取 changed files、`active/`、相关索引和最近 worklog。
- 不为 curation 默认读取 archive 或全部历史日志；writeback draft 和 curation draft 不进入默认读取路径。
- CLI 只做机械发现和草案生成，不裁决语义事实。

P1 命令：

- 已实现：`acf review stale` 机械检查默认注意力入口是否可能过期，例如 Active 当前任务长期未更新、Feedback 长期未处理、Context 缺少审阅信号、Knowledge 草案长期未推进；命令只读，只输出 stale candidates，不判断内容真假。
- 已实现：Context 文件级审阅标记最小规范，推荐 `Last reviewed: YYYY-MM-DD` / `上次审阅：YYYY-MM-DD`，不要求条目级事实 ID。
- 已实现：`acf review stale --json` 输出契约增强，提供稳定 `kind`、`reason`、`age_days`、`status`、`suggested_action` 字段和 `summary.by_kind` / `summary.by_path` 汇总。
- 已实现：`acf review stale` 的 clean 状态和 `next_actions` 精炼；无 stale candidate 时明确报告 clean，有候选时按 `kind` 给出低风险机械下一步建议。
- 已实现：`acf curate draft` 最小版只消费 `review stale` 的结构化 stale signals，生成 `worklog/curation-drafts/` 下的可审阅注意力治理草案；无候选时不创建空草案，同名草案已存在时安全拒绝。
- 已实现：`acf audit context` MVP，只读输出 active 层上下文治理 candidates；第一版仅覆盖 `active_section_too_long`、`stale_current_task_or_workstream_stage` 和 `terminal_conclusion_not_merged`（ReadyToMerge 待合并或 Done 缺合并结果），不判断事实真假、不写文件、不接入 strict。
- 已实现：`acf doctor`，设计文档为 `docs/ai/reference/Doctor_Reconcile_Design.md`；命令默认只读，报告 Task / Current_Task 生命周期漂移、终态 Workstream authority scope 残留、Workstreams / Archive generated index 漂移、Workstream 协议 drift、Decisions / Sources / data evidence 和 attention hygiene findings；`--fix safe` 只做可回退的确定性修复，数据 hash 证据只读取项目根内相对路径，`--report` / `--draft-semantic` 生成人工可审阅产物，`--projects` 用于多项目只读巡检。
- 已实现：upgrade compatibility runner，以 `tests/fixtures/upgrade_matrix/` 的最小旧形态 fixture 验证旧项目可以升级到当前工具可治理状态，而不是自动变干净；runner 先执行 `upgrade --plan --json` 验证只读评估和 no-write/no-log，再执行 dry-run/apply/idempotency 检查；quick 模式随单元测试运行，full 模式作为 release 前扩展检查。
- 已实现：`reference/Context_Curation_Prompt.md` 作为按需读取的上下文整理 prompt 模板，帮助 AI 输出整理建议；它不是默认 active 规则，也不是 CLI 自动语义清理能力。
- 后续增强：`acf curate draft` 可再考虑基于 changed files、`active/`、索引文件和最近 N 天 worklog 生成更丰富整理草案，列出疑似重复事实、疑似陈旧 active 内容、已完成但未归档任务、已处理但仍留在 inbox 的内容，以及可能应升格到 Context / Knowledge / ADR 的近期结论。

暂缓：

- 全量事实 ID 化。
- 每条事实 `Last reviewed`。
- 语义级自动去重。
- CLI 自动判断哪个事实是真的。
- curation draft 默认进入读取路径。

### P0 governance hardening baseline

状态：已完成，基线版本为 `v0.0.3.26`。

**P0 governance hardening**：先把 FCC 暴露的阶段注册、Workstream 内部阶段焦点、权威写入、合并结果、active 滞留做成 `acf check --strict` 的确定性门禁；generated index 只在 Workstream 上先检测后 sync；content audit 独立后置，不进入默认 strict。

实施顺序：

1. Task Stage registry：在 `active/Task_Plan.md` 增加 `## 任务阶段` 表，检查 `T001.4` 这类阶段编号的注册、父任务和 Workstream 绑定。
2. Workstream Stage Focus：在 Workstream 详情中支持 optional `current_stage` 和 `## 阶段` 表，检查 `WS004.2` 这类内部阶段注册、归属、唯一 Active 阶段和终态 Workstream 阶段状态；第一版不实现 stage CLI，也不实现全局 `active/Current_Task.md` 阶段对齐。
3. Authority write gate + `merge_targets`：禁止 Workstream 通过 `owned` / `assigned` 直接 claim 内置 authority path；需要影响权威文件时使用 `merge_targets` 和合并请求；本阶段不做 `merge_resolution`。
4. Merge resolution + active retention gate：Done Workstream 必须有 evidence 和 `merge_resolution`；Done / Cancelled 留 active 必须有 `keep_active_reason` 和 `keep_active_until`。
5. Workstream index consistency check, then sync：PR 4a 先检测 `active/Workstreams.md` 与详情 front matter 是否一致；PR 4b 引入 `acf workstream sync --dry-run --json`，只更新 `active/Workstreams.md`，不删除缺详情的旧索引行。
6. 后续独立 `audit context`：只输出 candidates，不进入默认 `check --strict`。

非目标：

1. 不新增 task object 单文件。
2. 不引入可配置 authority map。
3. 不让 generated index 覆盖 Knowledge / ADR / Archive。
4. 不把 content audit 接入默认 strict。
5. 不做自动事实裁决、自动语义去重或自动合并权威上下文。
6. PR 1b 不实现完整 `acf workstream stage` / `focus` 命令。

基线验证：

```bash
uv run acf check template
uv run acf check docs/ai --strict --json
uv run acf upgrade docs/ai --dry-run --json
uv run python -m unittest
uv run python scripts/minimal_smoke.py --acf uv run acf
uv run python scripts/upgrade_matrix.py --mode quick
```

### P1 audit context MVP

状态：MVP 已实现。设计文档为 `docs/ai/reference/Context_Audit_Design.md`。

目标：

1. 定义只读 `acf audit context docs/ai --json` 的输出契约。
2. 只输出 candidates、summary 和 next_actions。
3. 不进入默认 `acf check --strict`。
4. 不自动修改 `active/Context.md` 或其他权威上下文。
5. 不做事实真假裁决、自动语义去重或自动合并。

第一版已实现候选规则限定为：

1. active section too long。
2. stale current task / stale workstream stage。
3. ReadyToMerge conclusion not merged / Done missing merge resolution。

暂缓：

1. duplicate active facts candidate。
2. volatile fact in wrong authority location。
3. strong claim without evidence。

默认读取范围只覆盖当前注意力入口和 Workstream 当前状态：

- `active/Context.md`
- `active/Current_Task.md`
- `active/Task_Plan.md`
- `active/Workstreams.md`
- `active/workstreams/*.md`

非目标：

1. 不做自动事实裁决。
2. 不做自动语义去重。
3. 不默认修改 `Context.md`。
4. 不进入 `check --strict`。
5. 不读取 archive 或全量 worklog。
6. 不生成 patch 或自动修复。

MVP JSON 形态保持极小：

```json
{
  "candidates": [],
  "summary": {},
  "next_actions": []
}
```

## 适合继续程序化的工作

优先做可验证、低歧义、可回退的命令：

1. 根薄入口自定义字段：允许用户在生成时追加少量仓库级规则，但仍不把完整上下文写入根入口。
2. `doctor` 后续增强：把更多真实项目中重复出现的机械漂移纳入 findings；新增自动修复前必须先有只读 finding、fixture 和 dry-run 测试。
3. `audit context` 后续增强：只在 MVP 稳定后评估 duplicate / evidence / volatile location 候选，仍保持只读 candidates，不接入 strict。
4. `curate draft` 后续增强：在当前 signal -> draft 边界内补充 changed-files / duplicate 机械信号。
5. `writeback-curator` 接入：由 subagent 生成更高质量的回写分类草案，但仍只输出草案。
6. 跨项目 dogfooding 评测脚本：记录常见命令是否能在真实项目子目录稳定运行。
7. 安全项目级编辑能力：评估是否需要让 CLI 在明确授权下维护 `docs/ai/` 外的仓库级文档；当前不放宽 `acf edit` 的 context-root 限制。

这些命令应默认只生成草案或骨架。真正写入权威上下文前，仍应由用户或主代理确认。

## 适合 subagent 的工作

subagent 适合处理需要语义判断、但不应静默修改权威文件的任务：

1. `readset-planner`：根据用户任务建议应读取哪些上下文文件，避免过读或漏读。
2. `writeback-curator`：把会话结果分类到 Context、Current_Task、Decision、Worklog、Archive。
3. `decision-curator`：判断某个结论是否应升格为 ADR，并草拟决策内容。
4. `history-distiller`：从 daily worklog 提炼关键结论，标记应同步到 Context 或 Decisions_Index 的候选内容。
5. `source-curator`：整理外部资料摘要、可信度和后续动作。

这些 subagent 的输出应是草案、评审意见或建议 patch，不应默认直接应用。

## 暂不建议自动化

以下内容现在不适合进入 MVP：

- 常驻 daemon 或 chat runtime。
- 向量库、数据库或私有格式存储。
- 通用 Markdown 编辑器。
- 让 CLI 进行语义判断或事实裁决。
- 让 subagent 自动修改 `active/Context.md`、`reference/Decisions_Index.md` 或 ADR 并静默提交。
- 用复杂编排替代当前的 Markdown 事实源。

原因是这些功能会削弱“模型无关、人工可审阅、文件即事实源”的设计边界，并提高调试和迁移成本。

## Dogfooding 规则

修改本项目时，应把本仓库当成第一个使用者：

1. Python 代码优先通过项目 uv 环境运行：`uv run python ...`。
2. acf CLI 优先通过项目 uv 入口运行：`uv run acf ...`；需要调试脚本入口时再使用 `uv run python acf.py ...`。
3. 发布前快速回归可运行 `uv run python scripts/minimal_smoke.py --acf uv run acf`；该脚本只验证少量最小主路径，不替代真实项目评测矩阵。
4. 模板结构变化后运行 `uv run acf check template`。
5. CLI 行为变化后运行 `uv run acf check --strict`、`uv run python -m unittest` 和 `uv run python -m py_compile acf.py tests\test_cli.py tests\test_upgrade_matrix.py scripts\minimal_smoke.py scripts\upgrade_matrix.py`。
6. 修改 `upgrade`、模板结构或注意力治理入口时，发布前运行 `uv run python scripts/upgrade_matrix.py --mode full --acf uv run acf`。
7. 发布前完整验收运行 `uv run python scripts/release_check.py --mode full`；只验证 wheel/sdist 安装链路时运行 `uv run python scripts/release_check.py --mode package`。
8. minimal 实例不保留 ADR 和 worklog 的占位模板文件，真实条目通过 `new adr` 和 `new worklog` 生成。
9. standard 实例包含 `human/Human_Notes.md`、`human/weekly/` 和 `human/reports/`，用于人工异步笔记、周记录和汇报材料；minimal 实例不补 human 层。
10. Obsidian `[[双链]]` 只服务人工导航，ACF 不解析、不校验、不依赖双链；结构化引用仍使用普通 Markdown 路径。
11. 模板占位符统一使用 `【ACF:KEY|提示】`，表格单元格内使用 `【ACF:KEY】`；机器维护块统一使用 `<!-- ACF:<DOMAIN>:<PURPOSE>:START --> ... END -->`。
12. 新增或重置当前任务时优先使用 `new task`，维护大任务 reference 规划依据时优先使用 `plan reference`，新增资料索引时优先使用 `new source`，重要设计决策优先使用 `new adr`，当天工作记录优先使用 `new worklog`。
13. 会话结束回写建议需要暂存时，优先使用 `writeback draft`，再由人或主代理审阅后决定是否写入权威上下文。
10. 维护 `docs/ai/` 内已有 section 或 table 时，优先使用 `edit section` 或 `edit table upsert`，高风险写入先用 `--dry-run --json`。
11. 修改 `docs/Automation.md` 等 `docs/ai/` 外仓库级文档时，当前仍使用常规补丁；是否提供项目级安全编辑能力应作为独立设计处理。
12. 需要评估 CLI 实际使用效果时，可用默认开启的 usage event log；日志是运行态元数据，不是 worklog。如需关闭某项目日志，运行 `acf log disable`。
12. 修改 `template/` 前先确认该变更属于通用产品模板需求，而不是本仓库 dogfooding 特例。
13. 如果发现跨文件同步问题，优先考虑补充 `acf.py check` 规则，而不是只补文档说明。
14. 如果某项维护动作重复出现两次以上，评估是否应新增 CLI 子命令或 subagent 草案流程。
