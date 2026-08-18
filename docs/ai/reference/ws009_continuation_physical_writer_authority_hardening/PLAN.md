# WS009 Continuation physical-writer and authority-drift hardening plan

## 状态

Active

## 目标

在不把 ACF 扩展为 agent runtime、进程管理器或语义事实裁判的前提下，收口 v0.0.3.63 dogfooding 暴露的三类通用问题：

1. continuation 的 generation fencing 只能保证 ACF-authorized writer，不能自动识别旧 generation 已启动、在 recovery 后继续写同一路径的 physical writer；
2. active attention / authority 生命周期存在可机械发现但当前 doctor/audit 未发现的滞留和 review drift；
3. Git/worktree 生命周期把 content-identical 的 stat/status-only 变化误报为 dirty，并且 Workstream reservation/worktree 的 Markdown 与本地 runtime authority 之间存在状态漂移。

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

### P0-B：content-identical porcelain dirty false block

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

### P2-A：Continuation design / Automation 文档漂移

**现象**：Continuation design 仍有一处旧表述称 doctor 依据 renew interval 区分 fresh/stale，而实现和后文已使用独立 `stale_after_minutes`；Automation 的部分 release/Trusted Publishing 状态也可能落后于 v0.0.3.63 事实；Workstream Design 还保留旧式 `--depends/--read/--write/--status` 参数描述，与当前 `workstream add/reserve/stage` CLI 不完全一致。WS009 setup 中重复传 `workstream stage add --depends` 时 argparse 只保留最后一个值，说明文档必须明确 stage dependency 是一个可解析摘要字符串，而不是暗示该参数可重复。

**策略**：按当前实现和真实发布状态同步单一权威描述；CLI/help/README/System Manual/template/Automation 同步检查，避免复制新的状态机正文。

### P2-B：复杂度与产品边界风险

**现象**：continuation 与 runtime 相关模块已接近 agent-friendly 2000 行 gate；universal challenge probe 是横切行为。

**策略**：WS009 不新增 death detector、daemon、PID supervisor、后台 scheduler、数据库或新的常驻协调层；新增逻辑优先落到已有小模块/helper，保持所有 package module <= 2000 行。只有 failing test / real dogfood evidence 才允许扩协议状态。

## 阶段计划

| 阶段 | 状态 | 目标 | 主要输出 | Gate |
|---|---|---|---|---|
| WS009.1 | Active | Baseline characterization and contract freeze | deterministic failing/characterization tests、problem matrix、scope/evidence | 不改变产品行为前先证明 physical-writer、terminal retention、stat-only dirty、Workspace/activation UX 当前边界 |
| WS009.2 | Open | Physical-writer/effect contract hardening | generated prompt + effect/job contract + failure injection | unresolved long-lived writer effect 阻止 recovery；无 daemon；旧 generation owner-protected calls 继续 fenced |
| WS009.3 | Open | Worktree semantic-clean and lifecycle UX hardening | canonical clean helper、stat-only diagnostics、Workspace section/next_actions fixes | staged/untracked/real diff 不误放行；content-identical stat-only 不阻塞；只读 verify 不改 index |
| WS009.4 | Open | Active attention and authority-drift hardening | review/doctor findings、dogfood authority cleanup plan、docs drift fixes | doctor 能看到 terminal retention + Context review stale；strict 不做语义裁决 |
| WS009.5 | Open | Full regression, release and adoption | version bump、release_check、package/PyPI、global install、self/FCC/AStock smoke、merge/archive | full unittest/template/strict/upgrade/release/package smoke 全绿；发布后安装态 generated prompt/doctor 兼容旧 state |

## 实现约束

1. 修改前使用 `acf continuation workspace intent` 声明具体文件；只写 WS009 write_scope。
2. 已有 worktree 中无关 dirty 不 stash/reset/clean/rebase/force，也不 `git add .`；只显式 stage 已验证 scoped 文件。
3. 当前 WS009 fresh-worktree egg-info stat-only 状态作为 dogfood evidence 保留到对应 Gate 能机械解释；不得为了“看起来 clean”直接 reset/checkout 覆盖。
4. Workstream authority 文件只通过 merge target / primary maintenance 收口，不在 Task Workstream 中直接写 `active/Context.md`、`Current_Task.md`、`Task_Plan.md`。
5. CLI 对外行为变化必须同步 JSON/error_code/next_actions/help/docs/tests，并评估版本号；预计需要下一个稳定版本（若 `.63` 后无并行版本，则候选 `v0.0.3.64`），最终版本以发布时主线事实为准。
6. 修改模板/默认文档契约时同步 README、template System Manual、dogfooding System Manual、Automation、packaging/upgrade 影响与测试。
7. 每个阶段优先 focused tests；行为冻结后运行 `uv run acf check template`、`uv run acf check --strict`、`uv run python -m unittest`、`git diff --check`；release 阶段运行 full upgrade matrix + `scripts/release_check.py --mode full`。
8. 新发现的通用 ACF/continuation/worktree dogfood 缺陷用 `acf continuation issue` 记录稳定 fingerprint；预期等待、正常 active lease、单纯业务失败不登记。

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

## 下一步

完成 WS009.1：建立 continuation control、冻结 failure/characterization tests，并在不改变生产行为的情况下确认每个问题的最小可复现证据。
