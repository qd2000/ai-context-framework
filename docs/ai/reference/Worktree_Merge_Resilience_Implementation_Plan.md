# ACF Worktree 合并并发、容错与结果迁移实施计划

## 1. 文档身份

- 产品仓库：`D:\PROJECT\Tools\ai-context-framework`
- 规划基线版本：`0.0.3.55`
- 主要实现模块：
  - `ai_context_framework/worktree_service.py`
  - `ai_context_framework/git_support.py`
  - `ai_context_framework/locks.py`
  - `ai_context_framework/json_contract.py`
  - `ai_context_framework/commands/worktree.py`
  - `ai_context_framework/worktree_merge_contracts.py`（新增）
- 主要测试入口：
  - `tests/test_worktree_cli.py`
  - `tests/test_worktree_merge_contracts.py`（新增）
  - `tests/worktree_scenarios.py`（新增测试夹具）
- 产品文档同步范围：
  - `README.md`
  - `template/AGENTS.md`
  - `template/reference/System_Manual.md`
  - `docs/Automation.md`（若维护和恢复边界变化）

本文件是 ACF 产品自身的唯一权威实施计划。FCC 等 dogfooding 项目只提供真实场景和版本升级验收，不维护 ACF 私有实现或平行计划。

---

## 2. 已冻结的架构决策

### 2.1 所有合并统一使用临时 integration worktree

无论是否预计存在冲突，每一次 `acf worktree merge` 都必须创建短生命周期 integration worktree。ACF 不再在 primary checkout 中创建 `--no-ff` merge commit。

统一执行模型：

```text
冻结 primary HEAD=P0 和 source HEAD=S0
        ↓
创建 integration branch/worktree，起点为 P0
        ↓
在 integration worktree 中 merge S0
        ↓
无冲突则生成候选 tip M；有冲突则保留现场
        ↓
在同一干净 worktree 中运行 post-check
        ↓
迁移并校验 required artifacts
        ↓
短暂获取 promotion lock
        ↓
确认 primary 当前状态可安全提升
        ↓
primary fast-forward 到候选 tip
        ↓
关闭来源 worktree和临时 worktree
```

临时 worktree 是唯一真实 merge 现场。`git merge-tree` 只用于只读预演和报告，不再作为另一套候选 commit 构造主链。

### 2.2 Primary 只执行 fast-forward promotion

integration worktree 中生成的候选 tip已经包含来源分支。primary checkout最后不再执行第二次 no-ff merge，只执行：

```text
git merge --ff-only <candidate-tip>
```

若 primary 已从 `P0` 推进到 `P1`，旧候选不能强行提升：

- 无人工冲突解决成果时，删除或隔离旧临时 worktree，基于 `P1` 自动重建；
- 已存在人工冲突解决成果时，在原 integration branch 中合入最新 primary，再重新验证；
- 最终只有当当前 primary 是候选 tip 的祖先时才允许 fast-forward。

### 2.3 Primary staged 内容不再一律阻塞

候选 merge commit已经在独立 worktree 中生成，因此 primary 中 staged 内容不会进入候选 commit。新门禁不是“index 必须为空”，而是：

- primary 无 `index.lock` 和未完成 Git sequencer；
- staged、unstaged、untracked、ignored 状态在 promotion 前稳定；
- 本地路径与候选写入集合没有危险碰撞，或属于严格验证的 identical overlap；
- `git merge --ff-only` 能在不改变受保护本地内容的前提下完成；
- promotion 后 staged/index blob、working-tree 内容和 mode 指纹符合保护合同。

如果 Git 在当前 index 状态下拒绝 fast-forward，ACF 将其分类为 retryable，等待对方提交或解除 index 状态；不使用 `update-ref` 绕过工作区/index更新，也不自动 stash、reset 或取消 staged 内容。

### 2.4 Artifact 默认在 promotion 前完成

正式默认流程不采用“代码先合并、artifact 后迁移”。顺序冻结为：

```text
source clean
→ artifact-plan
→ integration merge
→ candidate post-check
→ required artifact migrate/verify
→ primary promotion
→ close
```

- `required`：promotion 前必须复制并校验；
- `retained_reference`：promotion 前必须验证外部稳定路径和摘要；
- `reproducible_cache`：无需复制，但必须有明确重建声明；
- `discardable`：允许随 worktree 删除，必须显式分类；
- `unknown`：阻止 promotion，等待分类。

