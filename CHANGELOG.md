# 更新日志

本文件记录 ACF 稳定版本的用户可见变化。完整实现证据、测试矩阵和 Workstream 归档仍保存在 `docs/ai/archive/workstreams/` 与 `docs/ai/worklog/`；本文件只保留发布级摘要。

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
