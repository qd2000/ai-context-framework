# Top-Level Implementation Gap

本文把 [reference/ACF_Top_Level_Design.md](ACF_Top_Level_Design.md) 的顶层要求映射到当前实现，用于决定后续受控实施顺序。它不是新功能设计，不替代专题文档；它只回答：哪些已经落地、哪些只是部分落地、哪些不应实现、哪些需要补测试 / 文档 / upgrade 兼容。

---

## 状态

Updated through WS017 runtime debt closure（六域 Gap Matrix：第 4 域运行态隔离与 open issue 计数、第 5 域 CI、版本收敛与发布链、第 3 域命令树快照路径数，已按代码、CHANGELOG 与 workflow 证据校准）。上一轮 P2 逐能力矩阵保留在本文「历史 Gap Matrix（P2 阶段，历史记录）」小节。

---

## 范围

当前六域矩阵覆盖：

1. Core context governance。
2. Workstream / worktree。
3. Continuation / execution control。
4. Observability / issue lifecycle。
5. Release / upgrade compatibility。
6. Dogfooding / current defects。

本文件只做路线校准，不实现新 CLI，不新增 strict 规则，不扩展 high-risk audit rules；具体实施由当前 Workstream 承担。

---

## 状态枚举

| 状态 | 含义 |
|---|---|
| 已实现 | 当前代码、测试和文档已经覆盖顶层要求。 |
| 部分实现 | 主路径已存在，但覆盖面、测试矩阵、兼容性或文档仍有缺口。 |
| 未实现 | 顶层设计已有方向，但当前没有对应实现。 |
| 不应实现 | 顶层设计明确为非目标或暂缓项。 |
| 需要补测试 | 实现存在，但缺少足够 fixture / contract / smoke 覆盖。 |
| 需要补文档 | 实现存在，但专题文档或用户入口仍需收敛。 |
| 需要补 upgrade 兼容 | 旧项目迁移或 fixture 覆盖不足。 |

---

## Gap Matrix（六域，当前）

### 1. Core context governance

| 条目 | 当前状态 | 证据 | 缺口 | 下一步 |
|---|---|---|---|---|
| 权威文档收口 | 已收敛（WS014） | `docs/Automation.md` 已拆为「当前有效自动化合同」与「历史演进说明」；`docs/ai/active/Context.md` 已收敛；WS013 详细计划移入 `docs/ai/archive/plans/`；WS014 子任务板移入 `docs/ai/archive/plans/` | 无 | 保持收敛，出现真实漂移时再修正 |
| 反馈生命周期 | 已实现 | `docs/ai/active/Feedback_Inbox.md`：F015/F017 已转 rules 并 Done、F019 转 Planned 指向 ADR-0006；`acf review stale` | 无长期滞留 Triaged 条目 | 保持 Open→Triaged→Planned→Done 推进，不长期停留 |
| 自检覆盖 | 已实现，但不等于产品健康 | `acf check --strict` 0 errors、`acf doctor` 0 findings、`acf audit context` 0 candidates，同时仓库仍存在文档漂移与运行态污染 | 语义问题不被机械检查覆盖；audit 没有 active 总文件预算 candidate | 保持 advisory；暂不扩 high-risk audit |

### 2. Workstream / worktree

| 条目 | 当前状态 | 证据 | 缺口 | 下一步 |
|---|---|---|---|---|
| Workstream 生命周期与归档 | 已实现 | `acf workstream reserve/add/set/ready/done/archive-candidates/archive-draft/archive`；`reference/Workstream_Lifecycle_Archive_Design.md` | 无 | 保持显式命令，不做自动归档 |
| curated handoff 后 worktree 退休 | 已实现（WS015） | 新增 `acf worktree retire --disposition curated_handoff --evidence-ref ... [--preserve-branch] [--apply]`；只移除 worktree 与 registry、永不删除分支；`close` 的 `branch_not_merged` 硬门不变；回归见 `tests/test_worktree_retire.py` | 无 | 保持显式证据绑定，不提供删除分支开关 |
| 通用 hunk 级别所有权 | 不应实现 | 会把 ACF 推向 patch 管理器、三方合并器或通用编辑器 | 无 | 用 serial coordination + 受控移植替代 |
| closeout authorization | 已实现 | `acf workstream authorization status/list/policy-set/approve/revoke` | 无 | 不改语义 |

### 3. Continuation / execution control

| 条目 | 当前状态 | 证据 | 缺口 | 下一步 |
|---|---|---|---|---|
| continuation 控制面 | 已实现 | owner lease、generation fencing、directive/effect journal、physical execution supervisor、challenge/reconcile/recover、workspace provenance | 复杂度已接近外部 agent 执行控制面，产品边界此前未正式定义 | 见 ADR-0006；分层实现后置 |
| ACF Core 与 Operations 边界 | 设计已落盘 | `decisions/ADR-0006.md` | 逻辑分层未实现，也未拆包 | 后续独立 Workstream 落地 |
| runtime 全局注入 | 已解耦（WS016） | `runtime_parts/*` 用模块级 `__acf_exports__` 显式声明导出并 fail-closed 安装；消费者改用显式 RuntimeContext；`build_parser()` 变为 31 处 `register_*_parser` 组合且不再内联命令组；`acf.py` 只走公开 `runtime.set_root` 且仅在 ROOT 真正变化时同步。护栏：`tests/test_cli_surface_snapshot.py`（212 条路径零漂移）+ `scripts/runtime_export_audit.py` | 命令组分散后定位成本上升（已记入 `reference/Architecture.md` 已知风险）；快照为文本级契约，help 文案变更需同步更新 | 新增 part 导出或命令组时按 ADR-0007 登记并跑两道护栏 |
| owner-context 网页链路 | ACF 侧已隔离验证通过，真实链路待复测 | `scripts/continuation_owner_fixture.py` 与 `tests/test_continuation_owner_fixture.py`：`assert-owner`、`progress`、`release --handoff` 全部通过并判定 `acf_side_ok`；协议见 `reference/Continuation_Owner_Context_Verification.md` | 真实网页工具链无法在本仓库复现，需用同一 argv 形状复测并判定失败层 | 若失败落在 `pre_acf`，改 connector invocation contract 而不是 ACF credential 校验 |

