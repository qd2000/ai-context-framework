# Product Roadmap

本文记录 ACF 的通用产品路线和验证原则。它用于防止真实项目 dogfooding 反馈被直接写成项目专用规则，并指导后续薄切片开发。

---

## 状态

Active

---

## 一句话路线

ACF 应先定义通用上下文治理契约，每次实现一个可验证的通用薄切片，再用 ACF 自身、FCC、minimal、legacy、synthetic fixtures 和其他非 PetroSim 项目共同验证，避免把单个项目特例产品化。

---

## 通用化原则

1. FCC 是压力测试样本，不是产品需求唯一来源。
2. 从 FCC 或任何真实项目暴露的问题进入 ACF 前，必须先抽象成通用上下文治理问题。
3. 新规则必须能用 fixture 或最小上下文写成确定性测试，不得只靠真实项目样本证明。
4. 新规则不得让 minimal / legacy 项目产生额外默认负担。
5. 启发式规则先进入 audit candidate，不直接进入 strict。
6. strict 只接收低误报、可机械裁决、跨项目可解释的规则。
7. 新能力必须保持 Markdown-first、模型无关、无第三方运行依赖、人工可审阅。
8. 真实项目反馈应先进入设计文档、worklog 或 fixtures，再决定是否产品化。

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

---

## 四层推进模型

### 1. 通用文档组织规范

稳定以下分层，不依赖 FCC：

```text
active/
  Context.md
  Task_Plan.md
  Current_Task.md
  Workstreams.md
  workstreams/*.md
rules/
reference/
decisions/
worklog/
archive/
```

本层回答：

1. 什么内容放 active。
2. 什么内容放 reference。
3. 什么内容放 worklog。
4. 什么内容必须归档。
5. 什么是唯一事实源。
6. 什么只是索引或 generated view。

### 2. 通用对象模型

不把全仓库改成固定 schema，只对状态型对象逐步定义机器字段：

```text
Task
Task Stage
Workstream
Workstream Stage
ADR
Knowledge
Archive item
```

对象字段应围绕通用治理关系，而不是项目业务字段：

```text
ID
status
owner / source
dependencies
evidence
merge state
updated / reviewed
```

### 3. 通用 CLI 能力

CLI 围绕通用上下文操作，不围绕 FCC 操作：

```bash
acf check --strict
acf status --json
acf workstream sync --dry-run --json
acf audit context --json
acf task ...
acf plan ...
acf archive ...
acf knowledge ...
```

能力分层：

1. `check --strict`：低误报、可机械裁决的硬门禁。
2. `audit context`：只读候选发现，不裁决事实，不写文件。
3. `sync`：只更新 generated / index view，不改详情事实。
4. `upgrade`：非破坏式补齐结构，不自动升格事实。
5. `draft`：生成可审阅草案，不静默修改权威上下文。

### 4. 多项目验证矩阵

后续验证至少覆盖：

| 样本 | 作用 | 进入规则 |
|---|---|---|
| ACF 自身 | 中等复杂 dogfooding，验证产品自洽 | 每个阶段默认检查 |
| FCC | 超复杂真实工程压力测试 | 只读优先；反馈必须抽象后进入 ACF |
| minimal project | 验证空白/小项目不增加负担 | init/status/check/audit 必须低噪声 |
| legacy project | 验证 upgrade 兼容 | 升级不破坏旧正文，不强制新对象 |
| synthetic fixtures | 验证边界和误伤 | 新规则必须优先补 fixture / unit test |
| non PetroSim project | 防止领域过拟合 | 论文、工具库、Web 项目或数据项目至少选一类 |

---

## 当前已完成的通用薄切片

P0 governance hardening：

1. Task Stage registry。
2. Workstream Stage Focus。
3. Authority write gate + `merge_targets`。
4. Merge resolution + active retention gate。
5. Workstream index consistency check + sync。

P1 audit context MVP：

1. 只读 `acf audit context [path] --json`。
2. `active_section_too_long`。
3. `stale_current_task_or_workstream_stage`。
4. `terminal_conclusion_not_merged`。
5. 候选输出保持 advisory，不进入 strict。

这些能力来自真实 dogfooding 压力，但已经抽象为通用上下文治理规则。

---

## 下一阶段建议

### P2 Generalization Plan

目标：先稳定产品路线和验证矩阵，不继续追加 FCC-driven 规则。

任务：

1. 明确真实项目反馈进入 ACF 的准入门槛。
2. 把多项目验证矩阵写入产品路线。
3. 评估现有 fixtures 是否覆盖 minimal / legacy / complex workstream / audit long section / authority gate。
4. 决定是否需要新增一个非 PetroSim 真实项目样本。

### P2 Test Matrix Expansion

目标：先补测试样本，再考虑新增 audit 规则。

候选 fixture：

```text
minimal_clean
legacy_old_context
workstream_complex
audit_long_section
authority_gate
```

### P3 Audit Rule Expansion

只有在多项目和 fixture 样本稳定后，再评估以下高误报规则：

1. `duplicate_active_fact_candidate`
2. `strong_claim_without_evidence`
3. `volatile_fact_in_wrong_authority_location`

这些规则第一版仍应只输出 audit candidates，不进入默认 strict。

---

## 非目标

1. 不把 FCC 业务规则写入 ACF。
2. 不为了单个真实项目新增专用 path、命令或 schema 字段。
3. 不闭门一次性开发完整 Object Graph。
4. 不在没有 fixture / 单元测试前新增 strict rule。
5. 不把启发式 audit 规则直接升级为 strict。
6. 不引入数据库、向量库、常驻 agent runtime 或自动事实裁决。

---

## 决策口径

后续新增能力时，先回答：

1. 这是通用上下文治理问题，还是某个项目的业务事实？
2. strict / audit / sync / draft / upgrade 中哪一层最合适？
3. 最小 fixture 怎么构造？
4. minimal 和 legacy 项目会不会被迫承担新负担？
5. `reason`、`error_code` 和 `next_actions` 是否足够让 AI 后续处理？
6. 是否有至少一个非 FCC 场景也能解释这条规则？

只有这些问题有清晰答案，才进入实现。
