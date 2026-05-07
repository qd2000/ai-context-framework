# Product Roadmap

本文记录 ACF 的阶段路线、准入门槛和近期实施顺序。顶层产品设计以 `reference/ACF_Top_Level_Design.md` 为准；本文件负责把顶层设计拆成可执行阶段，防止真实项目 dogfooding 反馈被直接写成项目专用规则。

---

## 状态

Active

---

## 一句话路线

ACF 应先收敛通用上下文治理蓝图，再按薄切片实现可验证能力，并用 ACF 自身、FCC、EcSOS、minimal、legacy、synthetic fixtures 和其他非 PetroSim 项目共同验证，避免把单个项目特例产品化。

---

## 路线总原则

1. 顶层设计先行：新增对象、规则或命令前，先确认它符合 `ACF_Top_Level_Design.md` 的定位、非目标和 CLI 分层。
2. FCC 是压力测试样本，不是产品需求唯一来源。
3. 从 FCC、EcSOS 或任何真实项目暴露的问题进入 ACF 前，必须先抽象成通用上下文治理问题。
4. 新规则必须能用 fixture、最小上下文或单元测试复现，不得只靠真实项目样本证明。
5. 新规则不得让 minimal / legacy 项目产生额外默认负担。
6. 启发式规则先进入 audit candidate，不直接进入 strict。
7. strict 只接收低误报、可机械裁决、跨项目可解释的规则。
8. 新能力必须保持 Markdown-first、模型无关、无第三方运行依赖、人工可审阅。
9. 真实项目反馈应先进入设计文档、worklog 或 fixtures，再决定是否产品化。
10. 不继续零散加规则；每个能力都必须落到明确阶段和分层。

---

## 反馈准入门槛

真实项目暴露的问题只有同时满足以下条件，才可以进入 ACF 产品规则或 CLI 能力：

1. 可抽象：能表述为通用上下文治理问题，而不是项目业务知识。
2. 可机械检测：能用路径、metadata、状态、引用、表格、heading、日期或稳定文本结构检测。
3. 可测试：能构造 fixture 或单元测试复现。
4. 可兼容：不会破坏旧上下文、minimal 项目或没有对应对象层的项目。
5. 可解释：候选或错误的 `reason` / `next_actions` 能让 AI 或人知道下一步。
6. 可降级：语义不确定时作为 audit candidate，而不是 strict error。
7. 可拒绝：如果只是单个项目的业务过程、临时文件布局或模型输出习惯，应保留在项目上下文，不写进 ACF。
8. 可分层：明确属于 `check`、`audit`、`sync`、`draft`、`upgrade` 或普通维护命令。
9. 可验证：至少有一个 synthetic fixture、一个 minimal 或 legacy 不误伤测试、一个真实项目 dogfooding 观察。

---

## 产品分层路线

### 1. 顶层治理契约

目标：稳定 ACF 的产品边界、内容分层、权威事实模型、对象模型和 CLI 分层。

权威文档：

1. `reference/ACF_Top_Level_Design.md`
2. `reference/Product_Roadmap.md`
3. `reference/Architecture.md`
4. `reference/System_Manual.md`

验收：

1. 新规则能明确说明属于哪一层。
2. 新对象能明确说明事实源、索引关系和兼容策略。
3. 新命令能明确说明是否写权威上下文、是否支持 dry-run、是否触发 check-after。

### 2. 内容组织规范

目标：稳定 `active/`、`reference/`、`worklog/`、`archive/`、`rules/` 和 `decisions/` 的职责边界。

关键规则：

1. `active/` 只放当前目标、当前事实、当前任务、当前任务板、当前 Workstream 和待处理 feedback。
2. `reference/` 放长期稳定背景、设计、索引和手册。
3. `worklog/` 放历史过程摘要，不是当前事实源。
4. `archive/` 放旧任务、旧计划、旧 Workstream 和已处理反馈，默认不读。
5. `rules/` 放当前项目约束，不夹带一次性任务计划。
6. `decisions/` 放稳定 ADR，不保存冗长过程。

