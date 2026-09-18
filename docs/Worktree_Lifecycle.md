# ACF Workstream 与 Git Worktree 生命周期

## 目标与兼容边界

ACF 的 Workstream 和 Git worktree 是两项独立能力：

- Workstream 管理任务编号、目标、scope、状态、阶段和证据；
- worktree 管理可选的 Git 分支、隔离目录、同步、合并和关闭；
- 创建 Workstream 不会隐式创建 branch/worktree；
- `acf workstream add`、状态流转、guard、archive 和不使用 Git worktree 的项目保持原行为；
- AI 在任务确实需要隔离环境时调用 `acf worktree create`，不要求用户手工拼 Git 命令。

未配置或未调用 `acf worktree` 时，旧 ACF 项目不依赖 Git worktree 配置。

## AI 推荐读取顺序

AI 不需要一次读取全部实现细节。推荐按任务逐步披露：

1. 先运行 `acf status --json`；未显式选择 Workstream 时保持 `GlobalOnly`，只读取全局文件指针和 Workstreams 摘要，不读取任何 WS detail/read_scope/reference/output；
2. 用户、自动化合同或执行环境明确指定 WS 后，运行 `acf status --workstream WSNNN --json` 获取 pointer-only 入口，再调用 `acf workstream context WSNNN`；
3. 只需要登记任务时查看 `acf workstream reserve --help`；
4. 只有决定使用隔离环境时再查看 `acf worktree create --help`；
5. 日常只读检查使用 `acf worktree verify|list|audit --help`；
6. 临近同步、合并或关闭时，再读取本文对应章节和目标子命令 `--help`。

## AI 调用决策

| 当前需求 | 推荐动作 | 是否创建 Workstream | 是否创建 worktree |
|---|---|---:|---:|
| 只登记、规划、审计或等待后续决策 | `acf workstream reserve ... --apply --json` | 是 | 否 |
| 已有 WS，任务长期、并行、多提交或需独立合并 | `acf worktree create --workstream WSNNN --apply --json` | 已存在 | 是 |
| 已有 WS，但任务可直接在现有执行位置完成 | 不调用 `acf worktree create` | 已存在 | 否 |
| 短期 bugfix / investigation / docs / maintenance | `acf worktree create --kind <kind> --slug <slug> --apply --json` | 否 | 是 |

## Semantic clean 与本地绑定权威

`acf worktree verify/list/sync/merge/close` 不把 porcelain 的每个 `M` 都等价为真实内容 dirty。统一 semantic-clean helper 在 `GIT_OPTIONAL_LOCKS=0` 下只读检查：staged、untracked、真实 unstaged diff、rename/delete/type/mode/unmerged/submodule 始终阻塞需要 clean 的 lifecycle；只有普通 tracked unstaged `M` 且 Git 规范化 diff 为空时作为 `stat_only_paths` 诊断，不修改 index、不要求 reset/checkout。continuation workspace observation 复用同一语义，避免同一路径在 worktree 与 continuation 两套控制面得到不同结论。

Workstream Markdown 的 `## Workspace` 只保存稳定 `slug` 和本地绑定权威说明。实际机器路径、branch、mode 以 `acf worktree verify/list` 与 Git-common-dir local registry 为准，不写回共享 Markdown。`workstream reserve` 仍创建 Open Workstream；它和 `worktree create` 都会在 next_actions 中明确提示执行前显式 `acf workstream set WSxxx --status Active`，不会偷偷 auto-activate。
| 已有标准 worktree 需要纳入 ACF | `acf worktree attach ... --apply --json` | 可选 | 绑定已有 |
| 状态不确定或怀疑错误仓库 | 先运行 `acf worktree audit --json` 和 `verify` | 不改变 | 不改变 |

创建 Workstream 本身永远不是创建 worktree 的充分条件。AI 必须基于任务持续时间、并行性、提交隔离、测试与合并需求单独作出 worktree 决策。

`attention: Now/Next/Waiting/Retained` 只用于管理看板，不会自动选择 Workstream。主 checkout 未显式选择时保持全局；专属 worktree 只有在 registry、路径、分支和 Git common-dir 全部一致后才可作为 `WorktreeSelected` 来源。选择冲突或无效时保持全局并 fail-closed。

## Workstream 编号预约

