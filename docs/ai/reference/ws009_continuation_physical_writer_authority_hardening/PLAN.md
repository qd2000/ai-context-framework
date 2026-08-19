# WS009 Continuation physical-writer and authority-drift hardening plan

## 状态

Active

## 目标

在不把 ACF 扩展为 agent runtime、进程管理器或语义事实裁判的前提下，收口 v0.0.3.63 dogfooding 暴露的通用问题：

1. continuation 的 generation fencing 只能保证 ACF-authorized writer，不能自动识别旧 generation 已启动、在 recovery 后继续写同一路径的 physical writer；
2. active attention / authority 生命周期存在可机械发现但当前 doctor/audit 未发现的滞留和 review drift；
3. Git/worktree 生命周期把 content-identical 的 stat/status-only 变化误报为 dirty，并且 Workstream reservation/worktree 的 Markdown 与本地 runtime authority 之间存在状态漂移。
4. legacy continuation 在没有 workspace manifest 时缺少显式 WIP adoption/import 路径；已经人工审阅确认属于当前任务的 dirty WIP 仍会被 `workspace_provenance_missing` 阻塞，只能先形成 semantic checkpoint 或破坏性 `init --force`。
5. expired owner 留下的 `prepared|active|unknown` effect 即使已经由外部权威证明终态，当前 `effect update` 仍要求旧 active fence，而 `reconcile/recover` 又因 unresolved effect 拒绝接管，形成 ownerless effect-reconciliation deadlock。
6. continuation runtime state 虽已统一走 `ACF_HOME/projects/<root>-<path-hash>/continuation/<task-id>/`，但缺少面向升级/诊断的统一可见性与迁移合同；Scheduled Task 的 generic protocol 已由 `acf continuation prompt` 统一生成，外层 project wrapper 仍主要靠人工/对话约定，容易再次漂移。

WS009 必须优先修复 correctness / deterministic governance 缺口，再做文档、release 和真实项目 adoption；便利性功能不阻塞发布。

## 第一性原理不变量

1. **Logical single writer**：同一 continuation task 同一时刻只有一个 fenced generation 拥有 ACF 写授权。
2. **Unknown physical writer fail-closed**：如果存在可能跨 generation 继续写项目文件或产生 side effect、但没有可复用 durable identity 的执行实体，不得把 recovery 宣称为安全。
3. **Dirty 不是冲突**：继续以 path/status/content digest/provenance/effect/HEAD/identity 判断具体冲突，不恢复 worktree-level blanket dirty gate。
4. **Commitless handoff 保留**：continuation handoff 与 Git semantic checkpoint 继续解耦，不为了释放 lease 制造半成品 commit。
5. **外部/长生命周期写操作必须有 durable identity**：能够跨越当前 Agent/tool-call 生命周期继续产生写入或 side effect 的 subprocess、DevSpace session、Runtime job 或外部作业，都按 effect/job 处理；无法持久识别和核对的 detached writer 不属于自动 recovery 的安全支持范围。
6. **语义不确定不进 strict**：Context 内容真假、版本语义等不由 CLI 自动裁决；机械 stale/terminal-retention 信号进入 review/audit/doctor candidate，必要时生成明确 next_actions。
7. **本地 runtime state 不冒充 Markdown 事实**：机器相关 worktree path/branch/binding 以 Git/ACF local registry + `worktree verify/list` 为运行期权威，不在共享 Workstream Markdown 中维护易漂移的“当前本地状态”副本。
8. **无第三方运行依赖**：继续只使用 Python 标准库、Git 和 Markdown；不新增 daemon、数据库、向量库或私有进程 supervisor。
9. **统一状态实现，隔离命名空间**：所有 continuation task 必须复用同一 `ACF_HOME`、目录解析器、schema 与原子写入路径；不同 resolved project/worktree 通过 path-hash namespace 隔离，不复制项目私有状态实现，也不把所有任务塞进一个共享可碰撞目录。
10. **Prompt 单一 generic authority + 薄 wrapper**：generic contention/recovery/workspace/effect 协议只由 `acf continuation prompt` 生成；scheduler wrapper 只保留固定执行身份、如何每轮获取 generated prompt、项目特有运行/科学/权限/验证约束。不得把 generic 状态机复制进 wrapper，也不得把项目科学判断硬编码进通用 ACF prompt。
11. **统一不等于限制推理能力**：ACF 统一的是可验证的 control-plane、安全边界、状态 schema 和 prompt 入口，不规定 Agent 的工程推理步骤、搜索策略、测试组合或一个自然 Gate 内的自主决策；只有冲突、身份、未决副作用和未知写结果继续 fail-closed。
12. **动态目标不写死在 Scheduled Task**：Scheduled Task 是稳定启动器，不是任务计划事实源。WS009 的问题、优先级、阶段、技术路线和成功标准以 Workstream + PLAN 为持久权威；continuation `state.next_action` 只保存当前 bounded 执行指针。普通目标调整通过更新 PLAN/stage/scope/next_action 生效，不要求重写 Scheduled Task。

## 标准 ACF 长任务结构

WS009 同时 dogfood 一套后续可复用的 ACF 长任务结构。标准任务最少只需要：

