# Continuation premature-final regression fix plan

## 背景

`v0.0.3.68` 已将 `acf continuation prompt` 从“每次只执行一个 bounded Gate”改为 goal-directed continuous execution，但真实 Scheduled Task dogfood 仍出现多个开发任务在短时间内主动返回 final 的现象。WS011 的 continuation 记录进一步证明，部分 execution session 在总体目标仍 open、存在明确 next action 且没有任务级 hard stop 时停止工具推进，甚至留下 live lease，导致下一次 scheduler wake 进入 contention/recovery。

本修复不是通过规定最短运行时长、最少工具调用次数或固定工作量来约束模型，而是清理 prompt 中会把 scheduler wake、Gate、checkpoint、release 或完整 protocol 阅读成“一个需要主动收口的工作回合”的结构与措辞。

## 用户需求

1. Scheduled Task wrapper 精简，但固定身份、项目事实源、工具入口、Runtime/节点/权限/科学/Git 等核心约束不变。
2. `acf continuation prompt` 清理尽可能多的提前结束暗示。
3. 保留网页版模型自主决定工作范围、顺序、实现策略和验证深度的能力，不增加“至少运行 N 分钟 / 至少做 N 步”之类工作量限制。
4. 修改完成后形成新稳定版本，提交 Git、合并主线、发布 PyPI，并升级本机全局 `acf`。

## 根因判断

### 已确认

1. `.68` 已正确移除 `Execute only the current bounded gate`，并明确 commit/checkpoint/Gate 非停止条件。
2. 现有 prompt 仍频繁使用 `activation`、`round`、`handoff/finalization` 等回合语言。
3. 现有 generic protocol 使用 1→14 的完整顺序 checklist；即使第 7 步要求持续推进，整体结构仍容易被解释为“走完流程即可结束”。
4. timing 信息在 prompt 前部高显著展示，特别是 heartbeat 10 分钟等数字可能形成无意时间锚；这些数字实际只服务 lease liveness。
5. `.68` 的 `platform activation approaching its execution boundary` 允许模型主观推断平台边界；真实平台边界应来自明确系统/工具信号，而不是 elapsed time 或“感觉该收尾”。
6. final response 在 ChatGPT Scheduled Task 中实际结束当前 execution session，因此必须明确其 terminal 语义；进度汇报本身不能成为 session-end 原因。

### 不采用

- 不规定每次必须运行 40/50/60 分钟。
- 不规定必须完成固定数量的子任务、测试、工具调用或 Gate。
- 不把 ACF 扩展成常驻 agent runtime、daemon 或 scheduler。
- 不让 CLI 自动裁决“总体目标是否真的完成”；语义判断仍由 Agent 基于本地事实完成。
- 不新增复杂 stop-reason 状态机来取代 Agent 判断。

## 目标设计

### 1. Scheduler wake 语义

Scheduler wake 只表示“从持久状态恢复同一个持续任务”，不是一个独立工作回合、汇报周期、工作配额或自然停止点。

### 2. Resume context 语义

`stage` 与 `next_action` 继续保持既有 JSON contract，但 prose 中定义为 resume context / resume hint；它们是恢复入口，不是当前 session 唯一允许完成的微任务或停止边界。

### 3. 持续执行默认值

总体目标仍 open，且当前仍存在安全、非重复、有价值的工作时，默认继续使用工具推进。Agent 自主决定工作范围、顺序、实现策略和验证深度。

### 4. Final response 语义

final assistant response 会结束当前 execution session。不得仅因为：

- 想汇报进度；
- 已经过一段时间；
- 完成若干步骤；
- 测试通过；
- commit/checkpoint/Gate 完成；
- 感觉“差不多该收尾”；
- 推测上下文或平台边界接近；

而主动 final。

不引入最短运行时长，只要求：若目标仍 open 且现在还能继续安全有效推进，就继续工作。

### 5. Generic protocol 结构

删除 1→14 顺序工作流。改为“按条件适用的安全规则组”，明确这些规则不是 checklist，读完最后一节也不产生 session-end 信号：