首版不提供默认 `merged_artifacts_pending` 成功路径，也不提供 `--merge-code-only` 捷径。

### 2.5 重规划参数

默认值由产品统一决定：

```text
max_replans = 8
conflict_replans = 3
lock_wait_timeout_seconds = 300
state_wait_timeout_seconds = 600
initial_delay_seconds = 0.5
max_delay_seconds = 15
jitter_ratio = 0.20
```

超过预算进入 `PAUSED_RETRYABLE`，operation 保留，可用 operation ID继续。

### 2.6 单一新引擎替换旧直接合并路径

最终只维护一套执行引擎：

```text
temporary integration worktree
→ validate
→ artifact handoff
→ collision-aware fast-forward promotion
```

`primary_dirty_policy=require_clean` 只允许作为同一引擎前置的严格策略门，不得恢复旧的“在 primary checkout 中直接 no-ff merge”实现。

---

## 3. 目标

1. 来源 worktree继续强制 clean，保证待删除 worktree中无未提交 tracked/untracked 成果。
2. primary checkout可保留与候选无碰撞的小任务 staged/unstaged 修改。
3. 所有 merge在临时 integration worktree中完成，冲突不污染 primary。
4. 并发 merge、短时 commit、HEAD推进、Git锁和 Windows文件占用具备等待、退避、自动 replan和 resume。
5. ignored结果在 promotion/close 前有明确分类、迁移和摘要证据。
6. operation在进程崩溃或部分成功后可幂等恢复。
7. 不自动 stash、reset、clean、rebase、force remove、`branch -D` 或覆盖未知本地内容。

---

## 4. 非目标

- 不要求所有小任务都创建独立 worktree。
- 不允许来源 worktree带未提交 tracked或非 ignored untracked内容进入合并。
- 不自动提交 primary 中其他任务的内容。
- 不自动选择 `ours`/`theirs` 解决真实冲突。
- 不在不明 owner 情况下删除或迁移 primary 本地文件。
- 不用直接更新 branch ref规避 Git工作区保护。
- 不修改已安装 site-packages来冒充正式发布。
- 不把一次锁竞争、一次 HEAD变化或一次文件占用当作永久失败。

---

## 5. 核心不变量

### 5.1 来源 worktree

在计划、候选构建、promotion 和 close 前均必须满足：

- registry、path、branch、Git common-dir一致；
- 来源分支为 registry绑定分支；
- tracked working tree clean；
- index clean；
- 无非 ignored untracked文件；
- 无 merge/rebase/cherry-pick/revert/bisect 等进行中状态；
- source HEAD固定记录；
- pre-check绑定具体 source HEAD；
- source HEAD变化后旧候选和检查全部失效。

ignored内容不属于 Git clean，但属于 artifact handoff 门禁。

### 5.2 Integration worktree

- 每次 operation 使用唯一内部 branch 和 path；
- 起点固定为当轮 `primary_head`；
- 实际 merge、冲突解决、候选 commit和 post-check只在这里发生；
- 无冲突候选必须包含 primary和source祖先；
- 有冲突时保留完整 Git冲突现场；
- 不允许直接作为长期任务 worktree复用；
- operation完成后按 journal清理 branch、worktree和临时 refs。

建议内部命名：

```text
branch: acf/integration/<target-key>/<operation-id-short>
path:   <worktree-root>/.acf-integration/<operation-id>
```

### 5.3 Primary checkout

- 当前分支必须为配置的 `primary_branch`；
- 无未完成 merge/rebase/cherry-pick/revert/bisect；
- 无活动 `index.lock`；
- 可以有稳定的 staged、unstaged、untracked、ignored内容；
- 所有本地状态都要形成 promotion 前后指纹；
- 候选写入路径不得覆盖内容不同的本地路径；
- promotion只允许 fast-forward；
- 只在 promotion临界区串行化 primary更新，不要求其他 worktree停止开发。

### 5.4 Artifact handoff

- ignored文件必须通过项目策略或 manifest分类；
- required迁移默认 copy，不先 move；
- 来源副本保留到 close完成；
- 来源和目标以 SHA-256、size、类型校验；
- 预算超限时结构化暂停；
- unknown不允许静默删除或 promotion。

---

## 6. Operation 状态机

每次 merge创建 `acf.git_operation.v2` journal。

