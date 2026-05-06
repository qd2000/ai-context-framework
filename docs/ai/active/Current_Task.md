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

Merge resolution + active retention gate

---

## 所属大任务

P0 governance hardening: task-stage registry, workstream stage focus, authority write gate, merge resolution, active retention gate

---

## 子任务 ID

T004

---

## 当前执行线

无。

---

## 本次任务目标

1. 硬化 Done / Cancelled 状态门禁。
2. 产出并验证输出物：`merge_resolution`、`keep_active_reason`、`keep_active_until` 检查

---

## 任务背景

该任务来自 `active/Task_Plan.md` 中的子任务 T004，所属大任务为“P0 governance hardening: task-stage registry, workstream stage focus, authority write gate, merge resolution, active retention gate”。依赖记录：T003

---

## 输入材料

- `active/Task_Plan.md`。
- `active/Context.md`。
- 依赖 T003 证据：acf.py; tests/test_cli.py; README.md; template/reference/System_Manual.md; docs/ai/reference/Workstream_Design.md; docs/ai/reference/System_Manual.md; worklog/daily/2026-05-06.md; verification: unittest, check template, strict docs check, upgrade dry-run, minimal smoke, quick upgrade matrix, py_compile

---

## 输出要求

- `merge_resolution`、`keep_active_reason`、`keep_active_until` 检查

---

## 成功标准

1. 输出物已完成：`merge_resolution`、`keep_active_reason`、`keep_active_until` 检查
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