```text
docs/ai/
├─ active/
│  ├─ Workstreams.md
│  └─ workstreams/
│     └─ WS009.md
└─ reference/
   └─ ws009_continuation_physical_writer_authority_hardening/
      ├─ PLAN.md
      └─ SCHEDULED_TASK_PROMPT.md
```

复杂协议任务可按需要渐进增加：

```text
PROBLEM_MATRIX.md
FAILURE_MATRIX.md
ADOPTION_MATRIX.md
```

职责必须保持单一：

1. `WS009.md`：当前状态、current_stage、read/write scope、证据指针、merge contract；不复制完整问题分析。
2. `PLAN.md`：任务问题矩阵、优先级、解决策略、阶段依赖、成功标准和非目标，是 WS009 技术路线的单一持久权威。
3. `SCHEDULED_TASK_PROMPT.md`：可直接复制到外部 scheduler 的薄 wrapper；只保存固定身份、每轮入口、任务级 guardrails 与动态目标解析规则，不保存 generic continuation 状态机。
4. `~/.acf/.../continuation/<task-id>/`：lease、generation、workspace ownership、round/effect/recovery 等运行态；不进入 Git，也不由人或 Scheduled Task 手改 JSON。
5. optional matrix 文件：仅当问题/失败/adoption 证据复杂到 PLAN 不宜继续膨胀时创建，不作为所有 WS 的强制模板。

## 目标与需求动态变更协议

### 权威优先级

交互式人工变更发生时，以用户最新明确指令最高；一旦决定让后续无人值守轮次继承，必须把变更落到本地权威状态。无人值守 Scheduled Task 的解析顺序统一为：

1. 当前 verified Workstream identity / scope；
2. 最新 `WS009.md` current_stage 与本 `PLAN.md`；
3. continuation state 中的 status / next_action / constraints / evidence refs；
4. Scheduled Task 静态 wrapper 中的历史描述。

如果 PLAN/current_stage 已经因为较新的人工需求发生变化，而 continuation `state.next_action` 仍旧陈旧，合法 owner 应先按当前 generated continuation protocol 更新 bounded checkpoint/next_action，再执行新的有效 Gate；不得机械执行陈旧 next_action，也不得绕过 ownership 直接手改 state JSON。

### 变更粒度

1. **小调整**：只改变执行顺序或下一步，不改变 mission/scope。更新 current stage 的 next_action 和 continuation checkpoint 即可。
2. **中等调整**：仍属于 WS009 mission，但新增/删除问题、改变优先级或技术路线。更新 PLAN，必要时调整 Workstream stage、scope 和 continuation next_action；Scheduled Task 不改。
3. **安全不变量变化**：例如决定允许 daemon/PID supervisor、改变 authority 规则或自动事实裁决。这属于产品边界变化，必须有明确人工批准，并同步 ADR/rules/PLAN；不能由 Scheduled Task 自行演化。
4. **根本换题**：新需求已经超出 WS009 mission。WS009 应完成、暂停、取消或保留边界说明，再 reserve 新 Workstream；不得无限扩展当前 WS。

### 何时才修改 Scheduled Task

只有两类变化需要修改外部 Scheduled Task：

1. 固定 identity 变化：project/worktree/branch/workstream/task-id 发生正式迁移；
2. ACF 官方 thin-wrapper contract 本身升级，需要统一迁移 wrapper。

普通目标、优先级、阶段和技术路线变化都不应通过 Scheduled Task 文本维护。

## v0.0.3.63 dogfood 基线

以下事实在 WS009 创建前后由本地命令直接验证：