### 4. Observability / issue lifecycle

| 条目 | 当前状态 | 证据 | 缺口 | 下一步 |
|---|---|---|---|---|
| usage log | 已实现，含孤儿命名空间治理 | `acf log enable/disable/status/tail/summarize/projects/prune` + `acf log gc --dry-run/--apply`（默认干跑、`--apply` 写 receipt） | 无默认后台消费者 | 保持显式 GC，不做自动清理 |
| 跨项目 issue 生命周期 | 已实现独立生命周期并完成两轮收口 | `acf log issue list/show/resolve/supersede/reject/reopen` 与用户级台账 `ACF_HOME/issues/ledger.jsonl`；`acf log issues` 叠加台账处置；open 由 9 条降到 4 条，curated handoff 退休路径（`d33a11a387320d21a862`）以 `git:17024d2` 与 `pypi:ai-context-framework:0.0.3.95` 证据 resolve 后再降到 3 条 | 剩余 3 条 open：owner-context 真实链路复测、child effect 委派设计、历史 state-loss 复现确认 | 3 条剩余项分别在明确创建的后续 Workstream 中处理，不并入当期重构范围 |
| test / smoke 运行态隔离 | 已实现（v0.0.3.93 落地，WS017 补齐同类实例） | `scripts/minimal_smoke.py` 的 `isolated_acf_home_env()` 生成逐场景 `ACF_HOME`，`scenario()` 在场景临时根内 set/restore `_scenario_env`，`run_acf()` 的 `subprocess.run(..., env=env)` 无条件注入；`tests/test_smoke_isolation.py` 断言子进程观测到的 `ACF_HOME` 位于场景临时根且不等于真实 HOME，并断言全量跑前后真实 `<ACF_HOME>/projects` 命名空间集合 created / removed 均为 `[]`；WS017 把同类实例 `scripts/worktree_release_smoke.py`（此前 0 处 `ACF_HOME`、`run()` 继承调用者环境且结束即删除临时仓库）改为 `isolated_runtime_state()` 上下文管理器 | `scripts/release_check.py` 的仓库门禁段（`acf check template` / `acf check --strict`）仍在真实 `ACF_HOME` 上执行；该段针对真实仓库、命名空间可解析，不构成孤儿 namespace，暂不隔离 | 保持逐场景隔离；新增会创建临时项目的脚本时按同一协议注入隔离 env 并补无污染回归 |

### 5. Release / upgrade compatibility

| 条目 | 当前状态 | 证据 | 缺口 | 下一步 |
|---|---|---|---|---|
| 发布链 | 已实现 | immutable tag、PyPI 发布（GitHub Trusted Publishing）、全局安装与 installed-state 验证；链路可用性由 v0.0.3.95 与 v0.0.3.96 连续证成，release workflow 以 CI（含 Windows package smoke）为必需门禁后进 publish | 无 | 保持；以同一授权流程发布 `v0.0.3.97` |
| upgrade matrix | 已实现 | `scripts/upgrade_matrix.py` quick / full | 新对象层需随功能增量补 fixture | 新增结构时同步扩 fixture |
| CI | 已实现（v0.0.3.93 收口） | `ci.yml` 的 `tests`（Python 3.10 / 3.12）与 `package` 两个 job 的 os 矩阵均为 `[ubuntu-latest, windows-latest]`；`ci.yml` 与 `release.yml` 的 `actions/checkout` 固定到不可变 SHA `3d3c42e5aac5…`，`astral-sh/setup-uv` 固定到 `08807647e706…`；`ci.yml` 暴露 `workflow_call`，`release.yml` 以 `verify: uses: ./.github/workflows/ci.yml` + `publish: needs: verify` 作为 publish 前必需门禁 | 仓库外的 `pypi` environment 强制 CI 与 `v*` tag protection 无法在代码中固化，已在 `release.yml` 注释记录 | 保持 SHA 固定；新增或升级 action 时同步更新全部引用 |
| 版本收敛与发布闭合 | 部分 | `ai_context_framework/version.py` = `v0.0.3.96`，`pyproject.toml`、`uv.lock` 与 `PKG-INFO` 同为 `0.0.3.96`；CHANGELOG 已有 v0.0.3.96 条目且「发布状态」注明 tag 创建、PyPI 发布与全局安装验证待授权执行。历史欠账已闭合：`v0.0.3.95` 修复 Windows 门禁三处测试夹具缺陷后成功发布（PyPI `latest=0.0.3.95`，`93f04fd` → `17024d2`） | 无 | WS017 已闭合 `v0.0.3.96`：不可变 tag 指向 `01f2dd8`、PyPI `latest=0.0.3.96`、全局安装 `acf v0.0.3.96`（canonical `acf.cmd`）；下一步以 `v0.0.3.97` 发布本轮债务修复（`active/Task_Plan.md` T005） |

### 6. Dogfooding / current defects

