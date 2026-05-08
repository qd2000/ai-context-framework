# Top-Level Implementation Gap

本文把 `reference/ACF_Top_Level_Design.md` 的顶层要求映射到当前实现，用于决定后续受控实施顺序。它不是新功能设计，不替代专题文档；它只回答：哪些已经落地、哪些只是部分落地、哪些不应实现、哪些需要补测试 / 文档 / upgrade 兼容。

---

## 状态

Updated through P2-6 human layer, Obsidian boundary, placeholder and canonical marker modernization.

---

## 范围

本轮 gap audit 覆盖：

1. 内容组织模型。
2. 对象模型。
3. CLI 分层。
4. strict check。
5. audit context。
6. sync。
7. upgrade。
8. draft。
9. JSON / error_code 契约。
10. Workstream stage flow。
11. 测试与多项目验证矩阵。

本轮是路线校准，不实现新 CLI，不新增 strict 规则，不扩展 high-risk audit rules。

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

## Gap Matrix

| 领域 | 顶层要求 | 当前状态 | 证据 | 缺口 | 优先级 | 下一步 |
|---|---|---|---|---|---|---|
| 产品定位 | Markdown-first、模型无关、人工可审阅、CLI 确定性、不做事实裁判 | 已实现 | `reference/ACF_Top_Level_Design.md`; `../../README.md`; `../Automation.md` | 无代码缺口；后续新增功能需持续检查 | Done | 作为所有后续 PR gate |
| 内容分层 | `active/reference/worklog/archive/rules/decisions` 职责明确 | 已实现 | `AGENTS.md`; `reference/System_Manual.md`; `template/` | 旧项目可能仍有历史漂移，只能通过 audit/curation 处理 | Done | 不新增规则；继续通过 check/audit 发现漂移 |
| Human notes layer | 人工异步笔记可在 ACF 上下文内保存，但不污染 active 默认注意力 | 已实现 | `human/Human_Notes.md`; `template/human/`; `reference/System_Manual.md`; `acf upgrade` | 无独立 human 命令；符合当前边界 | Done / P2 | standard profile 维护 human 层，minimal 不补；AI 按需读取 |
| 唯一事实源 | 写入前判断权威位置，索引不替代详情 | 部分实现 | Workstream 详情 front matter 作为事实源；`acf workstream sync`; `rules/Always_Active.md` | 仅 Workstream 有强 sync/check；Knowledge/ADR/Archive 尚未设计 generated view | P2 | 后续如做 sync 扩展，先设计 generated marker |
| Task | 主线任务使用 `active/Task_Plan.md` / `active/Current_Task.md` | 已实现 | `acf plan`; `acf task`; `tests/test_cli.py` | 无 | Done | 保持 table-first |
| Active-reference traceability | active 层必须能追溯当前大任务对齐的 reference 设计、路线或差距文档 | 已实现当前 P2 薄切片 | `active/Task_Plan.md` 的 `## 规划依据`; `acf plan reference list/add/remove`; `task start` 继承有效依据到 `active/Current_Task.md`; `acf upgrade` 非破坏式补结构 | 未接入 `acf check` 断链门禁；未做更重的 plan init reference wizard | Done / P2 | 后续可评估 `acf plan init --reference`、reference 存在性 warning/check 或批量替换占位符工具 |
| Task Stage | `T001.4` 必须注册，父任务和 Workstream 引用可检查 | 已实现当前 P2 薄切片 | `acf check` 已接入 Task Stage registry；`acf plan stage list/add/set/done` 维护 `active/Task_Plan.md` 的 `## 任务阶段` 表 | 未做 task object 单文件；未做 `active/Current_Task.md` 自动切换，符合顶层边界 | Done / P2 | 后续仅在表格能力不足时再评估更重对象模型 |
| Workstream | 可选并行目标线，不是 runtime / 调度器 / 权限系统 | 已实现 | `acf workstream init/add/set/block/cancel/ready/done/claim/note/show/list/status/archive-candidates/archive-draft/archive`; `Workstream_Design.md` | 显式单个 Workstream 归档已实现；后续可观察真实项目批量需求，但不做自动归档 | Done / P2 | 保持显式命令，不让 sync/upgrade 自动归档 |
| Workstream Stage | stage add/list/focus/done；focus 拒绝多 Active；done 要 evidence | 已实现 | `acf.py`; `tests/test_cli.py`; `tests/fixtures/context_matrix/workstream_stage_flow`; `tests/test_context_matrix.py`; `scripts/minimal_smoke.py`; `System_Manual.md` | synthetic fixture 和 smoke 已覆盖；真实复杂样本复核仍可作为 dogfooding 观察，不阻塞下一切片 | Done | 后续真实项目只读复核只记录观察，不新增规则 |
| Workstream lifecycle | Done / Cancelled 短期留 active 必须 keep-active，长期进入 archive | 已完成显式归档闭环 | `acf check` keep-active gate; `acf workstream archive-candidates`; `acf workstream archive-draft`; `acf workstream archive`; `Workstream_Lifecycle_Archive_Design.md`; `tests/fixtures/context_matrix/workstream_lifecycle_archive` | 无自动批量归档；真实项目使用后可再评估批量 apply 或更细 archive index sync | Done / P2 | 先 dogfood 单个显式 archive，不扩大为自动清理 |
| Authority gate | Workstream 不得通过 owned/assigned 直接写 authority path | 已实现 | `acf check --strict`; `tests/fixtures/context_matrix/authority_gate`; `tests/test_context_matrix.py` | 仅内置 authority map；可配置 map 明确后置 | Done | 保持内置清单，避免配置复杂化 |
| Merge contract | ReadyToMerge 需要合并请求；Done 需要 evidence + merge_resolution | 已实现 | `acf workstream merge-request/ready/done`; strict check; `Workstream_Design.md` | 无明显缺口 | Done | 后续只补归档生命周期 |
| Workstream sync | sync 只更新 `active/Workstreams.md`，不改详情、不删除缺详情旧行 | 已实现 | `acf workstream sync`; `tests/test_context_matrix.py`; `System_Manual.md` | 只覆盖 Workstream；其他索引 sync 尚未设计 | Done / P2 | 不扩展到 Knowledge/ADR/Archive，除非先设计 marker |
| Placeholder / marker convention | 模板占位符和机器维护块必须可统一识别、兼容旧格式 | 已实现 | ACF-keyed template placeholder form; `ACF:<DOMAIN>:<PURPOSE>` marker; `acf check template` warning; legacy marker compatibility | 未做批量替换命令；当前无需独立 CLI | Done / P2 | 保持 template 迁移和旧格式 warning，不让真实项目 strict 承担格式迁移 |
| strict check | 低误报、机械裁决、跨项目可解释 | 已实现，持续扩展 | `acf check --strict`; `tests/test_cli.py`; `tests/test_context_matrix.py`; `scripts/upgrade_matrix.py` | 新规则必须补 fixture；不应把 audit heuristic 升级为 strict | Done | 作为后续 PR gate |
| audit context | 只读 candidates，不写文件，不接入 strict | 已实现 MVP | `acf audit context`; `Context_Audit_Design.md`; tests for clean/long/stale/terminal candidates | high-risk rules 暂缓；阈值和 message 仍需 dogfooding | P2 | 暂不扩展 duplicate/evidence/volatile |
| review stale / curate draft | stale 只读，curate draft 只生成可审阅草案 | 已实现 | `acf review stale`; `acf curate draft`; `tests/test_cli.py`; `upgrade_matrix` | curate draft 后续可更丰富，但不应自动 apply | P2 | 等 gap 更明确后再扩 |
| draft | writeback / curate / knowledge 草案不进入默认读取路径 | 已实现 | `acf writeback draft`; `acf curate draft`; `acf knowledge draft`; `AGENTS.md` | 无 | Done | 保持草案边界 |
| upgrade | 非破坏式补结构，不改事实，不自动归档 | 已实现当前 P1 兼容矩阵 | `acf upgrade`; `scripts/upgrade_matrix.py`; `tests/fixtures/upgrade_matrix/*`; `tests/test_upgrade_matrix.py` | 已覆盖 old without Workstreams、old Workstreams without current_stage、old ADR without front matter、custom AGENTS + missing reference combo；后续新对象层仍需随功能增量补 fixture | Done | 新增结构时同步扩 upgrade matrix |
| JSON contract | AI-facing 命令稳定 `schema_version/ok/command/next_actions`，失败有 `error_code/message` | 已实现基础契约测试 | `tests/test_cli.py#test_ai_facing_success_json_contracts`; `tests/test_cli.py#test_ai_facing_failure_json_contracts`; `acf.py` | 仍不是全命令同形重排；后续新增 AI-facing 命令必须复用 contract helper | Done | 新命令新增时补契约测试 |
| error_code recovery | 常见失败路径有稳定 error_code 和 next_actions | 已实现基础契约测试 | JSON contract failure tests; workstream stage errors; check/status input errors | 不是完整 error catalog；安全拒绝仍可保留通用 `safety_refused` | Done / P2 | 如做 error catalog，单独设计 |
| context_matrix | minimal/legacy/audit/workstream/authority 防过拟合 fixture | 部分实现 | `tests/fixtures/context_matrix/*`; `tests/test_context_matrix.py` | `task_stage_registry`、`workstream_stage_flow` 和 `workstream_lifecycle_archive` 已补；audit stale / terminal merge 仍只有单元测试，缺独立 fixture | P2 | 下一代码切片优先补 `audit_stale_stage` 和 `audit_terminal_merge` fixtures |
| minimal smoke | 快速覆盖 init/status/check/worklog/workstream/task-stage 主路径 | 已实现当前 P2 范围 | `scripts/minimal_smoke.py` 包含 Workstream stage add/focus/done、workstream sync dry-run no-op、audit context clean、archive-candidates / archive-draft / archive 主路径，以及 Task Stage add/list/done | 仍是 release smoke，不替代全量单元/fixture 测试 | Done | 保持轻量 |
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
13. 统一模板占位符和 canonical ACF marker，兼容旧 marker 并给出 future warning。
14. `upgrade` 非破坏式结构补齐主路径。
15. context_matrix 和 upgrade_matrix 基础设施。

