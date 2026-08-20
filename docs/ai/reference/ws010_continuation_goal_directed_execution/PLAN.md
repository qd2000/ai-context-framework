# WS010 Goal-directed continuous execution prompt plan

## 状态

Active

## 一句话目标

把 `acf continuation prompt` 从“限定 Agent 每轮只完成一个 bounded Gate 的流程控制器”收敛为“只约束危险动作、默认持续推进总体目标的薄执行协议”，并形成一份可复用、可填入项目专用约束的 Scheduled Task 薄模板。

## 当前问题

现有 generated prompt 把安全边界、异常恢复流程和工作量边界混在一起，尤其是 `Execute only the current bounded gate`、`stop without modifying the worktree` 等表述，容易让 Agent 在完成一个小步骤、一次测试、一个 commit 或一次 checkpoint 后主动结束。

这与用户的真实目标冲突：只要项目仍有安全、非重复且有价值的下一步，Agent 就应继续执行，并自行决定当前最有效的工作范围。

## 第一性原理

1. ACF 约束危险动作，不规定 Agent 一次能完成多少工作。
2. bounded 只用于 lease、写入边界、外部副作用和恢复安全，不是任务粒度限制。
3. 当前 `next_action` 是恢复入口，不是唯一允许完成的微任务。
4. checkpoint 只保存进度；commit 只形成自然语义检查点；二者都不等于退出。
5. Agent 在 ownership 有效期间自主选择工作范围、顺序、实现策略和验证深度。
6. 某个具体动作被安全拒绝，只禁止该动作；不自动停止整个任务。
7. 项目专用工具、Runtime、VM/节点、权限、安全、验证和 issue 记录要求必须进入每轮有效 prompt，但不硬编码进通用 ACF 产品逻辑。

## 任务级硬停止条件

generated prompt 只允许把任务停止或转入终态解释为以下四类：

1. 总体目标真正完成。
2. 用户明确暂停。
3. 明确需要人工授权、凭据或不可替代的决策。
4. DevSpace 经合理重连后仍不可用。

以下情况只是当前 activation 的等待、让行或持久化交接，不是任务停止：

- 另一个 authenticated owner 正在推进；
- 外部任务仍在运行且已有 durable identity；
- 即将触及平台执行上下文边界；
- 某个具体恢复、写入或副作用动作暂时被安全拒绝。

发生这些情况时必须保持任务为可恢复状态，保存具体 `next_action`，不得擅自标记 `paused`、`blocked_human` 或 `done`。

## 持续执行规则

1. 一次 Scheduled Task activation 获取 ownership 后，可以连续完成多个子任务、Gate、测试、修复、commit 和 checkpoint。
2. 完成一个步骤后重新读取当前事实，选择最有价值的下一步继续。
3. 只要存在安全、非重复且有价值的下一步，就不得因为局部完成而主动 release/退出。
4. 没有新信息、输入变化、环境变化或策略变化时，不原样重复同一个失败动作；应诊断、缩小复现、修改条件、换策略或等待明确外部变化。
5. Git checkpoint 与 continuation checkpoint 均可在 activation 中多次发生；只有真正准备交接当前执行上下文时才 release。

## 项目专用约束槽

统一 Scheduled Task wrapper 保留一个显式的 `项目专用约束` 区域。可包含：

- 固定 DevSpace/connector 和项目路径；
- 允许或禁止使用的 VM、节点、Runtime、主机和资源；
- 权限、凭据、隐私和泄露边界；
- 科学、工程和业务验证要求；
- 项目专用 issue/问题记录规则；
- self-hosting control-plane / product-under-test 分离；
- 项目特有的测试、发布和验收命令。

通用 `acf continuation prompt` 同时渲染 continuation state 中已有的 `constraints` 与 `plan_refs`，并在 JSON contract 中稳定暴露项目专用约束槽。外层 wrapper 不复制 generic contention/recovery 状态机。

## 实现范围

### 修改

- `ai_context_framework/commands/continuation_workspace.py`
- `tests/test_continuation_cli.py`
- `README.md`
- `docs/Automation.md`
- `docs/ai/reference/Continuation_Control_Design.md`
- `template/reference/System_Manual.md`
- `docs/ai/reference/System_Manual.md`
- `CHANGELOG.md`
- 版本权威文件