| 条目 | 当前状态 | 证据 | 缺口 | 下一步 |
|---|---|---|---|---|
| 跨项目 open issue 收口 | 两轮完成，curated handoff 已 resolve | 9 条 open 处置为 3 resolved / 1 superseded / 2 rejected / 4 open；处置证据与理由写入用户级台账 `ACF_HOME/issues/ledger.jsonl`；`worktree curated handoff 退休路径`（`d33a11a387320d21a862`）由 WS015 的 `acf worktree retire` 落地，并于 v0.0.3.95 以 `git:17024d2` 与 `pypi:ai-context-framework:0.0.3.95` 证据 resolve（open 4 → 3） | 剩余 3 条未关闭项：owner-context 真实链路复测、child effect 委派设计、历史 state-loss 事故复现确认 | 分别进入 owner-context 验证、后续设计决策与真实链路复测 |
| System Manual 双份同步 | 已知成本 | `reference/System_Manual.md` 与 `template/reference/System_Manual.md` 分别维护 | 共享 CLI 合同容易再次漂移 | 本期只修过期内容；marker 共享区块机制后置 |
| 多 agent / 多 Workstream UX（F019） | 已收为设计输入 | `decisions/ADR-0006.md` | 具体 UX 改进未实现 | 后续独立的 continuation / Workstream UX 计划 |
| 自检盲区 | 已确认 | 机械检查全绿时仍存在错误绝对路径、版本矛盾、退役命令引用与 issue 滞留 | 无综合只读入口 | 暂缓 `acf maintenance status`，先靠 WS014 收口 |

---

## 历史 Gap Matrix（P2 阶段，历史记录）

下表是 P2 阶段的逐能力矩阵，保留用于追溯，不再作为当前路线依据。