### 部分实现

1. sync：Workstream 已实现，Knowledge/ADR/Archive sync 仍需先设计 marker。

### 未实现但可后置

1. Knowledge / Decisions / Archive sync。
2. 更强 curation draft。

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

状态：已完成。实现见 `tests/test_cli.py` 的 AI-facing success/failure JSON contract tests；`check/status --json` 失败 payload 已补 `message`，版本 bump 到 `v0.0.3.28`。

### P1-2 Workstream stage flow fixture

理由：命令已实现，但顶层设计要求多项目 / synthetic 防过拟合。当前缺独立 context_matrix fixture 表达完整 stage flow。

建议范围：

1. 新增 `tests/fixtures/context_matrix/workstream_stage_flow`。
2. 覆盖 stage add/list/focus/done、focus 多 Active 拒绝、done evidence 和 clear-current。
3. minimal smoke 可补 audit clean 和 sync dry-run no-op。

验收：

1. `tests/test_context_matrix.py` 覆盖该 fixture。
2. `uv run python scripts/minimal_smoke.py --acf uv run acf` 覆盖 stage flow、sync 和 clean audit。

状态：已完成。新增 `tests/fixtures/context_matrix/workstream_stage_flow`，`tests/test_context_matrix.py` 覆盖 stage add/list/focus/done、dependency blocked、multi Active conflict、missing evidence、clear-current required、strict check、sync no-op 和 audit clean；`scripts/minimal_smoke.py` 已显式断言 sync dry-run no-op 与 audit candidates=[]。

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