- Lenovo 全局 `acf` 为 `v0.0.3.63`；`uv tool upgrade ai-context-framework` 返回 `Nothing to upgrade`。
- PyPI JSON API 返回最新发布版本 `0.0.3.63`，因此没有重复发布同一 immutable version。
- `acf doctor --json` 对当前 ACF 自身返回 0 findings；`acf audit context --json` 返回 0 candidates；`acf check --strict --json` 通过。
- 同一上下文的 `acf review stale --json` 能发现 `active/Context.md` review marker 已超过默认阈值，但没有发现 Done 的 `Current_Task.md` / `Task_Plan.md` 应退出 active。
- `active/Context.md` 仍保留 `v0.0.3.57` / `v0.0.3.53` 数字版本事实，而真实发布版本已经是 v0.0.3.63；这证明 strict/doctor 不能证明语义事实新鲜度。
- WS009 使用 v0.0.3.63 `workstream reserve -> worktree create -> verify -> worktree sync` 建立；reservation commit 为 `905620d9...`，Active 生命周期提交为 `322a1a2...`。
- `workstream reserve` 默认生成 Open Workstream；直接显式选择 Open WS 会 `selection_invalid`，需要额外 `workstream set ... --status Active`。当前 next_actions 未把这一执行前步骤明确串起来。
- Workstream detail 的 `## Workspace` 仍写 `mode: none`，但 ACF local registry 已有真实 worktree；该 section 的 stateful 字段会自然漂移。
- 新建且原本 clean 的 WS009 worktree 第一次执行 `uv run acf` 后，4 个 tracked `ai_context_framework.egg-info/*.txt` 被 `git status`/`worktree verify` 报为 modified；但 `git diff --quiet` 为 0，working-tree blob hash 与 index blob hash 完全一致。当前 `is_clean()` 只信任 porcelain，因此产生 content-clean/status-dirty 假 dirty。
- FCC WS079 legacy handoff 证明：旧 generation 没有 workspace manifest 时，3 个已经 file-scoped guard 验证、且仅用于 E118 closeout 的 task WIP 仍被 `workspace_provenance_missing` 阻塞；最终只能先形成 semantic recovery checkpoint `eeaea2a2...`，再 `reconcile -> recover -> checkpoint -> release` 建立 v2 workspace manifest。
- FCC WS080 legacy handoff复现同一问题：完成的 per-CN heteroatom/metals Gate 经 machine SHA、focused tests 与 file-scoped guard 验证后，仍必须先形成 checkpoint `f6938d74...` 才能从无 manifest 的旧状态迁入 `.63`。
- FCC WS086 提供更强的 effect recovery 反例：Git/workspace clean，Runtime 0.36.3 权威已证明 `ws086-operation-activity-bulk-q03-v11` 为 `60/60 completed`、`unfinished=0`、`collection_state=collected`，但 effect journal 仍为 `prepared`。旧 owner 已 expired；新 runner 不能 `effect update`，而 `reconcile/recover` 又因 unresolved effect 阻塞。dogfood issue fingerprint=`9b497840ecf1c7a015f2`。
- WS079 legacy migration gap 已记录 dogfood issue fingerprint=`e0151f84e6b5be2e3d4f`。
- FCC WS079/WS080/WS086 continuation timing 已统一到 `long-running` profile（scheduler/TTL/renew/heartbeat/stale=`60/180/45/10/25` 分钟），表明 timing 可以作为统一 control-plane profile，而不应在 Scheduled Task wrapper 中复制定时逻辑。
- 源码确认 continuation state 默认统一落在 `%USERPROFILE%/.acf`（可由 `ACF_HOME` 整体覆盖），项目/工作树 namespace 由 resolved root 的 slug + path hash 派生，task 再位于统一 `continuation/<task-id>` 子树；这是应保留的 canonical layout。
- 源码与 System Manual/Automation 已确认 `acf continuation prompt` 是 generic Scheduled Task protocol 的唯一权威生成器；当前剩余问题是把“薄 wrapper”本身也形成稳定的 help/docs/可机器读取 recipe，而不是继续由不同对话各自复制一份大提示词。

## 问题矩阵与解决策略

### P0-A：post-recovery physical writer attribution gap

**现象**：generation N 已启动一个长生命周期进程；N stale 后 generation N+1 formal recover 并继承同一路径 write intent；旧进程随后写该路径。当前 classifier 在新 generation 持有 intent 时，会把 live digest 变化继续归为 `task_owned`，无法证明字节来自新 owner 还是旧 physical writer。

**原因**：path/digest ownership 能证明“路径当前属于哪个逻辑 task”，不能给 OS filesystem write 打 generation 标签；fence token 只能保护经过 ACF 的操作。

**策略**：

1. 不尝试通过 PID polling、进程 kill、daemon 或 OS lock 把 ACF 做成 runtime。
2. 冻结 cooperative contract：凡是可能在当前 owner/tool-call 结束后继续产生 project write 或 non-idempotent side effect 的操作，在启动前必须 `effect prepare` 获得 deterministic logical identity；启动后记录可核对 external/job identity，并保持 `prepared|active|unknown` 直到权威终态。
3. `prepared|active|unknown` effect 继续阻止 formal recovery；下一 runner 只能查询/复用同一个 identity，不能重新 submit。
4. 无 durable identity 的 detached local writer 明确禁止跨 owner 生命周期运行；需要长计算时交给项目 Runtime/background job，并以 `waiting_external` + job identity handoff。
5. 长时间纯只读/blocking tool call 不要求登记 writer effect，但返回后、任何下一次项目写入或非幂等动作前必须重新 `assert-owner`。
6. 扩充 generated `acf continuation prompt`、System Manual、Automation 和 tests，使 “external/non-idempotent effect” 明确包含 long-lived local subprocess / DevSpace / Runtime writer，而不是只让 agent 联想到远端 API。
7. 添加 deterministic failure injection：旧 generation writer identity 未终态时 recovery 必须 blocked；终态/可证明结束后才允许 generation+1。另保留一项 boundary characterization，明确“完全绕过 ACF 且没有 durable identity 的旧 writer”不可自动归属，不能伪装成已解决。

### P0-B：ownerless externally-proven effect reconciliation deadlock

**现象**：旧 generation 的 effect journal 仍是 `prepared|active|unknown`；owner 已过期且 fence token 不再可用，但项目 Runtime/API/ledger 能以 deterministic identity 证明该 effect 已 terminal/collected/failed。当前 `effect update` 只能由 active fenced owner 写回，而 `reconcile/recover` 在 effect unresolved 时又拒绝建立新 owner。

**策略**：