| 领域 | 顶层要求 | 当前状态 | 证据 | 缺口 | 优先级 | 下一步 |
|---|---|---|---|---|---|---|
| 产品定位 | Markdown-first、模型无关、人工可审阅、CLI 确定性、不做事实裁判 | 已实现 | [reference/ACF_Top_Level_Design.md](ACF_Top_Level_Design.md); [../../README.md](../../../README.md); [../Automation.md](../../Automation.md) | 无代码缺口；后续新增功能需持续检查 | Done | 作为所有后续 PR gate |
| 内容分层 | `active/reference/worklog/archive/rules/decisions` 职责明确 | 已实现 | `AGENTS.md`; [reference/System_Manual.md](System_Manual.md); `template/` | 旧项目可能仍有历史漂移，只能通过 audit/curation 处理 | Done | 不新增规则；继续通过 check/audit 发现漂移 |
| 安全对象创建 | AI 应能通过确定性 CLI 创建常见上下文文件，避免直接手写路径和索引 | 已实现当前 MVP | `acf new task/source/reference/rule/feedback/human-note/worklog/adr`; [tests/test_cli.py](../../../tests/test_cli.py); [reference/System_Manual.md](System_Manual.md) | 第一版仍不自动判断内容应归属哪个事实源；Feedback 和 Human note 只写待整理入口 | Done / P2 | 后续按真实反馈评估更细对象创建命令 |
| Human notes layer | 人工异步笔记可在 ACF 上下文内保存，但不污染 active 默认注意力 | 已实现 | [human/Human_Notes.md](../human/Human_Notes.md); `template/human/`; [reference/System_Manual.md](System_Manual.md); `acf upgrade`; `acf new human-note` | 不支持 weekly/report 创建；符合当前边界 | Done / P2 | standard profile 维护 human 层，minimal 不补；AI 按需读取 |
| Markdown link traceability | 面向人的导航应可被 Obsidian/GitHub 点击，同时保持 ACF Markdown-first、非 Obsidian 绑定 | 已实现 | `acf linkify`; `acf link add`; `acf check` 本地 Markdown link / image / heading anchor 校验；`archive current-task/task-plan` 移动重写本地链接；`System_Manual.md` | `linkify` 第一版仍不默认修改 archive 详情和 daily worklog；不解析 `[[双链]]`；不做 backlink/index graph | Done / P2 | 默认保守 linkify，后续仅在真实使用需要时评估更强批量范围 |
| 唯一事实源 | 写入前判断权威位置，索引不替代详情 | 已实现当前 MVP | Workstream 详情 front matter 作为事实源；`acf workstream sync`; `acf knowledge sync`; `acf decisions sync`; `acf archive sync`; `ACF:ARCHIVE:RECORD`; [reference/Generated_Marker_Sync_Design.md](Generated_Marker_Sync_Design.md); [rules/Always_Active.md](../rules/Always_Active.md) | 旧 Task/Plan archive 没有 record marker 时仍只能 fallback；新归档已可恢复 reason | Done / P2 | 后续仅按真实反馈评估更细 archive record 字段 |
| Task | 主线任务使用 [active/Task_Plan.md](../active/Task_Plan.md) / [active/Current_Task.md](../active/Current_Task.md) | 已实现 | `acf plan`; `acf task`; [tests/test_cli.py](../../../tests/test_cli.py) | 无 | Done | 保持 table-first |
| Active-reference traceability | active 层必须能追溯当前大任务对齐的 reference 设计、路线或差距文档 | 已实现当前 P2 薄切片 | [active/Task_Plan.md](../active/Task_Plan.md) 的 `## 规划依据`; `acf plan reference list/add/remove`; `task start` 继承有效依据到 [active/Current_Task.md](../active/Current_Task.md); `acf upgrade` 非破坏式补结构 | 未接入 `acf check` 断链门禁；未做更重的 plan init reference wizard | Done / P2 | 后续可评估 `acf plan init --reference`、reference 存在性 warning/check 或批量替换占位符工具 |
| Task Stage | `T001.4` 必须注册，父任务和 Workstream 引用可检查 | 已实现当前 P2 薄切片 | `acf check` 已接入 Task Stage registry；`acf plan stage list/add/set/done` 维护 [active/Task_Plan.md](../active/Task_Plan.md) 的 `## 任务阶段` 表 | 未做 task object 单文件；未做 [active/Current_Task.md](../active/Current_Task.md) 自动切换，符合顶层边界 | Done / P2 | 后续仅在表格能力不足时再评估更重对象模型 |
| Workstream | 可选并行目标线，不是 runtime / 调度器 / 权限系统 | 已实现 | `acf workstream init/add/set/block/cancel/ready/done/claim/note/show/list/status/archive-candidates/archive-draft/archive`; `Workstream_Design.md` | 显式单个 Workstream 归档已实现；后续可观察真实项目批量需求，但不做自动归档 | Done / P2 | 保持显式命令，不让 sync/upgrade 自动归档 |
| Workstream Stage | stage add/list/focus/done；focus 拒绝多 Active；done 要 evidence | 已实现 | `acf.py`; [tests/test_cli.py](../../../tests/test_cli.py); `tests/fixtures/context_matrix/workstream_stage_flow`; [tests/test_context_matrix.py](../../../tests/test_context_matrix.py); [scripts/minimal_smoke.py](../../../scripts/minimal_smoke.py); `System_Manual.md` | synthetic fixture 和 smoke 已覆盖；真实复杂样本复核仍可作为 dogfooding 观察，不阻塞下一切片 | Done | 后续真实项目只读复核只记录观察，不新增规则 |
| Workstream lifecycle | Done / Cancelled 短期留 active 必须 keep-active，长期进入 archive | 已完成显式归档闭环 | `acf check` keep-active gate; `acf workstream archive-candidates`; `acf workstream archive-draft`; `acf workstream archive`; `Workstream_Lifecycle_Archive_Design.md`; `tests/fixtures/context_matrix/workstream_lifecycle_archive` | 无自动批量归档；真实项目使用后可再评估批量 apply 或更细 archive index sync | Done / P2 | 先 dogfood 单个显式 archive，不扩大为自动清理 |
| Authority gate | Workstream 不得通过 owned/assigned 直接写 authority path | 已实现 | `acf check --strict`; `tests/fixtures/context_matrix/authority_gate`; [tests/test_context_matrix.py](../../../tests/test_context_matrix.py) | 仅内置 authority map；可配置 map 明确后置 | Done | 保持内置清单，避免配置复杂化 |
| Merge contract | ReadyToMerge 需要合并请求；Done 需要 evidence + merge_resolution | 已实现 | `acf workstream merge-request/ready/done`; strict check; `Workstream_Design.md` | 无明显缺口 | Done | 后续只补归档生命周期 |
| Workstream sync | sync 只更新 [active/Workstreams.md](../active/Workstreams.md)，不改详情、不删除缺详情旧行 | 已实现 | `acf workstream sync`; [tests/test_context_matrix.py](../../../tests/test_context_matrix.py); `System_Manual.md` | 只覆盖 Workstream；其他索引 sync 尚未设计 | Done / P2 | 不扩展到 Knowledge/ADR/Archive，除非先设计 marker |
| Placeholder / marker convention | 模板占位符和机器维护块必须可统一识别、兼容旧格式 | 已实现 | ACF-keyed template placeholder form; `ACF:<DOMAIN>:<PURPOSE>` marker; `acf check template` warning; legacy marker compatibility | 未做批量替换命令；当前无需独立 CLI | Done / P2 | 保持 template 迁移和旧格式 warning，不让真实项目 strict 承担格式迁移 |
| strict check | 低误报、机械裁决、跨项目可解释 | 已实现，持续扩展 | `acf check --strict`; [tests/test_cli.py](../../../tests/test_cli.py); [tests/test_context_matrix.py](../../../tests/test_context_matrix.py); [scripts/upgrade_matrix.py](../../../scripts/upgrade_matrix.py) | 新规则必须补 fixture；不应把 audit heuristic 升级为 strict | Done | 作为后续 PR gate |
| audit context | 只读 candidates，不写文件，不接入 strict | 已实现 MVP | `acf audit context`; `Context_Audit_Design.md`; tests for clean/long/stale/terminal candidates | high-risk rules 暂缓；阈值和 message 仍需 dogfooding | P2 | 暂不扩展 duplicate/evidence/volatile |
| review stale / curate draft | stale 只读，curate draft 只生成可审阅草案 | 已实现 | `acf review stale`; `acf curate draft`; [tests/test_cli.py](../../../tests/test_cli.py); `upgrade_matrix` | curate draft 后续可更丰富，但不应自动 apply | P2 | 等 gap 更明确后再扩 |
| draft | writeback / curate / knowledge 草案不进入默认读取路径 | 已实现 | `acf writeback draft`; `acf curate draft`; `acf knowledge draft`; `AGENTS.md` | 无 | Done | 保持草案边界 |
| upgrade | 非破坏式补结构，不改事实，不自动归档 | 已实现当前 P1 兼容矩阵 | `acf upgrade`; [scripts/upgrade_matrix.py](../../../scripts/upgrade_matrix.py); `tests/fixtures/upgrade_matrix/*`; [tests/test_upgrade_matrix.py](../../../tests/test_upgrade_matrix.py) | 已覆盖 old without Workstreams、old Workstreams without current_stage、old ADR without front matter、custom AGENTS + missing reference combo；后续新对象层仍需随功能增量补 fixture | Done | 新增结构时同步扩 upgrade matrix |
| JSON contract | AI-facing 命令稳定 `schema_version/ok/command/next_actions`，失败有 `error_code/message` | 已实现基础契约测试 | [tests/test_cli.py#test_ai_facing_success_json_contracts](../../../tests/test_cli.py#test_ai_facing_success_json_contracts); [tests/test_cli.py#test_ai_facing_failure_json_contracts](../../../tests/test_cli.py#test_ai_facing_failure_json_contracts); `acf.py` | 仍不是全命令同形重排；后续新增 AI-facing 命令必须复用 contract helper | Done | 新命令新增时补契约测试 |
| error_code recovery | 常见失败路径有稳定 error_code 和 next_actions | 已实现基础契约测试 | JSON contract failure tests; workstream stage errors; check/status input errors | 不是完整 error catalog；安全拒绝仍可保留通用 `safety_refused` | Done / P2 | 如做 error catalog，单独设计 |
| context_matrix | minimal/legacy/audit/workstream/authority 防过拟合 fixture | 部分实现 | `tests/fixtures/context_matrix/*`; [tests/test_context_matrix.py](../../../tests/test_context_matrix.py) | `task_stage_registry`、`workstream_stage_flow` 和 `workstream_lifecycle_archive` 已补；audit stale / terminal merge 仍只有单元测试，缺独立 fixture | P2 | 下一代码切片优先补 `audit_stale_stage` 和 `audit_terminal_merge` fixtures |
| minimal smoke | 快速覆盖 init/status/check/worklog/workstream/task-stage 主路径 | 已实现当前 P2 范围 | [scripts/minimal_smoke.py](../../../scripts/minimal_smoke.py) 包含 Workstream stage add/focus/done、workstream sync dry-run no-op、audit context clean、archive-candidates / archive-draft / archive 主路径，以及 Task Stage add/list/done | 仍是 release smoke，不替代全量单元/fixture 测试 | Done | 保持轻量 |
| 多项目验证 | ACF/FCC/EcSOS/minimal/legacy/fixtures 共同验证 | 部分实现 | worklog 记录 FCC/EcSOS dogfooding；context/upgrade fixtures; Workstream stage / archive synthetic fixtures | P1/P2 主链路已有 synthetic 和部分真实项目只读验证；新 archive apply 尚未在外部真实项目执行 | P2 | 先补 audit fixtures；真实项目继续只读或 dry-run，写入前单独确认 |
| Task object 文件 | 不急于 `active/tasks/T001` 单文件化 | 不应实现 | `ACF_Top_Level_Design.md` | 无 | Deferred | 暂不做 |
| high-risk audit | duplicate、strong claim、volatile wrong location | 不应现在实现 | `Context_Audit_Design.md`; `Product_Roadmap.md` | 需要多项目样本和 fixture 后再评估 | Deferred | 暂缓 |
| agent runtime / scheduler | 非目标 | 不应实现 | Top-Level non-goals; Workstream Design | 无 | Never | 不做 |
| 自动合并 Context | 非目标；Workstream 只产出 merge input | 不应实现 | `Workstream_Design.md`; `ACF_Top_Level_Design.md` | 无 | Never | 不做 |

---

## Layer Summary

### 已实现

1. Markdown-first 上下文分层和默认读取路径。
2. `plan` / `task` 主线任务维护。
3. optional Workstream 层与 Workstream 状态机。
4. Workstream stage add/list/focus/done。
5. Workstream authority gate、merge_targets、merge_resolution、keep-active gate。
6. Workstream index consistency check 和 sync。
7. Workstream archive-candidates / archive-draft / explicit archive 归档闭环。
8. `audit context` MVP。
9. `review stale` 和 `curate draft` 最小链路。
10. writeback / knowledge draft 草案边界。
11. active -> reference 规划依据追溯，含模板、upgrade、task start 继承和 `plan reference` 确定性编辑命令。
12. standard profile human layer，支持 Obsidian 人工双链边界但不解析双链。
13. Markdown link traceability：`check` 校验本地 Markdown link / image / heading anchor，`linkify` 和 `link add` 支持确定性链接维护。
14. 统一模板占位符和 canonical ACF marker，兼容旧 marker 并给出 future warning。
15. `upgrade` 非破坏式结构补齐主路径。
16. `new reference` / `new rule` / `new feedback` 安全创建常见上下文文件，并维护 Rules_Index / Feedback_Inbox。
17. `feedback list|triage|done|reject|archive-candidates|archive` 维护 Feedback_Inbox 生命周期，单条显式归档到 archive/feedback/YYYY-MM dot md。
18. `new human-note` 安全写入标准 profile 的 `human/Human_Notes.md` Inbox。
19. `ACF:ARCHIVE:RECORD` 让新 Task/Plan 归档可被 `archive sync` 恢复原因。
20. context_matrix 和 upgrade_matrix 基础设施。

### 部分实现

1. sync：Workstream、Knowledge、Decisions 和 Archive MVP 已实现。

### 未实现但可后置

1. 更强 curation draft。

### 不应现在实现

1. high-risk audit rules。
2. 语义去重。
3. 自动事实裁决。
4. agent runtime / scheduler。
5. 自动合并 Context。
6. Task object 全文件化。

---

## Prioritized Next Slices

### P1-1 JSON contract consistency

理由：顶层设计要求 AI-facing 命令稳定输出；当前已有大量 JSON，但缺统一 contract inventory。该项是所有后续 CLI 能力的地基。

建议范围：

1. 建立 JSON contract test helper。
2. 覆盖 status、check、upgrade dry-run、audit context、review stale、curate draft dry-run、workstream status/list/show、workstream stage list、workstream stage add dry-run、edit section get。
3. 对现有 payload 做兼容记录，不强行一次性重排所有字段。
4. 对失败路径覆盖 check_failed、input_error、safety_refused、workstream_stage_active_conflict、curation_draft_exists。

验收：

1. 每个被列为 AI-facing 的命令至少验证 `schema_version`、`ok`、`command` 或等价命令标识、`next_actions`。
2. 失败 payload 至少验证 `ok=false`、`error_code`、`message` 或可读错误、`next_actions`。
3. 不改变 JSON 兼容字段，除非明确 bump patch/minor。

状态：已完成。实现见 [tests/test_cli.py](../../../tests/test_cli.py) 的 AI-facing success/failure JSON contract tests；`check/status --json` 失败 payload 已补 `message`，版本 bump 到 `v0.0.3.28`。

### P1-2 Workstream stage flow fixture

理由：命令已实现，但顶层设计要求多项目 / synthetic 防过拟合。当前缺独立 context_matrix fixture 表达完整 stage flow。

建议范围：

1. 新增 `tests/fixtures/context_matrix/workstream_stage_flow`。
2. 覆盖 stage add/list/focus/done、focus 多 Active 拒绝、done evidence 和 clear-current。
3. minimal smoke 可补 audit clean 和 sync dry-run no-op。

验收：

1. [tests/test_context_matrix.py](../../../tests/test_context_matrix.py) 覆盖该 fixture。
2. `uv run python [scripts/minimal_smoke.py](../../../scripts/minimal_smoke.py) --acf uv run acf` 覆盖 stage flow、sync 和 clean audit。

状态：已完成。新增 `tests/fixtures/context_matrix/workstream_stage_flow`，[tests/test_context_matrix.py](../../../tests/test_context_matrix.py) 覆盖 stage add/list/focus/done、dependency blocked、multi Active conflict、missing evidence、clear-current required、strict check、sync no-op 和 audit clean；[scripts/minimal_smoke.py](../../../scripts/minimal_smoke.py) 已显式断言 sync dry-run no-op 与 audit candidates=[]。

### P1-3 Upgrade matrix expansion

理由：顶层设计强调旧项目兼容。当前 upgrade matrix 已覆盖 attention governance 历史版本，但还缺对象层旧形态。

建议 fixture：

1. old context without Workstreams。
2. old context with Workstreams but no current_stage。
3. old ADR without front matter。
4. custom AGENTS combined with missing new reference document。

验收：

1. quick 模式不变重。
2. full 模式覆盖新增旧形态。
3. upgrade 仍不自动启用 optional Workstream。

状态：已完成。新增 old without Workstreams optional、old Workstreams without current_stage、old ADR without front matter、custom AGENTS + missing reference combo fixtures；runner 增加 expected_absent、detected_features、changed_files suffix 和 Workstream sync no-op 断言；quick/full matrix 均通过。

### P2-1 Task Stage CLI

理由：Task Stage check 已有，CLI 尚无。它有价值，但优先级低于 JSON contract 和兼容矩阵。

建议命令：

```bash
acf plan stage add ...
acf plan stage set ...
acf plan stage done ...
```

前置条件：

1. JSON contract consistency 完成。
2. task_stage_registry fixture 完成。
3. 明确不创建 task object 单文件。

状态：已完成。新增 `acf plan stage list/add/set/done`，只维护 [active/Task_Plan.md](../active/Task_Plan.md) 的 `## 任务阶段` 表；`add/set` 校验 stage ID 归属父任务、父任务存在、optional Workstream owner 存在；`done` 要求 evidence；未创建 task object 单文件，未自动修改 `Current_Task`，未联动 Workstream。新增 `tests/fixtures/context_matrix/task_stage_registry`、CLI 单元测试和 minimal smoke Task Stage 主路径。

### P2-2 Workstream lifecycle / archive helper

理由：keep-active gate 已有，但 Done / Cancelled 到 archive 的闭环仍靠人工。

前置条件：

1. archive/workstream lifecycle design。
2. fixture 证明不会误归档当前计划仍需解释的 Workstream。
3. 明确第一版是否只生成 draft，而不是移动文件。

状态：已完成设计与 fixture，并在 P2-3 落地只读 helper。新增 [reference/Workstream_Lifecycle_Archive_Design.md](Workstream_Lifecycle_Archive_Design.md)，明确第一版先做 `workstream archive-candidates` 或 archive draft 这类只读/草案 helper，不直接移动文件；新增 `tests/fixtures/context_matrix/workstream_lifecycle_archive` 和 context_matrix 测试，覆盖 retained terminal Workstream strict clean、terminal Workstream 作为当前执行线被拒绝、expired keep-active 被 strict 拦截。

### P2-3 Workstream archive-candidates

```bash
acf workstream archive-candidates docs/ai --json
```

状态：已完成。该命令只读输出 `candidates`、`blocked`、`blocked_by`、`changed_files: []` 和 summary，不修改文件、不移动详情、不修改索引、不接入 strict。已覆盖 CLI 单元测试、AI-facing JSON contract、context_matrix lifecycle fixture 和 minimal smoke。

### P2-4 Workstream archive-draft and explicit archive

```bash
acf workstream archive-draft docs/ai --date 2026-05-08 --json
acf workstream archive WS001 docs/ai --reason "reviewed in worklog/archive-drafts/2026-05-08.md" --json
```

状态：已完成。`archive-draft` 写入 worklog/archive-drafts/YYYY-MM-DD dot md，包含 candidates + blocked、候选建议命令和 blocked suggested_action；默认不覆盖已有草案，支持 `--name`、`--force` 和 `--dry-run`。`archive` 复用候选 blocker，只允许 Done / Cancelled 单个 Workstream，移动详情到 `archive/workstreams/`，删除 active index 对应行并重算 Workstream 状态，追加 [archive/Archive_Index.md](../archive/Archive_Index.md) 7 列记录和 `ACF:WORKSTREAM:ARCHIVE-RECORD` marker；不修改 merge target、Context、Current_Task 或 Task_Plan。已覆盖 CLI 单元测试、context_matrix draft-to-archive flow 和 minimal smoke。

### P2-6 Human layer, placeholder and marker modernization

状态：已完成。标准 profile 现在生成 [human/Human_Notes.md](../human/Human_Notes.md)、`human/weekly/` 和 `human/reports/`，用于人工异步笔记、周记录和汇报材料；minimal profile 不补 human 层。`upgrade` 只在推断为 standard profile 时非破坏式补齐 human 层，不把 human 内容自动升格为 active 事实，也不新增独立 human CLI。

Obsidian 边界已写入手册：项目可以把 `docs/` 作为 vault 根目录，`[[双链]]` 只服务人工查看和编辑；ACF 不解析、不校验、不依赖双链，结构化引用仍使用普通 Markdown 路径。模板占位符已迁移为 ACF-keyed placeholder form，表格单元格使用无提示形式；机器维护块统一为 `ACF:<DOMAIN>:<PURPOSE>` marker，旧 `ACF:UPGRADE-NOTES` 和 `ACF:WORKSTREAM-ARCHIVE` 兼容识别并给出 future warning。

### P2-7 Markdown link traceability

```bash
acf linkify docs/ai --format markdown --dry-run --json
acf link add docs/ai active/Current_Task.md --heading "## 输入材料" --target reference/System_Manual.md --target-heading "Markdown 链接与人工导航" --json
```

状态：已完成。ACF 仍不解析、不依赖 Obsidian `[[双链]]`，但结构化路径引用可以转换为普通 Markdown 链接，便于 Obsidian、GitHub 和其他 Markdown 工具点击导航。`acf check` 会校验本地 Markdown 链接和图片链接目标存在，并校验 `.md#anchor` 能匹配目标 Markdown 标题；URL 和其他 URI scheme 跳过网络校验。

`acf linkify` 第一版只支持 `--format markdown`，默认处理 active、reference、rules、decisions、[worklog/Worklog_Index.md](../worklog/Worklog_Index.md) 和 [archive/Archive_Index.md](../archive/Archive_Index.md)，保守跳过 archive 详情和 daily worklog；缺失目标默认跳过并报告，`--allow-missing` 才生成链接。`acf link add` 第一版只向指定 section 追加链接 bullet，要求目标在上下文内，`--target-heading` 会生成并校验 anchor，重复链接默认拒绝。

`v0.0.3.37` 已补通用本地 Markdown 链接移动重写 helper，并接入 `acf archive current-task/task-plan`：归档当前任务或计划时会按归档文件的新位置重写已有本地相对链接，避免 `--check-after --strict` 在工具刚写完后因移动断链失败。该能力不重写 URL/URI、缺失目标或代码块内链接。

### P2-5 Context matrix audit fixture expansion

状态：已完成。

理由：

1. 它不改变产品行为，只把已实现的 audit MVP 用独立 fixture 固化，风险低。
2. 当前 `audit_stale_stage` 和 `audit_terminal_merge` 只有单元测试，缺 context_matrix 级防过拟合样本。
3. 它符合“每个新能力先补 fixture，再实现命令或规则”的路线，且能为后续 audit 调优提供基线。
4. 它比直接扩 Knowledge / ADR / Archive sync 更小；后者需要先设计 generated marker 和删除策略。

建议范围：

1. 新增 `tests/fixtures/context_matrix/audit_stale_stage`，覆盖 Active Current_Task / Workstream stage stale candidate 的可解释输出。
2. 新增 `tests/fixtures/context_matrix/audit_terminal_merge`，覆盖 ReadyToMerge 待合并或 Done 缺合并结果的 advisory candidate。
3. 更新 fixture inventory 和 context_matrix tests；不新增 audit rule，不接入 strict。

验收：

1. `uv run python -m unittest` 通过。
2. `uv run acf check docs/ai --strict --json` 通过。
3. `uv run python [scripts/minimal_smoke.py](../../../scripts/minimal_smoke.py)` 不需要扩大，除非 fixture 暴露了现有 smoke 缺口。

完成记录：已新增 `tests/fixtures/context_matrix/audit_stale_stage` 和 `tests/fixtures/context_matrix/audit_terminal_merge`，并在 [tests/test_context_matrix.py](../../../tests/test_context_matrix.py) 覆盖 stale Current_Task / stale Workstream stage、ReadyToMerge merge input 和 Done 缺 `merge_resolution` 的 advisory candidates；未新增 audit rule，未接入 strict。

### P2 Active-reference traceability

```bash
acf plan reference add docs/ai --path reference/Product_Roadmap.md --purpose "阶段路线和近期优先级"
acf plan reference list docs/ai --json
```

状态：模板 / upgrade / 生成逻辑已补齐，并已完成稳定化补测。[active/Task_Plan.md](../active/Task_Plan.md) 现在有稳定 `## 规划依据` 小节；`task start` 会把有效 reference bullets 带入 [active/Current_Task.md](../active/Current_Task.md) 的 `## 输入材料`；`upgrade` 会给旧计划非破坏式补结构，并给 Active 当前任务追加查看计划依据的提示；`plan reference list|add|remove` 可确定性维护路径和一句话用途，支持 `--allow-missing`、`--force`、`--missing-ok` 和显式 `--sync-current-task`。

稳定化覆盖：`old_active_reference_traceability` upgrade matrix fixture 覆盖旧 [active/Task_Plan.md](../active/Task_Plan.md) / Active [active/Current_Task.md](../active/Current_Task.md) 的非破坏式补齐；CLI 边界测试覆盖 dry-run sync、不标准 Current_Task 引用保守跳过、模板占位符不继承、`--missing-ok` 幂等，以及 `task start` 不生成嵌套 bullet。EcSOS dry-run 验证为 clean / status ok，升级会补 [active/Task_Plan.md](../active/Task_Plan.md) 和 [active/Current_Task.md](../active/Current_Task.md) 追溯结构，同时刷新旧 schema 文档；FCC dry-run 验证为 clean / status ok，升级会补 [active/Task_Plan.md](../active/Task_Plan.md)，并因旧 [active/Current_Task.md](../active/Current_Task.md) 缺少 `## 输入材料` 给出预期保守 warning。

后续可能增强：`acf plan init --reference`、`acf plan reference check`、`acf check` 对规划依据断链给 warning、或统一占位符批量替换命令。本轮不把 reference 存在性接入 `check`，避免旧项目和模板占位符产生迁移噪声。

### Deferred audit rules

继续暂缓：

1. `duplicate_active_fact_candidate`
2. `strong_claim_without_evidence`
3. `volatile_fact_in_wrong_authority_location`

进入条件仍是多 fixture、多项目观察和只读 candidate。

---

## Next Code PR Decision

当前批次是缺陷与欠账修复（WS017），按依赖顺序：

```text
1. release closure for the v0.0.3.96 change set (immutable tag, PyPI publish, global install verification)  [done]
2. worktree_release_smoke runtime-state isolation plus no-pollution regression  [done]
3. minute-level timestamp CLI generation helper (acf clock now) plus contract and docs sync  [done]
4. six-domain gap matrix calibration for domains 4 and 5  [done]
5. v0.0.3.97 version convergence, full gate, workstream closeout, and release  [pending]
```

WS017 之后的下一批候选（未排序，均需独立 Workstream 与验收标准）：

```text
1. System Manual shared-block sync mechanism
2. owner-context real web chain re-verification; supervised child effect delegation design
3. historical state-loss incident reproduction confirmation
4. ACF Core / Operations layering implementation (ADR-0006)
```

理由：

1. 这些都是已确认为真实的欠账或过期事实：`v0.0.3.96` 已完成版本收敛但尚未发布；`scripts/worktree_release_smoke.py` 会在真实运行态留下指向已删除临时目录的孤儿命名空间；分钟级时间字段只能手写（规则已要求 `YYYY-MM-DD HH:MM` 但没有生成入口）；第 4/5 域矩阵行与代码、CHANGELOG、workflow 事实矛盾。
2. 它们都不触碰 runtime 组合契约、continuation 语义与对外 CLI 契约；唯一的新增能力是只输出时间的纯函数命令，回归面可控。
3. 发布闭合必须先于代码变更：`v0.0.3.96` 的 CHANGELOG 发布状态说明已注明待授权发布，若被 `v0.0.3.97` 挤后再发会让该记录变成假事实。
4. 矩阵只校准有硬证据的矛盾行，不顺势扩张新的分析结论；`scripts/release_check.py` 仍在真实 `ACF_HOME` 上跑仓库门禁，但针对的是可解析的真实仓库，已作为观测项留在第 4 域而不是本轮修复范围。

拒绝的替代：

| 替代 | 暂不选择原因 |
|---|---|
| 通用 hunk 级别所有权系统 | 会把 ACF 推向 patch 管理器与三方合并器；改用 serial coordination + 保存外部 diff/hash + 独立 patch/commit 受控移植。 |
| 继续扩 high-risk semantic audit | 当前问题是收口与治理，不是缺少更多审计规则；新增规则只会增加误报与维护负担。 |
| 在同一版本内重构 runtime 全局注入 | 影响面大，需独立 Workstream 与显式分层设计，不能与本次小范围修复混合。 |
| 直接扩 curation draft 语义能力 | 需要先有更多 fixture 与多项目样本，避免草案噪声。 |
| 做自动 Context merge | 明确非目标。 |

---

## Verification Plan

本 gap audit 文档阶段只需要：

```bash
uv run acf check docs/ai --strict --json
uv run acf audit context docs/ai --json
```

不需要运行完整 unittest，因为本轮不改 CLI 代码、不改模板行为、不改变 JSON 输出。

如果下一阶段进入新的代码切片，则需要运行：

```bash
uv run python -m unittest
uv run acf check docs/ai --strict --json
uv run python scripts/minimal_smoke.py
```

---

## 结论

ACF 继续保持受控实施阶段；audit fixture 矩阵、generated marker 设计、通用 marker helper、Knowledge sync MVP、Decisions sync MVP 和 Archive sync MVP 已补齐。下一步不应扩大 high-risk audit 或自动事实裁决，应基于真实使用反馈选择小边界修正。

推荐顺序：

1. Knowledge / Decisions / Archive sync 后续只根据真实使用反馈补小边界，不扩大为语义去重。
2. Curation draft enhancement，必须基于 P2-5 fixture 和多项目观察。
3. high-risk audit rules 继续暂缓。
4. 真实项目继续只读或 dry-run 观察，写入前单独建任务。

当前进度：P1-1、P1-2、P1-3、P2-1、P2-2、P2-3、P2-4、P2-5、P2-6、active-reference traceability、generated marker design、marker helper、Knowledge sync MVP、Decisions sync MVP、Archive sync MVP、Task/Plan archive record marker、Feedback lifecycle、human-note 与 safe context object creation MVP 已完成；下一入口应由真实 dogfooding 反馈决定。