状态：已完成。新增 `acf plan stage list/add/set/done`，只维护 `active/Task_Plan.md` 的 `## 任务阶段` 表；`add/set` 校验 stage ID 归属父任务、父任务存在、optional Workstream owner 存在；`done` 要求 evidence；未创建 task object 单文件，未自动修改 `Current_Task`，未联动 Workstream。新增 `tests/fixtures/context_matrix/task_stage_registry`、CLI 单元测试和 minimal smoke Task Stage 主路径。

### P2-2 Workstream lifecycle / archive helper

理由：keep-active gate 已有，但 Done / Cancelled 到 archive 的闭环仍靠人工。

前置条件：

1. archive/workstream lifecycle design。
2. fixture 证明不会误归档当前计划仍需解释的 Workstream。
3. 明确第一版是否只生成 draft，而不是移动文件。

状态：已完成设计与 fixture，并在 P2-3 落地只读 helper。新增 `reference/Workstream_Lifecycle_Archive_Design.md`，明确第一版先做 `workstream archive-candidates` 或 archive draft 这类只读/草案 helper，不直接移动文件；新增 `tests/fixtures/context_matrix/workstream_lifecycle_archive` 和 context_matrix 测试，覆盖 retained terminal Workstream strict clean、terminal Workstream 作为当前执行线被拒绝、expired keep-active 被 strict 拦截。

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

