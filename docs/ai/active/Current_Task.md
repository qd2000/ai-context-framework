本文件记录当前正在处理的具体任务。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前阶段目标请查看：`active/Context.md`
- 当前大任务计划请查看：`active/Task_Plan.md`
- 本文件只维护当前具体任务

如果用户在当前对话中提出了新的具体需求，并且该需求与本文件冲突，以用户当前消息为准。

---

## 当前任务状态

Done

---

## 任务名称

Write general product roadmap and validation matrix

---

## 所属大任务

P2 generalization plan

---

## 子任务 ID

T001

---

## 当前执行线

无。

---

## 本次任务目标

1. 新增通用产品路线文档，明确 ACF 不能按单一 FCC 样本持续补规则。
2. 把 FCC 定位为压力测试样本，而不是产品需求唯一来源。
3. 定义真实项目反馈进入 ACF 的准入门槛。
4. 定义多项目验证矩阵，防止后续规则过拟合。
5. 本轮只写文档，不改代码。

---

## 任务背景

P0 governance hardening 和 P1 audit context MVP 已完成，FCC dogfooding 已证明工具能发现真实复杂项目的上下文治理信号。下一步不应继续围绕 FCC 扩规则，而应先把通用产品路线和验证矩阵固化，确保后续能力来自可迁移的上下文治理问题。

---

## 输入材料

- `reference/Project_Brief.md`
- `../Automation.md`
- `reference/Context_Audit_Design.md`
- `reference/Workstream_Design.md`
- `active/Task_Plan.md`

---

## 输出要求

1. 新增 `reference/Product_Roadmap.md`。
2. 在 `../Automation.md` 中挂接通用产品路线。
3. 在 `reference/Project_Brief.md` 中补充 Product Roadmap 入口。
4. 更新 Task_Plan / Current_Task / worklog。
5. 不修改 `acf.py` 或测试。

---

## 成功标准

1. Product Roadmap 明确通用化原则、反馈准入门槛、四层推进模型、多项目验证矩阵和非目标。
2. 文档明确：FCC 是压力测试样本，不是唯一需求来源。
3. 文档明确：新规则必须可抽象、可机械检测、可测试、可兼容。
4. `uv run acf check docs/ai --strict --json` 通过。
5. `uv run acf status docs/ai --json` 通过。

完成证据：

- `reference/Product_Roadmap.md`
- `../Automation.md`
- `reference/Project_Brief.md`
- `worklog/daily/2026-05-07.md`
- `uv run acf check docs/ai --strict --json`
- `uv run acf status docs/ai --json`

---

## 失败信号

1. 本轮开始实现新 audit rule。
2. 本轮把 FCC 业务细节写成 ACF 产品规则。
3. 本轮修改 FCC 内容。
4. Product Roadmap 只复述当前功能，没有给出后续准入门槛。

---

## 约束条件

1. 只做文档规划。
2. 不新增运行依赖。
3. 不修改 CLI 行为。
4. 不读取或修改 FCC 内容。

---

## 不允许做的事

- 不改 `acf.py`。
- 不新增测试。
- 不实现 duplicate / evidence / volatile audit rules。
- 不把启发式 audit 接入 strict。

---

## 需要 AI 协助判断的问题

1. 什么情况下真实项目反馈可以进入 ACF。
2. strict / audit / sync / draft / upgrade 的边界如何作为后续设计门槛。
3. 多项目验证矩阵应覆盖哪些样本。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. Product Roadmap 的核心原则。
2. 后续候选任务：P2 Test Matrix Expansion，而不是继续 FCC-driven audit rule 扩展。
