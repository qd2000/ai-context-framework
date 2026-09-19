本文件记录当前正在处理的具体任务。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前阶段目标请查看：`active/Context.md`
- 本文件只维护当前具体任务

如果用户在当前对话中提出了新的具体需求，并且该需求与本文件冲突，以用户当前消息为准。

---

## 当前任务状态

Active

说明：

- Active：当前任务正在进行
- Paused：当前任务暂停
- Done：当前任务已完成
- Empty：暂无需要写入文件的当前任务

---

## 任务名称

建立 WS016 与任务结构

---

## 所属大任务

WS016 Runtime 全局注入解耦

---

## 子任务 ID

T001

---

## 所属 Workstream

WS016

---

## 当前执行线

WS016 / T001 建立 WS016 与任务结构

---

## 本次任务目标

1. 进入 T002 allowlist 合并
2. 产出并验证输出物：WS016 详情、范围声明、Task_Plan 与 Current_Task

---

## 任务背景

该任务来自 `active/Task_Plan.md` 中的子任务 T001，所属大任务为“WS016 Runtime 全局注入解耦”。依赖记录：无明确依赖。

---

## 输入材料

当前任务应列出必要 active 文件和相关 reference 规划依据；不要只写 `active/Context.md`。

- `active/Task_Plan.md`。
- `active/Context.md`。
- [reference/Top_Level_Implementation_Gap.md](../reference/Top_Level_Implementation_Gap.md)：六域真实差距与 runtime 条目的当前状态。
- [reference/ACF_Top_Level_Design.md](../reference/ACF_Top_Level_Design.md)：模块边界与 CLI 分层上位约束。
- [reference/Architecture.md](../reference/Architecture.md)：当前模块依赖方向，重构后需同步。
- [reference/Product_Roadmap.md](../reference/Product_Roadmap.md)：阶段路线，确认本轮属内部重构而非新能力。
- [reference/System_Manual.md](../reference/System_Manual.md)：用户可见命令合同，重构不得改变。

---

## 输出要求

- WS016 详情、范围声明、Task_Plan 与 Current_Task

---

## 成功标准

1. 输出物已完成：WS016 详情、范围声明、Task_Plan 与 Current_Task
2. 子任务 T001 的完成证据已写回任务板。
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
