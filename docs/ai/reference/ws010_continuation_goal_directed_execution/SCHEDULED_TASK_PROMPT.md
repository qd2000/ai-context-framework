# WS010 Standard Scheduled Task Wrapper

本文件是 WS010 可直接复制到外部 Scheduled Task 的薄 wrapper，也是后续其他 ACF continuation 自动任务的模板样本。

它只固定执行身份、每轮 dynamic prompt 入口和项目专用约束；不复制 generic claim、contention、workspace、effect、reconcile 或 recover 状态机。

---

## Prompt

@DevSpace Local

持续推进 ACF WS010「Goal-directed continuous execution prompt」。

每次运行都是独立无人值守执行轮次。不要依赖网页聊天历史恢复任务状态；本地 Git、Workstream、PLAN、continuation state、tests/evidence 和当前已安装稳定 ACF 是执行事实源。

固定身份：

- Project：`D:\PROJECT\Tools\ai-context-framework`
- Worktree：`D:\PROJECT\Tools\ai-context-framework_worktrees\ws010-continuation-goal-directed-execution`
- Branch：`codex/ws010-continuation-goal-directed-execution`
- Workstream：`WS010`
- Continuation task-id：`WS010`
- Plan：`docs/ai/reference/ws010_continuation_goal_directed_execution/PLAN.md`

每轮先使用 @DevSpace Local 打开上述固定 worktree，不创建重复 worktree，不切换到 primary checkout 开发。读取根 `AGENTS.md`、`docs/ai/AGENTS.md`、`acf workstream context WS010` 和当前 `PLAN.md`，并验证 path、branch、HEAD、worktree registry、Git common-dir 与固定身份一致。

每轮先运行稳定控制面诊断：

`acf continuation doctor "D:\PROJECT\Tools\ai-context-framework_worktrees\ws010-continuation-goal-directed-execution" --task-id WS010 --json`

在 WS010 新版本发布并安装前，使用 worktree 候选实现只读生成本轮协议：

`uv run acf continuation prompt "D:\PROJECT\Tools\ai-context-framework_worktrees\ws010-continuation-goal-directed-execution" --task-id WS010 --json`

候选 `uv run acf continuation prompt` 只负责渲染 product-under-test prompt；所有 claim、coordination、heartbeat、renew、workspace、effect、checkpoint、release、reconcile 和 recover 写控制命令仍使用当前已安装稳定 `acf`。新稳定版本发布并完成安装态验证后，将上述 prompt 命令切换为全局 `acf continuation prompt`。

严格执行本轮返回的 generated prompt。它是 generic continuation 执行政策和安全协议的唯一权威。完成一个子任务、测试、commit、checkpoint 或 Gate 不构成停止理由；只要仍存在安全、非重复且有价值的下一步，就继续推进总体目标，Agent 自主决定本次工作范围和执行顺序。

## 项目专用约束

以下内容是 WS010/ACF self-hosting 的项目专用补充，不属于通用 continuation 状态机：

1. 只使用 @DevSpace Local 操作本 worktree；不得创建重复 worktree，也不得在 primary checkout 开发。
2. 当前全局稳定 `acf` 是 canonical control plane；worktree 内 `uv run acf` 是 product under test。除只读 prompt 渲染和隔离测试外，发布安装前不得让候选实现修改 WS010 canonical ACF_HOME continuation state。
3. 任务目标、优先级、范围和成功标准以 `WS010.md` 与 `PLAN.md` 为准；`state.next_action` 是恢复入口，不是唯一允许完成的微任务。
4. 不新增第三方运行依赖，不把 ACF 扩展为 daemon、常驻 agent runtime、数据库、向量库或语义事实裁判。
5. 修改 CLI 对外 prompt、JSON contract、默认执行政策或模板时，同步检查 README、Automation、两套 System Manual、CHANGELOG、版本权威和 tests。
6. 发现新的、具体、可复用且有证据支持的 ACF/continuation/worktree 缺陷时，立即使用当前稳定控制面记录：

   `acf continuation issue "D:\PROJECT\Tools\ai-context-framework_worktrees\ws010-continuation-goal-directed-execution" --task-id WS010 --category <category> --severity <low|medium|high|critical> --text <concise-issue> --evidence-ref <durable-ref> --json`

   正常 active-owner 让行、预期等待、普通测试失败和已记录问题不得重复登记。
7. 只显式暂存已验证的 WS010 scoped 文件，禁止 `git add .`；不得 stash/reset/clean/rebase/force 或覆盖无关修改。
8. 根据实际修改运行 focused tests，并至少执行 `uv run acf workstream guard WS010 --files <实际修改文件...> --json`、`git diff --check`、`uv run acf check template`、`uv run acf check --strict`；形成 release 候选前运行完整 continuation suite 和 full unittest。

## 本轮收口

只有 generated prompt 定义的任务级硬停止条件成立，或当前执行平台即将强制结束时，才允许结束本次 activation。平台边界、另一个 authenticated owner 正在推进或 durable external job 正在等待都只是可恢复交接，不得把任务标记为 paused、blocked_human 或 done。

真正退出前，保存准确进度、具体 `next_action`、必要 evidence，刷新 workspace，执行 bounded checkpoint，并使用同一 stable owner credential release。checkpoint 或 commit 本身不要求 release；如果还有安全且有价值的下一步，继续执行。

最终用中文简洁汇报：

- 当前总体目标和阶段；
- 本轮连续完成的工作；
- 修改文件；
- tests / guard；
- issue fingerprint；
- commit 或 commitless handoff；
- continuation 最终状态与 `next_action`；
- 是否存在四类任务级硬停止条件中的任一项。

---

## 通用模板预留

将本 wrapper 迁移到其他项目时，只替换：

1. DevSpace/connector；
2. project/worktree/branch/workstream/task-id/PLAN 固定身份；
3. `项目专用约束`，包括允许 VM/节点、Runtime、权限、安全、验证和 issue 记录要求；
4. ACF self-hosting 特有的 stable-control-plane / product-under-test 条款应删除或替换为目标项目自己的约束。

不得把 generic continuation 状态机复制进外层 Scheduled Task。
