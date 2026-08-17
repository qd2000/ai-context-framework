# 更新日志

本文件记录 ACF 稳定版本的用户可见变化。完整实现证据、测试矩阵和 Workstream 归档仍保存在 `docs/ai/archive/workstreams/` 与 `docs/ai/worklog/`；本文件只保留发布级摘要。

## v0.0.3.61 — 2026-08-17

### Dogfooding 可观测性

- `continuation` 与 `worktree` CLI 命令现在进入用户级 usage event log，记录 command、exit/error code、duration 和 changed files；不再因为缺少 context routing 而静默漏记。
- 新增 `acf continuation issue`：外部 agent 可在发现具体、可复用、证据支持的 ACF / continuation / 自动化工作流缺口时写入结构化 issue event，包含 task/workstream/stage、category、severity、evidence refs、related command 和稳定 fingerprint。
- 新增 `acf log issues [--all-projects]`：按 fingerprint 聚合不同 worktree / task 中的重复 issue occurrence，保留 count、首次/最近出现时间、最高严重度、任务/项目和证据引用，便于多任务并行 dogfood 后直接进入下一轮产品改进。
- `acf continuation prompt` 自动包含 issue 记录协议；正常 active-lease no-op、等待和任务自身业务失败明确不作为产品 issue。

### 验证

- 新增 continuation usage logging、issue 记录/去重聚合和 prompt 协议回归测试。

## v0.0.3.60 — 2026-08-17

### 安全修复

- `acf continuation` 不再把“lease 已过期但 Git HEAD 已从该 lease 的起始 HEAD 前进”的 `running` 轮次自动判定为可恢复。该场景可能表示前一轮已经完成并提交了非幂等写操作、但在 checkpoint/release 前中断；自动重新 claim 会有重复执行风险。
- `doctor` 现在返回 `expired_round_head_changed=true`、`can_claim=false` 和 `blocked_reasons=[..., "expired_round_head_changed"]`；直接 `claim` 返回 `continuation_reconciliation_required`，并提供 lease HEAD 与当前 HEAD 供审计。
- 保留原有安全恢复路径：如果 lease 过期、state 仍为 `running`、worktree clean 且 HEAD 未变化，则仍允许从 clean checkpoint 重新 claim。

### 验证

- 新增 failure-injection 回归测试，覆盖“上一轮提交后崩溃、lease 随后过期”的 clean-but-advanced-HEAD 场景，确认不会重复自动执行。

## v0.0.3.59 — 2026-08-16

### 新增

- 新增 `acf continuation init|doctor|claim|renew|checkpoint|release|pause|resume|prompt`，为外部 Scheduled Task、其他 AI scheduler 和人工多轮任务提供模型无关的 bounded continuation 控制面。
- continuation 运行态保存在用户级 `~/.acf/projects/.../continuation/`，不会因为 lease、pause 或 compact state 更新污染目标 Git worktree；现有 clean worktree 可直接初始化，不需要重建。
- 可选 `--workstream WSNNN` 会复用 ACF worktree registry/path/branch/common-dir 验证；无 Workstream 项目仍可使用独立 `--task-id`。
- 增加单写者 lease、续期、expired recovery、人工 pause/resume、dirty release → reconciling 和 compact state 原始历史字段拒绝。

### 边界

- ACF continuation 不创建 Scheduled Task、不读取聊天历史、不运行常驻 agent、不保存 transcript，也不替代 Task Plan、Workstream、Git/scientific checkpoint 或 evidence。
- 外部调度周期可以固定；本地 lease 只承担并发与恢复安全门，不动态修改 scheduler 时间。

## v0.0.3.58 — 2026-08-10

### 发布与安装

- 新增 `scripts/release_check.py`，覆盖发布前检查、wheel/sdist 构建、隔离安装和 console script smoke。
- 新增 uv 一键安装/更新脚本，以及 GitHub Actions CI 和 `v*` tag PyPI 发布 workflow。

## v0.0.3.57 — 2026-08-10

### 修复

- `acf workstream reserve --apply` 不再因为 primary checkout 存在其他 agent 的无关 staged、unstaged 或 untracked 修改而失败。
- 预约提交改为只提交 reservation detail/index；只有预约路径本身或父子路径发生冲突时才 fail-closed，并保留其他本地修改。
- 补充预约路径冲突、并行 dirty 状态保留和冲突修复后恢复测试及对应 JSON error contract。

### 验证

- 通过 template/strict check、编译检查、diff check 和分片 unittest；分片覆盖 423 项测试。
- 完整 `uv run python -m unittest` 在工具 10 分钟窗口内超时，但各测试分片均通过，未将聚合超时计作通过。

## v0.0.3.56 — 2026-08-06

### 新增

- `acf worktree merge` 统一改为临时 integration worktree 执行：真实 no-ff merge、冲突解决和 post-check 不再发生在 primary checkout；primary 只执行候选验证后的 fast-forward promotion。
- primary checkout 允许保留与候选无碰撞的 staged、unstaged 和 untracked 修改；merge-plan 输出结构化工作区快照、候选写入集合、相同重叠和分歧碰撞。
- 新增有限等待、指数退避、lock heartbeat、stale-lock 安全隔离、primary/source HEAD 自动重规划和 operation v2 resume。
- 新增 `acf worktree artifact-plan|artifact-migrate`，对 ignored/untracked 结果执行显式分类、复制或稳定引用和 SHA-256 验证；普通路径默认 `unknown`，不能静默删除。
- 冲突、post-check 失败和 artifact 未完成时保留 integration worktree；修复或分类后使用原 operation ID 继续。
- close 与 merge 共用来源 lifecycle 锁，支持 Windows 文件占用退避、部分成功 journal 和幂等恢复。