### 3. 轻量对象模型

目标：只对状态型对象逐步定义机器字段，不把全仓库改成强 schema。

对象清单：

1. Task。
2. Task Stage。
3. Workstream。
4. Workstream Stage。
5. ADR。
6. Knowledge。
7. Archive item。

当前策略：

1. Task 和 Task Stage 继续使用 `active/Task_Plan.md` 中的 Markdown table。
2. Workstream 使用详情文件 front matter + 正文 section。
3. Workstream Stage 使用详情文件 `## 阶段` 表。
4. ADR、Knowledge 和 Archive 继续通过索引 + 详情或草案维护。
5. 不急于把 Task 全部拆成单文件对象。

### 4. CLI 分层

目标：让 CLI 只做确定性维护，不做语义事实裁决。

固定分层：

| 层 | 用途 | 写文件 | 典型命令 |
|---|---|---|---|
| `check --strict` | 低误报硬门禁 | 否 | `acf check --strict --json` |
| `audit context` | 只读候选发现 | 否 | `acf audit context --json` |
| `sync` | 同步 generated / index view | 是，只改索引 | `acf workstream sync --dry-run --json` |
| `upgrade` | 非破坏式补结构 | 是，结构补齐 | `acf upgrade --dry-run --json` |
| `draft` | 生成可审阅草案 | 是，只写草案 | `acf writeback draft` |
| 普通维护命令 | 确定性结构落盘 | 是 | `plan`、`task`、`archive`、`knowledge`、`new`、`edit` |

新增 CLI 必须明确：

1. 是否写权威上下文。
2. 是否支持 `--json`。
3. 是否支持 `--dry-run`。
4. 是否支持 `--check-after`。
5. 失败 `error_code` 和 `next_actions` 是什么。
6. 是否改变 upgrade、template 或 JSON 契约。

### 5. 多项目验证矩阵

目标：防止过拟合 FCC 或任何单一真实项目。

| 样本 | 作用 | 当前要求 |
|---|---|---|
| ACF 自身 | 产品自洽、中等复杂 dogfooding | 每个阶段默认检查 |
| FCC | 超复杂真实工程压力测试 | 只读优先，反馈必须抽象 |
| EcSOS | 非 PetroSim、论文 / 数据分析 / Python 工具项目 | 验证 upgrade、stale、audit 低噪声 |
| minimal project | 验证小项目不增加负担 | init/status/check/audit clean |
| legacy project | 验证旧项目升级兼容 | upgrade 不破坏旧正文 |
| synthetic fixtures | 验证边界和误伤 | 新规则必须优先补 fixture / unit test |
| non PetroSim project | 防止领域过拟合 | 高误报 audit 前必须覆盖 |

---

## 当前已完成的通用薄切片

### P0 governance hardening

已完成：

1. Task Stage registry。
2. Workstream Stage Focus。
3. Authority write gate + `merge_targets`。
4. Merge resolution + active retention gate。
5. Workstream index consistency check + sync。

这些能力来自真实 dogfooding 压力，但已经抽象为通用上下文治理规则。

### P1 audit context MVP

已完成：

1. 只读 `acf audit context [path] --json`。
2. `active_section_too_long`。
3. `stale_current_task_or_workstream_stage`。
4. `terminal_conclusion_not_merged`。
5. 候选输出保持 advisory，不进入 strict。

暂缓：

1. `duplicate_active_fact_candidate`。
2. `strong_claim_without_evidence`。
3. `volatile_fact_in_wrong_authority_location`。

### P2 Workstream Task Flow

已完成：

1. `acf workstream stage add`。
2. `acf workstream stage list`。
3. `acf workstream focus`。
4. `acf workstream stage done`。
5. `--update-current-task` 评估后继续后置，不进入默认行为。

稳定边界：