```text
PLANNED
→ SOURCE_VERIFYING
→ SOURCE_VERIFIED
→ ARTIFACTS_PLANNING
→ ARTIFACTS_PLANNED
→ INTEGRATION_CREATING
→ INTEGRATION_READY
→ MERGING_SOURCE
→ CONFLICT_RESOLUTION_REQUIRED | CANDIDATE_READY
→ CANDIDATE_VALIDATING
→ CANDIDATE_VALIDATED
→ ARTIFACTS_MIGRATING
→ ARTIFACTS_VERIFIED
→ WAITING_PROMOTION
→ PROMOTING
→ PROMOTED
→ POST_VERIFY
→ MERGED
→ READY_TO_CLOSE
→ CLOSING
→ CLOSED
```

可暂停状态：

```text
PAUSED_RETRYABLE
MANUAL_ACTION_REQUIRED
FAILED_TERMINAL
```

必须保存：

- operation ID、target identity；
- source/primary每轮 HEAD；
- integration branch/path/tip；
- replan/lock/state重试计数；
- pre/post-check结果摘要；
- primary本地状态指纹；
- artifact manifest状态；
-每一步开始、完成或失败时间；
- resume允许点和下一动作。

---

## 7. Source 检查

### 7.1 Identity

验证 registry、branch、path、common-dir、workstream状态和 ReadyToMerge合同。

### 7.2 Clean

来源 worktree必须：

- `git status --porcelain=v2 --untracked-files=all` 无 tracked/index/nonignored untracked条目；
- 无 Git sequencer状态；
- source HEAD可解析且与 registry分支 tip一致。

dirty来源不盲目循环重试，进入：

```text
MANUAL_ACTION_REQUIRED/source_worktree_dirty
```

提交完成后通过 operation ID resume。

### 7.3 Pre-check

- 在来源 worktree执行；
- 绑定具体 source HEAD；
-基础设施失败最多重试 3 次，退避 `2s, 5s, 15s`；
-确定性失败不重试；
- source HEAD变化后结果失效。

---

## 8. Artifact 计划与迁移

### 8.1 发现

在创建候选之前执行 artifact-plan：

-读取项目配置的 artifact roots和分类规则；
-读取 target对应 `acf.artifact_handoff.v1` manifest；
-使用 `git ls-files --others --ignored --exclude-standard` 对 ignored路径做有界清单；
-记录 path、type、size、mtime、分类、目标和是否需要摘要；
-常见缓存必须由项目配置明确标为 `reproducible_cache` 或 `discardable`，不能由 ACF凭名称猜测。

### 8.2 分类

```text
required
retained_reference
reproducible_cache
discardable
unknown
```

任何 `unknown` 都阻止 promotion。

### 8.3 迁移

candidate post-check通过后、promotion前：

1. copy到目标临时路径；
2. flush/close；
3.计算目标 size和 SHA-256；
4.与来源比对；
5.原子 rename到正式目标；
6. manifest标记 verified；
7.来源副本保留。

失败可幂等重试，不重新复制已经验证且 digest一致的对象。

---

## 9. Integration worktree 合并流程

### 9.1 创建

-固定 `P0=primary HEAD`、`S0=source HEAD`；
-创建内部 integration branch/worktree，起点为 `P0`；
-记录 branch、path、base HEAD；
-确保 worktree clean且 Git identity可提交。

### 9.2 只读预演

可以用 `git merge-tree` 提前报告潜在冲突，但预演结果不替代真实 integration merge，也不构成成功证据。

### 9.3 实际 merge

在 integration worktree执行：

```text
git merge --no-ff <S0> -m <message>
```

-无冲突：产生候选 tip `M0`；
-有冲突：保留 MERGE_HEAD、index冲突项和工作区现场，进入人工/agent解决阶段；
-primary checkout不发生任何写入。

### 9.4 Post-check

-在 integration worktree的候选 tip上运行；
-正式验收不在 primary checkout运行；
-失败时 primary尚未改变；
-修复来源后，无人工冲突成果的候选可自动重建；
-若人工冲突解决内容需要保留，继续在原 integration branch修复并提交。

---

## 10. 冲突处理

### 10.1 初次冲突

如果 primary正在快速推进，最多自动重新基于新 primary构建 3 次，排除短时陈旧基线造成的冲突报告。

### 10.2 稳定冲突

真实冲突保留在 integration worktree：

