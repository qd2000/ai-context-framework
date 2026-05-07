本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、状态、证据入口和下一步，不记录长过程、完整日志或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P2 generalization plan

---

## 大任务目标

1. 把 ACF 下一阶段路线从 FCC-driven 调参切回通用产品路线。
2. 明确 FCC 是压力测试样本，不是产品需求唯一来源。
3. 定义真实项目反馈进入 ACF 的通用化准入门槛。
4. 建立多项目验证矩阵，为后续扩展 audit rules 或 object model 提供防过拟合约束。
5. 本阶段只写路线和验证策略，不新增 CLI 功能。

---

## 成功标准

1. `reference/Product_Roadmap.md` 记录通用化原则、反馈准入门槛、四层推进模型、多项目验证矩阵和非目标。
2. `../Automation.md` 指向通用产品路线，并明确真实项目反馈必须抽象后产品化。
3. `reference/Project_Brief.md` 的相关资料包含 Product Roadmap。
4. 本轮不修改 `acf.py` 或测试。
5. `uv run acf check docs/ai --strict --json` 通过。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Write general product roadmap and validation matrix | P1 audit context MVP dogfooding | 通用化原则、反馈准入门槛、四层推进模型、多项目验证矩阵 | `reference/Product_Roadmap.md`; `../Automation.md`; `reference/Project_Brief.md`; `worklog/daily/2026-05-07.md`; verification: `uv run acf check docs/ai --strict --json`, `uv run acf status docs/ai --json` | 无。 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 非目标

本阶段不做：

1. 不新增 audit candidate rule。
2. 不继续围绕 FCC 做专用调参。
3. 不修改 FCC 项目内容。
4. 不扩展 Object Graph 实现。
5. 不新增 CLI 命令。
6. 不把启发式 audit 接入 `check --strict`。

---

## 后续候选

1. P2 Test Matrix Expansion：补 minimal / legacy / complex workstream / audit long section / authority gate fixtures。
2. 选择一个非 PetroSim 真实项目作为验证样本。
3. 在验证矩阵稳定后，再评估 duplicate / evidence / volatile audit rules。

---

## 基线验证

本规划任务至少运行：

```bash
uv run acf check docs/ai --strict --json
uv run acf status docs/ai --json
```

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