1. 新增一个明确的 recovery-time effect reconciliation 路径；优先设计为 `reconcile` receipt 的 bounded assertion/evidence，或独立 `effect reconcile`，不得复用普通 owner `effect update` 的语义。
2. 只允许更新**已经存在的 deterministic logical key**，不得借 recovery 新建 effect、改变外部 identity 或触发执行。
3. 必须携带 owner-ended/forfeiture 证据、当前 generation/effect digest、external authority evidence refs 和 terminal classification；receipt 绑定 observed digest，任何 journal/HEAD/identity 漂移都令 receipt 失效。
4. recovery-time reconciliation 只记录“观察到的终态”，绝不自动调用外部 collect/submit/cancel；如果外部状态仍 unknown，继续 fail-closed。
5. 加入 WS086 等价 fixture：`prepared collect -> owner expires -> external authority says collected -> record terminal observation -> reconcile eligible -> recover`；同时覆盖 external authority unknown/identity mismatch/observation drift 必须 blocked。

### P0-C：legacy pre-manifest dirty WIP adoption gap

**现象**：从 `.63` 之前升级来的 continuation task 没有 workspace manifest，而 worktree 中保留经过人工/测试确认的 task WIP。当前 changed paths 一律变成 `workspace_provenance_missing`；`init --force` 会重建 state 并删除 rounds/effects/reconcile/recovery 历史，因此不是正常迁移工具。

**策略**：

1. 提供显式、一次性、可审计的 legacy workspace adoption/import 操作，不自动猜 dirty 归属。
2. 调用方必须显式列出 concrete paths，并选择 `task_owned` 或 `baseline_external`；每个 path 记录当前 Git status/content digest、旧 task/generation、evidence refs 与 adoption receipt。
3. bound Workstream 的 `task_owned` adoption 必须通过 write_scope/guard 边界；冲突路径、父子 overlap、HEAD ambiguity 或无法确定来源仍 fail-closed。
4. adoption 只创建/升级 workspace manifest，不重置 continuation state、rounds/effects/coordination，不要求为了工具迁移制造 Git commit。
5. `doctor` 对 legacy no-manifest changed paths 给出可机器解析的 next_action，明确区分“先审阅后 adopt”与“无法确认归属则保留阻塞”，不再把 `init --force` 作为常规升级捷径。

**WS009.2 implementation evidence（2026-08-19）**：已实现 `acf continuation workspace adopt` 与 workspace manifest v3 adoption receipt。adopt 只允许在无 active owner 且 manifest 缺失时执行，要求把当前全部 changed paths 显式分类为 `task_owned` / `baseline_external`，记录 status/content digest/prior generation/evidence refs；task-owned 路径受 bound Workstream direct write_scope 约束，遗漏/重叠分类、HEAD drift、active/unknown owner 继续 fail-closed。adoption 只补建 workspace provenance，不重置 control/state/round/effect/coordination/lease history，也不要求先形成 Git semantic checkpoint。deterministic regression 覆盖 successful adopt→reconcile→recover、history byte preservation、active-owner/head-drift rejection、incomplete classification 与 out-of-scope rejection；`tests.test_continuation_cli` 61/61、full unittest 480/480、`acf check template` 与 `acf check --strict` 均通过，README、Automation、template System Manual 与 dogfooding System Manual 已同步 manifest v3/adopt 契约。

### P0-D：content-identical porcelain dirty false block

**现象**：`uv run acf` 刷新 tracked package metadata 的 stat/checkout 状态后，porcelain 报 `.M`，但 `git diff --quiet` 和 blob hash 证明没有 Git content change；`acf worktree verify` 仍返回 `clean=false` / `worktree_dirty`。

**策略**：

1. 定义 `semantic Git dirty` 与 `status/stat-only observation` 的机械差异。
2. 对 ordinary tracked unstaged entries，仅当 Git diff/metadata 确认真实 index-vs-worktree 变化时计入 lifecycle dirty；staged、untracked、rename/delete/type/mode/unmerged/submodule 等仍按现有严格规则处理。
3. 只做只读比较，不使用 `git update-index --refresh` 作为 `verify` 的隐式修复，避免只读命令修改 index metadata。
4. `worktree verify/audit/sync/merge/close` 与 continuation workspace observation/refresh 共享同一 canonical clean 语义；可额外报告 bounded `stat_only_paths` / warning，但不得让内容相同项阻塞生命周期。已有 continuation manifest 中因此误捕获的 `baseline_external` 应在后续 refresh 观察到路径语义 clean 后自然消失，而不是靠 reset/checkout/手改 manifest 清理。
5. 添加 synthetic Git fixture 和 Windows dogfood 回归；跨平台无法稳定制造 racy/stat-only 状态时，使用 parser/helper 单元测试 + Windows 真实 smoke 双证据。

### P1-A：terminal Current_Task / Task_Plan 滞留 active

**现象**：当前 ACF 自己的 `Current_Task.md`、`Task_Plan.md` 已 Done 且属于旧 v0.0.3.56 工作，但仍长期占据 `active/`；doctor/audit/strict 都不提示。

**策略**：

1. `review stale` 新增机械信号 `current_task_terminal_retained` 与 `task_plan_terminal_retained`：终态对象仍是非 Empty active 内容时给出 archive/clear 建议，不需要判断正文真假。
2. `doctor` 的 attention hygiene 复用这些机械 stale/lifecycle signals，至少能在一次健康诊断中看到终态 active retention；不复制第二套语义逻辑。
3. 不把 terminal retention 直接接入 `check --strict`，避免把短暂“刚完成、尚未归档”的正常收口窗口变成硬错误。
4. 不让 Task Workstream WS009 直接改 authority。实现合并后，在 primary maintenance 收口中使用 `acf archive current-task` / `acf archive task-plan` 清理 ACF 自身 dogfood，并记录证据。