1. stage 命令只维护 Workstream 详情文件。
2. focus 只更新 `current_stage` 和目标阶段状态。
3. stage done 要求 evidence，完成当前阶段时要求 `--clear-current`。
4. 不自动激活下一阶段。
5. 不自动修改 `active/Current_Task.md`。
6. 不自动合并 Context。

---

## 分阶段路线图

### Phase A：顶层设计收敛

状态：当前优先阶段。

目标：

1. 把顶层需求沉淀为正式设计蓝图。
2. 对齐 Product Roadmap、Workstream Design、Context Audit Design、Upgrade Migration Plan 和 System Manual。
3. 明确 strict/audit/sync/draft/upgrade 职责。
4. 明确所有新增规则的通用化准入门槛。

产物：

1. `reference/ACF_Top_Level_Design.md`。
2. 更新后的 `reference/Product_Roadmap.md`。
3. `reference/Sources_Index.md` 中的索引记录。
4. 必要时更新 `../Automation.md` 和 `reference/System_Manual.md` 的引用。

验收：

1. `uv run acf check docs/ai --strict --json` 通过。
2. `uv run acf audit context docs/ai --json` 可运行。
3. 新设计不改变 CLI 行为，不需要 bump version。

### Phase B：Workstream Task Flow 收口

状态：主命令闭环已完成，后续进入稳定化和 fixture 扩展。

目标：

1. Workstream 内部阶段可注册、查询、聚焦、完成。
2. Workstream 仍保持 optional，不变成 runtime。
3. `active/Current_Task.md` 同步继续后置。

产物：

1. `acf workstream stage add/list/done`。
2. `acf workstream focus`。
3. `context_matrix/workstream_complex`。
4. minimal smoke 覆盖 stage/focus/done/sync。

验收：

```bash
uv run acf check template --json
uv run acf check docs/ai --strict --json
uv run python -m unittest
uv run python scripts/minimal_smoke.py --acf uv run acf
```

### Phase C：对象模型补齐

状态：后续阶段。

目标：

1. 统一 Task、Task Stage、Workstream、Workstream Stage、ADR、Knowledge、Archive item 的字段口径。
2. 明确哪些对象用 front matter，哪些继续用 table。
3. 明确哪些索引是 derived view，哪些是事实源。

产物：

1. metadata schema 文档。
2. table schema 文档。
3. check rule matrix。
4. fixture：`task_stage_registry`、`workstream_stage_flow`、`old_adr_without_front_matter`。

不做：

1. 不急于 `active/tasks/T001` 单文件化。
2. 不全量改造叙述型 reference 文档。
3. 不引入第三方 YAML parser。

### Phase D：Audit 稳定化

状态：MVP 已实现，后续先调优再扩展。

目标：

1. 让 audit candidates 低噪声、可行动。
2. 稳定 candidate JSON 输出。
3. 明确每条 candidate 的 reason 和 suggested_action。

先做：

1. `active_section_too_long` 阈值和 wrapper 逻辑继续观察。
2. `stale_current_task_or_workstream_stage` message 调优。
3. `terminal_conclusion_not_merged` 与 strict merge_resolution 规则保持边界清楚。

再考虑：

1. duplicate。
2. evidence。
3. volatile。

进入条件：

1. 至少 3 个 synthetic fixtures。
2. 至少 2 类真实项目样本观察。
3. minimal / legacy 不误伤。
4. 只输出 candidate，不进入 strict。

### Phase E：Upgrade / Sync 扩展

状态：后续阶段。

目标：

1. 旧项目可以安全进入新结构。
2. 索引可以由详情派生，但不误删旧人工内容。
3. sync 行为有 generated block marker 和删除策略。

产物：

1. 更多 upgrade fixture。
2. archive/workstream lifecycle design。
3. generated block marker design。
4. `upgrade_matrix` full 模式扩展。

候选扩展：

1. `acf knowledge sync`。
2. `acf decisions sync`。
3. `acf archive sync`。