状态：已完成。`archive-draft` 写入 worklog/archive-drafts/YYYY-MM-DD dot md，包含 candidates + blocked、候选建议命令和 blocked suggested_action；默认不覆盖已有草案，支持 `--name`、`--force` 和 `--dry-run`。`archive` 复用候选 blocker，只允许 Done / Cancelled 单个 Workstream，移动详情到 `archive/workstreams/`，删除 active index 对应行并重算 Workstream 状态，追加 `archive/Archive_Index.md` 7 列记录和 `ACF:WORKSTREAM:ARCHIVE-RECORD` marker；不修改 merge target、Context、Current_Task 或 Task_Plan。已覆盖 CLI 单元测试、context_matrix draft-to-archive flow 和 minimal smoke。

### P2-6 Human layer, placeholder and marker modernization

状态：已完成。标准 profile 现在生成 `human/Human_Notes.md`、`human/weekly/` 和 `human/reports/`，用于人工异步笔记、周记录和汇报材料；minimal profile 不补 human 层。`upgrade` 只在推断为 standard profile 时非破坏式补齐 human 层，不把 human 内容自动升格为 active 事实，也不新增独立 human CLI。

Obsidian 边界已写入手册：项目可以把 `docs/` 作为 vault 根目录，`[[双链]]` 只服务人工查看和编辑；ACF 不解析、不校验、不依赖双链，结构化引用仍使用普通 Markdown 路径。模板占位符已迁移为 ACF-keyed placeholder form，表格单元格使用无提示形式；机器维护块统一为 `ACF:<DOMAIN>:<PURPOSE>` marker，旧 `ACF:UPGRADE-NOTES` 和 `ACF:WORKSTREAM-ARCHIVE` 兼容识别并给出 future warning。

### P2-5 Context matrix audit fixture expansion

推荐作为下一代码切片。

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
3. `uv run python scripts/minimal_smoke.py` 不需要扩大，除非 fixture 暴露了现有 smoke 缺口。

### P2 Active-reference traceability

```bash
acf plan reference add docs/ai --path reference/Product_Roadmap.md --purpose "阶段路线和近期优先级"
acf plan reference list docs/ai --json
```

状态：模板 / upgrade / 生成逻辑已补齐，并已完成稳定化补测。`active/Task_Plan.md` 现在有稳定 `## 规划依据` 小节；`task start` 会把有效 reference bullets 带入 `active/Current_Task.md` 的 `## 输入材料`；`upgrade` 会给旧计划非破坏式补结构，并给 Active 当前任务追加查看计划依据的提示；`plan reference list|add|remove` 可确定性维护路径和一句话用途，支持 `--allow-missing`、`--force`、`--missing-ok` 和显式 `--sync-current-task`。