### P1-B：Context review drift 与 volatile current-version duplication

**现象**：`review stale` 能看到 Context 19 天未审阅，但 doctor 仍 0 findings；Context 还重复维护已经过期的具体版本号。

**策略**：

1. doctor attention hygiene 汇总 `context_missing_review_marker/context_review_stale` 机械信号，使 doctor 与 review stale 不再互相矛盾。
2. 不新增“自动判断 Context 中哪个版本号是真的”的语义规则，也不做 ACF 专用正则进入通用 strict。
3. ACF 自身在 WS009 合并后的 primary maintenance 中移除/改写易漂移的“当前版本 = x.y.z”重复事实，改为引用 canonical release/version authority（README + `ai_context_framework/version.py`/发布元数据），并刷新 Context review marker。
4. 真实项目如果没有 canonical version 对象，不增加任何额外负担。

**WS009.4 implementation evidence（2026-08-19）**：`review stale` 已机械报告 `current_task_terminal_retained` / `task_plan_terminal_retained`，`doctor` 直接复用这两个 terminal-retention signals 与 `context_missing_review_marker` / `context_review_stale`，统一输出 `attention_hygiene` warning + `draft_only`，不进入 `check --strict`，也不自动改写自然语言事实。focused attention/doctor regression 6/6；完整 `tests.test_cli` 276/276；`acf check template`、`acf check --strict`、`git diff --check` 与 WS009 file-scoped guard 全部通过。generation 24 的 stale owner 先由 timed-out challenge + reconcile receipt `3ff4a15a-0e99-4eb0-8260-f581852c17d6` 证明可恢复，再在用户临时 self-hosting override 下通过候选 control-plane formal recover 到 generation 25；未手工编辑 ACF_HOME JSON。

### P1-C：Workstream Workspace section 与本地 runtime authority 漂移

**现象**：reserve 时 Markdown 写 `mode: none`；create 后 local registry 已有 worktree，但 Markdown 不更新。

**策略**：

1. 不把机器相关 path/branch/binding 同步回共享 Markdown，避免跨主机和生命周期漂移。
2. reservation 的 `## Workspace` 只保留稳定 `slug` 和“本地 binding 以 `acf worktree verify/list` 为权威”的说明；取消 stateful `mode: none` 断言。
3. `read_workstream_info` 继续只消费 slug，旧文件的 `mode: none` 保持兼容，不要求 destructive migration。
4. README/System Manual/Worktree lifecycle 文档明确 Markdown 与 local registry 的职责分工。

### P1-D：reserve -> Open -> create 的执行 UX 断点

**现象**：reserve 成功后 next_actions 只提示可创建 worktree；Workstream 仍为 Open，显式 `status --workstream` 会 fail-closed。

**策略**：

1. 保持 `reserve` 与 “开始执行” 两个语义动作分离，不偷偷 auto-activate。
2. 改善 AI-facing `next_actions`：当 reservation 为 Open 时明确给出 `acf workstream set WSxxx --status Active`，再进入 worktree/context；worktree create 遇到 Open WS 时也给出相同 bounded warning/next action。
3. 用测试保证 agent 不需要从自然语言错误反推缺失生命周期步骤。

**WS009.3 implementation evidence（2026-08-19）**：新增 canonical `semantic_status()`，只在 ordinary tracked unstaged `M` 且 `GIT_OPTIONAL_LOCKS=0 git diff --name-only` 无 normalized content diff 时归入 `stat_only_paths`；`is_clean`、worktree verify/list/sync/merge/close 与 continuation workspace snapshot 复用该语义。synthetic CRLF/LF fixture、真实 unstaged/staged/untracked/delete/rename blocker、verify index-byte-preservation smoke 均通过。reservation `## Workspace` 已移除 `mode:none`，改为稳定 slug + local registry/verify/list authority；reserve/create 对 Open Workstream 均返回显式 Active transition next_action。focused worktree status/CLI/resilient-merge suite 62/62 通过。

### P1-E：统一 ACF_HOME continuation schema / upgrade visibility

**现状**：状态存储已经统一实现：默认 `~/.acf/projects/<root-slug>-<path-hash>/continuation/<task-id>/`，`ACF_HOME` 仅整体覆盖根目录；control/state/workspace/rounds/effects/coordination/reconcile/recovery 共享同一代码/schema。这个设计应保留，而不是把 state 写进各项目 Git 或给不同项目复制实现。

**策略**：

1. 在 help/System Manual 中把 canonical layout、path-hash 隔离原因、`ACF_HOME` override 和 schema ownership 写成稳定合同，但不承诺用户手工编辑这些 JSON。
2. 增强统一的只读 discovery/doctor 能力，能够列出当前 ACF_HOME 下 project/task、schema version、control version/timing profile 与需要 migration 的 legacy state；升级仍由 ACF deterministic command 完成，不让 Scheduled Task 自己改 JSON。
3. state schema 升级必须向后兼容或提供显式 migration/dry-run/receipt；禁止因为 CLI 升级静默丢弃 rounds/effects/recovery history。
4. `task_id` 与 `workstream_id` 明确分层，并在 `doctor/prompt/list` JSON 中稳定暴露，避免 WS080/WS086 这类 wrapper 错把 Workstream ID 当 continuation task-id。