`acf workstream reserve` 是 `workstream add` 之上的可选高层入口：

```powershell
acf workstream reserve `
  --title "PetroSim Column 自动建模" `
  --slug petrosim-column-builder `
  --owner codex `
  --apply `
  --json
```

它只执行：

1. 在 primary checkout 获取预约锁；
2. 从 active/archive/index、local/remote refs、worktree registry 和 operation journal 扫描已使用编号；
3. 创建 Workstream detail 和索引行；
4. 运行结构检查；
5. 精确暂存 detail/index；
6. 创建 `文档：登记WSNNN任务占位` 提交。

预约不要求 primary checkout 完全 clean。与 reservation detail、`active/Workstreams.md` 或其父子路径无关的 staged、unstaged、untracked 修改会被保留，预约提交只包含 detail/index 两个目标文件；如果这两个目标路径已有其他修改，ACF 会 fail-closed 并要求先处理路径冲突。

它不会创建分支或 worktree。取消、归档、失败 journal 中已经出现的编号都不自动复用。

默认命令只输出计划；`--apply` 才写入和提交。预约被 Git hook 或其他可恢复错误中断时：

```powershell
acf workstream reserve `
  --resume-operation <operation-id> `
  --apply `
  --json
```

恢复必须复用 journal 中的原编号和原内容；内容冲突时 fail-closed。

## 项目 Git 配置

`acf worktree` 从项目根的可选 `.acf/project.toml` 读取配置：

```toml
[git]
primary_checkout = "C:/PROJECT/fcc_workspace"
primary_branch = "main"
worktree_root = "C:/PROJECT/fcc_workspace_worktrees"
branch_prefix = "codex"

workstream_branch_template = "{branch_prefix}/{workstream_lower}-{slug}"
workstream_worktree_template = "{worktree_root}/{workstream_lower}-{slug}"
non_workstream_branch_template = "{branch_prefix}/{kind}-{slug}"
non_workstream_worktree_template = "{worktree_root}/{kind}-{slug}"

sync_strategy = "merge"
merge_strategy = "no-ff"
primary_dirty_policy = "allow_non_overlapping" # 或 require_clean；两者均使用 integration 引擎
artifact_cache_patterns = ["**/__pycache__/*.pyc"]
artifact_discardable_patterns = ["output/tmp/**"]
```

配置缺失时，ACF 从 Git common-dir 推导 primary checkout，优先选择 `main`/`master`，并使用 primary checkout 的同级 `<repo>_worktrees` 目录。配置错误只阻断 `worktree`/`reserve` Git 能力，不影响原有纯上下文命令。

## 正式 Workstream Worktree

预约完成后，AI 可按任务需要调用：

```powershell
acf worktree create `
  --workstream WS081 `
  --apply `
  --json
```

默认命名：

```text
branch:   codex/ws081-petrosim-column-builder
worktree: C:/PROJECT/fcc_workspace_worktrees/ws081-petrosim-column-builder
```

创建前验证：

- Workstream 已进入 primary branch；
- reservation commit 可达；
- branch/path/registry 未被其他任务占用；
- branch 不在其他 worktree checkout；
- target path 不覆盖普通目录；
- Git common-dir 与 primary repository 一致；
- 不生成 detached HEAD；
- primary branch 未在计划后前进。

重复调用是幂等的；已有合法 branch、缺少 worktree 时会继续创建；branch/path 已正确绑定时返回 `already_created`。

## 非 Workstream Worktree

短期隔离任务不创建 WS：

```powershell
acf worktree create `
  --kind investigation `
  --slug runtime-timeout `
  --apply `
  --json
