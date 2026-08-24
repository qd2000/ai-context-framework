# WS012 — Project Observer Operational Dogfood & Maintenance

## 1. Mission

WS012 承接已经完成并归档的 WS011 之后的 **production operational dogfood**，不是重新开发 Project Observer。

目标：

- 让正式 `ACF Project Observer` Scheduled Task 长期以稳定安装态 ACF 运行；
- 让独立 Maintenance Writer 持续监督 watchdog 是否真的按期刷新，而不是自己替 watchdog 刷新；
- 验证 Dashboard freshness、北京时间展示、跨 worktree authority/source consistency、Writer 并行、异常检测和版本升级后的稳定性；
- 发现具体、可复用的 Observer/ACF 缺陷时，用正式 issue → fix → tests → release → installed-state dogfood 闭环处理；
- 不复活 WS011，不把 WS012 变成常驻 agent runtime、数据库或私有 scheduler。

WS011 保持历史事实：核心 Project Observer 产品已经完成、发布并归档。

---

## 2. Scheduler topology

当前 ACF dogfood 固定采用两个职责完全不同的 Scheduled Task：

### Production Observer

- 名称：`ACF Project Observer`
- cadence：每小时 `:34`
- project：`D:\PROJECT\Tools\ai-context-framework`
- workspace：primary checkout / existing-checkout
- control boundary：`read broad / write narrow / control none`
- 只允许稳定安装态 `acf observer` 写 `~/.acf/projects/<project-id>/observer/`
- 不 claim/challenge/recover/release Writer，不修改 Git/Workstream/project files，不升级 ACF
- v0.0.3.77 起，Dashboard 所有人类可见时间统一显示北京时间 `UTC+08:00`；canonical state/history 继续保存 UTC

### Maintenance Writer

- Workstream：WS012
- 标准 worktree：由 `acf worktree verify/list` 与 local registry 决定，不在共享 Markdown 固化机器绝对路径
- scheduler cadence：每小时 `:04`
- continuation task-id：`WS012`
- 负责诊断、修复、测试、release 和 installed-state verification
- 普通 wake **不得代替 Production Observer 例行执行 `observer snapshot` / render**

`:04 → :34` 保持约 30 分钟间隔，使 Writer 的真实变化先发生，Observer 再独立观察。

---

## 3. Anti-masking contract

这是 WS012 最重要的 dogfood 规则。

正式 Observer 已上线后，Maintenance Writer 每轮首先读取：

- `observer_status.json`
- `state/runs.jsonl`
- `state/current.json`
- `semantic/interpretations.jsonl`
- `dashboard.html` mtime / 可见 freshness

并判断最近一次 **Production Observer** 是否按期成功。

普通 Maintenance wake 禁止为了“让 Dashboard 看起来新鲜”而例行运行：

```text
acf observer snapshot
acf observer interpret
```

否则会掩盖：

- scheduler 没触发；
- watchdog 自身失败；
- lock/overlap 问题；
- data age stale；
- semantic 长期 stale。

只有以下场景允许 Maintenance 主动运行 Observer 写操作：

1. 修复后 focused verification；
2. 明确诊断实验，且已先保存故障前的 durable evidence；
3. release smoke / installed-state dogfood；
4. migration 或用户明确要求的人工刷新。

这类主动运行必须在 continuation effect/evidence 中注明用途，不能被当成 Production Observer 的 scheduler 成功证据。

---

## 4. Initial operational defect

首个已确认问题：

- issue fingerprint：`e469e99755604428cd08`
- evidence：Observer revision 88
- 现象：primary master 已将 WS011 归档为 Done，但另一个仍注册的旧 worktree 保留历史 `WS011=Active` detail；Observer 将该旧副本重新投影成当前 Active Workstream，并产生 `registry-lifecycle-mismatch` warning 与 stale semantic。

这说明 Project Observer 当前的 Workstream source authority 仍可能把“同项目其他 worktree 中的历史副本”误当作当前 project authority。

### 期望 authority 规则

优先验证并实现以下原则，而不是简单忽略 warning：

1. primary checkout 的 active/archive lifecycle 是 project-level Workstream 当前/终态 authority；
2. 某 Workstream 自己的 bound worktree 只有在 registry/lifecycle 允许时，才能作为该 Workstream 的当前专属 source；
3. 任意其他 registered worktree 中顺带存在的旧 Active Workstream detail，不能单独复活一个在 primary 已归档/终态的 Workstream；
4. 这类历史副本可以作为 provenance / divergence / stale-source evidence 被观察，但不能覆盖 canonical current lifecycle；
5. 若 primary 与该 Workstream 自己的 active bound worktree 真正冲突，应 fail-visible（warning/critical + source consistency），不能静默选一个版本。

