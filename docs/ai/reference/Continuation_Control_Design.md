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

放入 ACF 后，任意已经存在的 clean worktree 都可以直接执行 `acf continuation init`，不需要重建 worktree，也不需要为了控制工具合并该任务分支。

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
            ├─ pause.json
            └─ last_run.json
```

项目内长期事实仍保留在普通 Markdown、Git 和项目自己的 evidence/checkpoint 中。`state.json` 只保存有界当前状态和引用。

## 命令面

```text
acf continuation init
acf continuation doctor
acf continuation claim
acf continuation renew
acf continuation checkpoint
acf continuation release
acf continuation pause
acf continuation resume
acf continuation prompt
acf continuation issue
```

`init` 从 clean Git checkpoint 建立控制状态。可选 `--workstream WSNNN` 时，同时验证 ACF registry、path、branch 和 Git common-dir；没有 Workstream 的普通项目也可只用 `--task-id`。

`doctor` 只读核对 Git top-level、branch、dirty 状态、可选 Workstream identity、pause、lease 和 compact state，并返回 `can_claim`。

`claim` 在本地 OS 文件锁保护下取得单一 active lease；第二个执行器看到 active lease 必须 no-op。expired lease 只有在身份和 clean 状态重新通过后才能接管。`renew` 只延长同一 lease，不改变外部调度周期。

默认时间参数：

- 外部周期元数据：60 分钟；
- lease TTL：120 分钟；
- 推荐续期：30 分钟；
- 最大单次 TTL：24 小时。

`checkpoint` 只覆盖一个 bounded `state.json`。状态最大 64 KiB，列表最多 64 项，单项最大约 4 KiB；`transcript/history/raw_output/tool_output/stdout/stderr` 等字段在任意嵌套层级都拒绝。

`release` 的收口规则：

- clean → 写 last-run receipt，进入指定 final status，删除 lease；
- dirty → 进入 `reconciling`，删除 lease但禁止下一轮自动 claim；
- active round 期间收到 pause → release 后进入 `paused`。

`issue` 用于记录**可复用的 ACF / continuation / 自动化工作流缺口**，不是业务任务自己的科学失败日志。事件写入用户级 ACF usage log，包含 task/workstream/stage、分类、严重度、简短描述、证据引用和稳定 fingerprint；相同 fingerprint 的多次出现保留为 occurrence，查询时自动聚合计数。

标准 `acf continuation prompt` 会要求外部 agent：只有发现具体、可复用、证据支持的产品或工作流问题时才调用 `acf continuation issue`；active lease no-op、正常等待、业务模型未收敛等预期状态不得当作产品 issue。

## Dogfood 可观测性与问题积累

ACF 使用两层用户级日志，不要求用户把多个聊天的问题重新手工汇总：

1. **usage event**：`continuation`、`worktree` 等 CLI 命令自动记录 command、exit code、error code、duration 和 changed files；
2. **continuation issue**：agent 在真实 dogfood 中发现可复用缺口时写结构化 issue event。

查询入口：

```text
acf log summarize <project> --errors-only --json
acf log issues <project> --json
acf log issues --all-projects --json
acf log projects --json
```

`log issues --all-projects` 按 fingerprint 聚合不同 worktree / 任务中的相同问题，输出 occurrence count、首次/最近出现时间、最高严重度、tasks/projects、相关命令和 evidence refs。多任务并行运行产生的经验可以直接作为下一轮 ACF 改进的输入。

## 固定小时调度与租约

外部 Scheduled Task 可以固定每小时一次，无需由 ACF 动态改时间。租约不是调度器，而是本地并发安全门：

```text
每小时触发
    ↓
doctor
    ├─ active lease → no-op
    ├─ paused/dirty/reconciling → no-op
    └─ can_claim=true → claim → 单轮执行
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

- `init` 要求 clean worktree；
- 不自动 stash/reset/clean/rebase/force/push；
- active lease 不可被第二个 claimant 覆盖；
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