### 配置与安全

- 新增 `primary_dirty_policy = "allow_non_overlapping"|"require_clean"`；两种策略都使用同一 integration 引擎，不恢复旧的 primary direct merge。
- 新增 `artifact_cache_patterns` 和 `artifact_discardable_patterns`；只有项目配置或本次 CLI 明确声明的路径才自动放行。
- 相同 untracked/ignored 重叠只在内容、mode 和类型全部与候选一致时使用可恢复 quarantine；promotion 失败会原子恢复，成功后才删除冗余副本。
- 继续禁止自动 stash、reset、clean、rebase、force、push 和静默冲突选择。

### 验证

- 新增临时真实 Git 仓库场景，覆盖无关 staged/unstaged 保留、相同/不同重叠、ignored 碰撞、短时路径竞争、锁等待、HEAD 推进重规划、冲突解决、post-check 修复、artifact 迁移、close 重试和部分恢复。
- 完整测试、模板/strict check、构建制品、隔离安装和真实 dogfooding 升级记录见 2026-08-06 worklog。

## v0.0.3.55 — 2026-08-04

### 变更

- `acf status|next` 未显式选择 Workstream 时改为 `GlobalOnly`：只披露全局上下文文件指针和 Workstream 摘要，不再因为一个或多个 active-class Workstream 自动进入任务。
- `attention: Now/Next/Waiting/Retained` 降级为 dashboard 管理元数据，不再决定默认上下文入口。
- 新增 `acf status|next --workstream WSNNN` 显式选择；Active `Current_Task` 唯一绑定和经过 registry/path/branch/common-dir 校验的专属 worktree 也可作为明确选择来源。
- 选择结果采用两级渐进式披露：状态命令只返回 pointer-only 入口，必须再调用 `acf workstream context WSNNN` 才读取专属 detail/read_scope，并继续按需读取 reference/output。
- 显式来源冲突或选择不存在、非活动 Workstream 时返回 `SelectionConflict` / `SelectionInvalid`，保持全局上下文并 fail-closed。

### 兼容性与安全

- 原 Workstream/Worktree 生命周期接口和 attention front matter 保持兼容；不要求旧项目批量修改 attention。
- 多个活动 Workstream 是正常项目状态，不再作为 `Ambiguous`；只有真正的显式选择冲突才报错。
- 默认 JSON 不包含任一 Workstream 正文、read_scope、reference、output 或专属 worklog 内容，降低 AI 上下文污染风险。

### 验证

- 新增 global-only、pointer-only、Current Task、显式选择、verified worktree、冲突/无效选择和专属预算隔离测试。
- 完整测试、Python 3.10、升级矩阵、模板/strict check、wheel 隔离安装和生产 console-script smoke 见 WS006 发布证据。

## v0.0.3.54 — 2026-08-04

### 新增

- 新增 `acf workstream reserve`：在 primary branch 上预约并提交唯一 Workstream 编号，扫描 active/archive/index、Git refs、worktree registry 和 operation journal；创建 Workstream 时不隐式创建 branch/worktree。
- 新增 `acf worktree create|attach|verify|list|audit|sync|merge-plan|merge|close|resume`，覆盖正式 Workstream 与分类非 Workstream 的完整 Git worktree 生命周期。
- 新增 `.acf/project.toml` 可选 Git 配置、Git common-dir operation journal、registry 和分层操作锁。
- 新增冲突预演、冻结 source/base commit、`--no-ff` 合并、部分失败恢复和幂等关闭。
- 新增 `docs/Worktree_Lifecycle.md` 教程、真实 Git 仓库测试矩阵和安装态完整生命周期 smoke。

### 兼容性

- 原 `acf workstream add`、状态流转、guard、archive 及不创建 worktree 的项目逻辑保持不变。
- 未配置或未调用 `acf worktree` 时，旧项目不依赖 Git worktree 配置。
- 支持 Python 3.10 及以上；Python 3.10 核心矩阵 46/46 通过。

### 安全边界

- 所有 Git 写命令默认只输出计划，显式 `--apply` 才执行。
- 不自动执行 `stash`、`reset`、`clean`、`rebase`、`branch -D`、`worktree remove --force`、`push` 或冲突解决。
- 错误仓库、detached HEAD、dirty 状态、路径占用、分支占用、primary 前进和内容冲突均 fail-closed。

### 验证

- 完整测试：353/353。
- 新增 worktree 生命周期测试：34/34。
- 完整旧项目 upgrade matrix、模板检查、dogfooding strict check、源码安装态 smoke、wheel 隔离安装 smoke 和生产 `acf.exe` 生命周期 smoke 全部通过。
- 发布 merge commit：`c16e0d1925ae444bec74ecdd4eeea72b74f873e5`。

## v0.0.3.53 — 2026-08-04

- 完善 Workstream guard 文件集强验收、旧项目升级迁移说明和注意力路由。
- 明确裸 `guard` / `--from-git` 仅用于快速查看；完成与状态切换优先使用 `--files`。

## v0.0.3.52 — 2026-06-09

- 发布旧项目升级审计、Workstream-first 上下文入口和模块化 CLI 稳定基线。
- 提供 `upgrade --plan --json`、全局项目日志盘点及稳定安装入口。