限制：

1. 不在没有 marker 设计前自动覆盖索引全文。
2. 不自动删除缺详情的历史行。
3. 不自动升格事实。

### Phase F：多项目 dogfooding

状态：持续阶段。

目标：

1. 验证 ACF 不过拟合某个项目。
2. 用真实项目和 fixture 共同评估 check/audit/upgrade/sync 噪声。
3. 只把重复出现、可抽象、可测试的维护动作产品化。

样本：

1. ACF。
2. FCC。
3. EcSOS。
4. minimal。
5. legacy。
6. synthetic fixtures。
7. 再选一个非 PetroSim 项目。

输出：

1. dogfooding worklog。
2. fixture 增量。
3. audit candidate 质量复盘。
4. Product Roadmap 阶段调整。

---

## 近期优先级

### 现在不要做

1. 不继续零散追加 audit 规则。
2. 不把 FCC 的业务过程写成 ACF 专用规则。
3. 不新增 task object 单文件。
4. 不新增自动合并 Context 能力。
5. 不让 Workstream 变成调度器。
6. 不扩大 strict 到高误报语义判断。

### 当前最建议做

1. 使用 `reference/Top_Level_Implementation_Gap.md` 作为进入新代码 PR 前的 gap-driven 实施依据。
2. JSON contract consistency tests、Workstream stage flow fixture、upgrade matrix expansion 与 Task Stage CLI 薄切片已完成；下一批继续 gap-driven P2 评估。
3. 暂不扩展 high-risk audit rules，暂不做 Task object 单文件化，暂不做自动 Context merge。
4. 后续每个新能力先补 fixture，再实现命令或规则。

### 下一批候选任务

1. P1-1：JSON contract consistency tests。已完成。
2. P1-2：补 `tests/fixtures/context_matrix/workstream_stage_flow`，覆盖 stage add/focus/done 的上下文形态。已完成。
3. P1-2：扩展 `scripts/minimal_smoke.py`，纳入 workstream stage/focus/done/sync 和 clean audit。已完成。
4. P1-3：扩展 upgrade matrix，覆盖 Workstream/ADR/custom AGENTS 旧形态。已完成。
5. P2-1：实现 Task Stage CLI 薄切片。已完成：`acf plan stage list/add/set/done` 只维护 `active/Task_Plan.md` 的 `## 任务阶段` 表，不创建 task object 单文件，不自动修改 `Current_Task`，不联动 Workstream。
6. P2-2：设计 Workstream lifecycle / archive helper。候选。

---

## 决策口径

后续新增能力时，先回答：

1. 这是通用上下文治理问题，还是某个项目的业务事实？
2. 它落在哪一层：strict、audit、sync、draft、upgrade，还是普通维护命令？
3. 最小 fixture 怎么构造？
4. minimal 和 legacy 项目会不会被迫承担新负担？
5. `reason`、`error_code` 和 `next_actions` 是否足够让 AI 后续处理？
6. 是否有至少一个非 FCC 场景也能解释这条规则？
7. 是否需要同步 README、System Manual、Automation、template、upgrade matrix 或版本号？

只有这些问题有清晰答案，才进入实现。

---

## 最终路线总结

ACF 要成为一个 Markdown-first 的 AI 上下文治理框架。它通过轻量对象模型、确定性 strict check、只读 audit candidates、索引 sync、非破坏式 upgrade 和多项目验证矩阵，降低 AI 长期维护上下文时的漂移、重复、污染和人工复核成本；同时保持模型无关、人工可审阅、旧项目兼容、不自动裁决事实、不绑定 FCC 或任何单个项目。

实施顺序是：先顶层设计，再薄切片实现；每个规则都要 fixture；每个真实项目反馈都要通用化；每个启发式先 audit；每个确定性问题才 strict；每次新增 CLI 都要 JSON、dry-run、check-after、tests、docs 和 upgrade 评估。