### 不修改

- 不重写 continuation lease、generation、workspace、effect、reconcile/recover 状态机。
- 不新增 daemon、常驻 runtime、数据库或 scheduler。
- 不新增统一 HTML/可视化框架。
- 不在本 Workstream 建立后续 ACF issue 自动修复任务；该任务在 WS010 结果稳定后另行规划。

## 实施阶段

阶段只用于记录证据和依赖，不限制单次 Agent activation 的工作量；Agent 可以在同一次有效 ownership 中跨越多个阶段。

| ID | 状态 | 内容 | 证据 | 下一步 |
|---|---|---|---|---|
| WS010.1 | Done | 冻结目标导向执行政策、硬停止条件和项目专用约束槽 | 本 PLAN、Scheduled Task wrapper | 已进入实现与回归 |
| WS010.2 | Done | 实现 prompt/contract，补 focused tests 和同步文档 | prompt tests 2/2；continuation suite 74/74；full unittest 496/496；template/strict check；file-scoped guard；exact-head release gate | 已发布并安装 v0.0.3.68 |
| WS010.3 | Active | 使用 WS010 Scheduled Task 持续 dogfood，完成 installed-state adoption 与收口 | PyPI v0.0.3.68；全局安装态 prompt contract；真实 Scheduled Task activation；continuation rounds/state | 再完成至少一轮 fresh activation 复核后，合并/归档并将薄 wrapper 迁移到其他四个开发任务 |

## 验收标准

1. generated prompt 不再包含 `Execute only the current bounded gate` 或把 bounded Gate 当成 activation 结束边界的等价表述。
2. generated prompt 明确 checkpoint、commit、测试通过和单个 Gate 完成都不是结束条件。
3. generated prompt 明确 Agent 可以根据总体目标、本地计划和证据自主决定工作范围。
4. generated prompt 明确任务级硬停止条件只有本 PLAN 列出的四类。
5. 某个动作被安全拒绝时，prompt 要求继续安全诊断、替代工作、证据核查或计划修正，而不是直接停止整个任务。
6. JSON 输出稳定暴露执行政策、硬停止条件、`plan_refs`、`constraints` 和项目专用约束槽合同。
7.统一 Scheduled Task wrapper 只固定 identity、每轮 prompt 入口和项目专用约束，不复制 generic continuation 状态机。
8. focused continuation prompt tests、完整 continuation suite、模板检查、strict check 和 full unittest 通过。
9. WS010 dogfood 中，一次有效 activation 可以连续推进多个有价值步骤；局部 Gate、commit 或 checkpoint 不触发主动结束。
10. 新发现的通用 ACF/continuation 缺陷使用 `acf continuation issue` 记录；正常等待和普通开发失败不重复登记。

## Dogfood 与发布策略

1. 当前全局稳定 ACF 负责 WS010 canonical continuation ownership 和所有写控制操作。
2. worktree 内 `uv run acf continuation prompt` 可只读渲染候选 prompt，用于 self-hosted dogfood；候选实现不得在发布安装前修改 canonical continuation state。
3. 候选实现通过回归后发布新的 immutable 版本并升级全局 ACF。
4. 安装态验证通过后，WS010 wrapper 切换为全局 `acf continuation prompt`。
5. 随后将统一薄模板和新 generated prompt 应用到其他四个开发任务。

## 当前下一步

v0.0.3.68 已发布到 PyPI 并升级为全局稳定控制面；WS010 continuation 已初始化，小时级 Scheduled Task 已启用。当前只剩 WS010.3 的真实 fresh-activation dogfood 与收口：每轮都重新消费安装态 `acf continuation prompt`，确认一次 activation 能在同一有效 ownership 下连续推进多个安全步骤，而不会在测试、commit、checkpoint 或单个 Gate 后提前退出。完成至少两轮独立 fresh activation 的一致行为证据后，执行 merge/archive closeout，并按 `SCHEDULED_TASK_PROMPT.md` 的迁移清单应用到其他四个开发任务。