**WS009.2 implementation evidence（2026-08-19）**：已新增只读 `acf continuation list`，当前项目模式按 control `workspace_root` 过滤，`--all-projects` 扫描整个 ACF_HOME path-hash namespace；输出稳定暴露 `task_id/workstream_id`、control generation、timing profile 和 control/state/workspace/round/effect/coordination/reconcile/recovery 等 schema compatibility。`continuation doctor` 在可正常加载时复用同一 contract 输出 `state_compatibility`。已新增显式 `continuation migrate --dry-run/--apply --reason`，当前只迁移代码明确支持的 legacy workspace v1/v2→v3，要求无 lease record，写 `last_migration.json` receipt，并对 control/state/round/effect/coordination/reconcile/recovery/last-run 等历史文件保存 byte digest；future/unknown schema 继续 blocked。P1-E focused 4/4、完整 `tests.test_continuation_cli` 65/65、template/strict 与真实 WS009 `continuation list` dogfood 均通过。

### P1-F：Scheduled Task thin-wrapper standardization

**现状**：`.63` 已经由 `acf continuation prompt` 统一生成 generic protocol，但 Scheduled Task 最外层 wrapper 仍由人工/Agent 组织，容易复制旧协议、写错 task-id，或把某个版本的 heartbeat/reconcile 规则冻结进提示词。

**策略**：

1. `acf continuation prompt` 继续是唯一 generic state-machine authority；不得增加第二份模板正文。
2. 在 `acf continuation prompt --help`、System Manual、Automation 和 README 提供统一的 **thin wrapper recipe**：固定 workspace/branch/workstream/task-id；每轮重新调用 `continuation prompt` 并执行返回 prompt；再加载项目特有 runtime/scientific/permission/validation refs。
3. 评估增加稳定 JSON 字段，例如 `scheduler_wrapper_contract` / `wrapper_requirements` / `identity`，让外部 ChatGPT Scheduled Task 或其他 scheduler 可以机器化组装 wrapper；不得引入 OpenAI 私有格式依赖。
4. wrapper 不重复 generic contention/recovery/heartbeat/workspace/effect 分支，不硬编码自然 Gate 时长，也不规定 Agent 的研究/编码步骤；Agent 仍根据 local plan/evidence 自主决定一个 bounded Gate 内的工程策略。
5. 对 ACF 自身 self-hosting 明确 control-plane / product-under-test 分离：continuation ownership 默认由当前已安装稳定 `acf` 控制；worktree 内 `uv run acf` 用于开发/测试候选实现。只有新稳定版发布并验证安装后，后续 round 才切换 control authority，避免未提交候选代码修改自己的恢复协议。

**WS009.2 implementation evidence（2026-08-19）**：`acf continuation prompt --json` 已增加稳定 `identity` 与 `scheduler_wrapper_contract`，明确 `generic_protocol_source=acf continuation prompt`、每轮必须 refresh generated prompt、wrapper 不复制 generic state machine，并把项目侧附加约束限定为 runtime/scientific/permission/validation classes。generated prompt、README、Automation、template/dogfooding System Manual 同步明确：long-lived local subprocess、DevSpace session、Runtime/external job 只要可能跨 owner/tool-call 生命周期继续写项目或产生非幂等副作用，就必须先建立 deterministic durable identity，并在权威 terminal observation 前保持 unresolved；纯只读 blocking 调用可不登记 writer effect，但返回后、下一次项目写入/副作用前必须重新 assert owner。generation 21 真实 self-hosting 中，旧 generation 20 的 `devspace-session:22254` 经用户临时授权使用候选 control-plane 形成 receipt-bound terminal observation 后完成 formal recovery；随后 generation 21 full unittest 在启动前登记 effect key、启动后绑定 `devspace-session:23114`、终态更新 completed，并通过 full unittest 480/480。该 override 只用于解除 `.63` 自举死锁，不改变最终产品默认的 stable-control-plane / product-under-test 分离边界。

### P2-A：Continuation design / Automation 文档漂移

**现象**：Continuation design 仍有一处旧表述称 doctor 依据 renew interval 区分 fresh/stale，而实现和后文已使用独立 `stale_after_minutes`；Automation 的部分 release/Trusted Publishing 状态也可能落后于 v0.0.3.63 事实；Workstream Design 还保留旧式 `--depends/--read/--write/--status` 参数描述，与当前 `workstream add/reserve/stage` CLI 不完全一致。WS009 setup 中重复传 `workstream stage add --depends` 时 argparse 只保留最后一个值，说明文档必须明确 stage dependency 是一个可解析摘要字符串，而不是暗示该参数可重复。

**策略**：按当前实现和真实发布状态同步单一权威描述；CLI/help/README/System Manual/template/Automation 同步检查，避免复制新的状态机正文。

### P2-B：复杂度与产品边界风险

**现象**：continuation 与 runtime 相关模块已接近 agent-friendly 2000 行 gate；universal challenge probe 是横切行为。