- startup / ownership；
- contention / recovery；
- workspace writes；
- liveness / timing；
- external side effects；
- progress / checkpoint；
- handoff / release；
- reusable issue reporting。

### 6. Timing 降权

timing 参数移动到 liveness 规则中，只解释 lease/heartbeat/renew/stale，不在 prompt 前部形成工作时长锚点，并明确它们不是 execution-duration target。

### 7. Platform boundary

只接受平台、系统或工具明确给出的即将终止信号；不得从 elapsed time、上下文感知、已完成工作量或主观判断推测。

### 8. Release

release 不是流程最后一步，也不是 checkpoint 后的默认动作。只有当前 execution session 确实需要 handoff/结束且存在具体事实依据时才执行；如果持有 live lease 并主动结束 session，应先保存必要恢复状态并 release，避免遗留 ghost/stale owner。

## Scheduled Task wrapper

当前 5 个开发类 Scheduled Task 已统一精简：

- ACF WS011；
- FCC WS079；
- FCC WS080；
- FCC WS086；
- AStockT_AI 项目自动推进。

wrapper 保留固定 identity、项目访问工具、事实源、Runtime/节点/科学/权限/Git 边界与 `acf continuation prompt` 动态入口；移除“独立 activation / 本轮收口 / 最终汇报义务”等短回合 framing。WS011 在本修复发布前保持暂停，避免并行修改 ACF 公共文件。

## 实施文件

核心：

- `ai_context_framework/commands/continuation_workspace.py`
- `tests/test_continuation_cli.py`

同步文档：

- `README.md`
- `docs/Automation.md`
- `docs/ai/reference/Continuation_Control_Design.md`
- `docs/ai/reference/System_Manual.md`
- `template/reference/System_Manual.md`
- `docs/ai/reference/ws010_continuation_goal_directed_execution/SCHEDULED_TASK_PROMPT.md`
- `CHANGELOG.md`

版本权威：

- `ai_context_framework/version.py`
- `pyproject.toml`
- `uv.lock`
- package metadata

## 验收标准

1. generated prompt 不包含把 scheduler wake、activation、round、Gate、checkpoint、commit 或 progress report 作为自然结束点的表述。
2. generated prompt 明确 scheduler wake 是 resume-only，不是 work round/reporting interval/stopping point。
3. `stage/next_action` 被定义为 resume context/hint，而不是 work quota。
4. final response 明确为 execution-session terminal action；目标 open 且有安全有效工作时继续使用工具。
5. elapsed time、tool-call count、context length、完成步骤数量、测试/commit/checkpoint/Gate 和进度汇报均明确不是 session-end reason。
6. platform boundary 只能来自明确平台/系统/工具信号。
7. generic protocol 不再使用 1→14 顺序 checklist，而是按条件适用的规则组。
8. timing 只服务 lease liveness，不作为 execution-duration target。
9. ownership、workspace、effect、reconcile/recover、heartbeat/renew、checkpoint/release 的既有安全能力没有被削弱。
10. JSON contract 保持向后兼容，并暴露机器可读的 continuous-execution/final-response 语义。
11. focused prompt tests、完整 continuation suite、full unittest、`acf check template`、`acf check --strict`、`git diff --check` 和 release build 通过。
12. 发布 `v0.0.3.69` 后，PyPI 可查询/安装，本机全局 `acf --version` 为 `v0.0.3.69`，安装态 `acf continuation prompt --json` 呈现新协议。

## 发布与恢复顺序

1. 在 `codex/bugfix-continuation-premature-final` 完成实现、文档和测试。
2. 提交 semantic Git checkpoint。
3. 合并到 `master`，不覆盖 WS011 保留 WIP。
4. 构建并发布 PyPI `0.0.3.69`。
5. 用非 editable 稳定安装升级本机全局 `acf`。
6. 从安装态验证版本与 generated prompt。
7. 验证仍启用的 Scheduled Task wrappers 继续动态调用全局 `acf continuation prompt`。
8. `.69` 稳定后再同步/恢复 WS011 Observer 工作。