-输出冲突路径和类型；
-记录 base/ours/theirs blob identity；
-状态设为 `CONFLICT_RESOLUTION_REQUIRED`；
-用户或 agent解决并提交；
-不得自动选择 ours/theirs；
-不得污染 primary。

### 10.3 冲突解决期间 primary推进

已有人工作成果时不删除 integration worktree。将最新 primary合入 integration branch：

-无新冲突：重新 post-check和 artifact验证；
-有新冲突：继续在同一 worktree解决；
-超过总 replan预算后 `PAUSED_RETRYABLE/primary_churn`。

---

## 11. Primary 状态、碰撞和 promotion

### 11.1 快照

promotion前采集：

- primary HEAD和branch；
- staged path及 index blob/mode；
- unstaged path及 working-tree hash/mode；
- untracked/ignored碰撞候选；
- sequencer状态；
- `index.lock`；
- snapshot时间和稳定性指纹。

至少连续两次采样一致才进入 promotion临界区。

### 11.2 候选写入集合

以当前 primary `P` 到候选 tip `M` 的 tree差异计算：

- add、modify、delete；
- rename source/target；
- mode/type变化；
- file-directory互换；
- Windows casefold和父子路径冲突。

### 11.3 无重叠本地修改

staged或unstaged路径与候选写入集合无危险碰撞时允许 promotion。promotion后必须验证这些本地内容和 index意图仍受保护。

### 11.4 Identical overlap

定义：候选会写某路径，而 primary本地 index和/或 working tree在该路径已经具有与候选最终 tree完全相同的内容、mode和对象类型。

允许自动收敛的必要条件：

-候选 blob、index blob、working-tree hash逐层一致；
-文件 mode/type一致；
-不存在 `index=A, working-tree=B` 的混合差异；
-rename/delete语义一致；
-Windows路径大小写无歧义；
-operation journal记录路径和摘要。

promotion后该本地修改可能自然变为 clean，因为其内容已由来源分支进入 main。这不是数据丢失，但必须显式报告。

### 11.5 Divergent overlap

内容、mode、类型或路径语义不同，进入：

```text
WAITING_PRIMARY_PATHS
```

按退避等待其他任务提交、撤回或转移；超时后 `MANUAL_ACTION_REQUIRED/primary_path_collision`。禁止自动 stash、覆盖或 reset。

### 11.6 Staged 内容

staged本身不阻塞。以下情况才等待：

- index在连续采样间变化；
-存在 `index.lock`；
-staged路径与候选 divergent overlap；
-Git拒绝安全 fast-forward；
-primary正在其他 Git操作。

### 11.7 Promotion

1.获取 primary promotion lock；
2.重新采样 primary和source；
3.确认当前 primary是候选 tip祖先；
4.确认本地状态稳定且碰撞可接受；
5.记录 pre-promotion指纹；
6.在 primary执行 `git merge --ff-only <candidate-tip>`；
7.确认 primary HEAD等于 candidate tip；
8.验证受保护 staged/unstaged/untracked内容；
9.验证候选 commit未夹带 primary本地内容；
10.更新 journal和 registry。

若 Git拒绝，分类并等待/replan，不直接失败，不使用 `update-ref`。

---

## 12. 并发、锁、等待和重规划

### 12.1 锁范围

- target lock：同一来源 target的 merge/artifact/close串行；
- promotion lock：只覆盖最终 primary采样和 fast-forward临界区；
- integration merge和测试可并发进行。

### 12.2 锁 payload

```text
operation_id
pid
process_start_identity
hostname
command
target_key
created_at
heartbeat_at
lease_deadline
expected_primary_head
expected_source_head
```

### 12.3 退避

```text
0.5s, 1s, 2s, 4s, 8s, 15s, 15s...
```

加入 ±20% jitter。

### 12.4 自动 replan

以下状态自动 replan：

- primary HEAD推进；
- source HEAD推进且来源仍 clean；
-另一个 merge先完成；
-promotion快照失效；
-短时 staged/index状态变化；
-无人工冲突成果的旧 integration候选过期。

总上限 8 次。超过后暂停并保留 operation。

### 12.5 Stale lock

同主机只有同时满足以下条件才隔离旧锁：

- PID不存在且 process start identity不匹配；
- heartbeat和lease过期；
-operation不处于未确认 PROMOTING；
-Git无进行中操作；
-旧锁移动到 `.git/acf/stale-locks/` 保留证据。

