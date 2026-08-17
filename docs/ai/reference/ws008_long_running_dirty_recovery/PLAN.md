# WS008 Long-running Continuation and Dirty Ownership Recovery

## 目标

把 continuation 的安全门从“worktree 是否整体 clean”升级为“当前 runner 是否与已有修改、外部副作用和真实 owner 发生冲突”，同时让单个 bounded Gate 可以正常持续 1-2 小时或更久。

## 核心原则

1. **Dirty 不是冲突。** dirty 只是一种观测；只有与当前 runner 的 write intent、Git checkpoint、external effect 或 owner identity 发生真实碰撞时才阻塞。
2. **无关修改必须保留。** claim 前人工修改、误改、其他任务留下的非重叠文件，以及 claim 后出现的非重叠外部修改，不得被 stash/reset/clean、不得自动提交，也不得阻止当前任务继续。
3. **任务 WIP 可继承。** stale/orphan runner 留下、能够通过 generation、baseline、write-intent 和 digest 证明属于该 round 的 WIP，可以在新 generation 下继续，不要求先把它恢复成 clean。
4. **同一路径冲突仍 fail-closed。** 同一文件或父子路径重叠、diff provenance 不可解释、HEAD 不可解释、effect 仍 active/unknown、manifest 漂移时进入 reconciliation。
5. **Fencing 处理“旧 runner 复活”。** safe recovery 后 generation 前进；旧 runner 再次执行 owner-protected ACF 操作必须失败。生成提示词要求所有非幂等 side effect 和关键写入前重新 assert owner。
6. **长 Gate 是正常形态。** Scheduled Task 每小时只是唤醒频率，不是 Gate 时长；Gate 不因定时器被机械切碎。
7. **通用协议只维护在 ACF。** Scheduled Task 只保存固定 worktree/branch/task-id 和项目特有约束；每轮先调用 `acf continuation prompt` 获取当前通用协议。

## Dirty 分类

### baseline_external

claim/init 时已经存在、且不是本轮 runner 创建的修改。保存路径、Git status 类别和内容/diff digest。默认只读保护，不进入本轮 commit。

### runner_owned

当前 generation 在显式 write intent 后产生的 tracked/untracked 修改。异常中断后可以作为 WIP recovery 候选。

### unexpected_nonoverlap

claim 后出现、但与 runner write intent 和 runner-owned 路径不重叠的外部修改。保留、报告、不自动提交；只要后续 Gate 也不声明碰撞路径，允许继续。

### conflict_or_ambiguous

包括同路径/父子路径碰撞、baseline path 被当前 runner 需要修改、runner-owned path 被外部再次改变、manifest digest 漂移、Git HEAD 无法解释或 side-effect identity 不确定。该类才真正阻塞。

## Workspace manifest

用户级 continuation state 新增 bounded workspace manifest，至少记录：

- baseline HEAD；
- baseline dirty paths/status/digest；
- generation；
- declared write-intent paths；
- runner-owned paths/digest；
- observed external non-overlap paths；
- last observation timestamp；
- classification summary。

manifest 不保存完整文件内容、完整 diff、tool output 或 transcript。

## Write intent

在修改项目文件前，由 ACF 接收本 Gate 的有限路径 intent。Intent 必须满足 Workstream write scope；若与受保护 baseline/external dirty path 碰撞则直接拒绝。

目标 CLI 形式在实现阶段冻结，候选为：

```text
acf continuation workspace status
acf continuation workspace intent --path <path> [--path <path> ...]
acf continuation workspace refresh
```

不要把 ACF 扩展成通用文本编辑器；它只管理 ownership metadata 和冲突判断。

## Long-running timing

将以下概念分离：

- scheduler interval；
- lease TTL；
- renew interval；
- heartbeat recommendation；
- stale threshold。

建议 long-running profile 初值：

```text
scheduler interval: 60 min
lease TTL: 180 min
renew interval: 45 min
heartbeat recommendation: 10 min
stale threshold: 25 min
```