**策略**：WS009 不新增 death detector、daemon、PID supervisor、后台 scheduler、数据库或新的常驻协调层；新增逻辑优先落到已有小模块/helper，保持所有 package module <= 2000 行。只有 failing test / real dogfood evidence 才允许扩协议状态。

## 阶段计划

| 阶段 | 状态 | 目标 | 主要输出 | Gate |
|---|---|---|---|---|
| WS009.1 | Done | Baseline characterization and contract freeze | deterministic failing/characterization tests、problem matrix、scope/evidence、legacy/effect recovery fixtures | physical-writer、ownerless effect deadlock、legacy adoption、terminal retention、stat-only dirty、Workspace/activation UX 边界已由测试冻结 |
| WS009.2 | Done | Continuation recovery/effect/prompt hardening | effect reconciliation、legacy adoption、generated prompt + durable effect/job contract + thin-wrapper contract、ACF_HOME/schema visibility | ownerless effect、legacy adoption、durable writer/thin-wrapper 与 P1-E discovery/migration 均完成；generation 21 full 480/480；continuation suite 65/65 |
| WS009.3 | Done | Worktree semantic-clean and lifecycle UX hardening | canonical clean helper、stat-only diagnostics、Workspace section/next_actions fixes | semantic verify Windows dogfood clean=true with four stat-only paths；continuation baseline 自然清空；focused 62/62 + baseline cleanup 3/3 |
| WS009.4 | Done | Active attention and authority-drift hardening | review/doctor findings、dogfood authority cleanup plan、docs drift fixes | terminal retention + Context review stale/missing-marker 统一进入 doctor attention hygiene；focused 6/6 + CLI 276/276 + template/strict/guard/diff-check 全绿 |
| WS009.5 | Active | Full regression, release and adoption | version bump、release_check、package/PyPI、global install、self/FCC/AStock smoke、merge/archive | `.65` Windows full release gate 全绿，但 GitHub run `32256066761` 在 Ubuntu 因两条 CRLF fixture 假设失败且未 publish；Lenovo stable `.65` 已验证 workspace v3；`.66` fixture 已改为显式 LF bytes + 强制 Git checkout 重建；prepared/no-external-id no-start recovery 已由 `49d6e50` + `c53df87` 收口；PR #1 run `32279505179` 已把 Windows 3.10/3.12 unit tests 推进到 488/488 全绿并保持 Ubuntu/package smoke 全绿，但最终 minimal smoke 在 cp1252 stdout 上因 Unicode JSON 输出失败。generation 27 同时留下两个 externally terminal unresolved effects，真实暴露 reconcile CLI 只能声明单 effect、而 receipt schema 已支持多 effect 的缺口 `0311d339427a631b4d80`；generation 28 已通过有备份、validated receipt 的 emergency override 原子收口两个 effect。当前 focused 实现让 repeated effect assertions 原子进入同一 receipt，并把 minimal smoke 最终 JSON 改为 ASCII-safe；待 focused/full Gate 验证、PR rerun 全绿后 tag/PyPI/installed-state adoption smoke |

## 实现约束

1. 修改前使用 `acf continuation workspace intent` 声明具体文件；只写 WS009 write_scope。
2. 已有 worktree 中无关 dirty 不 stash/reset/clean/rebase/force，也不 `git add .`；只显式 stage 已验证 scoped 文件。
3. 当前 WS009 fresh-worktree egg-info stat-only 状态作为 dogfood evidence 保留到对应 Gate 能机械解释；不得为了“看起来 clean”直接 reset/checkout 覆盖。WS009.5 full sdist build 后 `SOURCES.txt` 出现真实内容变化，仅新增 `continuation_inventory.py`，因此已重新分类为合法 release metadata 并正式扩入 scope；其余 `dependency_links.txt` / `entry_points.txt` / `top_level.txt` 仍保持 content-identical/stat-only，不混入 release commit。
4. Workstream authority 文件只通过 merge target / primary maintenance 收口，不在 Task Workstream 中直接写 `active/Context.md`、`Current_Task.md`、`Task_Plan.md`。
5. CLI 对外行为变化必须同步 JSON/error_code/next_actions/help/docs/tests，并评估版本号；发布前必须重新查询 Git tag、远端 tag 与 PyPI。`v0.0.3.64` 与失败的 `v0.0.3.65` tag 都必须保持 immutable、不得复用；当前新的发布候选为 `v0.0.3.66`，发布前仍需再次 collision probe。
6. 修改模板/默认文档契约时同步 README、template System Manual、dogfooding System Manual、Automation、packaging/upgrade 影响与测试。
7. 每个阶段优先 focused tests；行为冻结后运行 `uv run acf check template`、`uv run acf check --strict`、`uv run python -m unittest`、`git diff --check`；release 阶段运行 full upgrade matrix + `scripts/release_check.py --mode full`。
8. 新发现的通用 ACF/continuation/worktree dogfood 缺陷用 `acf continuation issue` 记录稳定 fingerprint；预期等待、正常 active lease、单纯业务失败不登记。
9. continuation state migration 不允许直接编辑 `~/.acf` JSON；所有修复必须通过 ACF 命令形成原子写入和 receipt，并保留旧 state/effect history 可审计。
10. Scheduled Task wrapper 只做稳定入口，不作为业务计划事实源；current stage/next_action/constraints 优先来自 continuation state 与项目 plan，wrapper 不重复维护易漂移的任务进度。