不同主机或无法证明安全时不自动破锁。

---

## 13. 崩溃恢复

### 13.1 Integration 创建/merge期间

resume检查 worktree、branch、MERGE_HEAD、候选 tip和journal：

-完整候选存在：继续验证；
-冲突现场存在：恢复冲突状态；
-仅部分创建：幂等清理或继续；
-状态不一致：暂停人工判定，不删除现场。

### 13.2 Artifact迁移期间

-复用已验证目标；
-临时文件摘要匹配则继续原子完成；
-摘要不一致不覆盖正式目标；
-来源副本始终保留。

### 13.3 Promotion期间

resume读取 primary HEAD、candidate tip、reflog和指纹：

- primary==candidate：promotion已完成，进入 post-verify；
- primary仍是旧祖先：重新采样后重试；
- primary已包含 candidate：视为后续提交已发生，标记 merged；
- primary出现无关分叉：人工介入，禁止 reset。

### 13.4 Close期间

根据 worktree、branch、registry、artifact manifest和journal逐步恢复，每步幂等。

---

## 14. Close 合同

close前必须确认：

-来源 worktree clean；
-source branch tip已被 primary包含；
-artifact manifest没有 required/unknown未完成条目；
-无来源或 integration未完成 Git操作；
-operation状态允许 close。

执行顺序：

1. remove来源 worktree；
2.删除已合并来源分支；
3. remove integration worktree；
4.删除内部 integration branch/ref；
5.更新 registry closed；
6.回收临时日志和 refs。

Windows删除失败退避：

```text
1s, 2s, 5s, 10s, 30s, 30s
```

部分成功进入 cleanup pending，禁止自动 force remove dirty worktree或 `branch -D`。

---

## 15. CLI 合同

### 15.1 merge-plan

新增结构化输出：

```text
source_head
primary_head
source_clean
artifact_handoff_status
integration_strategy=always
primary_staged_paths
primary_unstaged_paths
primary_untracked_paths
candidate_changed_paths
identical_overlap_paths
divergent_overlap_paths
branch_conflicts
recommended_action
retryable
```

### 15.2 merge

建议参数：

```text
--wait-timeout 600
--lock-wait-timeout 300
--max-replans 8
--conflict-replans 3
--resume-operation <id>
```

不再需要可选 conflict strategy；integration worktree是唯一策略。

### 15.3 operation

```text
acf worktree operation-status --operation-id <id> --json
acf worktree merge-resume --operation-id <id> --apply --json
```

### 15.4 artifacts

```text
acf worktree artifact-plan --workstream WS079 --json
acf worktree artifact-migrate --workstream WS079 --apply --json
```

### 15.5 close

```text
acf worktree close --workstream WS079 --apply --wait-timeout 120 --json
```

---

## 16. JSON 合同

### 16.1 `acf.git_operation.v2`

必须至少包含：

- operation identity和状态；
- target/source/primary identity；
- integration branch/path/tip/conflict信息；
- retry policy和attempt counters；
- pre/post-check摘要；
- primary保护指纹；
- artifact handoff状态；
- step journal和timestamps；
- resume_allowed、pause reason和next action。

### 16.2 `acf.artifact_handoff.v1`

每个 entry至少包含：

- relative_path；
- classification；
- transfer策略；
- destination；
- size和 SHA-256（需要迁移时）；
-状态和验证时间；
-重建或丢弃依据（非 required时）。

---

## 17. 错误分类

| 场景 | 分类 | 默认处理 |
|---|---|---|
| source dirty | Manual | 提交后 resume |
| target lock占用 | Retryable | 等待 |
| promotion lock占用 | Retryable | 等待 |
| primary/source HEAD推进 | Replan | 自动重建或吸收最新 primary |
| staged稳定且无碰撞 | Allowed | 继续 |
| staged变化或 index.lock | Retryable | 等待 |
| identical overlap | Allowed with audit | 记录并继续 |
| divergent overlap | Retryable then Manual | 等待，超时人工处理 |
| untracked/ignored碰撞 | Retryable/Manual | artifact分类或路径处理 |
| ignored unknown artifact | Manual | 分类后 resume |
| merge conflict | Manual in integration | 保留现场解决 |
| pre-check基础设施失败 | Retryable | 3次退避 |
| pre-check确定失败 | Manual | 修复来源 |
| post-check失败 | Manual | primary不变，修复候选/来源 |
| Git拒绝 ff-only | Retryable/Replan | 重新采样 |
| artifact digest不一致 | Manual/Terminal | 不 promotion |
| Windows删除占用 | Retryable | close退避 |
| already merged/closed | Idempotent success | 返回现状 |

