# ACF Workstream 与 Git Worktree 生命周期

## 目标与兼容边界

ACF 的 Workstream 和 Git worktree 是两项独立能力：

- Workstream 管理任务编号、目标、scope、状态、阶段和证据；
- worktree 管理可选的 Git 分支、隔离目录、同步、合并和关闭；
- 创建 Workstream 不会隐式创建 branch/worktree；
- `acf workstream add`、状态流转、guard、archive 和不使用 Git worktree 的项目保持原行为；
- AI 在任务确实需要隔离环境时调用 `acf worktree create`，不要求用户手工拼 Git 命令。

未配置或未调用 `acf worktree` 时，旧 ACF 项目不依赖 Git worktree 配置。

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

第一版要求：

- source worktree clean；
- primary checkout clean；
- Workstream 状态为 `ReadyToMerge` 或 `Merging`；
- merge-tree 无冲突；
- branch/path/registry 验证通过。

正式操作使用冻结 source commit 执行 `--no-ff` merge，不自动 push。可选检查使用 JSON argv 数组，不接受 shell 字符串：

```powershell
acf worktree merge `
  --workstream WS081 `
  --pre-check-json '["python","-m","unittest"]' `
  --post-check-json '["python","-m","unittest"]' `
  --apply `
  --json
```

pre-check 失败时不合并；post-check 失败时保留已经产生的 merge commit 并返回 `merged_checks_failed`，ACF 不自动 reset。

## 关闭

```powershell
acf worktree close --workstream WS081 --json
acf worktree close --workstream WS081 --apply --json
```

关闭前必须证明 branch 已合入 primary、worktree clean。执行顺序：

1. `git worktree remove`；
2. `git branch -d`；
3. 删除 local registry。

不使用 `--force` 或 `branch -D`。目录或分支已被人工完成其中一步时，命令按当前事实恢复；重复关闭返回 `already_closed`。

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
git worktree remove --force
git push
自动解决冲突
覆盖既有目录
```

所有写命令默认 plan-only，AI 选择执行时显式传入 `--apply`。出现不确定状态时保留 journal 和现有文件，返回稳定 error_code，由 AI 或用户审阅后决定下一步。
