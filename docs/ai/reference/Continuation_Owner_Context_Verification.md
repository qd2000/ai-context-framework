# Continuation Owner-Context 传输验证协议

本文件定义如何在**完全隔离**的环境中重复验证 continuation owner-context 在外部调度/网页工具链里的可执行性，用于区分失败发生在哪一层。

本文件是验证协议与结论记录，不是当前事实源；当前有效事实仍以 `active/Context.md` 为准。

---

## 1. 背景问题

`.91` 期间的真实证据表明：

1. `acf continuation recover` 能成功；
2. ACF 能生成本地 `owner_context` capability handle；
3. 但后续命令携带 `--owner-file <local-handle>` 时，被**外围安全层在 ACF 执行前**拒绝；
4. Agent 因此无法执行 `assert-owner`、`progress`、`execution`、`checkpoint`、`release`，continuation 再次进入「成功恢复但无法继续操作」的死锁。

`.92` 主要删除 Observer，未实质修改 owner-context transport。

因此结论是：**该问题很可能仍存在，但必须重新验证，不能按历史记录直接改 ACF 代码。**

---

## 2. 分层失败模型

验证的核心产出不是「成功/失败」，而是**失败发生在哪一层**：

| 层 | 名称 | 判定特征 |
|---|---|---|
| L0 | 网页安全层 | 命令在执行前被外围策略拒绝，ACF 从未收到参数 |
| L1 | MCP / DevSpace 参数层 | 参数被截断、重写或拒绝，发生在 ACF parser 之前 |
| L2 | Shell（PowerShell / bash） | ACF 收到参数，但 shell 转义、引号或路径展开损坏 handle |
| L3 | ACF parser | ACF 收到参数，但参数解析失败（例如 `--owner-file` 缺失） |
| L4 | ACF owner binding | ACF 解析成功，但 handle 与 canonical lease/generation 校验失败 |

只有当失败落在 L3/L4 时，修改 ACF credential 校验逻辑才有意义；若落在 L0/L1，应调整**本地 connector invocation contract**，例如把 capability handle 作为结构化工具字段传递，而不是自由命令行字符串。

---

## 3. 隔离要求

验证必须在完全隔离的环境中执行，**不得触碰任何真实运行态**：

1. 临时 Git 仓库（不得使用本仓库或任何真实项目）；
2. 临时 `ACF_HOME`（必须显式覆盖，禁止写入真实 `~/.acf`）；
3. 临时 continuation task；
4. 不读取 owner context 内容（验证传输本身，不验证其内容）；
5. 结束后清理临时仓库与临时 `ACF_HOME`。

推荐实现载体：`scripts/continuation_owner_fixture.py`。

---

## 4. 步骤

1. 建立临时 Git 仓库与最小 ACF 上下文，并设 `ACF_HOME` 指向临时目录。
2. `acf continuation init` 建立一个最小 task。
3. `acf continuation claim`（或 `recover`）取得 owner context capability handle。
4. **不读取** handle 内容，只记录其路径与大小。
5. 以与正式 Scheduled Task 相同的调用形状，依次执行：
   - `acf continuation assert-owner --owner-file <handle> ...`
   - `acf continuation progress --owner-file <handle> ...`
   - `acf continuation release --owner-file <handle> ...`
6. 对每一步记录：退出码、`error_code`、stderr、以及命令是否到达 ACF（可用 ACF 侧日志/usage event 判断）。
7. 按第 2 节分层模型给出结论。

---

## 5. 可重复执行的判定

- 同一 fixture 连续运行两次，ACF 侧行为必须一致；
- fixture 运行前后，真实 `~/.acf/projects` 目录集合与内容必须完全不变；
- 若 ACF 侧三步全部通过而真实网页链路仍失败，则问题在 L0/L1，结论应记录为「阻断发生在 ACF 之前」。

---

## 6. 本地验证结果与当前状态

### 6.1 环境约束（已实测）

- `ACF_HOME` 必须位于被测 Git worktree **之外**：临时 `ACF_HOME` 必须是被测仓库的兄弟目录，而不是仓库内子目录。
- 临时仓库必须先有至少一个提交，否则 `continuation init` 返回 `git_command_failed: git command failed: rev-parse HEAD`。

### 6.2 ACF 侧隔离验证（已通过）

载体：`scripts/continuation_owner_fixture.py`，回归见 `tests/test_continuation_owner_fixture.py`。

命令形状与调度 wrapper 一致：

```text
acf continuation claim <worktree> --task-id <id> --runner-id <runner> --json
acf continuation assert-owner <worktree> --task-id <id> --owner-file <handle> --json
acf continuation progress <worktree> --task-id <id> --owner-file <handle> --phase executing --milestone <text> --json
acf continuation release <worktree> --task-id <id> --owner-file <handle> --handoff --json
```

结果：`assert-owner` 返回 `owner_confirmed`（`liveness=fresh`）、`progress` 返回 `progress_recorded`、`release --handoff` 返回 `released_to_running_handoff` 且 owner-context 被 revoke。fixture 不读取 handle 内容，只确认 capability 文件存在且位于隔离 `ACF_HOME` 内。因此 **ACF 侧的 owner-context 传输本身是可用的**。

失败层判定实现为 `classify_layer`：没有可解析 JSON payload 即判为 `pre_acf`（shell / mux / 网页安全层）；有 payload 时按 `error_code` 区分 `acf_parser` 与 `acf_owner_binding`。

### 6.3 真实网页工具链复测（待执行）

真实 DevSpace / 网页工具链复测仍未执行，本仓库无法复现外围安全层。复测时必须使用与 6.2 完全相同的 `--owner-file` 形状，并记录失败落在哪一层。

- 若命令在 ACF 之前就被拒绝（`pre_acf`），应调整本地 connector invocation contract（例如把 capability handle 作为结构化工具字段传递），而不是继续修改 ACF credential 校验。
- 在该结论更新前，该问题保持 open（fingerprint `9a71c4eeb823b752e55b`），不得标记为已修复。