---

## 18. 实施阶段

### T001：合同和测试基线

-重写本计划并冻结单一 integration主链；
-新增 `worktree_merge_contracts.py`；
-定义 operation v2、artifact handoff v1、状态和默认重试参数；
-新增通用临时 Git仓库场景夹具；
-测试证明 ignored artifact可在 Git clean下存在、integration候选不改变 primary；
-不改变现有 merge生产行为。

### T002：Primary状态和碰撞分析

- porcelain v2结构化解析；
- staged/unstaged/untracked/ignored分类；
-候选写入集合；
-identical/divergent overlap；
- Windows casefold、rename、delete、type和父子路径碰撞；
- merge-plan开始返回结构化结果。

### T003：Integration worktree候选主链

-每次 merge创建 integration branch/worktree；
-无冲突自动生成候选；
- post-check在 integration执行；
-旧 primary直接 no-ff merge路径停止使用。

### T004：Promotion保护和并发恢复

- staged/unstaged稳定快照；
-promotion lock、heartbeat和退避；
- ff-only promotion；
- HEAD变化自动 replan；
-operation status/resume；
-primary本地内容保护审计。

### T005：Artifact handoff

- manifest和项目配置；
- ignored发现与分类；
-copy/hash/atomic finalize；
-required/unknown promotion门禁；
-预算和去重。

### T006：冲突现场和人工恢复

- integration conflict状态；
-冲突报告；
-人工解决后的 resume；
-primary推进后在原 integration吸收最新 main。

### T007：Close韧性

- artifact和branch祖先门禁；
-Windows退避；
-部分成功和崩溃恢复；
-临时 worktree/branch/ref回收。

### T008：文档、灰度和发布

- README、template、System Manual、Automation；
-同一引擎的 `require_clean`严格策略；
-全量测试；
-版本升级；
-真实 dogfooding仓库验收。

---

## 19. 测试矩阵

至少覆盖：

1. clean primary/source；
2. primary无关 unstaged；
3. primary无关 staged；
4. staged提交期间状态变化；
5. identical overlap（index和working tree一致）；
6. index与working tree混合差异；
7. divergent overlap随后被其他任务提交；
8.两个 merge并发排队；
9. primary连续推进和8次replan上限；
10. source推进和source dirty；
11. index.lock和Git sequencer；
12. rename/delete/type/file-directory/casefold碰撞；
13. untracked覆盖风险；
14. ignored required artifact迁移；
15. ignored unknown阻止 promotion；
16. reproducible/discardable不复制；
17. artifact digest不一致和预算超限；
18.无冲突也创建 integration worktree；
19.真实冲突只存在于 integration；
20.冲突解决期间 primary推进；
21. pre-check基础设施/确定性失败；
22. post-check失败时 primary不变；
23. promotion前后 primary本地状态保护；
24. Git拒绝 ff-only后的等待；
25. integration/validation/promotion崩溃恢复；
26. close文件占用和部分成功；
27. already merged/closed幂等；
28.内部 branch/ref清理；
29. merge commit父子和祖先审计；
30.旧 primary直接 no-ff路径不可达。

---

## 20. 完成标准

只有全部满足，才能发布并替换旧行为：

-来源 clean和identity门禁未削弱；
-每次 merge都在 integration worktree执行；
-primary staged/unstaged无碰撞时可安全保留；
-primary本地内容不进入候选 commit且 promotion后受保护；
-required/unknown artifact在 promotion前完成处理；
-真实冲突不污染 primary；
-并发、HEAD推进、锁和文件占用可等待/replan/resume；
-崩溃不导致重复 merge、重复迁移或强制清理；
-旧 primary直接 no-ff执行路径删除或不可达；
-严格模式只作为同一引擎前置策略；
-模板检查、strict检查、全量 unittest和dogfooding全部通过；
-发布新版本并完成下游升级验证。

---

## 21. 当前执行入口

当前从 T001 开始：冻结 Python合同、默认重试参数和测试夹具，不改变已发布 merge行为。T001通过后立即进入 T002，不在 site-packages中直接打补丁。