```

允许的 kind：

```text
bugfix docs experiment investigation maintenance refactor release
```

分支和目录分别为：

```text
codex/investigation-runtime-timeout
<worktree_root>/investigation-runtime-timeout
```

`temp`、`test`、`new`、`fix`、`backup` 等低信息 slug 会被拒绝。

## 只读发现与绑定

```powershell
acf worktree list --json
acf worktree audit --json
acf worktree verify --workstream WS081 --json
acf worktree attach --workstream WS081 --target <path> --apply --json
```

- `list` 显示 Git registry 和 ACF local registry；
- `audit` 报告 detached、prunable、错误 primary branch、配置根目录外 worktree 和 stale registry；
- `verify` 校验路径、branch、HEAD、reservation ancestry、common-dir 和 registry；
- `attach` 只接受已经符合标准名称、正确仓库和唯一绑定的 worktree。

## 同步 primary branch

```powershell
acf worktree sync --workstream WS081 --json
acf worktree sync --workstream WS081 --apply --json
```

默认把冻结的 primary commit merge 到任务分支，不使用 rebase。计划阶段用 `git merge-tree` 预演；dirty worktree、冲突或 primary 前进时不进入真实 merge。

## 合并回 primary branch

```powershell
acf worktree merge-plan --workstream WS081 --json
acf worktree merge --workstream WS081 --apply --json
```

来源 worktree 仍必须 clean，且 Workstream 必须处于 `ReadyToMerge` 或 `Merging`。primary checkout 不再要求完全 clean；ACF 会结构化区分 staged、unstaged、untracked、ignored、index lock 和 Git sequencer 状态，并计算候选写入集合与本地路径碰撞。

每次正式合并都使用同一条执行主链：

1. 冻结 source HEAD 和当前 primary HEAD；
2. 创建短生命周期临时 integration worktree；
3. 在 integration worktree 中执行真实 `--no-ff` merge；
4. 在该干净候选环境运行 post-check；
5. 对来源 worktree 的 ignored/untracked 结果执行 artifact handoff；
6. 获取短时 primary promotion 锁，重新检查 primary 本地状态和路径碰撞；
7. 使用 `git merge --ff-only <integration-tip>` 将已验证候选提升到 primary branch；
8. 验证 primary 中无关的 staged/unstaged/untracked 内容未改变且未进入 merge commit；
9. 清理临时 integration worktree。

可选检查使用 JSON argv 数组，不接受 shell 字符串：

```powershell
acf worktree merge `
  --workstream WS081 `
  --pre-check-json '["python","-m","unittest"]' `
  --post-check-json '["python","-m","unittest"]' `
  --wait-timeout 600 `
  --lock-wait-timeout 300 `
  --max-replans 8 `
  --apply `
  --json
```

pre-check 失败时 primary 不变；post-check 失败时保留 integration worktree 和候选 commit，primary 仍不变。修复并提交候选后使用 `acf worktree resume <operation-id> --apply --json` 继续。

### Primary dirty 与自动恢复

- 非重叠 staged/unstaged/untracked 修改允许保留；
- 路径重叠但 index/worktree 内容、mode 和类型都与候选最终状态一致时，可以安全收敛；ACF 只对已证明一致的 untracked/ignored 路径使用可恢复 quarantine；
- 内容不同、父子路径、rename/delete/type 或 Windows 大小写碰撞会进入有限等待；状态解除后自动继续，超时后返回可恢复暂停；
- primary 或 source HEAD 推进时自动重建候选，默认最多 8 次；
- promotion 锁被占用时有限退避等待；同主机 stale lock 只有在 PID 已死亡、heartbeat 过期且 operation 不在 `PROMOTING` 时才移入证据目录；
- 稳定 Git 冲突只留在 integration worktree；解决并提交后 resume。若期间 primary 前进，ACF 将最新 primary 合入同一 integration 分支，保留人工冲突解决成果。

### Ignored / untracked 结果迁移

```powershell
acf worktree artifact-plan `
  --workstream WS081 `
  --required 'output/result.ksc=C:\Artifacts\WS081\result.ksc' `
  --apply `
  --json