稳定化覆盖：`old_active_reference_traceability` upgrade matrix fixture 覆盖旧 `active/Task_Plan.md` / Active `active/Current_Task.md` 的非破坏式补齐；CLI 边界测试覆盖 dry-run sync、不标准 Current_Task 引用保守跳过、模板占位符不继承、`--missing-ok` 幂等，以及 `task start` 不生成嵌套 bullet。EcSOS dry-run 验证为 clean / status ok，升级会补 `active/Task_Plan.md` 和 `active/Current_Task.md` 追溯结构，同时刷新旧 schema 文档；FCC dry-run 验证为 clean / status ok，升级会补 `active/Task_Plan.md`，并因旧 `active/Current_Task.md` 缺少 `## 输入材料` 给出预期保守 warning。

后续可能增强：`acf plan init --reference`、`acf plan reference check`、`acf check` 对规划依据断链给 warning、或统一占位符批量替换命令。本轮不把 reference 存在性接入 `check`，避免旧项目和模板占位符产生迁移噪声。

### Deferred audit rules

继续暂缓：

1. `duplicate_active_fact_candidate`
2. `strong_claim_without_evidence`
3. `volatile_fact_in_wrong_authority_location`

进入条件仍是多 fixture、多项目观察和只读 candidate。

---

## Next Code PR Decision

下一批代码 PR 不应是新增 audit 规则，也不应直接扩 Knowledge / ADR / Archive sync。

推荐下一 PR：

```text
P2-5 Context matrix audit fixture expansion
```

原因：

1. 当前路线已完成 JSON contract、Workstream stage、upgrade matrix、Task Stage CLI、active-reference traceability 和 Workstream archive 闭环。
2. 剩余最小确定缺口是 audit MVP 缺少 `audit_stale_stage` / `audit_terminal_merge` 的 context_matrix fixture。
3. 该 PR 只加 fixture 和测试，不改变 CLI 输出语义，不扩大 strict，不做事实裁决。
4. 它为后续 audit message 调优或 curation draft 增强提供低噪声样本。

拒绝的替代：

| 替代 | 暂不选择原因 |
|---|---|
| 直接扩 high-risk audit rules | 误报风险高，违反当前路线。 |
| 直接做 Knowledge / ADR / Archive sync | 需要先设计 generated marker、事实源边界和删除策略。 |
| 扩 curation draft 语义能力 | 需要先有更多 audit fixture 和多项目样本，避免草案噪声。 |
| 做自动 Context merge | 明确非目标。 |

---

## Verification Plan

本 gap audit 文档阶段只需要：

```bash
uv run acf check docs/ai --strict --json
uv run acf audit context docs/ai --json
```

不需要运行完整 unittest，因为本轮不改 CLI 代码、不改模板行为、不改变 JSON 输出。

如果下一阶段进入 P2-5 fixture expansion，则需要运行：

```bash
uv run python -m unittest
uv run acf check docs/ai --strict --json
uv run python scripts/minimal_smoke.py
```

---

## 结论

ACF 继续保持受控实施阶段，但下一步应补 audit fixture 矩阵，而不是继续扩 audit 规则或直接实现新 sync。

推荐顺序：

1. P2-5：context_matrix audit fixture expansion。
2. Generated marker design for Knowledge / ADR / Archive sync。
3. Curation draft enhancement，必须基于 P2-5 fixture 和多项目观察。
4. high-risk audit rules 继续暂缓。

当前进度：P1-1、P1-2、P1-3、P2-1、P2-2、P2-3、P2-4、P2-6 与 active-reference traceability 已完成；下一入口仍是 P2-5 audit fixture expansion，除非 human layer dogfooding 暴露新的通用结构缺口。