### Required regression

至少覆盖：

- primary archived Done + unrelated registered worktree stale Active → canonical 不复活；
- primary Active + bound worktree Active → 正常聚合；
- primary Active + bound worktree lifecycle divergence → 明确 Alert；
- unrelated worktree 的历史 WS detail 不参与 canonical current selection；
- history/provenance 仍可保留旧 source，不丢证据。

---

## 5. Operational dogfood gates

### WS012.1 — Bootstrap and separation

完成条件：

- 正式 `ACF Project Observer` task 启用且 cadence=`:34`；
- WS012 Writer cadence=`:04`；
- Dashboard shortcut 唯一维护在 `C:\Users\lenovo\Documents\ACF Project Observer.lnk`，只更新原快捷方式 target，不创建版本/时间戳副本；
- production / maintenance 权限边界和 anti-masking 文档化；
- WS012 continuation 初始化并使用稳定 ACF control plane。

### WS012.2 — Source authority hardening

完成条件：

- issue `e469e99755604428cd08` 有 deterministic regression；
- 修复后 focused Observer tests、strict/template checks、file-scoped guard 和 `git diff --check` 通过；
- 真正的 installed-state Observer 不再把已归档 WS011 ghost-resurrect 为 Active；
- 修复不删除历史 evidence，不把 arbitrary worktree 变成新的 authority。

**Implementation evidence（2026-08-24）**：已新增 primary archive authority 与 active-registry source gate。两个新回归先在旧实现上分别失败：primary 归档后 WS123 被 stale worktree 复活；registry 已 merged 时 stale bound Active 覆盖 primary Done。修复后这两个回归与既有 registry-scoped source 测试均通过，完整 `tests.test_observer_cli` 37/37 通过。真实 ACF candidate `observer snapshot --dry-run` 保留 production runtime 不写入，结果 `snapshot_consistency=stable`、current workstreams 仅 `WS012:Active`、alerts 为空、7 个 worktree diagnostics 仍保留；issue `e469e99755604428cd08` 的 ghost WS011 现场被产品层 source-authority 修复而不是靠清理旧 worktree 绕过。

### WS012.3 — 24-hour production watchdog window

至少观察 24 个连续 hourly Production Observer activation，期间 Maintenance 不做例行 snapshot。

验收至少包括：

- scheduler run cadence 正常；
- `dashboard.html` freshness 持续更新；
- visible timestamps 始终为北京时间，canonical JSON 始终 UTC；
- snapshot consistency / self-health / source consistency 可审计；
- 至少覆盖一次 Writer active/HEAD 变化后由后半小时 Observer 独立观察；
- unchanged period 不制造重复 meaningful history；
- semantic stale/current 行为不由 Maintenance 刷新所掩盖；
- 没有重复 Observer task、重复 Dashboard 或重复 shortcut。

不为了测试“miss”主动破坏 production task；scheduler miss/failure 用 deterministic test 覆盖，若真实发生则作为额外 dogfood evidence。

### WS012.4 — Longitudinal maintenance

24h gate 通过不自动把 WS012 Done。

后续 hourly Writer wake：

- 有真实新 issue / release / authority change → 执行有价值工作；
- 没有当前安全、有价值工作 → 不 claim、不制造 control-plane busywork，结束本次重复 wake；
- mission 保持为长期 Maintenance，除非用户明确关闭或另行迁移。

---

## 6. Release discipline

Observer 修复进入稳定版前必须：

1. focused tests；
2. `acf workstream guard WS012 --files ... --json`；
3. `git diff --check`；
4. `uv run acf check template --json`；
5. `uv run acf check docs/ai --strict --json`；
6. 与风险匹配的 full unit / upgrade matrix / `scripts/release_check.py --mode full`；
7. merge/tag/publish side effect 使用 continuation effect identity；
8. PyPI/remote authority 证明确认后才 terminalize effect；
9. 全局稳定安装后再跑 installed-state Observer dogfood。

普通 checkpoint、commit、测试通过或一次 hourly observation 都不是 mission 结束条件。

---

## 7. Immediate next action

先完成 WS012.1，并以 issue `e469e99755604428cd08` 进入 WS012.2：复现并修复“unrelated stale worktree ghost-resurrect archived Workstream”的 source authority 选择问题；修复前不得通过 Maintenance 手工刷新来掩盖正式 Observer 的真实输出。