## 明确非目标

- 不证明 ChatGPT/Agent/OS process “死亡”。
- 不在 ACF 内实现进程 kill、Job Object supervisor、daemon、watchdog 或远端 worker runtime。
- 不把所有文件写入包装成 ACF 文本编辑 API。
- 不重新引入 whole-worktree clean 作为 continuation owner/liveness/recovery Gate。
- 不让 CLI 自动判断 Context 中哪条自然语言事实为真。
- 不因 WS009 便利性需求无限增加 continuation coordination 状态。

## 完成标准

1. 上述 P0/P1 问题各有 deterministic regression 或明确 boundary test；P2 文档/边界风险有同步证据。
2. physical-writer 支持范围被精确定义为 cooperative durable-effect contract；旧 writer 未终态时不能自动 recover，完全绕过 ACF 的 writer 明确保持 out-of-scope/fail-closed，不作虚假保证。
3. fresh worktree 的 content-identical status-only 变化不再被 worktree lifecycle 当成真实 dirty blocker，同时真实 Git 修改仍保持安全门。
4. `review stale` / `doctor` 能机械发现 terminal active retention 与 Context review stale；`check --strict` 不承担事实真假裁决。
5. 新 reservation 不再把易漂移 `mode: none` 当持久事实；Open->Active 生命周期 next_actions 对 AI 清晰。
6. ACF 自身旧 Done Task/Plan 和 stale Context 在代码合并后的 primary maintenance 中通过 ACF 正式命令收口，不由 WS009 Task 越权直接修改。
7. 所有 package modules 保持 <= 2000 行，无新增第三方依赖。
8. release/full regression、PyPI、新稳定版全局安装以及至少 ACF-self + FCC continuation + AStock continuation 的 installed-state smoke 通过。
9. WS079/WS080 类型 legacy no-manifest WIP 有无需强制 commit/`init --force` 的显式迁移路径；WS086 类型 externally-proven terminal effect 可以在旧 owner 消失后通过审计 receipt 收口且不重放副作用。
10. `ACF_HOME` continuation layout/schema/help 保持单一实现与可升级合同，外部 scheduler 不需要理解或手工修改 JSON 文件。
11. Scheduled Task generic protocol 只来自 `acf continuation prompt`；官方 thin-wrapper recipe 能被不同对话/模型一致复用，同时项目工程推理保持开放。

## 下一步

继续 WS009.5：`.65` tag 已由 GitHub run `32256066761` 证明在 Ubuntu full unittest 的两个 CRLF fixture 断言上失败，未进入 PyPI；其本地 full-gated wheel 已在用户临时 self-hosting override 下安装到 Lenovo，并证明 stable `acf continuation doctor/prompt` 能直接读取 WS009 canonical workspace v3，FCC WS079/080/WS086 legacy v2 state 也可稳定只读。`.66` portability fixture、prepared/no-external-id no-start recovery 与 Windows TEMP short-path canonicalization 已分别收口。最新 PR #1 run `32279505179` 进一步证明 Ubuntu Python 3.10/3.12、Ubuntu/Windows package smoke 以及 Windows Python 3.10/3.12 的 488/488 unit tests 全绿；唯一 CI 失败收敛到 `scripts/minimal_smoke.py` 最终 `ensure_ascii=False` JSON 在 Windows cp1252 stdout 上触发 `UnicodeEncodeError`，fingerprint=`db3b1ed19b23d13d8311`。同一 generation 27 的 local release-check process 已权威不存在、PR CI 已权威 failure，但 stable reconcile CLI 只能接收一个 effect assertion，无法一次覆盖两个 unresolved effects；receipt schema 与 recover 内部实现本来支持列表，因此登记通用缺陷 `0311d339427a631b4d80`。用户长期授权下先完整备份 canonical continuation state，再用候选现有 validation/schema 生成双 effect eligible receipt `bdd19c74-2791-45c4-8358-4be33e69e9bd`，随后由 stable `recover` 正式进入 generation 28；未伪造 identity、未直接改 effects journal。当前 bounded Gate 已增加 multi-effect CLI characterization（旧实现确定性失败），实现 repeated `--effect-key/--effect-terminal-status/--effect-external-id` 原子 assertions，并保持 `--effect-not-started` 单 effect fail-closed；focused recovery regression 通过。minimal smoke 最终汇总改为 ASCII-safe JSON，并有 cp1252 可编码的 unit regression。下一步完成 normal minimal smoke、continuation/full CLI focused regression、template/strict/guard/diff-check，形成 scoped checkpoint 并 push；然后 fresh local `.66` full release gate 与 PR cross-platform CI 同时重跑。双绿后 resolve 新 issue 与既有 portability issue，重新 collision probe，只创建一次 `.66` tag，让 GitHub release workflow 决定 PyPI publish；公开发布后升级 Lenovo/qdspc 稳定安装态并完成 ACF-self、FCC continuation、AStock continuation smoke，最后进入 merge/archive 与 primary-maintenance authority cleanup。