heartbeat 只表示近期 owner activity，不延长 TTL；renew 才延长 TTL。单轮持续超过 2 小时只需继续 renew，不需要人为结束 Gate。

## Stale recovery

新的 Scheduled Task 看到 active lease 时：

1. fresh heartbeat：真实 owner 仍活跃，no-op；
2. stale heartbeat：进入 reconciliation，而不是等待完整 TTL；
3. 若 effect active/unknown：复用同一 identity 并等待/核对，不重复 submit；
4. 若 workspace 仅包含 baseline_external、unexpected_nonoverlap 和可证明 runner_owned：允许 formal recover 生成新 generation；
5. 新 runner 继承 runner_owned WIP，保留 external dirty，不自动 commit external dirty；
6. 若任何 ownership/digest/HEAD/effect 无法证明，则保持 reconciling。

这保证“假的并行”不会因为旧 lease 或无关 dirty 长期阻塞；真正并行或未知写入仍保持安全门。

## Scheduled Task 统一策略

现有任务不再复制完整 generic protocol。统一 wrapper：

1. 固定 project/worktree/branch/task-id；
2. 读取项目 AGENTS/Workstream；
3. 运行 `acf continuation doctor`；
4. 运行 `acf continuation prompt` 并以其当前协议为准；
5. 添加项目独有 Runtime、科学、权限和验收约束；
6. 允许自然完整 Gate 持续执行，按当前 ACF timing heartbeat/renew；
7. 异常恢复使用当前 ACF formal recovery surface，不在 Scheduled Task 中冻结命令细节。

## 文档权威

- ACF 通用行为：`docs/ai/reference/Continuation_Control_Design.md`、README、System Manual、CLI `--help`。
- Scheduled Task/外部 scheduler 操作规范：`docs/Automation.md` + `acf continuation prompt`。
- 业务项目只保留一份简短 human runbook，说明如何初始化和引用 ACF 生成协议；不复制状态机细节。
- 活跃 worktree 不为同步通用协议而强行 merge/sync；安装态 ACF prompt 是运行期权威。项目主线文档更新后在各任务安全同步点自然带入。

## 阶段与验收

### WS008.1 Dirty taxonomy and long-run protocol

- 冻结上述分类和时序语义；
- 用测试复现 blanket dirty false block；
- 覆盖 clean orphan、dirty orphan、pre-existing manual dirty 和 unrelated post-claim dirty。

### WS008.2 Workspace baseline and write-intent ownership

- bounded manifest；
- intent 与 Workstream scope 校验；
- 非重叠 dirty 不阻塞；
- 不自动删除/提交外部 dirty。

### WS008.3 Interrupted WIP recovery

- stale generation 的 runner-owned WIP 可被 formal recovery 继承；
- old generation resurrection 被拒绝；
- conflict/ambiguous 仍 fail-closed。

### WS008.4 Long-running timing and unified prompt

- heartbeat/stale/renew 解耦；
- 支持现有 task 原位 configure，不要求 force re-init；
- long-running profile；
- `continuation prompt` 成为唯一 generic Scheduled Task 协议。

### WS008.5 Failure injection, project adoption and release

- 1-2 小时模拟 round 多次 heartbeat/renew；
- crash with clean WIP / runner WIP / external dirty / overlap / HEAD advance / active effect；
- WS079、WS080、WS086、AStockT_AI wrapper 切换到生成协议；
- README、Automation、Continuation design、System Manual、CLI help 同步；
- full unittest/release/package smoke；
- dogfood 后发布并 merge。

## 不承诺的边界

ACF 不能控制 ChatGPT 平台本身是否允许一次网页执行持续完整 1-2 小时，也不能从 OS 层阻止一个完全绕过 ACF 的旧 runner 直接修改文件。目标是：所有遵守 continuation 协议的 runner 在平台异常后都能安全识别、fence、恢复和继承 WIP；无关 dirty 不制造假冲突，真实不确定性仍不会被伪装成安全。