acf worktree artifact-migrate --workstream WS081 --apply --json
```

分类包括 `required`、`retained_reference`、`reproducible_cache`、`discardable` 和 `unknown`。普通 ignored/untracked 文件默认是 `unknown`，不能静默删除；required 采用临时目标复制、SHA-256 校验和原子替换，支持幂等重试。所有需保留项验证完成后才允许 promotion 和 close。

## 关闭

```powershell
acf worktree close --workstream WS081 --json
acf worktree close --workstream WS081 --wait-timeout 120 --apply --json
```

关闭前必须证明 branch 已合入 primary、来源 worktree **semantic-clean**，且 artifact handoff 已完成。执行顺序仍为 worktree remove、已合并分支安全删除和 registry 更新，但每一步进入同一 operation journal，并与 merge 共用来源 lifecycle 锁。Windows 文件占用会有限退避；部分成功后使用同一 operation ID resume。

真实 staged/unstaged/untracked/conflict 一律在 remove 前拒绝；branch 始终只用 `branch -d`，不使用 `branch -D`。当且仅当 canonical semantic-clean helper 已证明没有真实 dirty、但仍存在 content-identical `stat_only_paths` 时，close 可内部调用 `git worktree remove --force` 绕过 Git porcelain/raw remove 对 stat-only 的假 dirty 拒绝。这个 `--force` 只是已证明 semantic-clean 后的兼容桥，不改变 close 的安全门。重复关闭返回 `already_closed`。

## 退役（curated handoff）

```powershell
acf worktree retire --workstream WS079 --disposition curated_handoff --evidence-ref "git:cherry-pick-commit" --json
acf worktree retire --workstream WS079 --disposition curated_handoff --evidence-ref "git:cherry-pick-commit" --preserve-branch --apply --json
```

`retire` 服务一种 `close` 无法覆盖的真实情形：调查或集成分支的必要提交已经通过 reviewed cherry-pick 或等价方式保存在别处，但该分支因为包含无关历史而**刻意不可合并**，因此永远不会成为 primary 的 ancestor。它是独立命令而不是 `close` 的开关，`close` 的 merged-only 语义和 `branch_not_merged` 硬门保持不变。

退役只移除 worktree 工作目录与本地 registry 记录，**绝不删除分支或其 Git 引用**，也不提供删除分支的开关。为了可审计，`--disposition` 与 `--evidence-ref` 都是必需的：第一版只支持 `curated_handoff`，`--evidence-ref` 必须指向「该分支所需提交已在别处保留」的 durable 证据，并随 operation journal 一起持久化 disposition、evidence、退役时的分支 HEAD 与 primary HEAD 快照。

拒绝条件全部 fail-closed，各自返回稳定 error_code：

| 情形 | error_code | 下一步 |
|---|---|---|
| 目标未登记 | `worktree_not_registered` | 先用 `worktree verify/list` 确认绑定 |
| 工作目录存在真实 dirty | `worktree_dirty` | 先提交或移除真实改动 |
| artifact handoff 未完成 | `artifact_handoff_required` | 先完成 `artifact-plan` / `artifact-migrate` |
| 缺少 `--evidence-ref` | `worktree_retire_evidence_required` | 提供保留提交的 durable 证据 |
| `--disposition` 不是 `curated_handoff` | `worktree_retire_disposition_unsupported` | 使用受支持的处置方式 |
| 分支其实已是 primary 的 ancestor | `worktree_retire_branch_already_merged` | 改用 `acf worktree close` |
| closeout authorization 为 manual 未批准或 deny | `workstream_human_approval_required` / `workstream_closeout_denied` | 先取得对应 Workstream/action 的授权 |

退役与 `close` 共用同一套 lifecycle 锁、operation journal 和写入顺序（先移除 worktree，再删除 registry），并同样支持文件占用退避与同一 operation ID resume。重复退役返回 `already_retired`。

## Journal、registry 与锁

本机状态位于 Git common-dir，不写入版本化项目文档：

```text
<git-common-dir>/acf/operations/*.json
<git-common-dir>/acf/worktrees/*.json
<git-common-dir>/acf/locks/*.lock
```

- operation journal 记录参数、冻结 commit、步骤、错误和 resume 状态；
- registry 记录 WS/non-WS 与 branch/path/common-dir 的本机绑定；
- reservation、目标 worktree 和 primary merge 使用独立锁；
- 锁包含 PID、hostname、时间和 operation ID；未确认记录进程失效前不得强删。

## 安全边界

ACF worktree 生命周期永不自动执行：

```text
git stash
git reset
git clean
git rebase
git branch -D
git push
自动解决冲突
覆盖既有目录
```

`git worktree remove --force` 只有上述 semantic-clean + `stat_only_paths` close bridge 这一条内部例外；ACF 不会用它绕过真实 dirty 或未完成 artifact handoff。

所有写命令默认 plan-only，AI 选择执行时显式传入 `--apply`。出现不确定状态时保留 journal 和现有文件，返回稳定 error_code，由 AI 或用户审阅后决定下一步。
