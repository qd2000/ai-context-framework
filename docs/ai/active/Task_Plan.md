本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Active

---

## 大任务名称

P2 Workstream Task Flow

---

## 大任务目标

1. 补齐 Workstream 内部阶段的任务管理闭环，让阶段可机械新增、查询、聚焦、完成和后续评估是否同步 Current_Task。
2. 保持 Workstream 仍是可选并行目标线，不扩展为 runtime、权限系统或复杂调度器。
3. 以详情文件 active/workstreams/WS*.md 为阶段事实源，并保持 current_stage、## 阶段表、Workstreams 索引和 strict check 一致。

---

## 成功标准

1. T001 先产出 workstream stage/focus 命令契约设计，覆盖通用治理问题、分层、fixture、兼容性和 next_actions。
2. PR 1 仅实现 workstream stage add/list：只修改目标详情文件，拒绝重复 ID 和跨 WS 阶段 ID，不改 Current_Task 或 Context。
3. PR 2 实现 workstream focus：current_stage 必须存在且非 Done/Cancelled/Skipped，同一 WS 不能多个 Active，依赖未 Done 默认拒绝。
4. PR 3 实现 workstream stage done：Done 阶段必须写 evidence，完成 current_stage 时第一版清空 current_stage，不自动激活下一阶段。
5. PR 4 仅评估 --update-current-task 同步选项，默认不触碰全局 Current_Task。
6. 每个实现 PR 后运行 uv run acf check template、uv run acf check docs/ai --strict --json 和 uv run python -m unittest。

---

## 当前焦点

T001

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Active | Design workstream stage/focus command contract | Product Roadmap 要求新能力先确认通用上下文治理问题、分层、fixture、兼容性和 next_actions | Workstream stage/focus CLI 设计契约，覆盖 PR1-PR4 边界、状态规则、检查规则和验收 fixture | 无。 | 先写设计文档，不实现代码 |
| T002 | Pending | Implement workstream stage add/list | T001 | acf workstream stage add/list；只修改目标 workstream 详情文件；新增阶段行；重复 ID 和跨 WS ID 拒绝 | 无。 | 为 stage 表读写、ID 归属和 JSON 输出补 fixture 与测试 |
| T003 | Pending | Implement workstream focus | T002 | acf workstream focus；更新 current_stage 和阶段 Active 状态；拒绝缺失、终态、多 Active 和依赖未 Done | 无。 | 实现前先锁定 strict check 对 current_stage/Active/depends 的一致性规则 |
| T004 | Pending | Implement workstream stage done | T003 | acf workstream stage done；Done 必须有 evidence；current_stage 完成后第一版清空，要求用户显式 focus 下一阶段 | 无。 | 实现 Done/evidence/current_stage strict fail 与 --clear-current 行为 |
| T005 | Pending | Evaluate Current_Task sync option | T002,T003,T004 | 评估 workstream focus --update-current-task 是否进入后续 PR；只同步 Current_Task 的当前执行线和当前阶段 section | 无。 | 前三个命令稳定后再决定是否设计/实现全局入口同步 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
