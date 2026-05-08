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

RC hardening verification

---

## 所属大任务

ACF RC hardening for feedback, archive, and human notes

---

## 子任务 ID

T004

---

## 当前执行线

无。

---

## 本次任务目标

1. 完成版本、文档和完整验证，形成可上线测试状态。

---

## 任务背景

该任务由当前维护流程创建，需要写入当前任务文件以便协作过程可追踪。

---

## 输入材料

当前任务应列出必要 active 文件和相关 reference 规划依据；不要只写 `active/Context.md`。

- acf.py
- tests/test_cli.py
- README.md
- template/reference/System_Manual.md
- docs/ai/reference/System_Manual.md

---

## 输出要求

- 通过验证的 RC 变更。

---

## 成功标准

1. unittest/check/smoke 全部通过。

---

## 失败信号

1. 目标无法验证。
2. 任务范围需要重新确认。

---

## 约束条件

1. 遵守当前项目规则。
2. 不引入无关依赖。

---

## 不允许做的事

- 无。

---

## 需要 AI 协助判断的问题

1. 无。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应写入 `reference/Knowledge_Index.md` 或 Knowledge 条目的可复用经验。
5. 应归档到 archive 的历史内容。

---

<!-- ACF:ARCHIVE:RECORD:START -->
- archived_at: 2026-05-08
- item_type: Task
- item_id: RC hardening verification
- source_path: active/Current_Task.md
- archive_path: `archive/tasks/2026-05-08-rc-hardening-verification.md`
- status: Archived
- archive_reason: ACF RC hardening v0.0.3.43 completed and verified.
<!-- ACF:ARCHIVE:RECORD:END -->
