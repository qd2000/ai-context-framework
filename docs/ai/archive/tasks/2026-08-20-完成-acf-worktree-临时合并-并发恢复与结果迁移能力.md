本文件记录当前正在处理的具体任务。

---

## 当前任务状态

Done

---

## 任务名称

完成 ACF Worktree 临时合并、并发恢复与结果迁移能力

---

## 所属大任务

ACF Worktree 临时合并工作树、并发恢复与结果迁移

---

## 子任务 ID

T008.1

---

## 当前执行线

v0.0.3.56 实现、测试、文档、制品构建、隔离安装和真实 dirty-primary dogfooding 已完成；等待发布提交完成后归档当前任务和计划。

---

## 本次任务目标

1. 所有 merge 统一进入临时 integration worktree。
2. Primary 只执行碰撞保护后的 fast-forward promotion。
3. 并发锁、短时路径碰撞和 HEAD 推进可等待、replan 和 resume。
4. ignored/untracked artifact 在 promotion 前显式分类和迁移。
5. close 可重试并恢复部分成功。
6. 发布 v0.0.3.56 制品并完成真实项目 dogfooding。

---

## 输入材料

- `reference/Worktree_Merge_Resilience_Implementation_Plan.md`
- `active/Task_Plan.md`
- `docs/Worktree_Lifecycle.md`
- `CHANGELOG.md`
- `tests/test_worktree_*.py`
- `scripts/worktree_release_smoke.py`

---

## 输出要求

- ACF v0.0.3.56 源码和 CLI
- wheel 与 sdist 制品
- 分片完整测试、升级矩阵和隔离安装 smoke 证据
- FCC dirty-primary 只读 dogfooding证据

---

## 成功标准

1. 分片执行的全部 420 项 unittest通过。
2. template check、dogfooding strict check、compileall、diff check和 full upgrade matrix通过。
3. wheel/sdist 构建成功且 wheel 隔离安装生命周期 smoke通过。
4. FCC `worktree audit` 在 dirty primary 下通过；dirty 来源仍由 `worktree_dirty`门禁阻止。
5. 所有实现和计划保存在 ACF 权威仓库，不在下游维护私有 fork。

---

## 完成证据

- 测试：274 + 35 + 32 + 13 + 66 = 420 项通过。
- Wheel SHA-256：`4a38b1a576946f8023676127f0f08decef53e5720e5a45e398740436d6ac9d14`。
- Sdist SHA-256：`54d6153d22622933b3f8ef3b585fe57833767ed26530c16292addf16ebfd7599`。
- Wheel smoke：`ok=true`，候选 merge、GlobalOnly/Selected/WorktreeSelected 和 close 全生命周期通过。
- FCC dogfooding：primary dirty、WS079 dirty、WS080 clean 的真实工作树矩阵被 v0.0.3.56 正确审计；WS079 merge-plan 返回 `worktree_dirty`。

---

## 约束条件

1. 不修改下游项目的并行任务文件来制造验收成功。
2. 不自动 stash、reset、clean、rebase、force、push 或静默解决冲突。
3. 发布提交前再次运行 ACF strict check、版本检查和 diff check。

---

## 完成后的回写要求

1. 将最终提交哈希和正式安装版本补入当日 worklog。
2. 发布提交完成后归档当前任务和计划，或在下一轮维护时统一归档。

---

<!-- ACF:ARCHIVE:RECORD:START -->
- archived_at: 2026-08-20
- item_type: Task
- item_id: 完成 ACF Worktree 临时合并、并发恢复与结果迁移能力
- source_path: active/Current_Task.md
- archive_path: `archive/tasks/2026-08-20-完成-acf-worktree-临时合并-并发恢复与结果迁移能力.md`
- status: Archived
- archive_reason: WS009 post-merge primary maintenance: archive terminal retained Current_Task after v0.0.3.66 release.
<!-- ACF:ARCHIVE:RECORD:END -->
