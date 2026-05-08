本文件记录当前正在处理的具体任务。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前阶段目标请查看：`active/Context.md`
- 本文件只维护当前具体任务

如果用户在当前对话中提出了新的具体需求，并且该需求与本文件冲突，以用户当前消息为准。

---

## 当前任务状态

Done

---

## 任务名称

Verify and record route calibration

---

## 所属大任务

P2-5 Gap Audit Refresh and Next Slice Selection

---

## 子任务 ID

T003

---

## 当前执行线

无。

---

## 本次任务目标

1. Run docs checks, audit context, and commit docs-only calibration
2. 产出并验证输出物：Clean checks, worklog entry, and committed route calibration

---

## 任务背景

该任务来自 `active/Task_Plan.md` 中的子任务 T003，所属大任务为“P2-5 Gap Audit Refresh and Next Slice Selection”。依赖记录：T002

---

## 输入材料

当前任务应列出必要 active 文件和相关 reference 规划依据；不要只写 `active/Context.md`。

- `active/Task_Plan.md`。
- `active/Context.md`。
- `reference/ACF_Top_Level_Design.md`：上位架构、边界和非目标。
- `reference/Top_Level_Implementation_Gap.md`：当前实现差距矩阵和候选切片依据。
- `reference/System_Manual.md`：dogfooding 维护命令和上下文治理规则。
- `reference/Product_Roadmap.md`：近期优先级和下一批候选任务。
- 依赖 T002 证据：Updated Product_Roadmap.md to recommend P2-5 context_matrix audit fixture expansion before generated sync design or curation draft enhancement.

---

## 输出要求

- Clean checks, worklog entry, and committed route calibration

---

## 成功标准

1. 输出物已完成：Clean checks, worklog entry, and committed route calibration
2. 子任务 T003 的完成证据已写回任务板。
3. `acf plan status` 能显示任务板可继续推进。

---

## 失败信号

1. 依赖任务未完成或证据不足。
2. 输出物无法通过检查或人工复核验证。
3. 执行中发现用户当前需求与任务板记录冲突。

---

## 约束条件

1. 遵守当前项目规则和默认读取顺序。
2. 保持 `active/Task_Plan.md` 与 `active/Current_Task.md` 状态同步。
3. 不要把一次性过程或当前事实直接写入 Knowledge。

---

## 不允许做的事

- 无。

---

## 需要 AI 协助判断的问题

1. 执行过程中是否发现应回写 Context、ADR、rules、Knowledge 或 archive 的内容？

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应写入 `reference/Knowledge_Index.md` 或 Knowledge 条目的可复用经验。
5. 应归档到 archive 的历史内容。
