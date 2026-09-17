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

执行完整兼容与 release 验证

---

## 所属大任务

WS013 Observer Retirement and v0.0.3.92

---

## 子任务 ID

T004

---

## 所属 Workstream

- `WS013`

---

## 当前执行线

无。

---

## 本次任务目标

1. 关闭所有回归和文档漂移后形成可发布候选。
2. 产出并验证输出物：strict/template、全量测试、smoke、upgrade matrix、release check、package evidence

---

## 任务背景

该任务来自 `active/Task_Plan.md` 中的子任务 T004，所属大任务为“WS013 Observer Retirement and v0.0.3.92”。依赖记录：T003

---

## 输入材料

当前任务应列出必要 active 文件和相关 reference 规划依据；不要只写 `active/Context.md`。

- `active/Task_Plan.md`。
- `active/Context.md`。
- [reference/ws013_observer_retirement_ws012_closeout/PLAN.md](../reference/ws013_observer_retirement_ws012_closeout/PLAN.md)：WS013 Observer 退役、WS012 收尾、验证矩阵与 v0.0.3.92 发布路线。
- 依赖 T003 证据：删除 4 个 Observer 专项测试套件与 output/observer 产物；minimal_smoke 改为 human report 场景；release_check 移除 Dashboard 前置；egg-info 重新生成仅保留 stub；新增 2 个墓碑无副作用回归；README/Automation/两份 System Manual/Context 同步退役说明；296+135 tests OK

---

## 输出要求

- strict/template、全量测试、smoke、upgrade matrix、release check、package evidence

---

## 成功标准

1. 输出物已完成：strict/template、全量测试、smoke、upgrade matrix、release check、package evidence
2. 子任务 T004 的完成证据已写回任务板。
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
